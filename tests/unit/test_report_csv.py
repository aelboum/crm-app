"""A report as CSV rows (decision P10-B, `crm_app.domains.reports.csv_rows`)."""

from __future__ import annotations

import uuid
from datetime import date

from crm_app.domains import export
from crm_app.domains import reports as rules

OWNER = uuid.uuid4()


def _deals() -> dict[str, object]:
    return {
        "period": {"start": date(2026, 10, 1), "end": date(2026, 10, 31), "days": 31},
        "capped": False,
        "created": 3,
        "created_before": 2,
        "won": 2,
        "won_before": 1,
        "win_rate": None,
        "win_rate_before": 100,
        "won_value": [{"currency": "EUR", "amount": "1000.50"}],
        "owners": [{"user_id": OWNER, "won": 1, "won_value": []}],
    }


def test_figures_come_with_their_comparison_and_breakdowns_by_item() -> None:
    rows = rules.csv_rows(_deals())
    assert rows[:4] == [
        {"section": "period", "item": "start", "value": date(2026, 10, 1), "previous": ""},
        {"section": "period", "item": "end", "value": date(2026, 10, 31), "previous": ""},
        {"section": "period", "item": "days", "value": 31, "previous": ""},
        {"section": "period", "item": "capped", "value": False, "previous": ""},
    ]
    assert {"section": "total", "item": "won", "value": 2, "previous": 1} in rows
    assert {"section": "total", "item": "win_rate", "value": None, "previous": 100} in rows
    assert {"section": "won_value", "item": "EUR", "value": "1000.50", "previous": ""} in rows
    assert {"section": "owners", "item": OWNER, "value": 1, "previous": ""} in rows
    # a comparison value is never a row of its own
    assert not [row for row in rows if str(row["item"]).endswith("_before")]


def test_the_csv_has_the_fixed_columns_and_empty_cells_for_none() -> None:
    text = export.to_csv(rules.CSV_COLUMNS, rules.csv_rows(_deals())).decode("utf-8-sig")
    lines = text.splitlines()
    assert lines[0] == "section,item,value,previous"
    assert "total,win_rate,,100" in lines
    assert f"owners,{OWNER},1," in lines
