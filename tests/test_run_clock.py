"""
T8/ADR-012 — the window is anchored to the RUN CLOCK, not the Excel mtime.

The single temporal reference of a run is the system clock at run time (or an
explicit ``--now`` override). The Excel mtime survives ONLY as a separate
diagnostic field and must never drive the window.

These tests pin:

- the window starts at the floor of the supplied reference, so a 09:55
  reference yields a 09:00 window start;
- ``main(excel_path, reference_now=...)`` flows that reference through the SAME
  single-reference path to ``meta.updatedAt``, ``windowStart``, the rules
  reference and the table's live-work filter;
- the CLI ``--now`` override reaches the contract;
- an unparseable ``--now`` fails loudly instead of silently using the clock;
- with no override the reference is the real system clock;
- the Excel mtime is reported separately and never anchors the window.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import pytest
from openpyxl import Workbook

import main
import renderer
from adapter import compute_window

# 09:55 -> window start 09:00 (floor), window end 17:00.
REFERENCE = datetime(2026, 10, 6, 9, 55)

# An arbitrary mtime, deliberately a year away from the reference date, so a
# run proves the window cannot be derived from it.
MTIME_TS = 1_760_000_000


def _make_workbook(path, *, start="06/10/2026 09:30"):
    """Write a minimal workbook with one in-scope row and pin its mtime."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append([
        "TICKET",
        "NOMBRE APP",
        "RECURSO",
        "RECURSO ASIGNADO",
        "ESTADO ACTUAL",
        "FEC. HORA. INI. IMPL",
        "FEC .HORA. FIN. IMPL",
    ])
    ws.append([
        "T1",
        "APP1",
        "Pool AgileOps Prod",
        "Ana Perez",
        "Coordinado",
        start,
        "06/10/2026 10:30",
    ])
    wb.save(path)
    os.utime(path, (MTIME_TS, MTIME_TS))
    return path


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Redirect the real renderer output into the test tmp dir."""
    out = tmp_path / "output"
    monkeypatch.setattr(renderer, "OUTPUT_DIR", out)
    return out


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------
# Window floor
# ---------------------------------------------------------------
def test_window_starts_at_floor_of_supplied_reference():
    window = compute_window(REFERENCE)
    assert window["start_hhmm"] == "09:00"
    assert window["end_hhmm"] == "17:00"
    assert window["updated_at"] == REFERENCE


def test_window_floor_is_never_rounded_up():
    assert compute_window(datetime(2026, 10, 6, 9, 0))["start_hhmm"] == "09:00"
    assert compute_window(datetime(2026, 10, 6, 8, 59))["start_hhmm"] == "08:00"


# ---------------------------------------------------------------
# Single reference: main(reference_now=...) -> contract
# ---------------------------------------------------------------
def test_reference_now_reaches_contract_meta(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb, reference_now=REFERENCE)
    data = _read_json(output_dir / "dashboard_data.json")
    assert data["meta"]["updatedAt"] == "2026-10-06T09:55:00"
    assert data["meta"]["windowStart"] == "09:00"
    assert data["meta"]["windowEnd"] == "17:00"


def test_reference_now_drives_rules_and_table_filter(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb, reference_now=REFERENCE)
    diag = _read_json(output_dir / "diagnostic_report.json")
    assert diag["windowStart"] == "09:00"
    assert diag["kpiScope"]["referenceNow"] == "2026-10-06T09:55:00"
    assert diag["tableScope"]["temporalFilter"]["reference"] == "2026-10-06T09:55:00"


# ---------------------------------------------------------------
# CLI --now override
# ---------------------------------------------------------------
def test_cli_now_override_reaches_contract(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    exit_code = main.cli([str(wb), "--now", "2026-10-06 09:55"])
    assert exit_code == 0
    data = _read_json(output_dir / "dashboard_data.json")
    assert data["meta"]["updatedAt"] == "2026-10-06T09:55:00"
    assert data["meta"]["windowStart"] == "09:00"


def test_cli_positional_path_still_works_without_flag(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    exit_code = main.cli([str(wb)])
    assert exit_code == 0
    assert (output_dir / "dashboard_data.json").exists()


def test_parse_now_accepts_forgiving_formats():
    assert main._parse_now("2026-10-06 09:55") == REFERENCE
    assert main._parse_now("2026-10-06T09:55") == REFERENCE
    assert main._parse_now("2026-10-06 09:55:00") == REFERENCE


def test_parse_now_rejects_garbage():
    with pytest.raises(argparse.ArgumentTypeError):
        main._parse_now("no-es-fecha")


def test_unparseable_now_fails_loudly(tmp_path, output_dir, capsys):
    wb = _make_workbook(tmp_path / "book.xlsx")
    with pytest.raises(SystemExit) as excinfo:
        main.cli([str(wb), "--now", "no-es-fecha"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err.lower()
    assert "--now" in err
    assert "invalid" in err


# ---------------------------------------------------------------
# No override -> real clock
# ---------------------------------------------------------------
def test_resolve_reference_now_returns_explicit_value():
    assert main._resolve_reference_now(REFERENCE) == REFERENCE


def test_resolve_reference_now_uses_real_clock_when_none():
    before = datetime.now()
    resolved = main._resolve_reference_now(None)
    after = datetime.now()
    assert before <= resolved <= after


def test_no_override_window_follows_clock(tmp_path, output_dir, monkeypatch):
    monkeypatch.setattr(main, "_now", lambda: REFERENCE)
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb)
    data = _read_json(output_dir / "dashboard_data.json")
    assert data["meta"]["updatedAt"] == "2026-10-06T09:55:00"
    assert data["meta"]["windowStart"] == "09:00"
    assert _read_json(output_dir / "diagnostic_report.json")["updatedAtSource"] == "run_clock"


def test_no_override_integration_uses_real_clock(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    before = datetime.now()
    main.main(wb)
    after = datetime.now()
    start = _read_json(output_dir / "dashboard_data.json")["meta"]["windowStart"]
    assert start in {before.strftime("%H:00"), after.strftime("%H:00")}


# ---------------------------------------------------------------
# updatedAtSource reports the truth
# ---------------------------------------------------------------
def test_updated_at_source_reports_override(tmp_path, output_dir):
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb, reference_now=REFERENCE)
    diag = _read_json(output_dir / "diagnostic_report.json")
    assert diag["updatedAtSource"] == "now_override"


# ---------------------------------------------------------------
# Excel mtime is diagnostic ONLY (never anchors the window)
# ---------------------------------------------------------------
def test_excel_mtime_is_separate_diagnostic_and_does_not_drive_window(
    tmp_path, output_dir
):
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb, reference_now=REFERENCE)
    diag = _read_json(output_dir / "diagnostic_report.json")
    data = _read_json(output_dir / "dashboard_data.json")

    expected_mtime = datetime.fromtimestamp(MTIME_TS).strftime("%Y-%m-%dT%H:%M:%S")
    # Reported separately...
    assert diag["excelFileMtime"] == expected_mtime
    # ...and NOTHING about the window comes from it: the anchor is the override,
    # the mtime is a different date entirely.
    assert diag["windowAnchor"] == "2026-10-06T09:55:00"
    assert data["meta"]["updatedAt"] == "2026-10-06T09:55:00"
    assert data["meta"]["windowStart"] == "09:00"
    assert expected_mtime != data["meta"]["updatedAt"]
    assert expected_mtime[:10] != data["meta"]["updatedAt"][:10]


def test_contract_has_no_mtime_field(tmp_path, output_dir):
    """The contract carries no Excel-mtime field at all (diagnostic only)."""
    wb = _make_workbook(tmp_path / "book.xlsx")
    main.main(wb, reference_now=REFERENCE)
    data = _read_json(output_dir / "dashboard_data.json")
    blob = json.dumps(data)
    assert "mtime" not in blob.lower()


# ---------------------------------------------------------------
# No second temporal reference: to_contract refuses to invent a window
# ---------------------------------------------------------------
def test_to_contract_requires_an_explicit_window():
    """The old `compute_window(datetime.now())` fallback was a second reference."""
    with pytest.raises(ValueError):
        main.to_contract([])
