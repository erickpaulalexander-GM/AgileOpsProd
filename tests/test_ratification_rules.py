"""
Test for ratification rules in rules.py.
"""
from datetime import datetime

from rules import (
    _apply_ratification_rules,
    count_ratifications_soon,
    count_ratifications_expired,
)


def test_soon_is_fin_based_not_start_based():
    """'Por vencer' means the ratification window CLOSES within the threshold
    (FIN_RATI), paired with 'vencida' (now > FIN_RATI) — never that the
    window is about to OPEN (the old start-based rule)."""
    ref = datetime(2026, 9, 10, 13, 0)
    rows = [
        # Window OPENS in 5 min but CLOSES in 65 min -> not "por vencer".
        {
            "ticket": "W1",
            "estado": "Coordinado",
            "inicio_rati": datetime(2026, 9, 10, 13, 5),
            "fin_rati": datetime(2026, 9, 10, 14, 5),
        },
        # Window CLOSES in 5 min -> "por vencer".
        {
            "ticket": "W2",
            "estado": "Coordinado",
            "inicio_rati": datetime(2026, 9, 10, 12, 0),
            "fin_rati": datetime(2026, 9, 10, 13, 5),
        },
        # Already closed -> vencida, never "por vencer".
        {
            "ticket": "W3",
            "estado": "Coordinado",
            "inicio_rati": datetime(2026, 9, 10, 11, 0),
            "fin_rati": datetime(2026, 9, 10, 12, 55),
        },
    ]
    result = _apply_ratification_rules(rows, reference_now=ref)
    by_ticket = {r["ticket"]: r for r in result}
    assert by_ticket["W1"]["_ratification_soon"] is False
    assert by_ticket["W2"]["_ratification_soon"] is True
    assert by_ticket["W3"]["_ratification_soon"] is False
    assert by_ticket["W3"]["_ratification_expired"] is True


def test_ratification_count_functions():
    """Test the counting functions for ratifications."""
    # Test data with ratification flags already set
    rows = [
        {
            "ticket": "TEST-001",
            "_ratification_soon": True,
            "_ratification_expired": False,
        },
        {
            "ticket": "TEST-002", 
            "_ratification_soon": True,
            "_ratification_expired": True,
        },
        {
            "ticket": "TEST-003",
            "_ratification_soon": False,
            "_ratification_expired": True,
        },
        {
            "ticket": "TEST-004",
            "_ratification_soon": False,
            "_ratification_expired": False,
        }
    ]
    
    soon_count = count_ratifications_soon(rows)
    expired_count = count_ratifications_expired(rows)
    
    assert soon_count == 2  # TEST-001 and TEST-002
    assert expired_count == 2  # TEST-002 and TEST-003


def test_ratification_count_empty():
    """Test counting functions with empty list."""
    rows = []
    
    soon_count = count_ratifications_soon(rows)
    expired_count = count_ratifications_expired(rows)
    
    assert soon_count == 0
    assert expired_count == 0


def test_ratification_count_none_flags():
    """Test counting functions when flags are missing."""
    rows = [
        {
            "ticket": "TEST-001",
            # No _ratification_soon flag
            # No _ratification_expired flag
        },
        {
            "ticket": "TEST-002",
        }
    ]
    
    soon_count = count_ratifications_soon(rows)
    expired_count = count_ratifications_expired(rows)
    
    assert soon_count == 0
    assert expired_count == 0


if __name__ == "__main__":
    test_ratification_count_functions()
    test_ratification_count_empty()
    test_ratification_count_none_flags()
    print("All ratification counting tests passed!")
