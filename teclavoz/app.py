"""teclavoz — teste de digitação estilo 10fastfingers que fala cada palavra digitada."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from . import theme as omarchy_theme
from .speech import DATA_DIR, DEFAULT_VOICES, VOICE_CHOICES, VOICE_PREFIX, Speaker, short_name
from .words import CATEGORIES, LANGS, sample, strip_accents

DURATIONS = [15, 30, 60, 120]
SETTINGS_FILE = DATA_DIR / "settings.json"
RECORDS_FILE = DATA_DIR / "records.json"
PREFETCH = 12
# Passos da F10 (1.0 = ritmo natural do Piper, maior = mais lento).
VOICE_SPEEDS = [1.0, 1.2, 1.35, 1.5, 1.7, 2.0]

# eco: fala a palavra quando você acerta · ditado: fala antes e você digita de ouvido
MODES = {"eco": "eco", "ditado": "ditado"}
MODE_ICONS = {"eco": "󰗋", "ditado": "󰋋"}


@dataclass
class Settings:
    lang: str = "pt"
    category: str = "comum"
    duration: int = 60
    voice: bool = True
    strict_accents: bool = True
    mode: str = "eco"
    # Duração das falas no Piper: 1.0 é o ritmo natural, maior é mais lento.
    voice_speed: float = 1.35
    voices: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VOICES))

    @classmethod
    def load(cls) -> Settings:
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2))

    @property
    def record_key(self) -> str:
        key = f"{self.lang}-{self.category}-{self.duration}"
        return key if self.mode == "eco" else f"{key}-{self.mode}"


def load_records() -> dict[str, float]:
    try:
        return json.loads(RECORDS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_record(key: str, wpm: float) -> bool:
    """Grava o recorde se for o melhor; devolve True quando é recorde novo."""
    records = load_records()
    if wpm <= records.get(key, 0):
        return False
    records[key] = round(wpm, 1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_FILE.write_text(json.dumps(records, indent=2))
    return True


class WordBoard(Widget):
    """Mostra duas linhas de palavras, como no 10fastfingers."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.words: list[str] = []
        self.results: list[bool | None] = []
        self.index = 0
        self.typed = ""
        self.strict = True
        # Modo ditado: as palavras só aparecem depois de digitadas.
        self.hidden = False

    def _lines(self, width: int) -> list[list[int]]:
        lines: list[list[int]] = [[]]
        used = 0
        for i, w in enumerate(self.words):
            need = len(w) + (1 if lines[-1] else 0)
            if lines[-1] and used + need > width:
                lines.append([])
                used, need = 0, len(w)
            lines[-1].append(i)
            used += need
        return lines

    def render(self) -> Text:
        t = self.app.current_theme
        muted = t.variables.get("muted", t.foreground)
        width = max(self.content_size.width, 10)
        lines = self._lines(width)
        row = next((n for n, line in enumerate(lines) if self.index in line), 0)

        out = Text()
        for n, line in enumerate(lines[row : row + 2]):
            if n:
                out.append("\n\n")
            for k, i in enumerate(line):
                if k:
                    out.append(" ")
                word = self.words[i]
                if i >= self.index and self.hidden:
                    word = "·" * len(word)
                if i < self.index:
                    # No ditado a palavra errada aparece legível, para você ver o que era.
                    wrong = f"{t.error} underline" if self.hidden else f"{t.error} strike"
                    style = t.success if self.results[i] else wrong
                elif i == self.index:
                    target = self.words[i] if self.strict else strip_accents(self.words[i])
                    typed = self.typed if self.strict else strip_accents(self.typed)
                    bg = t.error if not target.startswith(typed) else t.primary
                    style = f"bold {t.background} on {bg}"
                elif n == 0:
                    style = t.foreground
                else:
                    style = muted
                out.append(word, style=style)
        return out


class CommandInput(Input):
    """Campo de digitação; com o menu de comandos aberto, setas/Tab navegam nele."""

    BINDINGS = [
        Binding("up", "menu(-1)", show=False),
        Binding("down", "menu(1)", show=False),
        Binding("tab", "complete", show=False),
    ]

    def action_menu(self, step: int) -> None:
        self.app.move_menu(step)

    def action_complete(self) -> None:
        self.app.complete_menu()


class ResultsScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("enter,escape,space", "dismiss", "Novo teste"),
        Binding("ctrl+q", "app.quit", "Sair"),
    ]

    def __init__(self, summary: Text) -> None:
        super().__init__()
        self.summary = summary

    def compose(self) -> ComposeResult:
        with Vertical(id="results"):
            yield Static(self.summary)
            yield Static("enter · nova rodada", id="results-hint")


class TeclaVoz(App):
    TITLE = "teclavoz"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen {
        background: ansi_default;
    }
    #center {
        width: 100%;
        height: 1fr;
        align: center middle;
    }
    #main {
        width: 100%;
        max-width: 96;
        height: auto;
        padding: 0 2;
    }
    #topbar {
        height: 1;
        margin-bottom: 1;
    }
    #brand {
        width: 1fr;
        color: $primary;
        text-style: bold;
    }
    #settings {
        width: auto;
        color: $muted;
    }
    WordBoard {
        height: 3;
        border: round $primary;
        padding: 1 2;
        box-sizing: content-box;
    }
    #typing {
        height: 3;
        margin-top: 1;
    }
    Input {
        width: 1fr;
        background: ansi_default;
        border: tall $primary 40%;
    }
    Input:focus {
        border: tall $primary;
    }
    Input:disabled {
        opacity: 60%;
    }
    #clock {
        width: 9;
        content-align: center middle;
        height: 3;
        color: $primary;
        text-style: bold;
    }
    #live {
        width: 12;
        content-align: center middle;
        height: 3;
        color: $foreground;
    }
    #status {
        height: 1;
        margin-top: 1;
        color: $muted;
    }
    #cmdmenu {
        overlay: screen;
        position: absolute;
        display: none;
        height: auto;
        max-height: 12;
        border: round $primary;
        background: $panel;
        padding: 0 1;
    }
    #cmdmenu > .option-list--option-highlighted {
        background: $primary 30%;
        text-style: bold;
    }
    Footer {
        background: ansi_default;
    }
    ResultsScreen {
        align: center middle;
        background: $background 60%;
    }
    #results {
        width: 46;
        height: auto;
        border: round $primary;
        background: $panel;
        padding: 1 3;
    }
    #results-hint {
        margin-top: 1;
        color: $muted;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("f2", "cycle_lang", "Idioma", priority=True),
        Binding("f3", "cycle_category", "Categoria", priority=True),
        Binding("f4", "cycle_duration", "Tempo", priority=True),
        Binding("f5", "toggle_voice", "Voz", priority=True),
        Binding("f6", "toggle_accents", "Acentos", priority=True),
        Binding("f7", "cycle_mode", "Modo", priority=True),
        Binding("f8", "repeat", "Repetir", priority=True),
        Binding("f9", "next_voice", "Trocar voz", priority=True),
        Binding("f10", "cycle_speed", "Velocidade", priority=True),
        Binding("escape", "restart", "Reiniciar", priority=True),
        Binding("ctrl+q", "quit", "Sair", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.speaker = Speaker(
            on_status=lambda s: self.call_from_thread(self._update_status),
            speed=self.settings.voice_speed,
            voices=self.settings.voices,
        )
        self.speaker.enabled = self.settings.voice
        self._menu_items: list[tuple[str, str]] = []
        self._theme_sig: tuple = ()
        self._theme_counter = 0
        self.started_at: float | None = None
        self.finished = False
        self.good_keys = 0
        self.bad_keys = 0

    # Montagem -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="center"), Vertical(id="main"):
            with Horizontal(id="topbar"):
                yield Static("󰌌 teclavoz", id="brand")
                yield Static(id="settings")
            yield WordBoard(id="board")
            with Horizontal(id="typing"):
                yield CommandInput(id="input")
                yield Static(id="clock")
                yield Static(id="live")
            yield Static(id="status")
        menu = OptionList(id="cmdmenu")
        menu.can_focus = False  # o foco fica no campo; as setas chegam via CommandInput
        yield menu
        yield Footer()

    def on_mount(self) -> None:
        self._sync_theme()
        self.set_interval(1.0, self._sync_theme)
        self.set_interval(0.2, self._tick)
        self.speaker.preload(self.settings.lang)
        self.new_test()

    # Tema do Omarchy ----------------------------------------------------

    def get_theme_variable_defaults(self) -> dict[str, str]:
        # Valores usados até o tema do Omarchy carregar (ou fora do Omarchy).
        return {"muted": "#808080", "selection": "#404040"}

    def _sync_theme(self) -> None:
        sig = omarchy_theme.signature()
        if sig == self._theme_sig:
            return
        self._theme_sig = sig
        self._theme_counter += 1
        new = omarchy_theme.load(self._theme_counter)
        if new is None:
            return
        old = self.theme
        self.register_theme(new)
        self.theme = new.name
        if old.startswith("omarchy-"):
            self.unregister_theme(old)
        self.query_one(WordBoard).refresh()
        self._update_status()

    # Teste --------------------------------------------------------------

    def new_test(self) -> None:
        s = self.settings
        board = self.query_one(WordBoard)
        board.words = sample(s.lang, s.category)
        board.results = [None] * len(board.words)
        board.index = 0
        board.typed = ""
        board.strict = s.strict_accents
        board.hidden = self._dictating
        board.refresh()
        self.started_at = None
        self.finished = False
        self.good_keys = self.bad_keys = 0
        inp = self.query_one(Input)
        inp.disabled = False
        inp.value = ""
        inp.placeholder = (
            "ouça e digite…  (F8 repete · /mode troca o modo)"
            if s.mode == "ditado"
            else "comece a digitar…  (/mode troca o modo)"
        )
        inp.focus()
        self.speaker.prefetch(s.lang, board.words[:PREFETCH])
        if self._dictating:
            self.speaker.say(s.lang, board.words[0])
        self._update_settings()
        self._update_status()
        self.refresh_bindings()
        self._tick()

    @property
    def _dictating(self) -> bool:
        """Ditado só faz sentido com a voz ligada; sem voz, as palavras ficam visíveis."""
        return self.settings.mode == "ditado" and self.settings.voice

    def _matches(self, typed: str, target: str) -> bool:
        if self.settings.strict_accents:
            return typed == target
        return strip_accents(typed).lower() == strip_accents(target).lower()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self.finished:
            return
        board = self.query_one(WordBoard)
        value = event.value
        if value.startswith("/"):
            # Comando (ex.: /mode): não conta como digitação nem inicia o relógio.
            board.typed = ""
            board.refresh()
            self._show_menu(value)
            return
        self._hide_menu()
        if value and self.started_at is None:
            self.started_at = time.monotonic()

        if " " in value:
            typed, _, rest = value.partition(" ")
            if typed:
                self._submit(typed)
            # Mantém o que veio depois do espaço (digitação muito rápida).
            event.input.value = rest.lstrip()
            return
        board.typed = value
        board.refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.startswith("/"):
            command = self._menu_choice() or event.value
            self._hide_menu()
            event.input.value = ""
            self._run_command(command[1:].split())
        elif event.value.strip() and not self.finished:
            self._submit(event.value.strip())
            event.input.value = ""

    def _submit(self, typed: str) -> None:
        board = self.query_one(WordBoard)
        target = board.words[board.index]
        ok = self._matches(typed, target)
        board.results[board.index] = ok
        if ok:
            self.good_keys += len(target) + 1
            if self.settings.mode == "eco":
                self.speaker.say(self.settings.lang, target)
        else:
            self.bad_keys += len(target) + 1
        board.index += 1
        board.typed = ""
        if board.index + PREFETCH < len(board.words):
            self.speaker.prefetch(self.settings.lang, [board.words[board.index + PREFETCH]])
        if board.index >= len(board.words):
            self._finish()
        elif self._dictating:
            self.speaker.say(self.settings.lang, board.words[board.index])
        board.refresh()

    def _elapsed(self) -> float:
        return 0.0 if self.started_at is None else time.monotonic() - self.started_at

    def _wpm(self, seconds: float) -> float:
        return (self.good_keys / 5) / (seconds / 60) if seconds > 0 else 0.0

    def _tick(self) -> None:
        if self.finished:
            return
        total = self.settings.duration
        elapsed = self._elapsed()
        left = max(0.0, total - elapsed)
        self.query_one("#clock", Static).update(f"{int(left) // 60}:{int(left) % 60:02d}")
        wpm = self._wpm(elapsed) if elapsed > 2 else 0
        self.query_one("#live", Static).update(f"{wpm:3.0f} WPM")
        if self.started_at is not None and left <= 0:
            self._finish()

    def _finish(self) -> None:
        self.finished = True
        inp = self.query_one(Input)
        inp.disabled = True
        board = self.query_one(WordBoard)
        s = self.settings

        seconds = min(self._elapsed(), s.duration) or s.duration
        wpm = self._wpm(seconds)
        done = [r for r in board.results if r is not None]
        right, wrong = done.count(True), done.count(False)
        keys = self.good_keys + self.bad_keys
        accuracy = 100 * self.good_keys / keys if keys else 0
        best_before = load_records().get(s.record_key, 0)
        is_record = save_record(s.record_key, wpm)

        t = self.current_theme
        muted = t.variables.get("muted", t.foreground)
        txt = Text()
        txt.append(f"{wpm:.0f}", style=f"bold {t.primary}")
        txt.append(" WPM", style=f"bold {t.foreground}")
        if is_record:
            txt.append("   novo recorde!", style=f"bold {t.warning}")
        txt.append("\n\n")
        rows = [
            ("Toques", f"({self.good_keys} | {self.bad_keys}) {keys}"),
            ("Precisão", f"{accuracy:.1f}%"),
            ("Palavras certas", str(right)),
            ("Palavras erradas", str(wrong)),
            ("Recorde anterior", f"{best_before:.0f} WPM" if best_before else "—"),
        ]
        for label, value in rows:
            color = t.success if label == "Palavras certas" else t.error if label == "Palavras erradas" else t.foreground
            txt.append(f"{label:<18}", style=muted)
            txt.append(f"{value}\n", style=color)
        txt.append(
            f"\n{MODES[s.mode]} · {LANGS[s.lang]} · {CATEGORIES[s.category]} · {s.duration}s",
            style=muted,
        )
        self.push_screen(ResultsScreen(txt), lambda _: self.new_test())

    # Status e configurações ---------------------------------------------

    def _update_settings(self) -> None:
        s = self.settings
        voice = "󰕾" if s.voice else "󰖁"
        accents = "acentos" if s.strict_accents else "sem acentos"
        self.query_one("#settings", Static).update(
            f"{MODE_ICONS[s.mode]} {MODES[s.mode]} · {LANGS[s.lang]} · {CATEGORIES[s.category]} · {s.duration}s · {accents} · {voice}"
        )

    def _update_status(self) -> None:
        name = omarchy_theme.theme_name() or "padrão"
        voice = short_name(self.speaker.voice_names[self.settings.lang])
        state = "" if self.speaker.status == "pronta" else f" ({self.speaker.status})"
        speed = self.settings.voice_speed
        self.query_one("#status", Static).update(
            f"tema: {name}  ·  voz: {voice}{state}  ·  velocidade: {speed:g}"
        )

    def _change(self, **changes) -> None:
        for k, v in changes.items():
            setattr(self.settings, k, v)
        self.settings.save()
        if isinstance(self.screen, ResultsScreen):
            self.screen.dismiss()  # o callback já chama new_test()
        else:
            self.new_test()

    @staticmethod
    def _next(options: list, current):
        return options[(options.index(current) + 1) % len(options)] if current in options else options[0]

    def action_cycle_lang(self) -> None:
        lang = self._next(list(LANGS), self.settings.lang)
        self.speaker.preload(lang)
        self._change(lang=lang)

    def action_cycle_category(self) -> None:
        self._change(category=self._next(list(CATEGORIES), self.settings.category))

    def action_cycle_duration(self) -> None:
        self._change(duration=self._next(DURATIONS, self.settings.duration))

    def action_toggle_voice(self) -> None:
        self.settings.voice = self.speaker.enabled = not self.settings.voice
        if not self.settings.voice:
            self.speaker.stop()
        self.settings.save()
        if self.settings.mode == "ditado":
            self.new_test()
        else:
            self._update_settings()

    def action_toggle_accents(self) -> None:
        self._change(strict_accents=not self.settings.strict_accents)

    def action_cycle_mode(self) -> None:
        self._set_mode(self._next(list(MODES), self.settings.mode))

    def _set_mode(self, mode: str) -> None:
        self._change(mode=mode)
        hint = "ouça a palavra e digite" if mode == "ditado" else "a palavra é falada quando você acerta"
        self.notify(hint, title=f"modo {MODES[mode]}", timeout=3)

    def action_repeat(self) -> None:
        board = self.query_one(WordBoard)
        if self.settings.mode == "ditado" and not self.finished and board.index < len(board.words):
            self.speaker.say(self.settings.lang, board.words[board.index])

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # "Repetir" só aparece no rodapé durante o ditado.
        if action == "repeat":
            return self._dictating
        return True

    def _run_command(self, args: list[str]) -> None:
        cmd, *rest = args or [""]
        if cmd in ("mode", "modo"):
            if not rest:
                self.action_cycle_mode()
            elif rest[0] in MODES:
                self._set_mode(rest[0])
            else:
                self.notify(f"modos: {', '.join(MODES)}", severity="error")
        elif cmd in ("repetir", "r"):
            self.action_repeat()
        elif cmd in ("voz", "voice"):
            self._voice_command(rest)
        elif cmd in ("velocidade", "vel"):
            self._set_voice_speed(rest)
        else:
            self.notify(
                "/mode [eco|ditado] · /repetir · /voz [nome|nº] · /velocidade [0.8–2.0]",
                title=f"comando desconhecido: /{cmd}",
                severity="warning",
            )

    def action_next_voice(self) -> None:
        lang = self.settings.lang
        self._choose_voice(self._next(VOICE_CHOICES[lang], self.speaker.voice_names[lang]))

    def _voice_command(self, args: list[str]) -> None:
        lang = self.settings.lang
        choices = VOICE_CHOICES[lang]
        current = self.speaker.voice_names[lang]
        if not args:
            listing = "\n".join(
                f"{'▸' if v == current else ' '} {n}. {short_name(v)}" for n, v in enumerate(choices, 1)
            )
            self.notify(f"{listing}\n\n/voz <nº ou nome> · F9 troca", title=f"vozes {LANGS[lang]}", timeout=8)
            return
        arg = args[0].lower()
        if arg.isdigit() and 1 <= int(arg) <= len(choices):
            name = choices[int(arg) - 1]
        else:
            # Aceita o apelido (cadu) ou o nome completo de qualquer voz do Piper (pt_BR-cadu-medium).
            name = next((v for v in choices if short_name(v) == arg), args[0])
            if not name.startswith(VOICE_PREFIX[lang]) or name.count("-") != 2:
                self.notify(f"voz não encontrada: {args[0]} (veja /voz)", severity="error")
                return
        self._choose_voice(name)

    def _choose_voice(self, name: str) -> None:
        lang = self.settings.lang
        self.notify(f"carregando {short_name(name)}…", title="voz", timeout=2)

        def done(ok: bool) -> None:
            def apply() -> None:
                if ok:
                    self.settings.voices[lang] = name
                    self.settings.save()
                    board = self.query_one(WordBoard)
                    self.speaker.prefetch(lang, board.words[board.index : board.index + PREFETCH])
                    self.notify(f"agora: {short_name(name)}", title="voz")
                    if board.index < len(board.words):
                        self.speaker.say(lang, board.words[board.index])
                else:
                    self.notify(f"não consegui baixar/carregar {name}", title="voz", severity="error")
                self._update_status()

            self.call_from_thread(apply)

        self.speaker.set_voice(lang, name, done)

    def action_cycle_speed(self) -> None:
        # Vai para o próximo passo acima do valor atual (que pode ter vindo do /velocidade).
        current = self.settings.voice_speed
        speed = next((v for v in VOICE_SPEEDS if v > current + 1e-9), VOICE_SPEEDS[0])
        self._set_voice_speed([str(speed)])

    def _set_voice_speed(self, args: list[str]) -> None:
        if not args:
            self.notify(f"atual: {self.settings.voice_speed} (1.0 = normal, maior = mais lenta)", title="velocidade da voz")
            return
        try:
            speed = round(float(args[0].replace(",", ".")), 2)
        except ValueError:
            speed = 0
        if not 0.8 <= speed <= 2.0:
            self.notify("use um valor entre 0.8 e 2.0, ex.: /velocidade 1.5", severity="error")
            return
        self.settings.voice_speed = self.speaker.speed = speed
        self.settings.save()
        board = self.query_one(WordBoard)
        # Regera o áudio das próximas palavras já na nova velocidade.
        self.speaker.prefetch(self.settings.lang, board.words[board.index : board.index + PREFETCH])
        self.clear_notifications()  # não empilhar avisos ao apertar F10 várias vezes
        self.notify(f"{speed:g} (1.0 = normal, maior = mais lenta)", title="velocidade da voz", timeout=2)
        self._update_status()
        board = self.query_one(WordBoard)
        if not self.finished and board.index < len(board.words):
            self.speaker.say(self.settings.lang, board.words[board.index])

    # Menu de comandos ---------------------------------------------------

    def _command_options(self) -> list[tuple[str, str]]:
        s = self.settings
        lang = s.lang
        current_voice = self.speaker.voice_names[lang]
        opts = [
            ("/mode", "alterna eco ↔ ditado"),
            ("/mode eco", "atual" if s.mode == "eco" else "fala a palavra quando você acerta"),
            ("/mode ditado", "atual" if s.mode == "ditado" else "ouça a palavra e digite"),
            ("/repetir", "repete a palavra (ditado)"),
            ("/voz", f"lista as vozes {LANGS[lang]}"),
        ]
        for v in VOICE_CHOICES[lang]:
            opts.append((f"/voz {short_name(v)}", "atual" if v == current_voice else f"voz {LANGS[lang]}"))
        opts.append(("/velocidade", f"atual: {s.voice_speed:g}"))
        for v in VOICE_SPEEDS:
            hint = "atual" if abs(v - s.voice_speed) < 1e-9 else "normal" if v == 1.0 else "mais lenta"
            opts.append((f"/velocidade {v:g}", hint))
        return opts

    def _show_menu(self, value: str) -> None:
        query = value.lower()
        self._menu_items = [(c, d) for c, d in self._command_options() if c.startswith(query)]
        menu = self.query_one("#cmdmenu", OptionList)
        if not self._menu_items:
            self._hide_menu()
            return
        muted = self.current_theme.variables.get("muted", self.current_theme.foreground)
        menu.clear_options()
        menu.add_options(
            Option(Text.assemble((f"{c:<18}", "bold"), (d, muted)), id=c) for c, d in self._menu_items
        )
        menu.highlighted = 0
        menu.display = True
        self.call_after_refresh(self._place_menu)

    def _place_menu(self) -> None:
        menu = self.query_one("#cmdmenu", OptionList)
        if not menu.display:
            return
        inp = self.query_one(CommandInput).region
        need = min(len(self._menu_items), 10) + 2
        below = self.screen.size.height - 1 - inp.bottom  # 1 linha do rodapé
        above = inp.y
        # Abaixo do campo; se não couber, do lado com mais espaço.
        if need <= below or below >= above:
            height, y = min(need, below), inp.bottom
        else:
            height = min(need, above)
            y = inp.y - height
        menu.styles.max_height = max(height, 3)
        menu.styles.width = inp.width
        menu.styles.offset = (inp.x, y)

    def _hide_menu(self) -> None:
        self._menu_items = []
        self.query_one("#cmdmenu", OptionList).display = False

    def _menu_choice(self) -> str | None:
        menu = self.query_one("#cmdmenu", OptionList)
        if menu.display and menu.highlighted is not None and self._menu_items:
            return self._menu_items[menu.highlighted][0]
        return None

    def move_menu(self, step: int) -> None:
        menu = self.query_one("#cmdmenu", OptionList)
        if menu.display and self._menu_items:
            menu.highlighted = ((menu.highlighted or 0) + step) % len(self._menu_items)

    def complete_menu(self) -> None:
        if choice := self._menu_choice():
            inp = self.query_one(CommandInput)
            inp.value = choice
            inp.cursor_position = len(choice)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # Clique com o mouse numa opção.
        command = event.option.id or ""
        self._hide_menu()
        self.query_one(CommandInput).value = ""
        self._run_command(command[1:].split())

    def action_restart(self) -> None:
        if self.query_one("#cmdmenu", OptionList).display:
            # Esc com o menu aberto só fecha o menu.
            self._hide_menu()
            self.query_one(CommandInput).value = ""
            return
        if isinstance(self.screen, ResultsScreen):
            self.screen.dismiss()
        else:
            self.new_test()


def main() -> None:
    TeclaVoz().run()


if __name__ == "__main__":
    main()
