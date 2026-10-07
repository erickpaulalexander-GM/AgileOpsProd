"""Ejecutor raiz para la PC corporativa (Task Scheduler apunta aca).

Si el interprete actual no tiene las dependencias, se re-ejecuta solo con
el venv que vive junto a este archivo — `py run.py` funciona aunque `py`
sea el Python del sistema. Sin .bat (bloqueados en la corporativa),
sin shell, sin descargas.

Uso:
    py run.py                  # bootstrap al venv si hace falta
    py run.py --now "2026-10-06 09:55"
    py run.py --config "D:\\corp\\config.yaml"
    py run.py "D:\\corp\\ControlPases.xlsx"

Lee config.yaml junto a este archivo por defecto (paths/sheet/timezone).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv-win" / "Scripts" / "python.exe"


def _ensure_venv() -> None:
    """Re-ejecuta con el venv si al interprete actual le faltan las deps."""
    try:
        import pandas  # noqa: F401
    except ImportError:
        pass
    else:
        return
    try:
        already = Path(sys.executable).resolve() == VENV_PYTHON.resolve()
    except OSError:
        already = False
    if already or not VENV_PYTHON.is_file():
        print(
            "[ERROR] Faltan dependencias (pandas) y no hay venv en "
            f"{VENV_PYTHON}.\n"
            "        Instala con: .\\.venv-win\\Scripts\\python.exe "
            "-m pip install -r requirements.txt"
        )
        raise SystemExit(1)
    # subprocess (no os.execv): en Windows execv no cita args con espacios
    # y partiría --now "2026-10-06 09:55" en dos. Se propaga el exit code.
    raise SystemExit(subprocess.call([str(VENV_PYTHON), *sys.argv]))


_ensure_venv()
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from main import cli  # noqa: E402 — python/ agregado arriba a propósito


if __name__ == "__main__":
    sys.exit(cli())
