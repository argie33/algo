"""Regression test for two more instances of the 2026-08-11 "dry mode missed" bug class
(see tests/unit/test_execution_mode_dry_paper_allowlist_consistency.py for the main sweep):

1. AlpacaSyncManager._sync_alpaca_positions_impl(): its own docstring said credential
   failures should be handled gracefully in "paper/review mode", but the check only ever
   tested `== "paper"` - neither "review" (contradicting its own docstring) nor "dry" (this
   system's default outside-market-hours mode) were actually included, so both fell through
   to the fail-hard branch and crashed position sync whenever real Alpaca credentials were
   unavailable.
2. DailyReconciliation.audit_stale_estimated_prices(): paper mode is skipped because no real
   broker fills ever happen there, but "dry" mode is equally broker-free and wasn't
   exempted, so it could raise a false ALERT/CRITICAL for exit prices that will never
   reconcile in dry mode either.

Both are small single-line-condition checks inside large, many-precondition functions -
uses source-inspection instead of full behavioral mocking, same pattern as
tests/unit/test_panel_status_dry_run_exit_not_halted.py.
"""

import inspect

from algo.infrastructure import alpaca_sync_manager as alpaca_sync_manager_module
from algo.infrastructure import reconciliation as reconciliation_module


class TestAlpacaSyncAndReconciliationDryModeGaps:
    def test_alpaca_sync_credential_failure_exempts_dry_and_review_mode(self):
        source = inspect.getsource(alpaca_sync_manager_module.AlpacaSyncManager._sync_alpaca_positions_impl)
        assert 'in ("paper", "dry", "review")' in source, (
            "credential-failure graceful-degradation must cover paper, dry, AND review mode "
            "(the docstring already promised review; dry was never added) - otherwise dry/review "
            "mode crashes position sync whenever real Alpaca credentials are unavailable"
        )

    def test_reconciliation_stale_estimated_price_audit_exempts_dry_mode(self):
        source = inspect.getsource(reconciliation_module.DailyReconciliation.audit_stale_estimated_prices)
        assert 'in ("paper", "dry")' in source, (
            "the stale-estimated-price audit must skip both paper AND dry mode - neither ever "
            'has real broker fills, so a bare `== "paper"` here incorrectly audited dry mode '
            "and could raise a false ALERT/CRITICAL"
        )
