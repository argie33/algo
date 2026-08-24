"""Regression: capital_routing_daily (algo/risk/capital_routing.py, computed inline by
loaders/load_market_status_daily.py's MarketStatusDailyLoader.run() right after
MarketExposure().compute()) was never declared in either MarketStatusDailyLoader.output_tables
or loaders/loader_registry.py's LOADER_TABLES - same bug class as
test_market_constituents_etf_symbols_output_table.py's etf_symbols gap (2026-08-17): the table
was correctly populated every run, but its data_loader_status row was never touched by the
generic output_tables UPSERT (utils/optimal_loader.py), so it stayed frozen at whatever
migration 1228 initially seeded (completion_pct=0.0, status=NULL) and showed as "untracked" in
the dashboard's table inventory panel before that migration even ran.
"""

from loaders.load_market_status_daily import MarketStatusDailyLoader
from loaders.loader_registry import all_tables


def test_capital_routing_daily_declared_as_output_table():
    assert "capital_routing_daily" in MarketStatusDailyLoader.output_tables


def test_output_tables_matches_registry_secondary_tables():
    registry_tables = set(all_tables("load_market_status_daily.py"))
    declared = {MarketStatusDailyLoader.table_name, *MarketStatusDailyLoader.output_tables}
    assert declared == registry_tables
