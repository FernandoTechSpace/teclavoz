"""Lê o tema atual do Omarchy e converte para um tema do Textual."""

from __future__ import annotations

import tomllib
from pathlib import Path

from textual.theme import Theme

THEME_DIR = Path.home() / ".local/state/omarchy/current/theme"
COLORS_FILE = THEME_DIR / "colors.toml"
NAME_FILE = THEME_DIR.parent / "theme.name"

# Temas antigos usam color0..color15 em vez de nomes.
ANSI_NAMES = {
    "color0": "background",
    "color1": "red",
    "color2": "green",
    "color3": "yellow",
    "color4": "blue",
    "color5": "magenta",
    "color6": "cyan",
    "color7": "foreground",
    "color8": "muted",
}


def signature() -> tuple:
    """Identifica a versão do tema em disco; muda quando o usuário troca de tema."""
    try:
        st = COLORS_FILE.stat()
        name = NAME_FILE.read_text().strip() if NAME_FILE.exists() else ""
        return (name, st.st_ino, st.st_mtime_ns)
    except OSError:
        return ()


def theme_name() -> str:
    try:
        return NAME_FILE.read_text().strip()
    except OSError:
        return ""


def load(counter: int) -> Theme | None:
    """Monta um Theme do Textual a partir do colors.toml (None se não houver)."""
    try:
        raw = tomllib.loads(COLORS_FILE.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None

    c: dict[str, str] = {k: v for k, v in raw.items() if isinstance(v, str)}
    for ansi, name in ANSI_NAMES.items():
        if ansi in c:
            c.setdefault(name, c[ansi])
    if "background" not in c or "foreground" not in c:
        return None

    accent = c.get("accent", c.get("blue", c["foreground"]))
    return Theme(
        # Nome único a cada recarga para o Textual reaplicar o CSS.
        name=f"omarchy-{counter}",
        primary=accent,
        secondary=c.get("blue", accent),
        accent=c.get("cyan", accent),
        warning=c.get("yellow"),
        error=c.get("red"),
        success=c.get("green"),
        foreground=c["foreground"],
        background=c["background"],
        surface=c.get("lighter_background", c["background"]),
        panel=c.get("dark_background", c["background"]),
        dark=raw.get("mode", "dark") != "light",
        variables={
            "muted": c.get("muted", c.get("dark_foreground", c["foreground"])),
            "selection": c.get("selection", accent),
        },
    )
