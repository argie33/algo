"""Tests for dashboard/fetchers_config.py:

1. fetch_health now threads loader_run_status (NOT_STARTED/RUNNING/COMPLETED/FAILED/
   TIMEOUT) and stale_threshold_days through from the API response - both were
   computed/written by the backend (lambda/api/routes/algo_handlers/market.py's
   _get_data_status) but previously dropped before reaching the dashboard.
2. fetch_table_inventory (new) parses /api/admin/inventory into untracked_tables/
   missing_tables and caches the result so the freshness panel's optional inventory
   enrichment doesn't hit the DB's per-table COUNT(*) scan on every refresh cycle.
"""

import dashboard.fetchers_config as fetchers_config
from dashboard.fetchers_config import fetch_health, fetch_table_inventory


def _reset_caches():
    fetchers_config._data_status_cache.clear()
    fetchers_config._inventory_cache.clear()


def test_fetch_health_threads_loader_run_status_and_threshold(monkeypatch):
    _reset_caches()
    api_response = {
        "sources": [
            {
                "name": "price_daily",
                "role": "CRIT",
                "status": "ok",
                "last_updated": "2026-07-27T09:00:00+00:00",
                "age_hours": 1.0,
                "row_count": 500,
                "loader_run_status": "COMPLETED",
                "stale_threshold_days": 1,
            },
            {
                "name": "insider_transaction_velocity",
                "role": "NORM",
                "status": "empty",
                "last_updated": None,
                "age_hours": None,
                "row_count": 0,
                "loader_run_status": "NOT_STARTED",
                "stale_threshold_days": 7,
            },
        ],
        "ready_to_trade": True,
    }
    monkeypatch.setattr(fetchers_config, "api_call", lambda *a, **k: api_response)

    result = fetch_health(None)

    assert "_error" not in result
    items = {item["tbl"]: item for item in result["items"]}
    assert items["price_daily"]["loader_run_status"] == "COMPLETED"
    assert items["price_daily"]["stale_threshold_days"] == 1
    assert items["insider_transaction_velocity"]["loader_run_status"] == "NOT_STARTED"
    assert items["insider_transaction_velocity"]["stale_threshold_days"] == 7
    _reset_caches()


def test_fetch_table_inventory_parses_untracked_and_missing(monkeypatch):
    _reset_caches()
    api_response = {
        "items": [
            {"name": "price_daily", "type": "tracked", "status": "COMPLETED"},
            {"name": "some_orphaned_table", "type": "untracked", "status": None},
        ],
        "missing_tables": ["a_dropped_table"],
        "summary": {"total_tables": 2, "untracked": 1},
    }
    monkeypatch.setattr(fetchers_config, "api_call", lambda *a, **k: api_response)

    result = fetch_table_inventory(None)

    assert "_error" not in result
    assert result["untracked_tables"] == ["some_orphaned_table"]
    assert result["missing_tables"] == ["a_dropped_table"]
    assert result["summary"]["total_tables"] == 2
    _reset_caches()


def test_fetch_table_inventory_caches_result(monkeypatch):
    _reset_caches()
    call_count = {"n": 0}

    def fake_api_call(*a, **k):
        call_count["n"] += 1
        return {"items": [], "missing_tables": [], "summary": {}}

    monkeypatch.setattr(fetchers_config, "api_call", fake_api_call)

    fetch_table_inventory(None)
    fetch_table_inventory(None)

    assert call_count["n"] == 1  # second call served from cache
    _reset_caches()


def test_fetch_table_inventory_api_error_not_cached(monkeypatch):
    _reset_caches()
    monkeypatch.setattr(fetchers_config, "api_call", lambda *a, **k: {"_error": "boom"})

    result = fetch_table_inventory(None)

    assert "_error" in result
    _reset_caches()
