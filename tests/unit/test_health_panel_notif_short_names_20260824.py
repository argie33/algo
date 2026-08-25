#!/usr/bin/env python3
"""Regression test for dashboard/panels/health.py's NOTIF_SHORT_NAMES - continuing the
dashboard test-coverage sweep after finding the same bug class in trades.py's
_resolve_exit_reason (see [[trades_panel_exit_reason_52pct_unresolved_fixed_20260824]]).

Live-measured against all 2472 real notification titles in the local dev DB: 71.8% (1774)
didn't match any key and fell through to raw_t[:24] truncation. Most of that is harmless
(ENTRY: SYMBOL / EXIT ORDER FAILED: SYMBOL titles stay fully informative even truncated), but a
real subset of the most CRITICAL alerts were getting garbled past the point of meaning -
"[ALGO ALERT] HALT_FLAG_ACTIVE: PORTFOLIO" (trading halted right now) truncated to
"[ALGO ALERT] HALT_FLAG_A" with no indication anything is wrong, "Reconciliation Initialization
Failed" truncated to "Reconciliation Initializ" (doesn't even convey "Failed"), "Phase 9: Exit
recording failed - permanent audit gap risk" truncated to "Phase 9: Exit recording " (reads as
a routine status line, not a compliance-audit-gap alert). Root cause: those titles use
SNAKE_CASE, not the space-separated phrasing the pre-existing keys expected.
"""

from dashboard.panels.health import NOTIF_SHORT_NAMES


def _resolve(raw_title: str) -> str | None:
    """Mirrors the resolution logic used at each NOTIF_SHORT_NAMES call site in health.py."""
    tl = raw_title.lower()
    return next((v for k, v in NOTIF_SHORT_NAMES.items() if k in tl), None)


class TestNotifShortNamesCriticalAlerts:
    """Each case is a REAL notification title from the local dev DB whose 24-char truncated
    fallback previously lost the alert's actual meaning (e.g. "Failed"/"HALT" itself)."""

    def test_halt_flag_active_resolves(self):
        assert _resolve("[ALGO ALERT] HALT_FLAG_ACTIVE: PORTFOLIO") == "HALTED NOW"

    def test_account_circuit_breaker_resolves(self):
        assert _resolve("[ALGO ALERT] ACCOUNT_CIRCUIT_BREAKER: PORTFOLIO") == "Halted: CB"

    def test_exit_check_failures_resolves(self):
        assert _resolve("[ALGO ALERT] EXIT_CHECK_FAILURES: PORTFOLIO") == "ExitCheck Fail"

    def test_reconciliation_initialization_failed_resolves(self):
        assert _resolve("Reconciliation Initialization Failed") == "ReconInit Fail"
        assert _resolve("Reconciliation Initialization Failed - Production Blocker") == "ReconInit Fail"

    def test_exit_recording_failed_resolves(self):
        assert _resolve("Phase 9: Exit recording failed - permanent audit gap risk") == "AuditGap!"

    def test_quantity_mismatch_resolves(self):
        assert _resolve("CRITICAL: Quantity Mismatch") == "QtyMismatch"

    def test_position_drift_resolves(self):
        assert _resolve("CRITICAL: Position Drift Detected") == "PosDrift"


class TestNotifShortNamesPreExisting:
    """Confirm the pre-existing entries still work (space-separated phrasing)."""

    def test_trading_halted_by_circuit(self):
        assert _resolve("Trading Halted by Circuit Breaker") == "Halted: CB"

    def test_circuit_breaker_check_failed(self):
        assert _resolve("CIRCUIT BREAKER CHECK FAILED") == "CB fired"


class TestNotifShortNamesUnmatchedFallsBackGracefully:
    def test_entry_notification_returns_none_but_stays_short_when_raw(self):
        """ENTRY: SYMBOL titles intentionally have no dict entry - already short/informative
        even in the raw_t[:24] fallback each call site uses, so no lost meaning."""
        assert _resolve("ENTRY: NVDA") is None
