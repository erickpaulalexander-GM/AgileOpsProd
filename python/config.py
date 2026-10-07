"""Config loader: config.yaml en raiz con fallback a defaults.

La PC corporativa cambia input/output; este modulo es la unica pieza que
conoce el archivo. Sin config.yaml el pipeline corre con los defaults
actuales (backward compatible, ADR-010).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"

DEFAULTS: dict[str, Any] = {
    "environment": "DEV",
    "paths": {
        "input_dir": str(REPO_ROOT / "workspace" / "input"),
        "output_dir": str(REPO_ROOT / "workspace" / "output"),
    },
    "excel": {
        "pattern": "ControlPases*.xlsx",
        "sheet": 0,
    },
    "app": {
        "name": "AgileOps Prod Console",
        "timezone": "America/Lima",
    },
}


def _resolve_dir(value: str) -> str:
    """Las rutas relativas se resuelven contra el repo root (ADR-010)."""
    p = Path(str(value))
    if p.is_absolute():
        return str(p)
    return str(REPO_ROOT / p)


def _with_defaults(data: dict[str, Any]) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "environment": data.get("environment", DEFAULTS["environment"]),
        "paths": {
            **DEFAULTS["paths"],
            **(data.get("paths") or {}),
        },
        "excel": {
            **DEFAULTS["excel"],
            **(data.get("excel") or {}),
        },
        "app": {
            **DEFAULTS["app"],
            **(data.get("app") or {}),
        },
    }
    cfg["paths"]["input_dir"] = _resolve_dir(cfg["paths"]["input_dir"])
    cfg["paths"]["output_dir"] = _resolve_dir(cfg["paths"]["output_dir"])
    return cfg


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Carga el yaml o devuelve defaults si no existe (warning, no crash)."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        logger.warning("config.yaml no encontrado en %s; uso defaults", target)
        cfg = _with_defaults({})
        cfg["_source"] = "defaults"
        cfg["_config_path"] = str(target)
        return cfg
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML no instalado; instalá requirements.txt (pyyaml)"
        ) from exc
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    cfg = _with_defaults(data)
    cfg["_source"] = "file"
    cfg["_config_path"] = str(target)
    return cfg


def resolve_input_file(
    cfg: dict[str, Any], explicit: str | Path | None = None
) -> Path:
    """CLI explicit > input_dir + pattern (match mas nuevo por mtime)."""
    if explicit is not None:
        return Path(explicit)
    paths = cfg.get("paths", {})
    excel = cfg.get("excel", {})
    input_dir = Path(str(paths.get("input_dir", DEFAULTS["paths"]["input_dir"])))
    if input_dir.is_file():
        return input_dir
    pattern = str(excel.get("pattern", DEFAULTS["excel"]["pattern"]))
    matches = [p for p in input_dir.glob(pattern) if p.is_file()]
    if not matches:
        raise FileNotFoundError(
            f"Sin matches para {pattern!r} en {input_dir} "
            f"(config: {cfg.get('_config_path', 'defaults')})"
        )
    return max(matches, key=lambda p: p.stat().st_mtime)


def resolve_output_dir(cfg: dict[str, Any]) -> Path:
    """Output dir ya normalizado contra repo root en load_config."""
    return Path(str(cfg.get("paths", {}).get("output_dir")))


def get_sheet(cfg: dict[str, Any]) -> int | str:
    """Sheet name o indice; default primera hoja (0)."""
    return cfg.get("excel", {}).get("sheet", 0)


def wall_now(timezone: str | None = None) -> datetime:
    """Wall-clock naive en la tz configurada (no rompe la matematica actual)."""
    tz_name = timezone or str(DEFAULTS["app"]["timezone"])
    try:
        from zoneinfo import ZoneInfo

        aware = datetime.now(tz=ZoneInfo(tz_name))
        return aware.replace(tzinfo=None)
    except (ValueError, KeyError, ImportError, OSError):
        logger.warning("Timezone %r invalida; uso reloj local", tz_name)
        return datetime.now()
