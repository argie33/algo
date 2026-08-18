"""Regression test: Phase 8's market-open exclusion window must honor
`market_open_exclusion_minutes`/`market_open_exclusion_enabled`, not a hardcoded,
always-on 60-minute cutoff.

Previously there were TWO overlapping guards:
  1. A phase-level guard (Session 32), gated by `market_open_exclusion_enabled`, but
     hardcoded to `dt_time(10, 30)` regardless of `market_open_exclusion_minutes`.
  2. A per-symbol guard inside the trade loop (Session 27+31), hardcoded to the same
     10:30 AM cutoff, but NOT gated by `market_open_exclusion_enabled` at all - so
     disabling the config flag had zero effect, entries were still silently dropped
     with reason "early_market_open_exclusion" until 10:30 AM regardless.

Fixed by making the phase-level guard compute its cutoff from
`market_open_exclusion_minutes`, and removing the redundant, ungated per-symbol guard
so the config flag is now the single source of truth end-to-end.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import run


def _kwargs(exclusion_enabled, exclusion_minutes, run_date=date(2026, 8, 18)):
    return {
        "config": {
            "execution_mode": "paper",
            "alpaca_paper_trading": True,
            "market_open_exclusion_enabled": exclusion_enabled,
            "market_open_exclusion_minutes": exclusion_minutes,
        },
        "run_date": run_date,
        "dry_run": True,
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
    }


def _run_at(now_time, exclusion_enabled, exclusion_minutes):
    kwargs = _kwargs(exclusion_enabled, exclusion_minutes)
    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(now_time.year, now_time.month, now_time.day, now_time.hour, now_time.minute)
        mock_dt.combine = datetime.combine
        return run(**kwargs)


def test_short_exclusion_window_blocks_before_its_own_cutoff():
    """15-minute window: 9:40 AM (10 min after open) must still be blocked."""
    result = _run_at(datetime(2026, 8, 18, 9, 40), exclusion_enabled=True, exclusion_minutes=15)

    assert result.status == "blocked"
    assert "market-open exclusion" in result.error.lower()
    assert "09:45" in result.error


def test_short_exclusion_window_allows_entries_after_its_cutoff():
    """15-minute window: 9:50 AM (20 min after open) must NOT be blocked by this guard -
    the old hardcoded 60-minute cutoff would have wrongly blocked this."""
    result = _run_at(datetime(2026, 8, 18, 9, 50), exclusion_enabled=True, exclusion_minutes=15)

    assert not (result.status == "blocked" and "market-open exclusion" in (result.error or "").lower())


def test_longer_exclusion_window_blocks_past_the_old_hardcoded_cutoff():
    """90-minute window: 10:45 AM (75 min after open) must still be blocked -
    the old hardcoded 60-minute cutoff would have wrongly allowed this through."""
    result = _run_at(datetime(2026, 8, 18, 10, 45), exclusion_enabled=True, exclusion_minutes=90)

    assert result.status == "blocked"
    assert "market-open exclusion" in result.error.lower()
    assert "11:00" in result.error


def test_disabled_flag_allows_entries_before_the_old_hardcoded_cutoff():
    """market_open_exclusion_enabled=False must fully disable the exclusion, including
    the old redundant per-symbol guard that used to ignore this flag entirely and keep
    blocking everything before 10:30 AM regardless."""
    result = _run_at(datetime(2026, 8, 18, 9, 35), exclusion_enabled=False, exclusion_minutes=60)

    assert not (result.status == "blocked" and "market-open exclusion" in (result.error or "").lower())
