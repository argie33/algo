"""Regression tests for algo/risk/unified_risk_monitor.py - the consolidated intraday
risk monitor that replaces 4 previously uncoordinated mechanisms (circuit-breaker Lambda,
execution-monitor Lambda, intraday_risk_monitor's alert-only mode, stop_loss_guardian's
own schedule). See that module's docstring for the full 2026-09-06 architecture rationale.

Focus of these tests: the escalation ladder (_apply_risk_verdict) is the genuinely new,
safety-critical logic - a breach must be re-confirmed on CONSECUTIVE_BREACH_RUNS_TO_HALT
consecutive runs before halting, and CONSECUTIVE_BREACH_RUNS_TO_ACT before an automated
reduce/flatten. Getting the debounce math wrong in either direction is real-money-critical:
too eager -> false-positive trades; too lax -> a genuine breach never gets acted on.
"""

from unittest.mock import MagicMock, patch

from algo.risk import unified_risk_monitor as urm


class _FakeRiskStateTable:
    """In-memory stand-in for the algo_risk_monitor_state table - persists across calls
    within one test, exactly like the real table persists across Lambda invocations."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def select(self, check_key):
        row = self.rows.get(check_key)
        if row is None:
            return None
        return (row["consecutive_breach_count"], row["last_breached"], row["last_action"])

    def upsert(self, check_key, count, breached, action, result_json):
        self.rows[check_key] = {
            "consecutive_breach_count": count,
            "last_breached": breached,
            "last_action": action,
        }


class _FakeCursor:
    def __init__(self, table: _FakeRiskStateTable, trade_rows=None):
        self._table = table
        self._trade_rows = trade_rows or []
        self._last_select_was_state = False
        self.executed_queries: list[tuple[str, object]] = []

    def execute(self, query, params=None):
        self.executed_queries.append((query.strip(), params))
        q = query.strip()
        if "FROM algo_risk_monitor_state" in q:
            self._last_select_was_state = True
            self._select_key = params[0]
        elif "INSERT INTO algo_risk_monitor_state" in q:
            check_key, count, breached, action, result_json = params[0], params[1], params[2], params[3], params[4]
            self._table.upsert(check_key, count, breached, action, result_json)
        elif "FROM algo_trades" in q:
            self._last_select_was_state = False
        else:
            self._last_select_was_state = False

    def fetchone(self):
        if self._last_select_was_state:
            return self._table.select(self._select_key)
        return None

    def fetchall(self):
        return self._trade_rows


class _FakeDbContext:
    def __init__(self, table: _FakeRiskStateTable, trade_rows=None):
        self._cur = _FakeCursor(table, trade_rows)

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):
        return False


def _patched_db(table, trade_rows=None):
    return patch("algo.risk.unified_risk_monitor.DatabaseContext", return_value=_FakeDbContext(table, trade_rows))


def _patched_db_capturing_context(table, trade_rows=None):
    """Like _patched_db, but also returns the underlying _FakeDbContext so a test can
    inspect exactly what SQL was executed (e.g. asserting the advisory lock was taken)."""
    db_context = _FakeDbContext(table, trade_rows)
    return patch("algo.risk.unified_risk_monitor.DatabaseContext", return_value=db_context), db_context


class TestEscalationLadder:
    def test_single_breach_run_only_warns_no_halt(self):
        table = _FakeRiskStateTable()
        alerts = MagicMock()
        with _patched_db(table), patch("algo.risk.unified_risk_monitor._get_halt_manager") as mock_get_mgr:
            verdict = urm._apply_risk_verdict(
                {}, alerts, "variance", True, "portfolio variance 20% exceeds 15%", {"variance": 0.20}
            )
        assert verdict["action"] == "warn"
        assert verdict["streak"] == 1
        mock_get_mgr.assert_not_called()
        alerts.send_position_alert.assert_called_once()
        assert alerts.send_position_alert.call_args[0][1] == "RISK_BREACH_OBSERVED"

    def test_second_consecutive_breach_halts(self):
        table = _FakeRiskStateTable()
        table.upsert("variance", 1, True, "warn", "{}")
        alerts = MagicMock()
        mock_manager = MagicMock()
        with _patched_db(table), patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager):
            verdict = urm._apply_risk_verdict(
                {}, alerts, "variance", True, "portfolio variance 20% exceeds 15%", {"variance": 0.20}
            )
        assert verdict["action"] == "halt"
        assert verdict["streak"] == 2
        mock_manager.set_halt_flag.assert_called_once()
        call_kwargs = mock_manager.set_halt_flag.call_args
        assert call_kwargs.kwargs["triggered_by"] == "unified_risk_monitor"
        alert_types = [c[0][1] for c in alerts.send_position_alert.call_args_list]
        assert "RISK_BREACH_HALTED" in alert_types

    def test_breach_persisting_past_halt_escalates_to_reduce_or_flatten(self):
        table = _FakeRiskStateTable()
        table.upsert("variance", 2, True, "halt", "{}")
        alerts = MagicMock()
        mock_manager = MagicMock()
        with (
            _patched_db(table),
            patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager),
            patch(
                "algo.risk.unified_risk_monitor._act_reduce_or_flatten", return_value={"closed": ["AAPL"], "failed": []}
            ) as mock_act,
        ):
            verdict = urm._apply_risk_verdict(
                {}, alerts, "variance", True, "portfolio variance 20% exceeds 15%", {"variance": 0.20}
            )
        assert verdict["action"] == "reduce_or_flatten"
        assert verdict["streak"] == 3
        mock_manager.set_halt_flag.assert_called_once()  # halt still (re-)asserted every confirmed run
        mock_act.assert_called_once()

    def test_action_failure_sends_distinct_escalation_alert(self):
        """Regression for the adversarial-review finding: a position that can't be closed
        must not just repeat the same routine alert forever - a distinct, filterable
        'manual intervention required' alert must fire whenever the action reports a
        failure, on top of (not instead of) the routine RISK_BREACH_HALTED alert."""
        table = _FakeRiskStateTable()
        table.upsert("variance", 2, True, "halt", "{}")
        alerts = MagicMock()
        mock_manager = MagicMock()
        with (
            _patched_db(table),
            patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager),
            patch(
                "algo.risk.unified_risk_monitor._act_reduce_or_flatten",
                return_value={"closed": [], "failed": [("DELISTED", "position cannot be closed")]},
            ),
        ):
            urm._apply_risk_verdict(
                {}, alerts, "variance", True, "portfolio variance 20% exceeds 15%", {"variance": 0.20}
            )
        alert_types = [c[0][1] for c in alerts.send_position_alert.call_args_list]
        assert "RISK_BREACH_ACTION_FAILED_MANUAL_INTERVENTION_REQUIRED" in alert_types

    def test_action_success_does_not_send_failure_escalation_alert(self):
        table = _FakeRiskStateTable()
        table.upsert("variance", 2, True, "halt", "{}")
        alerts = MagicMock()
        mock_manager = MagicMock()
        with (
            _patched_db(table),
            patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager),
            patch(
                "algo.risk.unified_risk_monitor._act_reduce_or_flatten",
                return_value={"closed": ["AAPL"], "failed": []},
            ),
        ):
            urm._apply_risk_verdict(
                {}, alerts, "variance", True, "portfolio variance 20% exceeds 15%", {"variance": 0.20}
            )
        alert_types = [c[0][1] for c in alerts.send_position_alert.call_args_list]
        assert "RISK_BREACH_ACTION_FAILED_MANUAL_INTERVENTION_REQUIRED" not in alert_types

    def test_non_breach_resets_streak_to_zero(self):
        table = _FakeRiskStateTable()
        table.upsert("variance", 2, True, "halt", "{}")
        alerts = MagicMock()
        with _patched_db(table), patch("algo.risk.unified_risk_monitor._maybe_clear_halt") as mock_clear:
            verdict = urm._apply_risk_verdict(
                {}, alerts, "variance", False, "variance within limits", {"variance": 0.02}
            )
        assert verdict["action"] == "none"
        assert verdict["streak"] == 0
        mock_clear.assert_called_once()
        assert table.rows["variance"]["consecutive_breach_count"] == 0

    def test_clean_run_clears_own_halt_but_not_unrelated_origin(self):
        alerts = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_halt_triggered_by.return_value = "manual_operator"
        mock_manager.clear_halt_flag.return_value = False
        with patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager):
            urm._maybe_clear_halt(alerts, "variance", "variance within limits")
        mock_manager.clear_halt_flag.assert_called_once()
        call_kwargs = mock_manager.clear_halt_flag.call_args
        assert call_kwargs.kwargs["allowed_triggers"] == frozenset({"unified_risk_monitor", None})
        alerts.send_position_alert.assert_not_called()  # refused clear = no "resolved" alert

    def test_intermittent_breach_never_reaches_two_consecutive_does_not_halt(self):
        # Breach, then a clean run (resets to 0), then breach again - streak must never
        # exceed 1 in this pattern, so halt must never fire despite 2 total breaches.
        table = _FakeRiskStateTable()
        alerts = MagicMock()
        mock_manager = MagicMock()
        mock_manager.clear_halt_flag.return_value = True
        with _patched_db(table), patch("algo.risk.unified_risk_monitor._get_halt_manager", return_value=mock_manager):
            v1 = urm._apply_risk_verdict({}, alerts, "variance", True, "breach", {})
            v2 = urm._apply_risk_verdict({}, alerts, "variance", False, "clean", {})
            v3 = urm._apply_risk_verdict({}, alerts, "variance", True, "breach again", {})
        assert v1["action"] == "warn"
        assert v2["action"] == "none"
        assert v3["action"] == "warn"
        # v2's non-breach legitimately checks/clears any pre-existing halt (harmless no-op
        # here since nothing halted yet) - the real assertion is that set_halt_flag itself
        # is never called across this whole intermittent (never 2-consecutive) sequence.
        mock_manager.set_halt_flag.assert_not_called()


class TestConcurrentInvocationSafety:
    def test_advisory_lock_taken_before_state_read_and_write(self):
        """Regression for the 2026-09-06 adversarial-review finding: mode=unified_risk_
        monitor is dispatched directly in lambda_handler, bypassing orchestrator.py's own
        run lock entirely - two overlapping 5-minute invocations racing _load_state's
        plain SELECT against _save_state's INSERT would be a lost-update. A transaction-
        scoped Postgres advisory lock keyed by check_key must be acquired first, so a
        second concurrent run for the SAME check blocks until the first commits.
        """
        table = _FakeRiskStateTable()
        alerts = MagicMock()
        patcher, db_context = _patched_db_capturing_context(table)
        with patcher, patch("algo.risk.unified_risk_monitor._get_halt_manager"):
            urm._apply_risk_verdict({}, alerts, "variance", True, "breach", {})

        queries = [q for q, _params in db_context._cur.executed_queries]
        lock_idx = next(i for i, q in enumerate(queries) if "pg_advisory_xact_lock" in q)
        select_idx = next(i for i, q in enumerate(queries) if "FROM algo_risk_monitor_state" in q)
        insert_idx = next(i for i, q in enumerate(queries) if "INSERT INTO algo_risk_monitor_state" in q)
        assert lock_idx < select_idx < insert_idx

        lock_params = db_context._cur.executed_queries[lock_idx][1]
        assert lock_params == ("variance",)


class TestResolveOffendingSymbols:
    def test_beta_breach_with_missing_beta_symbol_identifies_it(self):
        risk_result = {"beta_breach": True, "concentration_breach": False, "symbols_missing_beta": ["UNKNOWN"]}
        assert urm._resolve_offending_symbols(risk_result) == ["UNKNOWN"]

    def test_beta_breach_with_no_missing_beta_symbols_returns_none(self):
        risk_result = {"beta_breach": True, "concentration_breach": False, "symbols_missing_beta": []}
        assert urm._resolve_offending_symbols(risk_result) is None

    def test_concentration_breach_alone_returns_none(self):
        risk_result = {"beta_breach": False, "concentration_breach": True, "symbols_missing_beta": []}
        assert urm._resolve_offending_symbols(risk_result) is None


class TestActReduceOrFlatten:
    def test_targets_only_offending_symbols_when_identified(self):
        table = _FakeRiskStateTable()
        trade_rows = [(101, "BAD")]
        alerts = MagicMock()
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}
        with (
            _patched_db(table, trade_rows=trade_rows),
            patch("algo.trading.executor.TradeExecutor", return_value=mock_executor),
            patch("algo.risk.unified_risk_monitor.fetch_live_quote", return_value=123.45),
        ):
            result = urm._act_reduce_or_flatten({"execution_mode": "paper"}, alerts, "beta", "beta breach", ["BAD"])
        assert result["closed"] == ["BAD"]
        mock_executor.exit_trade.assert_called_once()
        assert mock_executor.exit_trade.call_args.kwargs["trade_id"] == 101
        alerts.send_position_alert.assert_called_once()
        assert alerts.send_position_alert.call_args[0][1] == "RISK_BREACH_AUTO_REDUCED"

    def test_falls_back_to_full_flatten_when_no_offending_symbols(self):
        table = _FakeRiskStateTable()
        trade_rows = [(101, "A"), (102, "B")]
        alerts = MagicMock()
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}
        with (
            _patched_db(table, trade_rows=trade_rows),
            patch("algo.trading.executor.TradeExecutor", return_value=mock_executor),
            patch("algo.risk.unified_risk_monitor.fetch_live_quote", return_value=50.0),
        ):
            result = urm._act_reduce_or_flatten(
                {"execution_mode": "paper"}, alerts, "variance", "variance breach", None
            )
        assert set(result["closed"]) == {"A", "B"}
        assert mock_executor.exit_trade.call_count == 2

    def test_quote_failure_for_one_symbol_does_not_block_others(self):
        table = _FakeRiskStateTable()
        trade_rows = [(101, "BADQUOTE"), (102, "GOOD")]
        alerts = MagicMock()
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        def _quote_side_effect(symbol, *a, **k):
            if symbol == "BADQUOTE":
                raise RuntimeError("quote API down")
            return 10.0

        with (
            _patched_db(table, trade_rows=trade_rows),
            patch("algo.trading.executor.TradeExecutor", return_value=mock_executor),
            patch("algo.risk.unified_risk_monitor.fetch_live_quote", side_effect=_quote_side_effect),
        ):
            result = urm._act_reduce_or_flatten(
                {"execution_mode": "paper"}, alerts, "variance", "variance breach", None
            )
        assert result["closed"] == ["GOOD"]
        assert len(result["failed"]) == 1
        assert result["failed"][0][0] == "BADQUOTE"


class TestCheckUnifiedRiskOrchestration:
    def test_runs_all_checks_and_aggregates_results(self):
        config = {
            "execution_mode": "paper",
            "portfolio_variance_threshold": 0.15,
            "max_portfolio_beta": 2.0,
            "max_top5_concentration_pct": 30.0,
        }
        alerts = MagicMock()
        with (
            patch("algo.risk.unified_risk_monitor._check_portfolio_variance", return_value={"variance": 0.02}),
            patch(
                "algo.risk.unified_risk_monitor.check_intraday_risk",
                return_value={
                    "beta_breach": False,
                    "concentration_breach": False,
                    "portfolio_beta": 1.0,
                    "top5_concentration_pct": 10.0,
                    "symbols_missing_beta": [],
                },
            ),
            patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step"),
            patch(
                "algo.risk.unified_risk_monitor._check_live_intraday_spy_move",
                return_value={"live_price": 500.0, "prior_close": 505.0, "intraday_change_pct": -0.99},
            ),
            patch(
                "algo.risk.unified_risk_monitor._apply_risk_verdict", return_value={"action": "none", "streak": 0}
            ) as mock_verdict,
        ):
            result = urm.check_unified_risk(config, alerts=alerts)
        assert set(result["checks"].keys()) == {
            "variance",
            "beta",
            "concentration",
            "stop_loss_protection",
            "market_health",
        }
        # variance + beta + concentration + market_health each call the ladder once = 4
        assert mock_verdict.call_count == 4

    def test_variance_check_infrastructure_failure_still_calls_ladder_as_breach(self):
        config = {
            "execution_mode": "paper",
            "portfolio_variance_threshold": 0.15,
            "max_portfolio_beta": 2.0,
            "max_top5_concentration_pct": 30.0,
        }
        alerts = MagicMock()
        with (
            patch("algo.risk.unified_risk_monitor._check_portfolio_variance", side_effect=RuntimeError("db down")),
            patch(
                "algo.risk.unified_risk_monitor.check_intraday_risk",
                return_value={
                    "beta_breach": False,
                    "concentration_breach": False,
                    "symbols_missing_beta": [],
                },
            ),
            patch("algo.orchestrator.phase9_reconciliation._verify_open_position_stop_loss_protection_step"),
            patch("algo.risk.unified_risk_monitor._check_live_intraday_spy_move", side_effect=RuntimeError("no quote")),
            patch(
                "algo.risk.unified_risk_monitor._apply_risk_verdict", return_value={"action": "warn", "streak": 1}
            ) as mock_verdict,
        ):
            result = urm.check_unified_risk(config, alerts=alerts)
        # variance and market_health both failed -> both must still be treated as a
        # confirmed breach input to the ladder (fail-closed: infra failure != safe)
        variance_call = [c for c in mock_verdict.call_args_list if c[0][2] == "variance"][0]
        assert variance_call[0][3] is True  # breached=True on infra failure
        assert "error" in result["checks"]["variance"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
