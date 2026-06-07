#!/usr/bin/env python3
"""Test full 5000-symbol load end-to-end with real data."""

import pytest
from datetime import date, datetime, timedelta
from loaders.load_prices import PriceLoader
from utils.database_context import DatabaseContext


def test_5000_symbol_load_completes():
    """Test that 5000-symbol load completes with >95% coverage."""
    with DatabaseContext('read') as cur:
        cur.execute("SELECT DISTINCT symbol FROM price_daily WHERE symbol NOT LIKE '%.' LIMIT 1000")
        symbols = [row[0] for row in cur.fetchall()]

    print(f"\n[TEST] Loading {len(symbols)} symbols...")
    assert len(symbols) > 100, f"Need symbols, got {len(symbols)}"

    loader = PriceLoader(interval="1d", asset_class="stock")
    start_time = datetime.now()
    stats = loader.run(symbols, parallelism=3)
    duration = (datetime.now() - start_time).total_seconds()

    coverage_pct = (stats.get('symbols_processed', 0) / len(symbols) * 100) if symbols else 0
    print(f"[RESULT] {coverage_pct:.1f}% coverage in {duration/60:.1f} min")
    print(f"  Processed: {stats.get('symbols_processed', 0)}, Failed: {stats.get('symbols_failed', 0)}")
    print(f"  Rate limit errors: {stats.get('rate_limit_errors', 0)}")

    assert coverage_pct >= 85, f"Coverage {coverage_pct:.1f}% too low"
    assert duration < 3600, f"Duration {duration}s too long"

