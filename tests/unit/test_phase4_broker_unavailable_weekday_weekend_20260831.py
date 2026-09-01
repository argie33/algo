"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix in
phase4_reconciliation.py's broker-unavailable/401/unauthorized branch: the code's own comment
already specified "Broker authentication/availability error during market hours = critical
failure. Only gracefully skip on weekends/market-closed, otherwise fail-fast" - but the code
below it never actually implemented that distinction, treating every broker-unavailable error
identically regardless of whether run_date was even a trading day.

Fixed to check MarketCalendar.is_trading_day(run_date): a non-trading-day broker error now
returns a non-halting "degraded" status (no real reconciliation need - market is closed), while
a trading-day broker error correctly fails fast with status="error"/halted=True (matching the
same-session fix to the ValueError/generic-Exception branches, see
tests/unit/test_phase4_error_paths_set_halted_true_20260831.py).
"""

from datetime import date
from unittest.mock import MagicMock, patch


def _run_with_reconciliation_result(run_date, reconciliation_result):
    from algo.orchestrator.phase4_reconciliation import run

    mock_config = MagicMock()
    mock_config.get.return_value = "auto"

    mock_recon = MagicMock()
    mock_recon.run_daily_reconciliation.return_value = reconciliation_result
    mock_recon.check_partial_fills.return_value = {"mismatches": 0, "no_broker": False}

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with (
        patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
        patch("utils.db.DatabaseContext", return_value=mock_ctx),
    ):
        return run(
            config=mock_config,
            run_date=run_date,
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=MagicMock(),
        )


class TestPhase4BrokerUnavailableWeekdayWeekend:
    def test_broker_unavailable_on_trading_day_fails_fast(self):
        """2026-08-10 is a Monday (confirmed via datetime.strftime) - a real trading day.
        A broker-unavailable error here must fail fast: status='error', halted=True."""
        result = _run_with_reconciliation_result(
            date(2026, 8, 10),
            {"success": False, "reason": "Broker unavailable: 401 unauthorized"},
        )

        assert result.status == "error"
        assert result.halted is True

    def test_broker_unavailable_on_weekend_gracefully_skips(self):
        """2026-08-08 is a Saturday - not a trading day. The same broker-unavailable error
        here must NOT be treated as a failure (no reconciliation need - market is closed):
        a non-error status and halted=False."""
        result = _run_with_reconciliation_result(
            date(2026, 8, 8),
            {"success": False, "reason": "Broker unavailable: 401 unauthorized"},
        )

        assert result.status != "error", (
            f"Expected a non-error status on a non-trading day, got {result.status!r} - "
            f"this is the exact weekday/weekend distinction the code's own comment specified "
            f"but never implemented before this fix"
        )
        assert result.halted is False

    def test_broker_unavailable_on_sunday_gracefully_skips(self):
        """Companion sanity check for the other weekend day."""
        result = _run_with_reconciliation_result(
            date(2026, 8, 9),
            {"success": False, "reason": "Broker unavailable: connection unavailable"},
        )

        assert result.status != "error"
        assert result.halted is False
