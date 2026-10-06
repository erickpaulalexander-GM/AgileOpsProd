"""
Test for late start rule in rules.py (corrected semantics, ADR-005 reference).

Rule: Inicio atrasado
    - Estado == "Coordinado"
    - reference_now is more than 5 minutes past the planned implementation start
"""
from datetime import datetime

from rules import _apply_late_start


def test_late_start_identified():
    """Coordinated pase whose start passed by >5 min => late."""
    rows = [
        {
            "ticket": "TEST-001",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Coordinado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 14, 10))
    assert result[0]["_late_start"] is True


def test_not_late_within_threshold():
    """Only 3 minutes past start => not late."""
    rows = [
        {
            "ticket": "TEST-002",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Coordinado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 14, 3))
    assert result[0]["_late_start"] is False


def test_boundary_exactly_five_minutes():
    """Exactly 5 minutes past start => not late (rule is strictly greater)."""
    rows = [
        {
            "ticket": "TEST-003",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Coordinado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 14, 5))
    assert result[0]["_late_start"] is False


def test_non_coordinado_state_not_late():
    """A closed pase is never a late start."""
    rows = [
        {
            "ticket": "TEST-004",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Terminado Satisfactorio",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 15, 0))
    assert result[0]["_late_start"] is False


def test_registrado_state_not_late():
    """Rule is strictly 'Coordinado'; 'Registrado' does not qualify."""
    rows = [
        {
            "ticket": "TEST-005",
            "inicio_impl": datetime(2026, 9, 10, 14, 0),
            "estado": "Registrado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 15, 0))
    assert result[0]["_late_start"] is False


def test_future_start_not_late():
    """A pase that starts after the reference time cannot be late."""
    rows = [
        {
            "ticket": "TEST-006",
            "inicio_impl": datetime(2026, 9, 10, 16, 0),
            "estado": "Coordinado",
        }
    ]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 13, 0))
    assert result[0]["_late_start"] is False


def test_missing_start_not_late():
    """Missing start date is skipped safely."""
    rows = [{"ticket": "TEST-007", "inicio_impl": None, "estado": "Coordinado"}]
    result = _apply_late_start(rows, reference_now=datetime(2026, 9, 10, 15, 0))
    assert result[0]["_late_start"] is False


if __name__ == "__main__":
    test_late_start_identified()
    test_not_late_within_threshold()
    test_boundary_exactly_five_minutes()
    test_non_coordinado_state_not_late()
    test_registrado_state_not_late()
    test_future_start_not_late()
    test_missing_start_not_late()
    print("All late start tests passed!")
