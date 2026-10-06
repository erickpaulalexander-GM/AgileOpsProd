"""
Test for hhmm_to_minutes conversion (ADR-004).
"""
from adapter import hhmm_to_minutes


def test_hhmm_to_minutes_basic():
    """Test basic conversions."""
    assert hhmm_to_minutes("23:00", "23:00") == 0
    assert hhmm_to_minutes("23:30", "23:00") == 30
    assert hhmm_to_minutes("00:00", "23:00") == 60
    assert hhmm_to_minutes("01:30", "23:00") == 150
    assert hhmm_to_minutes("07:00", "23:00") == 480


def test_hhmm_to_minutes_crossing_midnight():
    """Test midnight crossing scenarios."""
    # From 23:00 window, 00:30 should be 90 minutes later
    assert hhmm_to_minutes("00:30", "23:00") == 90
    
    # From 06:00 window, 07:30 should be 90 minutes later  
    assert hhmm_to_minutes("07:30", "06:00") == 90
    
    # From 22:00 window, 01:00 should be 180 minutes later (crossing midnight)
    assert hhmm_to_minutes("01:00", "22:00") == 180


def test_hhmm_to_minutes_same_time():
    """Test when time equals window start."""
    assert hhmm_to_minutes("14:00", "14:00") == 0
    assert hhmm_to_minutes("09:30", "09:30") == 0


if __name__ == "__main__":
    test_hhmm_to_minutes_basic()
    test_hhmm_to_minutes_crossing_midnight()
    test_hhmm_to_minutes_same_time()
    print("All hhmm_to_minutes tests passed!")
