"""Regression test (2026-09-04, real-money-readiness push): phase8_entry_execution.py's run()
used to contain TWO independent price-freshness re-validations - the market-hours/early-close
-aware `_check_price_data_freshness()` (called first, returns early on failure) and a second,
looser "at most 1 trading day old" check further down with no early-close/intraday awareness
(the exact class of bug `_check_price_data_freshness()`'s own 2026-08-24 fix addressed). The
second check could never actually let stale data through today, since the first always runs
first and halts on failure - but it was a landmine: if the call order were ever refactored, the
looser check would silently become the live guard. Removed as dead, redundant code rather than
reconciled, since `_check_price_data_freshness()` already covers every case (including the
dry-run/empty-price_daily allowance).

This test guards against a second such check being reintroduced.
"""

import inspect

from algo.orchestrator import phase8_entry_execution


class TestPhase8SinglePriceFreshnessCheck:
    def test_run_source_has_no_second_freshness_query(self) -> None:
        source = inspect.getsource(phase8_entry_execution.run)

        # The removed block's own literal SQL/marker text - if this reappears, someone
        # reintroduced the redundant second check.
        assert "Price data freshness query returned no results" not in source
        assert "most_recent_trading_day = run_date" not in source

    def test_check_price_data_freshness_still_called_exactly_once(self) -> None:
        source = inspect.getsource(phase8_entry_execution.run)

        assert source.count("= _check_price_data_freshness(run_date)") == 1
