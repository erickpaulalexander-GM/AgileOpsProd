"""Bootstrap de run.py — el chequeo de deps debe cubrir requirements completo.

Regresión 2026-10-26: el check solo miraba `import pandas`; un intérprete
con pandas pero sin yaml (pyyaml) entraba al pipeline y revienta después en
config.load_config. La suite corre con .venv-win (README), donde
sys.executable == VENV_PYTHON — ese es el path que ejercita el error loud.
"""
from __future__ import annotations

import builtins

import pytest

import run


def _import_fallando_por(*ausentes):
    """__import__ de reemplazo que lanza ImportError solo para `ausentes`."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ausentes:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    return fake_import


def test_ensure_venv_no_pasa_en_silencio_si_falta_yaml(monkeypatch):
    """Regresión: pandas presente + yaml ausente debe disparar el fallback."""
    monkeypatch.setattr(builtins, "__import__", _import_fallando_por("yaml"))
    with pytest.raises(SystemExit):
        run._ensure_venv()


def test_missing_deps_vacio_con_deps_completas():
    assert run._missing_deps() == []


def test_missing_deps_reporta_solo_lo_ausente(monkeypatch):
    monkeypatch.setattr(builtins, "__import__", _import_fallando_por("yaml", "openpyxl"))
    # Orden = _REQUIRED_MODULES ("pandas", "openpyxl", "yaml").
    assert run._missing_deps() == ["openpyxl", "yaml"]


def test_ensure_venv_error_loud_nombra_modulos_faltantes(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(run, "_missing_deps", lambda: ["yaml", "openpyxl"])
    monkeypatch.setattr(run, "VENV_PYTHON", tmp_path / "no-existe" / "python.exe")
    with pytest.raises(SystemExit) as exc:
        run._ensure_venv()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "yaml" in out and "openpyxl" in out


def test_ensure_venv_reexecuta_con_venv(monkeypatch, tmp_path):
    fake_venv = tmp_path / "Scripts" / "python.exe"
    fake_venv.parent.mkdir(parents=True)
    fake_venv.touch()
    monkeypatch.setattr(run, "_missing_deps", lambda: ["yaml"])
    monkeypatch.setattr(run, "VENV_PYTHON", fake_venv)
    seen: list[list[str]] = []
    monkeypatch.setattr(run.subprocess, "call", lambda argv: seen.append(list(argv)) or 0)
    with pytest.raises(SystemExit) as exc:
        run._ensure_venv()
    assert exc.value.code == 0
    assert seen[0][0] == str(fake_venv)
