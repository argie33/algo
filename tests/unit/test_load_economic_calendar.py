#!/usr/bin/env python3
"""Regression test for loaders/load_economic_calendar.py.

Added 2026-08-24 (real-money-readiness goal session): economic_calendar had no loader
anywhere in history despite being listed in terraform monitoring config - 13 stale rows from
2026-06-01/03, zero future events. This is the new loader's test coverage: FRED release-date
fetching (mocked, no live network), event assembly, and idempotent upsert storage.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_economic_calendar import (
    FOMC_MEETING_DATES,
    FRED_RELEASES,
    build_events,
    fetch_fred_release_dates,
    store_events,
)


def test_fetch_fred_release_dates_parses_response():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "release_dates": [
            {"release_id": 50, "date": "2026-09-04"},
            {"release_id": 50, "date": "2026-10-02"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    with patch("loaders.load_economic_calendar.requests.get", return_value=mock_response) as mock_get:
        dates = fetch_fred_release_dates("fake_key", 50, date(2026, 8, 1))

    assert dates == ["2026-09-04", "2026-10-02"]
    # release_id and api_key must actually be forwarded to FRED, not silently dropped.
    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["release_id"] == 50
    assert call_params["api_key"] == "fake_key"
    assert call_params["include_release_dates_with_no_data"] == "true"


def test_fetch_fred_release_dates_raises_on_missing_key_not_silent_empty_list():
    # A malformed/unexpected FRED response must fail loudly (fail-fast governance), not
    # silently return [] and let the loader report a fake success with zero real coverage.
    mock_response = MagicMock()
    mock_response.json.return_value = {"unexpected": "shape"}
    mock_response.raise_for_status.return_value = None

    with patch("loaders.load_economic_calendar.requests.get", return_value=mock_response):
        with pytest.raises(RuntimeError, match="missing 'release_dates'"):
            fetch_fred_release_dates("fake_key", 50, date(2026, 8, 1))


def test_build_events_includes_all_fred_releases_and_fomc_dates():
    with patch("loaders.load_economic_calendar.fetch_fred_release_dates", return_value=["2026-09-04"]):
        events = build_events("fake_key")

    event_ids = {e["event_id"] for e in events}
    # One event per FRED release_id (mocked to one date each) + every FOMC date.
    assert len(events) == len(FRED_RELEASES) + len(FOMC_MEETING_DATES)
    for fomc_date in FOMC_MEETING_DATES:
        assert f"FOMC_{fomc_date}" in event_ids
    assert all(e["category"] in ("Economic", "FOMC") for e in events)


def test_store_events_upserts_on_event_id_and_event_date():
    events = [
        {
            "event_id": "FOMC_2026-09-16",
            "event_date": "2026-09-16",
            "event_name": "FOMC Meeting Decision",
            "category": "FOMC",
            "country": "US",
            "importance": "HIGH",
        }
    ]

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur

    with patch("loaders.load_economic_calendar.DatabaseContext", return_value=mock_ctx):
        stored = store_events(events)

    assert stored == 1
    insert_sql, insert_params = mock_cur.execute.call_args.args
    assert "ON CONFLICT (event_id, event_date) DO UPDATE" in insert_sql
    assert insert_params["event_id"] == "FOMC_2026-09-16"


def test_store_events_empty_list_is_noop():
    with patch("loaders.load_economic_calendar.DatabaseContext") as mock_ctx_cls:
        stored = store_events([])
    assert stored == 0
    mock_ctx_cls.assert_not_called()
