"""T1 — config loader: defaults, yaml override, input resolve, sheet passthrough."""
from __future__ import annotations

from pathlib import Path

import config


def test_defaults_when_file_missing(tmp_path):
    cfg = config.load_config(tmp_path / "no-existe.yaml")
    assert cfg["environment"] == "DEV"
    assert cfg["paths"]["input_dir"].endswith("workspace/input".replace("/", str(Path().anchor)[:0] or "/")) or "workspace" in cfg["paths"]["input_dir"]
    assert cfg["excel"]["pattern"] == "ControlPases*.xlsx"
    assert cfg["_source"] == "defaults"


def test_loads_custom_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "environment: PROD\n"
        "paths:\n"
        f"  input_dir: {tmp_path.as_posix()}/in\n"
        f"  output_dir: {tmp_path.as_posix()}/out\n"
        "excel:\n"
        '  pattern: "ControlPases*.xlsx"\n'
        "  sheet: Hoja1\n"
        "app:\n"
        '  name: "Demo"\n'
        '  timezone: "America/Lima"\n',
        encoding="utf-8",
    )
    cfg = config.load_config(p)
    assert cfg["environment"] == "PROD"
    assert cfg["excel"]["sheet"] == "Hoja1"
    assert cfg["app"]["name"] == "Demo"
    assert cfg["_source"] == "file"


def test_resolve_input_picks_newest_match(tmp_path):
    import os
    import time

    in_dir = tmp_path / "in"
    in_dir.mkdir()
    old = in_dir / "ControlPases_01.xlsx"
    new = in_dir / "ControlPases_02.xlsx"
    old.write_bytes(b"x")
    time.sleep(0.02)
    new.write_bytes(b"y")
    # Asegurar mtimes distintos aunque el FS sea grueso.
    os.utime(new, (old.stat().st_mtime + 5, old.stat().st_mtime + 5))
    cfg = {
        "paths": {"input_dir": str(in_dir), "output_dir": str(tmp_path / "out")},
        "excel": {"pattern": "ControlPases*.xlsx", "sheet": 0},
    }
    assert config.resolve_input_file(cfg) == new


def test_explicit_path_wins_over_pattern(tmp_path):
    direct = tmp_path / "otro.xlsx"
    direct.write_bytes(b"z")
    cfg = {
        "paths": {"input_dir": str(tmp_path), "output_dir": str(tmp_path)},
        "excel": {"pattern": "ControlPases*.xlsx", "sheet": 0},
    }
    assert config.resolve_input_file(cfg, explicit=str(direct)) == direct
