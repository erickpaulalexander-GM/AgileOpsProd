"""
Test for overlap detection in rules.py.
"""
from rules import _has_time_overlap
from datetime import datetime


def test_has_time_overlap():
    """Test time overlap detection."""
    # Create mock rows with datetime objects
    row_a = {
        "inicio_impl": datetime(2026, 9, 9, 14, 0),  # 14:00
        "fin_impl": datetime(2026, 9, 9, 15, 0),     # 15:00
    }
    
    row_b = {
        "inicio_impl": datetime(2026, 9, 9, 14, 30),  # 14:30
        "fin_impl": datetime(2026, 9, 9, 15, 30),    # 15:30
    }
    
    # Should overlap (14:30-15:00 overlap)
    assert _has_time_overlap(row_a, row_b)
    assert _has_time_overlap(row_b, row_a)  # Should be symmetric


def test_no_time_overlap():
    """Test when there's no overlap."""
    row_a = {
        "inicio_impl": datetime(2026, 9, 9, 14, 0),  # 14:00
        "fin_impl": datetime(2026, 9, 9, 15, 0),     # 15:00
    }
    
    row_b = {
        "inicio_impl": datetime(2026, 9, 9, 15, 0),  # 15:00 (starts when A ends)
        "fin_impl": datetime(2026, 9, 9, 16, 0),     # 16:00
    }
    
    # Should not overlap (they are adjacent, not overlapping)
    assert not _has_time_overlap(row_a, row_b)
    assert not _has_time_overlap(row_b, row_a)


def test_back_to_back_times():
    """Test when one ends exactly when another starts."""
    row_a = {
        "inicio_impl": datetime(2026, 9, 9, 14, 0),  # 14:00
        "fin_impl": datetime(2026, 9, 9, 15, 0),     # 15:00
    }
    
    row_b = {
        "inicio_impl": datetime(2026, 9, 9, 15, 0),  # 15:00 (same as A's end)
        "fin_impl": datetime(2026, 9, 9, 16, 0),     # 16:00
    }
    
    # Should not overlap
    assert not _has_time_overlap(row_a, row_b)


def test_fully_contained_overlap():
    """Test when one time period is fully contained in another."""
    row_a = {
        "inicio_impl": datetime(2026, 9, 9, 14, 0),  # 14:00
        "fin_impl": datetime(2026, 9, 9, 16, 0),     # 16:00
    }
    
    row_b = {
        "inicio_impl": datetime(2026, 9, 9, 14, 30),  # 14:30
        "fin_impl": datetime(2026, 9, 9, 15, 30),    # 15:30
    }
    
    # Should overlap (B is contained in A)
    assert _has_time_overlap(row_a, row_b)
    assert _has_time_overlap(row_b, row_a)


if __name__ == "__main__":
    test_has_time_overlap()
    test_no_time_overlap()
    test_back_to_back_times()
    test_fully_contained_overlap()
    print("All overlap detection tests passed!")
