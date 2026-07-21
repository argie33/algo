#!/usr/bin/env python3
"""Regression test for loaders/load_economic_data.py::store_economic_data.

Guards against re-introducing an unscoped DELETE that wipes an economic series'
entire history instead of just the date range being refreshed.
"""

from unittest.mock import MagicMock, patch

from loaders.load_economic_data import store_economic_data


def test_delete_is_scoped_to_fetched_date_range_not_whole_series():
    records = [
        {"date": "2026-01-05", "value": 1.5},
        {"date": "2026-03-10", "value": 1.7},
        {"date": "2026-06-30", "value": 1.9},
    ]

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur

    with patch("loaders.load_economic_data.DatabaseContext", return_value=mock_ctx):
        inserted = store_economic_data("T10Y2Y", records)

    assert inserted == 3

    delete_calls = [c for c in mock_cur.execute.call_args_list if "DELETE" in c.args[0]]
    assert len(delete_calls) == 1
    delete_sql, delete_params = delete_calls[0].args

    # Must scope by series_id AND a date range - not just series_id alone (which would
    # delete every row ever stored for this series, not only the ones being replaced).
    assert "date >=" in delete_sql
    assert "date <=" in delete_sql
    assert delete_params == ("T10Y2Y", "2026-01-05", "2026-06-30")

    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT" in c.args[0]]
    assert len(insert_calls) == 3


def test_empty_records_does_not_touch_database():
    with patch("loaders.load_economic_data.DatabaseContext") as mock_db_context:
        inserted = store_economic_data("T10Y2Y", [])

    assert inserted == 0
    mock_db_context.assert_not_called()
