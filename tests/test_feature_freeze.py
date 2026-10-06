"""
Tests for Feature Freeze v1.0 (ADR-007).

- FIN_RATI is the ONLY ratification end reference.
- FIN_RATI_TOTAL is not mapped and not parsed.
- Reversion columns are not read from Excel; reversions is a
  "próximamente" placeholder sourced from JIRA.
"""
from column_map import COLUMN_MAP, DATE_COLUMNS
from kpi import calculate_kpis, REVERSIONS_STATUS, REVERSIONS_SOURCE


def test_fin_rati_total_only_for_actions():
    """ADR-008 supersedes ADR-007 for this column: FIN_RATI_TOTAL is mapped
    ONLY for the informational action payload. It never feeds KPIs or rules."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    rules_src = (root / "python" / "rules.py").read_text(encoding="utf-8")
    kpi_src = (root / "python" / "kpi.py").read_text(encoding="utf-8")
    assert "fin_rati_total" not in rules_src
    assert "fin_rati_total" not in kpi_src
    # Mapped for the action payload only (ADR-008)
    assert COLUMN_MAP.get("FEC. HORA. FIN. RATI. TOTAL") == "fin_rati_total"
    assert "fin_rati_total" in DATE_COLUMNS


def test_fin_rati_is_the_only_reference():
    """FIN_RATI (inicio/fin) remain mapped and parsed."""
    assert COLUMN_MAP["FEC. HORA. INI. RATI"] == "inicio_rati"
    assert COLUMN_MAP["FEC. HORA. FIN. RATI"] == "fin_rati"
    assert "inicio_rati" in DATE_COLUMNS
    assert "fin_rati" in DATE_COLUMNS


def test_reversion_columns_not_read():
    """No reversion column is mapped or parsed from Excel (ADR-007)."""
    for excel_col in ("TIEMPO REVERSION", "FEC_HOR_INI_REVERSION", "FEC_HOR_FIN_REVERSION"):
        assert excel_col not in COLUMN_MAP
    for internal in ("tiempo_reversion", "inicio_reversion", "fin_reversion"):
        assert internal not in COLUMN_MAP.values()
        assert internal not in DATE_COLUMNS


def test_reversions_kpi_is_placeholder():
    """Reversions is always 0 regardless of input rows."""
    rows = [
        {
            "ticket": "T1",
            "estado": "Coordinado",
            "_late_start": False,
            "_ratification_soon": False,
            "_ratification_expired": True,
        },
        {"ticket": "T2", "estado": "Coordinado"},
    ]
    kpis = calculate_kpis(rows)
    assert kpis["reversions"] == 0


def test_reversions_metadata():
    """Reversions placeholder metadata points to JIRA."""
    assert REVERSIONS_STATUS == "proximamente"
    assert REVERSIONS_SOURCE == "JIRA"


def test_contract_kpi_shape_unchanged():
    """The contract still exposes the 4 KPI keys (shape frozen)."""
    kpis = calculate_kpis([])
    assert set(kpis) == {
        "lateStarts",
        "ratificationsSoon",
        "ratificationsExpired",
        "reversions",
    }


if __name__ == "__main__":
    test_fin_rati_total_only_for_actions()
    test_fin_rati_is_the_only_reference()
    test_reversion_columns_not_read()
    test_reversions_kpi_is_placeholder()
    test_reversions_metadata()
    test_contract_kpi_shape_unchanged()
    print("All feature-freeze tests passed!")
