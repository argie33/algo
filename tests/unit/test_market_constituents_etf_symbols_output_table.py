"""Regression: load_market_constituents.py's etf_symbols row was reaped FAILED on every run.

BUG FOUND 2026-08-17: loader_registry.py's LOADER_TABLES already listed
"load_market_constituents.py": ["stock_symbols", "etf_symbols"] - used by
local_loader_scheduler.py to pre-mark BOTH tables RUNNING before the subprocess starts.
But MarketConstituentsLoader never declared output_tables, which is the only thing
runner.py's mark_completed()/mark_failed() secondary-table sweep (and
OptimalLoader._update_final_status()) actually looks at. Every run correctly
TRUNCATE+rebuilt etf_symbols via raw SQL (_upsert_etf_symbols), but its
data_loader_status row stayed RUNNING forever and was later reaped FAILED - live-confirmed
2026-08-17 19:37 UTC: loader logged "SUCCESS: 4854 records loaded in 2.57s" yet
etf_symbols was reaped FAILED as stuck 15 minutes later. 3 consecutive occurrences in the
DB history (2026-08-16 11:47, 2026-08-17 05:32, 2026-08-17 19:37) - every single run, not
intermittent.
"""

from loaders.load_market_constituents import MarketConstituentsLoader
from loaders.loader_registry import all_tables


def test_etf_symbols_declared_as_output_table():
    assert "etf_symbols" in MarketConstituentsLoader.output_tables


def test_output_tables_matches_registry_secondary_tables():
    registry_tables = set(all_tables("load_market_constituents.py"))
    declared = {MarketConstituentsLoader.table_name, *MarketConstituentsLoader.output_tables}
    assert declared == registry_tables
