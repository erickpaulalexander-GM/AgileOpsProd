"""
Tests for ADR-008 — window.ChangeOpsActions payload (renderer.build_actions).

The payload is informational and derived from existing rule flags; it must
not modify the Data Contract v1 nor add business rules.
"""
from datetime import datetime

from renderer import build_actions


def _row(ticket, **kw):
    base = {
        "ticket": ticket,
        "nombre_app": "APP-" + ticket,
        "responsable": "Resp " + ticket,
        "estado": "Coordinado",
        "inicio_impl": datetime(2026, 9, 10, 16, 0),
        "fin_impl": datetime(2026, 9, 10, 17, 0),
        "inicio_rati": datetime(2026, 9, 10, 17, 0),
        "fin_rati": datetime(2026, 9, 10, 18, 0),
        "fin_rati_total": datetime(2026, 9, 10, 19, 0),
    }
    base.update(kw)
    return base


def test_payload_keys():
    a = build_actions([], [])
    assert set(a) == {
        "passesInWindow",
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "inFlightNow",
        "staleInFlight",
    }


def test_required_fields_present():
    a = build_actions([], [_row("T1")])
    rec = a["passesInWindow"][0]
    assert rec["ticket"] == "T1"
    assert rec["app"] == "APP-T1"
    assert rec["resource"] == "Resp T1"
    assert rec["status"] == "Coordinado"
    assert rec["iniImpl"] == "10/09/2026 16:00"
    assert rec["finImpl"] == "10/09/2026 17:00"


def test_late_starts_use_impl_times():
    rows = [_row("L1", _late_start=True), _row("L2", _late_start=False)]
    a = build_actions(rows, [])
    assert [r["ticket"] for r in a["lateStarts"]] == ["L1"]
    assert "iniImpl" in a["lateStarts"][0]
    assert "endRatiTotal" not in a["lateStarts"][0]


def test_ratifications_soon_use_rati_times():
    rows = [_row("S1", _ratification_soon=True)]
    a = build_actions(rows, [])
    assert [r["ticket"] for r in a["ratificationsSoon"]] == ["S1"]
    assert a["ratificationsSoon"][0]["iniRati"] == "10/09/2026 17:00"
    assert "endRatiTotal" not in a["ratificationsSoon"][0]


def test_ratifications_expired_include_end_rati_total():
    rows = [_row("E1", _ratification_expired=True)]
    a = build_actions(rows, [])
    rec = a["ratificationsExpired"][0]
    assert rec["ticket"] == "E1"
    assert rec["iniRati"] == "10/09/2026 17:00"
    assert rec["finRati"] == "10/09/2026 18:00"
    assert rec["endRatiTotal"] == "10/09/2026 19:00"  # informational only


def test_missing_values_are_empty_strings():
    row = _row("M1", nombre_app="", responsable=None, fin_rati_total=None)
    a = build_actions([], [row])
    rec = a["passesInWindow"][0]
    assert rec["app"] == ""
    assert rec["resource"] == ""


if __name__ == "__main__":
    test_payload_keys()
    test_required_fields_present()
    test_late_starts_use_impl_times()
    test_ratifications_soon_use_rati_times()
    test_ratifications_expired_include_end_rati_total()
    test_missing_values_are_empty_strings()
    print("All action payload tests passed!")
