"""T8 — el header evidencia el archivo fuente (nombre + mtime).

El dash mostraba solo el reloj de corrida: imposible saber si el Excel
esta fresco. El renderer incrusta `window.AgileOpsSource` (payload
separado, NO contrato — el contrato sigue sin campo mtime) y el header
lo muestra junto a Actualización.
"""
from __future__ import annotations

import json

from renderer import render_dashboard


def _contract():
    return {"meta": {"updatedAt": "2026-10-07T17:51:32"}}


def test_html_embeds_source_stamp(tmp_path):
    diag = {
        "excelFileName": "ControlPases.xlsx",
        "excelFileMtime": "2026-10-07T17:11:04",
    }
    out = render_dashboard(_contract(), diag, None, output_dir=tmp_path)
    html = out["dashboard_html"].read_text(encoding="utf-8")
    assert "window.AgileOpsSource" in html
    assert "ControlPases.xlsx" in html
    assert "2026-10-07T17:11:04" in html


def test_contract_has_no_source_fields(tmp_path):
    diag = {
        "excelFileName": "ControlPases.xlsx",
        "excelFileMtime": "2026-10-07T17:11:04",
    }
    out = render_dashboard(_contract(), diag, None, output_dir=tmp_path)
    data = json.loads(out["dashboard_data"].read_text(encoding="utf-8"))
    assert "excelFileMtime" not in data
    assert "AgileOpsSource" not in json.dumps(data)


def test_missing_source_keys_do_not_crash(tmp_path):
    out = render_dashboard(_contract(), {}, None, output_dir=tmp_path)
    html = out["dashboard_html"].read_text(encoding="utf-8")
    assert "window.AgileOpsSource" in html
