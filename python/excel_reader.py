"""
Excel reader: reads the Excel file and returns normalized rows.

Responsibilities:
- Read Excel with pandas
- Map column names to internal fields
- Parse date strings to datetime
- Handle empty/missing values
- Filter the in-scope pool resources (column_map.is_in_scope_pool)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from column_map import (
    DATE_COLUMNS,
    EXCEL_DATE_FORMAT,
    REQUIRED_FIELDS,
    is_in_scope_pool,
    map_columns,
)

logger = logging.getLogger(__name__)


def read_excel(path: str | Path, sheet: int | str = 0) -> dict[str, Any]:
    """
    Read Excel file and return normalized data.

    Args:
        path: workbook path.
        sheet: sheet name or index (default 0 = first sheet, config excel.sheet).

    Returns:
        dict with keys:
            - rows: list of normalized row dicts
            - diagnostic: dict with read statistics
    """
    path = Path(path)
    logger.info(f"Reading Excel: {path} (sheet={sheet!r})")

    df = pd.read_excel(path, sheet_name=sheet, dtype=str)  # all str, parseado propio
    df = df.fillna("")

    # Map columns
    col_map = map_columns(df)
    logger.info(f"Mapped {len(col_map)} columns")

    # Rename columns
    df = df.rename(columns=col_map)

    # Keep only mapped columns
    mapped_cols = list(col_map.values())
    df = df[[c for c in mapped_cols if c in df.columns]]

    # Parse dates
    invalid_dates = 0
    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col], errors = _parse_dates(df[col])
            invalid_dates += errors

    # Filter the in-scope pool resources (exact match, see column_map)
    total_rows = len(df)
    df = df[df["recurso"].apply(is_in_scope_pool)]
    in_scope_rows = len(df)

    # Convert to list of dicts
    rows = df.to_dict(orient="records")

    # Count missing required fields
    missing_fields = []
    for field in REQUIRED_FIELDS:
        if field in df.columns:
            empty_count = (df[field].apply(lambda x: x == "" or x is None)).sum()
            if empty_count > 0:
                missing_fields.append({"field": field, "count": int(empty_count)})

    diagnostic = {
        "rowsRead": total_rows,
        "rowsAfterFilter": in_scope_rows,
        "rowsIgnored": total_rows - in_scope_rows,
        "missingFields": missing_fields,
        "invalidDates": invalid_dates,
        "columnsMapped": len(col_map),
    }

    logger.info(
        f"Read {total_rows} rows, {in_scope_rows} in-scope rows "
        f"({total_rows - in_scope_rows} ignored), {invalid_dates} invalid dates"
    )

    return {"rows": rows, "diagnostic": diagnostic}


def _parse_dates(series: pd.Series) -> tuple[pd.Series, int]:
    """
    Parse date strings in DD/MM/YYYY HH:MM format.

    Returns:
        (parsed_series, error_count)
    """
    errors = 0
    result = []

    for val in series:
        if not val or val == "":
            result.append(None)
            continue
        try:
            dt = datetime.strptime(str(val).strip(), EXCEL_DATE_FORMAT)
            result.append(dt)
        except (ValueError, TypeError):
            # Try common alternatives
            try:
                dt = datetime.strptime(str(val).strip(), "%Y-%m-%d %H:%M")
                result.append(dt)
            except (ValueError, TypeError):
                result.append(None)
                errors += 1

    # dtype=object keeps None for invalid dates (avoids pandas NaT, which
    # passes isinstance(dt, datetime) and breaks datetime arithmetic).
    return pd.Series(result, index=series.index, dtype=object), errors
