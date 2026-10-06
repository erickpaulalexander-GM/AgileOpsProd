"""
Test for midnight crossing scenarios (ADR-004).
"""
from adapter import hhmm_to_minutes


def test_midnight_crossing_scenarios():
    """Test various midnight crossing scenarios."""
    # Standard 23:00-07:00 window
    assert hhmm_to_minutes("23:00", "23:00") == 0
    assert hhmm_to_minutes("23:59", "23:00") == 59
    assert hhmm_to_minutes("00:00", "23:00") == 60
    assert hhmm_to_minutes("00:30", "23:00") == 90
    assert hhmm_to_minutes("01:00", "23:00") == 120
    assert hhmm_to_minutes("06:59", "23:00") == 479
    assert hhmm_to_minutes("07:00", "23:00") == 480


def test_different_windows():
    """Test with different window starts."""
    # 22:00 to 06:00 window
    assert hhmm_to_minutes("22:00", "22:00") == 0
    assert hhmm_to_minutes("23:59", "22:00") == 119
    assert hhmm_to_minutes("00:00", "22:00") == 120
    assert hhmm_to_minutes("05:59", "22:00") == 479
    assert hhmm_to_minutes("06:00", "22:00") == 480


def test_wraparound_behavior():
    """Test that times wrap correctly."""
    # Ensure we don't get negative values for reasonable inputs
    assert hhmm_to_minutes("08:00", "09:00") == -60  # 08:00 is 60 min before 09:00
    assert hhmm_to_minutes("08:30", "09:00") == -30  # 08:30 is 30 min before 09:00


if __name__ == "__main__":
    test_midnight_crossing_scenarios()
    test_different_windows()
    test_wraparound_behavior()
    print("All midnight crossing tests passed!")
