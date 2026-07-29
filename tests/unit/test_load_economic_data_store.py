#!/usr/bin/env python3
"""Regression test for loaders/load_economic_data.py::store_economic_data.

Guards against re-introducing an unscoped DELETE that wipes an economic series'
entire history instead of just the date range being refreshed.
"""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_economic_data import mark_unavailable, store_economic_data


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


def test_mark_unavailable_upserts_instead_of_bare_insert():
    """economic_data has a UNIQUE(series_id, date) constraint. A same-day retry after
    an earlier failure (or an earlier real fetch) must not raise a swallowed
    duplicate-key error - it must use ON CONFLICT, and must only ever overwrite a row
    that is ALREADY a data_unavailable marker, never real data fetched earlier the
    same day."""
    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur

    with patch("loaders.load_economic_data.DatabaseContext", return_value=mock_ctx):
        mark_unavailable("T10Y2Y", "fred_api_timeout")

    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT" in c.args[0]]
    assert len(insert_calls) == 1
    sql, params = insert_calls[0].args

    assert "ON CONFLICT" in sql
    assert "(series_id, date)" in sql
    # Must gate the overwrite on the existing row already being a marker - real data
    # fetched earlier the same day must never be clobbered by a later failed retry.
    assert "data_unavailable = TRUE" in sql
    assert params == ("T10Y2Y", date.today(), None, True, "fred_api_timeout")


def test_store_economic_data_raises_on_database_failure():
    """Fail-fast: store_economic_data must raise RuntimeError when database write fails,
    not swallow the error and return 0. Returning 0 masks write failures and makes the
    caller think no records were stored (false success)."""
    records = [{"date": "2026-01-05", "value": 1.5}]

    mock_ctx = MagicMock()
    mock_ctx.__enter__.side_effect = RuntimeError("Database connection failed")

    with patch("loaders.load_economic_data.DatabaseContext", return_value=mock_ctx):
        with pytest.raises(RuntimeError, match="Failed to store T10Y2Y"):
            store_economic_data("T10Y2Y", records)


def test_mark_unavailable_raises_on_database_failure():
    """Fail-fast: mark_unavailable must raise RuntimeError when database write fails,
    not swallow the error silently. Silent failures hide database connectivity issues."""
    mock_ctx = MagicMock()
    mock_ctx.__enter__.side_effect = RuntimeError("Database connection failed")

    with patch("loaders.load_economic_data.DatabaseContext", return_value=mock_ctx):
        with pytest.raises(RuntimeError, match="Failed to mark T10Y2Y unavailable"):
            mark_unavailable("T10Y2Y", "test_reason")
