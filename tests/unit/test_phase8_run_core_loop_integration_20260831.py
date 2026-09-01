"""Integration harness for Phase 8's `run()` core per-symbol trade loop.

Every existing `tests/unit/test_phase8_*.py` file either unit-tests a helper function in
isolation, or drives `run()` only as far as its early guards (market-hours, signal-freshness,
pending-orders) before returning "blocked" - none of them exercise the ~2,200-line core loop
that actually persists signals, sizes positions, and calls `TradeExecutor.execute_trade()`.
One existing test's own docstring says outright: "run() has ~15 injected dependencies with no
existing test harness" (test_phase8_execution_failure_audit_gap.py), and works around it via
`inspect.getsource()` string-matching instead of actually invoking `run()`.

This file builds that harness: `TradeExecutor`/`PositionSizer`/`LiquidityChecks`/`PreTradeChecks`
are patched to controllable mocks (their own behavior is independently unit-tested elsewhere -
see position_sizer/pretrade_checks/liquidity test files), `DatabaseContext` is backed by a small
fake cursor that answers the handful of read queries the core loop issues, and the market-hours/
signal-freshness/price-freshness guards are bypassed the same way existing shallow tests do, so
each test reaches the actual trade-execution wiring.

Two things found while building this harness were fixed the same session (not by this file):
the dead "CHECKPOINT 3" block that used to sit unreachable after an early `return` in
`phase8_entry_execution.py` was deleted, and `config.get("max_signal_age_hours", default=24)`
was changed to positional (`config.get(..., 24)`) so it no longer silently depends on `config`
always being the real `AlgoConfig` class rather than a plain dict. `_ConfigStub` below predates
that second fix and is kept anyway - it's harmless, and it's the correct thing to reach for again
if a future `config.get(..., default=...)` keyword call is ever reintroduced.
"""

from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _POLICY_REJECTION_STATUSES, run

RUN_DATE = date(2026, 7, 27)
MARKET_HOURS_NOW = datetime.combine(RUN_DATE, time(11, 0))


class _ConfigStub(dict):
    """Mimics algo/infrastructure/config/main.py's real Config.get(key, default=...) signature.

    A plain dict's `.get()` is C-implemented and positional-only - `dict.get("x", default=24)`
    raises `TypeError: dict.get() takes no keyword arguments`. run() used to call
    `config.get("max_signal_age_hours", default=24)` (keyword form), which only worked because
    production `config` is always the real Config class (a real Python method, so keyword args
    bind normally), never a plain dict - that call site has since been changed to positional, so
    a plain dict would work there now too. Kept as a defensive stub in case another keyword-style
    `.get(..., default=...)` call is ever added to the core loop; every existing test's
    `_base_kwargs()` uses a plain dict and never reaches this deep either way.
    """

    def get(self, key, default=None):
        return dict.get(self, key, default)


def _base_config(execution_mode: str = "paper", **overrides: object) -> _ConfigStub:
    cfg = _ConfigStub(
        execution_mode=execution_mode,
        alpaca_paper_trading=True,
        max_positions=20,
        max_total_risk_pct=4.0,
        max_position_size_pct=8.0,
        min_signal_quality_score=60,
        market_open_exclusion_enabled=False,
    )
    cfg.update(overrides)
    return cfg


def _make_signal(symbol: str = "TEST", **overrides: object) -> dict:
    signal = {
        "symbol": symbol,
        "entry_price": 100.0,
        "sma_50": 95.0,
        "atr_14": 5.0,
        "close": 100.0,
        "composite_score": 80.0,
        "rs_percentile": 70.0,
        "signal_quality_score": 85,
        "sector": "Technology",
        "industry": "Software",
        "trend_template_score": 5,
        "base_quality": "high",
        "base_type": "flat_base",
        "signal_date": RUN_DATE.isoformat(),
    }
    signal.update(overrides)
    return signal


class _FakeCursor:
    """Answers the handful of read queries run()'s core loop issues, keyed by SQL content.

    Not a general-purpose SQL mock - just enough to let a qualified trade flow through to
    TradeExecutor.execute_trade() without hitting a real database. Every write (INSERT/UPDATE)
    is accepted silently; only SELECTs need a scripted answer.
    """

    def __init__(self, portfolio_value: float = 100_000.0, open_position_count: int = 0):
        self.portfolio_value = portfolio_value
        self.open_position_count = open_position_count
        self._last_sql = ""
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> None:
        self._last_sql = sql
        self.executed.append((sql, params))

    def fetchone(self):
        sql = self._last_sql.upper()
        if "MAX(DATE) AS LATEST_PRICE_DATE" in sql:
            return (RUN_DATE,)
        if "TOTAL_PORTFOLIO_VALUE" in sql:
            return (self.portfolio_value, RUN_DATE)
        if "COUNT(*)" in sql and "ALGO_POSITIONS" in sql:
            return (self.open_position_count,)
        if "COUNT(*)" in sql and "ALGO_TRADES" in sql:
            return (0,)  # not already entered today
        if "MIN(LOW)" in sql:
            return (None,)  # no 52w support data -> skip support-based stop adjustment
        if "SELECT ID FROM ALGO_TRADES" in sql:
            return None  # no existing open/pending position for this symbol
        if sql.strip() == "SELECT 1":
            return (1,)
        return (0,)

    def fetchall(self):
        return []


class Phase8Deps:
    """Context manager wiring every external dependency run()'s core loop touches.

    `executor_result` configures TradeExecutor.execute_trade()'s return value (or side_effect
    via a callable). Everything else defaults to "this candidate sails through every gate."
    """

    def __init__(self, executor_result, sizer_result=None, liquidity_result=(True, "ok"), pretrade_result=(True, "ok")):
        self.executor_result = executor_result
        self.sizer_result = sizer_result or {"status": "ok", "shares": 10}
        self.liquidity_result = liquidity_result
        self.pretrade_result = pretrade_result
        self._patches = []
        self.mock_trade_executor = None
        self.fake_cursor = _FakeCursor()

    def __enter__(self):
        p = lambda target, **kw: self._start(patch(target, **kw))  # noqa: E731

        mock_dt = p("algo.orchestrator.phase8_entry_execution.datetime")
        mock_dt.now.return_value = MARKET_HOURS_NOW
        mock_dt.combine = datetime.combine
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_dt.strptime = datetime.strptime

        p(
            "algo.risk.stale_signal_circuit_breaker.StaleSignalCircuitBreaker.check_signal_freshness",
            return_value=(True, "fresh"),
        )
        p("algo.orchestrator.phase8_entry_execution._check_price_data_freshness", return_value=(True, "fresh"))
        p(
            "algo.orchestrator.phase8_entry_execution._calculate_current_total_risk_pct",
            return_value=(0.0, 4.0),
        )
        p("algo.orchestrator.phase8_entry_execution._batch_fetch_technical_data", return_value={})
        p("algo.orchestrator.phase8_entry_execution._cleanup_orphaned_positions", return_value=0)
        p(
            "algo.orchestrator.phase8_entry_execution.PreEntryHealthValidator.validate",
            return_value=(True, []),
        )
        p(
            "algo.config.credential_manager.get_credential_manager",
            return_value=MagicMock(get_alpaca_credentials=MagicMock(return_value={"key": "k", "secret": "s"})),
        )

        mock_db_ctx = p("algo.orchestrator.phase8_entry_execution.DatabaseContext")
        mock_db_ctx.return_value.__enter__.return_value = self.fake_cursor
        mock_db_ctx.return_value.__exit__.return_value = False

        mock_sizer_cls = p("algo.orchestrator.phase8_entry_execution.PositionSizer")
        mock_sizer_cls.return_value.calculate_position_size.return_value = self.sizer_result

        mock_liq_cls = p("algo.orchestrator.phase8_entry_execution.LiquidityChecks")
        mock_liq_cls.return_value.run_all.return_value = self.liquidity_result

        mock_pretrade_cls = p("algo.orchestrator.phase8_entry_execution.PreTradeChecks")
        mock_pretrade_cls.return_value.run_all.return_value = self.pretrade_result

        mock_executor_cls = p("algo.orchestrator.phase8_entry_execution.TradeExecutor")
        self.mock_trade_executor = mock_executor_cls.return_value
        if callable(self.executor_result) and not isinstance(self.executor_result, dict):
            self.mock_trade_executor.execute_trade.side_effect = self.executor_result
        else:
            self.mock_trade_executor.execute_trade.return_value = self.executor_result

        p(
            "algo.orchestrator.phase8_entry_execution._persist_signals_to_database",
            return_value=1,
        )

        return self

    def _start(self, patcher):
        mock = patcher.start()
        self._patches.append(patcher)
        return mock

    def __exit__(self, *exc_info):
        for patcher in reversed(self._patches):
            patcher.stop()
        return False


def _run_kwargs(qualified_trades, execution_mode="paper", check_halt_flag=None, **config_overrides):
    return {
        "config": _base_config(execution_mode, **config_overrides),
        "run_date": RUN_DATE,
        "dry_run": False,
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
        "qualified_trades": qualified_trades,
        "exposure_constraints": {
            "halt_new_entries": False,
            "max_new_positions_today": 10,
            "max_concentration_pct": 50.0,
            "regime": "confirmed_uptrend",
        },
        "check_halt_flag": check_halt_flag,
    }


def test_successful_entry_flows_through_to_trade_executor_and_result():
    """A qualified trade that clears every gate reaches TradeExecutor.execute_trade() and the
    PhaseResult reflects one real entry - the core, previously-completely-untested wiring."""
    signal = _make_signal("AAPL")
    executor_result = {
        "success": True,
        "trade_id": 4242,
        "alpaca_order_id": "order-abc",
        "status": "filled",
    }

    with Phase8Deps(executor_result=executor_result) as deps:
        result = run(**_run_kwargs([signal]))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    call_kwargs = deps.mock_trade_executor.execute_trade.call_args.kwargs
    assert call_kwargs["symbol"] == "AAPL"
    assert call_kwargs["shares"] == 10

    assert result.data["entered"] == 1
    assert result.data.get("failed", 0) == 0
    assert result.halted is False


def test_genuine_execution_failure_is_counted_and_audited_not_silently_dropped():
    """A real broker/execution failure (status not in _POLICY_REJECTION_STATUSES) must
    increment failed_count/failed_entries and be persisted via _log_signal_rejection -
    the exact audit-trail gap this file's sibling test (test_phase8_execution_failure_audit_gap.py)
    already regression-tests for _log_signal_rejection() in isolation; this proves the wiring
    from a real run() failure branch actually calls it with the right arguments."""
    signal = _make_signal("BADCO")
    executor_result = {
        "success": False,
        "status": "order_rejected",
        "message": "Insufficient buying power",
    }

    with (
        Phase8Deps(executor_result=executor_result) as deps,
        patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection,
    ):
        result = run(**_run_kwargs([signal]))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert result.data["entered"] == 0

    execution_failed_calls = [c for c in mock_log_rejection.call_args_list if c.args[1] == "execution_failed"]
    assert len(execution_failed_calls) == 1
    assert execution_failed_calls[0].args[0] == "BADCO"
    assert "Insufficient buying power" in execution_failed_calls[0].args[2]


def test_policy_rejection_is_skipped_not_counted_as_a_failure():
    """A pre-attempt policy rejection (duplicate/pending/reentry) must be counted as a skip,
    never a failure - see test_policy_rejection_statuses_exclude_genuine_execution_failures in
    the audit-gap test file for why conflating these corrupts success_rate. Uses the module's
    own _POLICY_REJECTION_STATUSES set rather than a hardcoded string so this stays correct if
    that set is ever edited."""
    policy_status = next(iter(_POLICY_REJECTION_STATUSES))
    signal = _make_signal("DUPCO")
    executor_result = {
        "success": False,
        "status": policy_status,
        "message": f"Rejected: {policy_status}",
    }

    with (
        Phase8Deps(executor_result=executor_result) as deps,
        patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection,
    ):
        result = run(**_run_kwargs([signal]))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert result.data["entered"] == 0

    rejection_calls = [c for c in mock_log_rejection.call_args_list if c.args[0] == "DUPCO"]
    assert len(rejection_calls) == 1
    assert rejection_calls[0].args[1] == policy_status


def test_halt_flag_set_before_loop_stops_before_any_executor_call():
    """check_halt_flag() returning True is checked before the trade loop even starts (the
    earliest of several checks in run()) and must stop everything before any order is ever
    submitted."""
    signal = _make_signal("HALTED")
    halt_flag = MagicMock(return_value=True)

    with Phase8Deps(executor_result={"success": True}) as deps:
        result = run(**_run_kwargs([signal], check_halt_flag=halt_flag))

    assert deps.mock_trade_executor.execute_trade.call_count == 0
    assert result.data["entered"] == 0


def test_halt_flag_tripped_mid_loop_stops_processing_remaining_symbols():
    """check_halt_flag() is re-checked at the TOP of every loop iteration (not just once
    up-front) specifically because "this loop can run for minutes" (run()'s own comment at the
    check site). Verifies a halt that trips *between* two candidates lets the first entry
    complete but stops the second from ever reaching the executor - distinct from the two
    pre-loop checks covered by the test above, which never process any symbol at all."""
    first, second = _make_signal("FIRST"), _make_signal("SECOND")
    # Calls in order: pre-loop guard (x2, both False) -> loop iteration 1 top-of-loop (False,
    # so FIRST proceeds) -> loop iteration 2 top-of-loop (True, so SECOND never processes).
    halt_flag = MagicMock(side_effect=[False, False, False, True])
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        result = run(**_run_kwargs([first, second], check_halt_flag=halt_flag))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert deps.mock_trade_executor.execute_trade.call_args.kwargs["symbol"] == "FIRST"
    assert result.data["entered"] == 1
