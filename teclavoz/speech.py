"""Fala as palavras usando Piper (voz neural offline), com fallback para espeak-ng."""

from __future__ import annotations

import hashlib
import itertools
import queue
import shutil
import subprocess
import threading
import wave
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path.home() / ".local/share/teclavoz"
VOICES_DIR = DATA_DIR / "voices"
CACHE_DIR = Path.home() / ".cache/teclavoz"

# Vozes oferecidas na troca (F9 / /voz). A primeira de cada idioma é a padrão.
# Qualquer outra voz do Piper do mesmo idioma também funciona pelo nome completo.
VOICE_CHOICES = {
    "pt": [
        "pt_BR-faber-medium",
        "pt_BR-cadu-medium",
        "pt_BR-jeff-medium",
        "pt_BR-edresson-low",
    ],
    "en": [
        "en_US-lessac-medium",
        "en_US-amy-medium",
        "en_US-ryan-medium",
        "en_US-kristin-medium",
        "en_US-joe-medium",
        "en_US-john-medium",
        "en_US-hfc_female-medium",
        "en_US-hfc_male-medium",
        "en_GB-alba-medium",
        "en_GB-alan-medium",
    ],
}
DEFAULT_VOICES = {lang: names[0] for lang, names in VOICE_CHOICES.items()}
VOICE_PREFIX = {"pt": "pt_BR-", "en": "en_"}
ESPEAK_LANG = {"pt": "pt-br", "en": "en-us"}
PLAYERS = (["pw-play"], ["paplay"], ["aplay", "-q"])


def short_name(voice: str) -> str:
    """pt_BR-faber-medium -> faber"""
    parts = voice.split("-")
    return parts[1] if len(parts) == 3 else voice


class Speaker:
    """Sintetiza em background, guarda os .wav em cache e toca sem bloquear a TUI."""

    def __init__(self, on_status=None, speed: float = 1.35, voices: dict[str, str] | None = None) -> None:
        self.enabled = True
        self.speed = speed
        self.voice_names = {**DEFAULT_VOICES, **(voices or {})}
        self.status = "carregando…"
        self._on_status = on_status or (lambda s: None)
        self._voices: dict[str, object] = {}
        self._failed: set[str] = set()
        # Um lock por voz: baixar uma voz nova não trava a fala da atual.
        self._guard = threading.Lock()
        self._locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        # Falar tem prioridade sobre pré-sintetizar as próximas palavras.
        self._jobs: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._playing: subprocess.Popen | None = None
        self._player = next((p for p in PLAYERS if shutil.which(p[0])), None)
        self._espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        threading.Thread(target=self._worker, daemon=True).start()

    # API pública -------------------------------------------------------

    def preload(self, lang: str) -> None:
        threading.Thread(target=self._voice, args=(lang,), daemon=True).start()

    def set_voice(self, lang: str, name: str, on_done=None) -> None:
        """Baixa/carrega a voz em background e só troca quando ela estiver pronta."""

        def run() -> None:
            self._failed.discard(name)  # permite tentar de novo após falha de rede
            ok = self._load(name) is not None
            if ok:
                self.voice_names[lang] = name
            if on_done:
                on_done(ok)

        threading.Thread(target=run, daemon=True).start()

    def prefetch(self, lang: str, words: list[str]) -> None:
        for w in words:
            self._jobs.put((1, next(self._seq), lang, w, False))

    def say(self, lang: str, word: str) -> None:
        if self.enabled and self._player:
            self._jobs.put((0, next(self._seq), lang, word, True))

    def stop(self) -> None:
        if self._playing and self._playing.poll() is None:
            self._playing.terminate()

    # Internos ----------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status = text
        self._on_status(text)

    def _voice(self, lang: str):
        return self._load(self.voice_names[lang])

    def _load(self, name: str):
        with self._guard:
            lock = self._locks[name]
        with lock:
            if name in self._voices or name in self._failed:
                return self._voices.get(name)
            model = VOICES_DIR / f"{name}.onnx"
            try:
                from piper import PiperVoice

                if not model.exists():
                    self._set_status(f"baixando {short_name(name)}…")
                    from piper.download_voices import download_voice

                    VOICES_DIR.mkdir(parents=True, exist_ok=True)
                    download_voice(name, VOICES_DIR)
                self._voices[name] = PiperVoice.load(str(model))
                self._set_status("pronta")
            except Exception as exc:  # sem piper, sem rede, nome inválido, modelo corrompido…
                self._failed.add(name)
                model.unlink(missing_ok=True)
                self._set_status("espeak-ng" if self._espeak else f"indisponível ({exc.__class__.__name__})")
            return self._voices.get(name)

    def _synth(self, lang: str, word: str) -> Path | None:
        voice = self._voice(lang)
        folder = self.voice_names[lang] if voice is not None else f"espeak-{lang}"
        digest = hashlib.sha1(f"{self.speed}:{word}".encode()).hexdigest()[:16]
        path = CACHE_DIR / folder / f"{digest}.wav"
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            if voice is not None:
                from piper import SynthesisConfig

                with wave.open(str(tmp), "wb") as wav:
                    voice.synthesize_wav(word, wav, SynthesisConfig(length_scale=self.speed))
            elif self._espeak:
                subprocess.run(
                    [self._espeak, "-v", ESPEAK_LANG[lang], "-w", str(tmp), word],
                    check=True,
                    capture_output=True,
                )
            else:
                return None
            tmp.replace(path)
            return path
        except Exception:
            tmp.unlink(missing_ok=True)
            return None

    def _worker(self) -> None:
        while True:
            _, _, lang, word, play = self._jobs.get()
            path = self._synth(lang, word)
            if play and path and self.enabled:
                # Interrompe a palavra anterior para não embolar quando se digita rápido.
                self.stop()
                self._playing = subprocess.Popen(
                    [*self._player, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
