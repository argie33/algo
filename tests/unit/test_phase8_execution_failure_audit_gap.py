"""Regression test: Phase 8 broker-execution failures must leave a queryable audit trail.

algo/orchestrator/phase8_entry_execution.py's _log_signal_rejection() persists skipped/
rejected signals to algo_signal_rejections, but a run this morning
(LOCAL-MORNING-20260727-103249-635466) reported "1 trades executed, 2 failed" via
logger.error() only - no row for either failure ever reached algo_signal_rejections,
because the audit call for the execution_failed/execution_error/processing_error stages
didn't exist yet at that point in the day (added later the same day, commit 4df7d36ed).
Without it, a real broker-execution failure (rejected order, API error) was undiagnosable
after the process exited - the only record was a log line, not a queryable row. This test
locks in that the fix actually persists the failure, so the gap can't silently regress.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _log_signal_rejection


def test_policy_rejection_statuses_exclude_genuine_execution_failures():
    """CRITICAL FIX regression: TradeExecutor.execute_trade() returns success=False for two
    fundamentally different reasons - (1) a pre-submission policy check correctly blocked the
    entry before an order was ever attempted (duplicate/pending/reentry-cooldown), or (2) a
    real broker/DB/execution failure. Confirmed live 2026-07-27 (run
    LOCAL-AFTERNOON-20260727-145647-651040): 2 signals correctly rejected by the 5-day
    reentry-reset rule for symbols closed earlier the same session were counted as
    failed_count instead of skipped_count, corrupting success_rate's attempted=executed+failed
    denominator and marking Phase 8 (and the whole run) "degraded" on a day every risk gate
    worked exactly as designed - indistinguishable in the final report from a real broker
    outage. This pins the taxonomy: only pre-attempt policy statuses belong here.
    """
    from algo.orchestrator.phase8_entry_execution import _POLICY_REJECTION_STATUSES

    assert _POLICY_REJECTION_STATUSES == {
        "duplicate",
        "duplicate_signal",
        "duplicate_position",
        "pending_trade_exists",
        "reentry_cooldown",
        "reentry_blocked",
    }
    # Statuses produced by genuine order/DB/execution failures (executor.py's exception
    # handlers) must never be classified as a policy skip.
    genuine_failure_statuses = {
        "order_rejected",
        "order_failed",
        "database_error",
        "trading_error",
        "error",
        "portfolio_value_unavailable",
        "invalid",
    }
    assert _POLICY_REJECTION_STATUSES.isdisjoint(genuine_failure_statuses)


def test_execution_failed_is_persisted_to_signal_rejections_audit_table():
    mock_cur = MagicMock()

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = mock_cur

        _log_signal_rejection(
            "KEX", "execution_failed", "Order rejected (status=rejected)", date(2026, 7, 27), 149.15, 1.5
        )

    # _log_signal_rejection now does 2 writes: the algo_signal_rejections audit-trail INSERT
    # checked here, and a follow-up algo_signals UPDATE (execution_status='rejected') so the
    # dashboard doesn't keep showing a rejected signal as still active.
    assert mock_cur.execute.call_count == 2
    sql, params = mock_cur.execute.call_args_list[0][0]
    assert "algo_signal_rejections" in sql
    assert params == (date(2026, 7, 27), "KEX", "execution_failed", "Order rejected (status=rejected)", 149.15, 1.5)


def test_long_rejection_reason_truncated_not_crashed():
    """CRITICAL FIX regression: algo_signal_rejections.rejection_reason is VARCHAR(200).
    Confirmed live 2026-07-27: a wrapped/re-wrapped pre-trade ValueError (a missing-config
    message re-raised through two layers) reached 320 chars, and the INSERT itself failed
    with StringDataRightTruncation - which the except block then re-raised as a fresh
    RuntimeError, crashing Phase 8 for every remaining symbol over an audit-logging
    formatting issue, not a real trading problem. Must truncate defensively instead."""
    mock_cur = MagicMock()
    long_reason = "X" * 250

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = mock_cur

        _log_signal_rejection("OHI", "processing_error", long_reason, date(2026, 7, 27))

    # See test_execution_failed_is_persisted_to_signal_rejections_audit_table: 2 writes now.
    assert mock_cur.execute.call_count == 2
    _, params = mock_cur.execute.call_args_list[0][0]
    persisted_reason = params[3]
    assert len(persisted_reason) == 200
    assert persisted_reason.endswith("...")


def test_sizer_blocked_and_liquidity_skips_are_persisted_to_audit_table():
    """CRITICAL FIX regression: the sizer_blocked (both the sizing["status"] != "ok" branch and
    the shares < 1 branch) and liquidity skip paths in run() incremented skipped_count and
    logged, but never called _log_signal_rejection() - unlike every other skip reason in the
    same loop (pretrade_check, duplicate_position, quality_gate, stop_too_tight, ...). Confirmed
    live 2026-07-27 (run LOCAL-AFTERNOON-20260727-154015-391286): with all 17 position slots
    full, all 16 qualified signals hit "sizer blocked - 17 open positions >= 17 hard limit" and
    algo_signal_rejections showed zero new rows for any of them - a routine, expected "at
    capacity" run was indistinguishable from a silent audit-logging failure. This is a source
    check (not a mocked run() call - run() has ~15 injected dependencies with no existing test
    harness) pinning that each skip branch's logger call is paired with a
    _log_signal_rejection(...) call using the given rejection_stage, so the pairing can't
    silently regress even though the assertion doesn't execute run() itself.
    """
    import inspect

    from algo.orchestrator import phase8_entry_execution as p8

    source = inspect.getsource(p8.run)

    liquidity_branch = source.split('if not liq_ok:')[1].split("continue", 1)[0]
    assert '_log_signal_rejection(' in liquidity_branch
    assert '"liquidity"' in liquidity_branch

    sizer_status_branch = source.split('if sizing["status"] != "ok":')[1].split("continue", 1)[0]
    assert '_log_signal_rejection(' in sizer_status_branch
    assert '"sizer_blocked"' in sizer_status_branch

    sizer_shares_branch = source.split('elif sizing["shares"] < 1:')[1].split("continue", 1)[0]
    assert '_log_signal_rejection(' in sizer_shares_branch
    assert '"sizer_blocked"' in sizer_shares_branch


def test_audit_failure_itself_raises_rather_than_silently_dropping():
    """If the audit insert itself fails, the caller must find out (raise), not swallow it -
    a silently-failing audit trail is worse than no audit trail (false confidence)."""
    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.side_effect = RuntimeError("connection lost")

        try:
            _log_signal_rejection("KEX", "execution_failed", "boom", date(2026, 7, 27))
            raised = False
        except RuntimeError:
            raised = True

    assert raised
