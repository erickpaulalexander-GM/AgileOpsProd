"""
Test for ADR-006: terminal states are excluded from operational KPIs
and from conflict detection.
"""
from datetime import datetime

from rules import (
    is_terminal,
    filter_operational,
    _apply_late_start,
    _apply_ratification_rules,
    _detect_conflicts,
)


def test_is_terminal_known_states():
    """Terminal states (and equivalents) are detected."""
    terminal = [
        "Cerrado",
        "Terminado Satisfactorio",
        "Rechazado",
        "Cancelado",
        "Anulado",
        "Registrado",
        "Pre Registrado",
        "Aprobado LT",       # approval family: inactive for operational KPIs
        "Aprobado CL QA",
        "Aprobado CL DEV",
        "Aprobado PO",
        "Aprobado Ops",
        "Preaprobado",       # substring of "aprobado"
        "cerrado",           # case-insensitive
        "TERMINADO",         # partial keyword
    ]
    for state in terminal:
        assert is_terminal(state) is True, state


def test_is_terminal_operational_states():
    """Operational states are NOT terminal."""
    operational = [
        "Coordinado",
        "Pase en curso",
        "Ratificación total en curso",
        "Ratificación Parcial Satisfactorio",
        "",
        None,
    ]
    for state in operational:
        assert is_terminal(state) is False, state


def test_filter_operational():
    """filter_operational keeps only non-terminal rows."""
    rows = [
        {"ticket": "A", "estado": "Coordinado"},
        {"ticket": "B", "estado": "Cerrado"},
        {"ticket": "C", "estado": "Rechazado"},
        {"ticket": "D", "estado": "Pase en curso"},
    ]
    result = filter_operational(rows)
    assert [r["ticket"] for r in result] == ["A", "D"]


def test_terminal_not_late_start():
    """A terminal pase is never a late start (even if it looks late)."""
    rows = [
        {
            "ticket": "T1",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Cerrado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 20, 0))
    assert result[0]["_late_start"] is False


def test_terminal_not_ratification_expired():
    """A closed pase does not count as an expired ratification (ADR-006)."""
    rows = [
        {
            "ticket": "T2",
            "estado": "Terminado Satisfactorio",
            "inicio_rati": datetime(2026, 9, 9, 10, 0),
            "fin_rati": datetime(2026, 9, 9, 11, 0),
        }
    ]
    ref = datetime(2026, 9, 10, 13, 28)
    result = _apply_ratification_rules(rows, reference_now=ref)
    assert result[0]["_ratification_expired"] is False
    assert result[0]["_ratification_soon"] is False


def test_operational_ratification_expired_still_counts():
    """A non-terminal pase with a past ratification end still counts."""
    rows = [
        {
            "ticket": "T3",
            "estado": "Coordinado",
            "inicio_rati": datetime(2026, 9, 9, 10, 0),
            "fin_rati": datetime(2026, 9, 9, 11, 0),
        }
    ]
    ref = datetime(2026, 9, 10, 13, 28)
    result = _apply_ratification_rules(rows, reference_now=ref)
    assert result[0]["_ratification_expired"] is True


def test_terminal_excluded_from_conflicts():
    """Terminal pases never produce conflicts (ADR-006)."""
    rows = [
        {
            "ticket": "IMP-1",
            "estado": "Coordinado",
            "recurso": "Pool AgileOps Prod",
            "responsable": "Alice",
            "inicio_impl": datetime(2026, 9, 10, 16, 0),
            "fin_impl": datetime(2026, 9, 10, 17, 0),
        },
        {
            "ticket": "IMP-2",
            "estado": "Cerrado",  # terminal → excluded
            "recurso": "Pool AgileOps Prod",
            "responsable": "Alice",
            "inicio_impl": datetime(2026, 9, 10, 16, 30),
            "fin_impl": datetime(2026, 9, 10, 17, 30),
        },
    ]
    result = _detect_conflicts(rows)
    by_ticket = {r["ticket"]: r for r in result}
    assert by_ticket["IMP-1"]["_conflicts_with"] == []
    assert by_ticket["IMP-2"]["_conflicts_with"] == []


def test_operational_conflict_still_detected():
    """Two non-terminal implementations with same responsable DO conflict."""
    rows = [
        {
            "ticket": "IMP-1",
            "estado": "Coordinado",
            "recurso": "Pool AgileOps Prod",
            "responsable": "Alice",
            "inicio_impl": datetime(2026, 9, 10, 16, 0),
            "fin_impl": datetime(2026, 9, 10, 17, 0),
        },
        {
            "ticket": "IMP-2",
            "estado": "Coordinado",
            "recurso": "Pool AgileOps Prod",
            "responsable": "Alice",
            "inicio_impl": datetime(2026, 9, 10, 16, 30),
            "fin_impl": datetime(2026, 9, 10, 17, 30),
        },
    ]
    result = _detect_conflicts(rows)
    by_ticket = {r["ticket"]: r for r in result}
    assert by_ticket["IMP-1"]["_conflicts_with"] == ["IMP-2"]
    assert by_ticket["IMP-2"]["_conflicts_with"] == ["IMP-1"]


if __name__ == "__main__":
    test_is_terminal_known_states()
    test_is_terminal_operational_states()
    test_filter_operational()
    test_terminal_not_late_start()
    test_terminal_not_ratification_expired()
    test_operational_ratification_expired_still_counts()
    test_terminal_excluded_from_conflicts()
    test_operational_conflict_still_detected()
    print("All terminal-state tests passed!")
