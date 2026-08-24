"""Regression test for the 2026-08-23 fix: _get_data_status's DAILY-table staleness branch
(max_age<=1, elapsed-hours based) in lambda/api/routes/algo_handlers/market.py claimed in its
own comment to "match monitor_data_staleness.py", but never ported that script's weekend/holiday
gap allowance - only the flat 24h/48h threshold numbers. The sibling weekly/biweekly branch
(_is_stale_by_trading_days, max_age>1) already got this exact fix on 2026-08-16
(test_data_status_weekend_trading_day_staleness.py) - this was the other half of the same bug
class, left unfixed.

Live-confirmed 2026-08-23 (a Sunday): price_daily/stock_scores/algo_trades/buy_sell_daily all
correctly read FRESH in monitor_data_staleness.py (which has the gap allowance) while this
endpoint - the one that actually drives the dashboard's "DATA FRESHNESS" panel and the
`ready_to_trade` flag - flagged them stale/error purely from the Friday->Sunday gap, producing a
false "NOT READY" state (42/47) with no real data problem.
"""

import importlib
from datetime import date

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")


def test_fridays_data_not_stale_on_sunday_for_whitelisted_table():
    """The core bug: a table updated Friday, checked Sunday, must not read as stale purely
    from the 2-day weekend gap."""
    friday = date(2026, 8, 21)
    sunday = date(2026, 8, 23)

    stale_cutoff, critical_cutoff = market_module._daily_table_staleness_cutoffs("price_daily", sunday, friday)
    # 24h/48h base thresholds + 2 gap days (48h) = 72h/96h
    assert stale_cutoff == 24.0 + 48.0
    assert critical_cutoff == 48.0 + 48.0


def test_non_whitelisted_table_gets_no_gap_allowance():
    """A table NOT on the once-per-trading-day whitelist (e.g. an intraday-refreshed one)
    must keep the flat 24h/48h thresholds even across a weekend - the allowance is scoped
    deliberately, not universal."""
    friday = date(2026, 8, 21)
    sunday = date(2026, 8, 23)

    stale_cutoff, critical_cutoff = market_module._daily_table_staleness_cutoffs(
        "some_intraday_table_not_on_the_list", sunday, friday
    )
    assert stale_cutoff == 24.0
    assert critical_cutoff == 48.0


def test_circuit_breaker_status_gets_the_allowance():
    """circuit_breaker_status writes once per real orchestrator run (once per trading day) -
    same cadence class as price_daily, needs the same allowance. Live-confirmed 2026-08-23:
    its most recent row's check_date was the correct last trading day (Friday), not stale at
    all - only the missing gap allowance made it read as stale."""
    friday = date(2026, 8, 21)
    sunday = date(2026, 8, 23)

    stale_cutoff, critical_cutoff = market_module._daily_table_staleness_cutoffs(
        "circuit_breaker_status", sunday, friday
    )
    assert stale_cutoff == 24.0 + 48.0
    assert critical_cutoff == 48.0 + 48.0


def test_no_gap_no_allowance_needed():
    """On a normal weekday with no trading-calendar gap, thresholds stay at the flat
    24h/48h baseline even for a whitelisted table."""
    monday = date(2026, 8, 17)
    tuesday = date(2026, 8, 18)  # expected_date == yesterday, a normal trading day

    stale_cutoff, critical_cutoff = market_module._daily_table_staleness_cutoffs("price_daily", tuesday, monday)
    assert stale_cutoff == 24.0
    assert critical_cutoff == 48.0


def test_genuinely_stale_data_still_flagged_across_a_weekend():
    """Sanity check: the fix must not silently disable the check - data from the Friday
    before last (over a week stale) must still exceed even the gap-scaled cutoff."""
    week_before_friday = date(2026, 8, 14)
    sunday = date(2026, 8, 23)
    last_friday = date(2026, 8, 21)  # expected_date: the most recent real trading day

    stale_cutoff, _ = market_module._daily_table_staleness_cutoffs("price_daily", sunday, last_friday)
    age_hours = (sunday - week_before_friday).days * 24
    assert age_hours > stale_cutoff
