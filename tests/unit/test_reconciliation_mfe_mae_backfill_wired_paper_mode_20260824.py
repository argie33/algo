"""Regression test: the paper-mode (self.broker is None) branch of run_daily_reconciliation
must also call backfill_all_trade_metrics(), not just the execution_mode=="auto" branch.

Bug found 2026-08-24 (same session as, and a follow-up to,
test_reconciliation_mfe_mae_backfill_wired.py's fix): that fix wired
backfill_all_trade_metrics() into run_daily_reconciliation(), but only into the code reached
past the `if self.broker is None: ... return result` early-return this method starts with.
Every paper/dry/local-mode run - which is 100% of what local dev, and this system's entire
pre-live-money verification phase, actually executes - takes that early-return branch and
never reaches the auto-mode-only call. Live-confirmed: all 96 closed trades in the local DB
had NULL mfe_pct/mae_pct despite the "wired" fix already being on main, because reconciliation
had genuinely run (via Phase 4/9) many times since - just always through this branch.

Exercising the paper-mode branch end-to-end requires mocking DatabaseContext across several
queries; source-inspection (same spirit as test_reconciliation_mfe_mae_backfill_wired.py) is
enough to pin that the call exists inside the `if self.broker is None:` branch specifically,
not just somewhere in the method.
"""

import inspect

from algo.infrastructure.reconciliation import DailyReconciliation


def test_paper_mode_branch_calls_backfill_all_trade_metrics() -> None:
    src = inspect.getsource(DailyReconciliation.run_daily_reconciliation)

    broker_none_start = src.index("if self.broker is None:")
    # The paper-mode branch ends at its own `return result` - the first `return result` after
    # the branch start marks that boundary (checked against the known source ordering below).
    dry_run_check = src.index("if dry_run:")
    assert broker_none_start < dry_run_check, "paper-mode branch must precede the dry_run check"

    paper_mode_branch = src[broker_none_start:dry_run_check]
    assert "backfill_all_trade_metrics(" in paper_mode_branch, (
        "backfill_all_trade_metrics() must be called inside the `if self.broker is None:` "
        "(paper/local mode) branch too - it was previously only wired into the "
        "execution_mode=='auto' branch further down, so paper-mode runs (the default for all "
        "local dev and pre-live verification) never computed mfe_pct/mae_pct at all."
    )
