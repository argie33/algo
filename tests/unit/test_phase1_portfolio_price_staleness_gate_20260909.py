"""Regression test: validate_portfolio_symbol_prices() used to only check that an
open-position portfolio symbol had ANY row in price_daily, with no recency bound - a symbol
stuck on a multi-day-old row (e.g. a same-day loader failure affecting only that symbol,
invisible to the aggregate table-freshness check and to DataPatrol's per-symbol staleness
check, which only fires WARN past a 7-day lag) passed this check indefinitely, leaving
Phase 3/6 to evaluate stops/exits for a real open position against a stale price. Real-money-
readiness audit, 2026-09-09: added an optional `acceptable_min_date` threshold (the same
per-run value phase1_data_freshness.py's aggregate check already computes) that, when
provided, halts on a portfolio symbol whose latest available price predates it.
"""

from datetime import date
from unittest.mock import MagicMock

from algo.orchestrator.phase1_readiness_checks import validate_portfolio_symbol_prices


def test_stale_portfolio_symbol_halts_when_threshold_given():
    cur = MagicMock()
    cur.fetchall.side_effect = [
        [("AAPL",)],  # open-position symbols
        [("AAPL", 150.0, date(2026, 8, 20))],  # latest price is 2+ weeks stale
    ]
    log_calls = []
    result = validate_portfolio_symbol_prices(
        cur, {}, lambda *a: log_calls.append(a), acceptable_min_date=date(2026, 9, 8)
    )

    assert result is not None, "a stale portfolio-symbol price must halt, not pass silently"
    assert result.halted is True
    assert result.status == "halted"
    assert "AAPL" in result.data["stale_prices"]


def test_fresh_portfolio_symbol_passes_with_threshold_given():
    cur = MagicMock()
    cur.fetchall.side_effect = [
        [("AAPL",)],
        [("AAPL", 150.0, date(2026, 9, 8))],  # exactly at the threshold - acceptable
    ]
    result = validate_portfolio_symbol_prices(cur, {}, lambda *a: None, acceptable_min_date=date(2026, 9, 8))
    assert result is None


def test_no_threshold_preserves_prior_any_row_behavior():
    """Backward compatibility: omitting acceptable_min_date must not newly halt on a stale
    (but present) row - only callers that opt in by passing the threshold get the new check."""
    cur = MagicMock()
    cur.fetchall.side_effect = [
        [("AAPL",)],
        [("AAPL", 150.0, date(2020, 1, 1))],  # very stale, but no threshold was given
    ]
    result = validate_portfolio_symbol_prices(cur, {}, lambda *a: None)
    assert result is None
