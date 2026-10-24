#!/bin/bash
# Instala o comando `teclavoz` e o atalho no launcher.
set -euo pipefail
cd "$(dirname "$0")"
uv tool install --force --python 3.13 -e .
install -Dm644 packaging/teclavoz.desktop ~/.local/share/applications/teclavoz.desktop
echo "Pronto: rode 'teclavoz' (as vozes são baixadas no primeiro uso, ~60 MB cada)."
