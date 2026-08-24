"""Regression test: run_daily_reconciliation must actually call backfill_all_trade_metrics().

Bug found 2026-08-24: algo_trades.mfe_pct/mae_pct were permanently NULL for every closed
trade (rendered as "--" in the TUI/API), even though the columns exist (migration 016) and
utils.trade_metrics.update_trade_metrics()/backfill_all_trade_metrics() correctly compute
them from price_daily. The only writer of these columns was never called from any production
code path: executor_exit_handler.py sets exit_r_multiple/trade_duration_days directly via SQL
at trade-close time but never touches mfe_pct/mae_pct, and reconciliation.py's step "1c.
Compute MAE/MFE metrics" only ever READ the columns (AVG(mfe_pct)/AVG(mae_pct) in
ReconciliationAnalytics.compute_closed_trade_metrics) - nothing computed them first, so the
averages were always over all-NULL data.

Fixed by calling backfill_all_trade_metrics(cur) in run_daily_reconciliation before
compute_closed_trade_metrics(cur) is invoked. Exercising run_daily_reconciliation end-to-end
requires mocking a live broker connection and the full reconciliation flow, so this pins the
wiring via source inspection instead, same spirit as
test_sla_monitor_wired_into_overridden_run_loaders.py.
"""

import inspect

from algo.infrastructure import reconciliation
from algo.infrastructure.reconciliation import DailyReconciliation


def test_run_daily_reconciliation_calls_backfill_all_trade_metrics() -> None:
    src = inspect.getsource(DailyReconciliation.run_daily_reconciliation)
    assert "backfill_all_trade_metrics(cur)" in src

    backfill_call = src.index("backfill_all_trade_metrics(cur)")
    compute_call = src.index("self.compute_closed_trade_metrics(cur)")
    assert backfill_call < compute_call, (
        "backfill_all_trade_metrics() must run before compute_closed_trade_metrics() reads "
        "the averages, or it will always average over NULLs"
    )


def test_reconciliation_module_imports_backfill_from_trade_metrics() -> None:
    assert reconciliation.backfill_all_trade_metrics.__module__ == "utils.trade_metrics"
