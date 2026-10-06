"""
Test for ratification rules in rules.py.
"""
from rules import count_ratifications_soon, count_ratifications_expired


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
