"""Regression test for the 2026-08-11 fix: multiple instances of the same bug class as
executor.py's credential-fetch fix (c86981a83) and phase2_circuit_breakers.py's leniency
fix (480c4fffb) - "paper" and "dry" are both LOCAL-only execution modes that never touch a
real broker, but several checks used a bare `!= "paper"` blocklist (or, in the market_events/
reconciliation cash-compute cases below, the positive-check mirror image `== "paper"`
missing "dry" from the allowlist) instead of `("paper", "dry")`:

1. reconciliation.py's cash-is-None check: live mode requires real broker cash and correctly
   raises when it's missing, but paper mode can compute cash from portfolio - positions. Dry
   mode was missing from that exemption, so a None cash value in dry mode incorrectly
   triggered the fatal "Live mode: Broker cash is missing" halt.
2. phase8_entry_execution.py's pending-order guard: paper mode has no real pending orders to
   check (simulation only), and dry mode is equally simulation-only, but only paper was
   exempted from this DB query.
3. market_events.py's MarketEventHandler.__init__: paper mode skips real-Alpaca-credential
   setup (local simulation only) - dry mode is equally broker-free but wasn't exempted, so
   dry mode fell through to requiring real Alpaca credentials, the same class of
   crash-on-init bug already fixed for TradeExecutor.
4. reconciliation.py's cash-compute block: a FOLLOW-UP catch on this same session's fix #1
   above - once dry mode was exempted from the fatal None-cash halt, a None cash in dry mode
   fell through to the `else` (live-mode) branch and called `Decimal(str(None))`, crashing
   with `decimal.InvalidOperation` instead of computing cash the same way paper mode does.

Full behavioral mocking of these large, many-precondition functions isn't practical for a
narrow single-line-condition regression - uses this file's existing source-inspection
pattern instead (see tests/unit/test_panel_status_dry_run_exit_not_halted.py for the same
approach applied elsewhere in this codebase).
"""

import inspect

from algo.infrastructure import market_events as market_events_module
from algo.infrastructure import reconciliation as reconciliation_module
from algo.orchestrator import phase8_entry_execution as phase8_module


class TestExecutionModeDryPaperAllowlistConsistency:
    def test_reconciliation_cash_none_check_exempts_dry_mode(self):
        source = inspect.getsource(reconciliation_module.DailyReconciliation.run_daily_reconciliation)
        assert 'if cash is None and execution_mode not in ("paper", "dry"):' in source, (
            "cash-is-None check must exempt both paper AND dry mode, not just paper - "
            'a bare `!= "paper"` here incorrectly fires the fatal live-mode halt in dry mode'
        )

    def test_phase8_pending_order_guard_exempts_dry_mode(self):
        source = inspect.getsource(phase8_module.run)
        assert 'if execution_mode not in ("paper", "dry"):' in source, (
            "the pending/recent-order DB guard must exempt both paper AND dry mode - "
            'a bare `!= "paper"` here runs a meaningless check in dry mode (which never '
            "places real orders, same as paper)"
        )

    def test_market_events_handler_init_exempts_dry_mode_from_credential_requirement(self):
        source = inspect.getsource(market_events_module.MarketEventHandler.__init__)
        assert 'if execution_mode in ("paper", "dry"):' in source, (
            "MarketEventHandler.__init__ must skip real-Alpaca-credential setup for both "
            'paper AND dry mode - a bare `== "paper"` here made dry mode fall through to '
            "requiring real credentials, crashing dry-run init"
        )

    def test_reconciliation_cash_compute_block_exempts_dry_mode(self):
        source = inspect.getsource(reconciliation_module.DailyReconciliation.run_daily_reconciliation)
        assert 'if execution_mode in ("paper", "dry"):' in source, (
            "the portfolio-minus-positions cash-compute branch must cover both paper AND dry "
            'mode - a bare `== "paper"` here left dry mode falling through to the live-mode '
            "`else` branch, crashing on Decimal(str(None)) when cash is genuinely None"
        )
