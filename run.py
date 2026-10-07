"""Ejecutor raiz para la PC corporativa (Task Scheduler apunta aca).

Uso:
    .\\.venv-win\\Scripts\\python.exe run.py
    .\\.venv-win\\Scripts\\python.exe run.py --now "2026-10-06 09:55"
    .\\.venv-win\\Scripts\\python.exe run.py --config "D:\\corp\\config.yaml"
    .\\.venv-win\\Scripts\\python.exe run.py "D:\\corp\\ControlPases.xlsx"

Lee config.yaml junto a este archivo por defecto (paths/sheettimezone).
Sin .bat: en la corporativa estan bloqueados.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from main import cli  # noqa: E402 — python/ agregado arriba a propósito


if __name__ == "__main__":
    sys.exit(cli())
