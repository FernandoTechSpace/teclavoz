"""Listas de palavras por idioma e categoria."""

from __future__ import annotations

import random
import unicodedata
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / "data"

LANGS = {"pt": "PT-BR", "en": "EN"}
CATEGORIES = {"comum": "dia a dia", "ti": "TI", "misto": "misto"}

FILES = {
    ("pt", "comum"): ["pt_comum.txt"],
    ("pt", "ti"): ["pt_ti.txt"],
    ("en", "comum"): ["en_common.txt"],
    ("en", "ti"): ["en_it.txt"],
}


@cache
def vocabulary(lang: str, category: str) -> tuple[str, ...]:
    cats = ["comum", "ti"] if category == "misto" else [category]
    words: dict[str, None] = {}
    for cat in cats:
        for name in FILES[(lang, cat)]:
            for line in (DATA / name).read_text(encoding="utf-8").splitlines():
                if (w := line.strip()) and not w.startswith("#"):
                    words[w] = None
    return tuple(words)


def sample(lang: str, category: str, n: int = 400) -> list[str]:
    """Sorteia n palavras sem repetir a mesma em sequência."""
    vocab = vocabulary(lang, category)
    out: list[str] = []
    while len(out) < n:
        w = random.choice(vocab)
        if not out or w != out[-1]:
            out.append(w)
    return out


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
