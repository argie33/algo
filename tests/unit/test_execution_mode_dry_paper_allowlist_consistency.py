"""Regression test for the 2026-08-11 fix: two more instances of the same bug class as
executor.py's credential-fetch fix (c86981a83) and phase2_circuit_breakers.py's leniency
fix (480c4fffb) - "paper" and "dry" are both LOCAL-only execution modes that never touch a
real broker, but several checks used a bare `!= "paper"` blocklist instead of the
`not in ("paper", "dry")` allowlist, so "dry" mode incorrectly fell through to live-mode-only
logic:

1. reconciliation.py's cash-is-None check: live mode requires real broker cash and correctly
   raises when it's missing, but paper mode can compute cash from portfolio - positions. Dry
   mode was missing from that exemption, so a None cash value in dry mode incorrectly
   triggered the fatal "Live mode: Broker cash is missing" halt.
2. phase8_entry_execution.py's pending-order guard: paper mode has no real pending orders to
   check (simulation only), and dry mode is equally simulation-only, but only paper was
   exempted from this DB query.

Full behavioral mocking of run_daily_reconciliation()/Phase 8's run() (both large, complex
functions with many preconditions) isn't practical for a narrow single-line-condition
regression - uses this file's existing source-inspection pattern instead (see
tests/unit/test_panel_status_dry_run_exit_not_halted.py for the same approach applied
elsewhere in this codebase).
"""

import inspect

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
