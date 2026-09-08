#!/usr/bin/env python3
"""Exit strategies for automated position exit decision-making.

Implements Strategy pattern for evaluating exit conditions. Each strategy
represents a specific exit rule (stop-loss, profit target, technical break, etc).
Strategies are evaluated in priority order; first match wins.

Exit hierarchy (by priority):
1. Stop-loss (price <= active stop)
2. Minervini break (close < 21-EMA) - DISABLED (0% win rate, backtest 2026-08-05; see
   ExitEngine.check_minervini_break's docstring). Kept in the priority list/strategy chain
   for its slot ordering and to re-enable via exit_on_minervini_break config; always returns
   no-trigger today.
3. RS line break (relative strength breakdown)
4. Time-based (held >= max_days)
5. Profit target T1 (1.5R)
6. Profit target T2 (3R)
7. Profit target T3 (4R)
8. Chandelier trail (3xATR from high)
9. TD Sequential (9-count or 13-count exhaustion)
10. First red day (after 2.5R+ gain)
11. Climax exhaustion (30+ days, 5R+ gain)
12. Distribution (market distribution days exceed limit)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from psycopg2.extensions import cursor as PsycopgCursor

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig
    from algo.trading.exit_engine import PositionContext


logger = logging.getLogger(__name__)


@dataclass
class ExitSignal:
    """Result of an exit strategy evaluation."""

    triggered: bool
    stage: str
    reason: str
    fraction: float = 0.0
    new_stop: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for backward compatibility."""
        return {
            "stage": self.stage,
            "fraction": self.fraction,
            "reason": self.reason,
            "new_stop": self.new_stop,
        }


class ExitStrategy(ABC):
    """Base class for exit decision strategies."""

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        """Initialize strategy with config.

        Args:
            config: AlgoConfig instance or dict-like config object
        """
        self.config = config

    @abstractmethod
    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        """Evaluate if this exit condition is triggered.

        Args:
            ctx: PositionContext with all position data
            cur: Database cursor (for queries if needed)

        Returns:
            ExitSignal with triggered=True if condition met, False otherwise
        """
        ...

    def _validate_decision(self, decision: dict[str, Any]) -> None:
        """Validate exit decision has required fields."""
        if not decision:
            return
        required_fields = ["stage", "reason", "fraction"]
        missing = [f for f in required_fields if f not in decision or decision[f] is None]
        if missing:
            raise ValueError(
                f"Exit decision incomplete: missing {missing}. Cannot process exit without all required fields."
            )

    def _get_config(self, key: str) -> Any:
        """Get config value (supports both AlgoConfig and dict).

        CRITICAL: Raises KeyError if key missing. NO defaults allowed - exit strategy
        config must be explicit and consistent across all callers.
        """
        if hasattr(self.config, "get"):
            value = self.config.get(key)
        else:
            # Fallback for object without .get() method (e.g., AlgoConfig instance)
            try:
                value = getattr(self.config, key)
            except AttributeError:
                value = None

        if value is None:
            raise KeyError(
                f"[EXIT_STRATEGY] Config key '{key}' required but missing. "
                "Exit strategy parameters must be explicitly configured in algo_config - no implicit defaults allowed."
            )
        return value

    def _evaluate_engine_strategy(
        self, check_method: Callable[[Any], tuple[bool, dict[str, Any] | None]], include_new_stop: bool = False
    ) -> ExitSignal:
        """Common pattern: create engine, call check method, validate and return signal.

        Args:
            check_method: Callable that takes engine and returns (should_exit, decision)
            include_new_stop: Whether to include new_stop from decision in result

        Returns:
            ExitSignal with decision fields or no-exit signal if not triggered
        """
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = check_method(engine)

        if _should_exit and decision:
            self._validate_decision(decision)
            kwargs = {
                "triggered": True,
                "stage": decision["stage"],
                "reason": decision["reason"],
                "fraction": decision["fraction"],
            }
            if include_new_stop:
                # CRITICAL: new_stop MUST be present if requested - don't silently default to None
                if "new_stop" not in decision:
                    raise ValueError(
                        f"[EXIT_STRATEGY] Exit decision requested new_stop but field missing. "
                        f"Decision keys: {list(decision.keys())}. "
                        f"Cannot create exit signal with incomplete stop-loss data."
                    )
                new_stop_val = decision["new_stop"]
                if new_stop_val is None:
                    raise ValueError(
                        f"[EXIT_STRATEGY] Exit decision new_stop is NULL. "
                        f"Cannot create exit signal with missing stop-loss price. "
                        f"Stage: {decision.get('stage')}, Reason: {decision.get('reason')}"
                    )
                kwargs["new_stop"] = new_stop_val
            elif decision.get("new_stop") is not None:
                # BUG FOUND 2026-08-24 (real-money-readiness goal session, exit-check test-
                # coverage sweep): TDSequentialStrategy/FirstRedDayStrategy/ClimaxExhaustionStrategy
                # all call this helper without include_new_stop=True (unlike
                # ChandelierTrailStrategy, which opts in) - so even though check_td_sequential's
                # 9-count branch / check_first_red_day / check_climax_exhaustion all compute and
                # return a real new_stop (raise stop to breakeven after a 50% de-risking partial
                # exit), it was silently dropped here, defaulting to ExitSignal's new_stop=None.
                # Live-confirmed downstream impact: executor_exit_handler.py's _execute_exit
                # falls back to the OLD stop_loss_price whenever new_stop_price is None - no
                # error, no log, just silently never raising the stop. A position that took a
                # TD-9/first-red-day/climax de-risking exit kept its original (lower) stop on the
                # remaining shares instead of the intended breakeven stop, exposed to giving back
                # more profit than the strategy intended before finally stopping out. Propagate
                # new_stop whenever the decision dict actually has one, independent of whether
                # this particular strategy class opted into the strict include_new_stop=True
                # validation above (that flag is for "does new_stop being missing/null indicate a
                # bug", not "should new_stop ever be included at all") - safe for every existing
                # caller since check_rs_line_break/check_time_exit/check_minervini_break never
                # populate this key, so this branch is a no-op for them.
                kwargs["new_stop"] = decision["new_stop"]
            return ExitSignal(**kwargs)
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class StopLossStrategy(ExitStrategy):
    """Exit if current price <= active stop-loss."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        if ctx.cur_price <= ctx.active_stop:
            return ExitSignal(
                triggered=True,
                stage="stop",
                reason=f"Stop triggered at ${float(ctx.cur_price):.2f} <= stop ${float(ctx.active_stop):.2f}",
                fraction=1.0,
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class MinerviniBreakStrategy(ExitStrategy):
    """Exit on Minervini break: close < 21-EMA on volume > 50d avg (or cleanly below 50-DMA).

    DISABLED: ctx.check_minervini_break() always returns no-trigger (0% win rate, backtest
    2026-08-05) - see its own docstring. This class stays wired into the strategy chain so
    its priority slot/config toggle (exit_on_minervini_break) still work if re-enabled.
    """

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_minervini_break(engine))


class RSLineBreakStrategy(ExitStrategy):
    """Exit on RS line breaking below support."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_rs_line_break(engine))


class TimeBasedExitStrategy(ExitStrategy):
    """Exit if position held >= max_hold_days."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_time_exit(engine))


class ProfitTargetStrategy(ExitStrategy):
    """Base class for profit target exits (T1, T2, T3)."""

    target_level: int

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)

        if self.target_level == 1:
            _should_exit, decision = ctx.check_target_t1(engine)
        elif self.target_level == 2:
            _should_exit, decision = ctx.check_target_t2(engine)
        elif self.target_level == 3:
            _should_exit, decision = ctx.check_target_t3()
        else:
            return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)

        if _should_exit and decision:
            self._validate_decision(decision)
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
                new_stop=decision.get("new_stop"),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class T1Strategy(ProfitTargetStrategy):
    """Exit 50% at target 1 (1.5R), raise stop to entry."""

    target_level = 1


class T2Strategy(ProfitTargetStrategy):
    """Exit 25% at target 2 (3R), raise stop to T1 area."""

    target_level = 2


class T3Strategy(ProfitTargetStrategy):
    """Exit final 25% at target 3 (4R)."""

    target_level = 3


class ChandelierTrailStrategy(ExitStrategy):
    """Exit on chandelier stop trail (3xATR from highest high or 21-EMA after 10d)."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_chandelier_trail(engine), include_new_stop=True)


class TDSequentialStrategy(ExitStrategy):
    """Exit on TD Sequential exhaustion (9-count 50%, 13-count 100%)."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_td_sequential(engine))


class FirstRedDayStrategy(ExitStrategy):
    """Exit 50% after 2.5R+ gain on first big down day with heavy volume."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_first_red_day(engine))


class ClimaxExhaustionStrategy(ExitStrategy):
    """Exit 50% after 30+ days, 5R+ gain, 20%+ in last 10 days (climax run exhaustion)."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        return self._evaluate_engine_strategy(lambda engine: ctx.check_climax_exhaustion(engine))


class DistributionStrategy(ExitStrategy):
    """Exit if market distribution day count exceeds configured limit."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        _should_exit, decision = ctx.check_distribution()
        if _should_exit and decision:
            self._validate_decision(decision)
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
                new_stop=decision.get("new_stop"),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class ExitStrategyChain:
    """Orchestrates multiple exit strategies in priority order.

    Evaluates each strategy in sequence; first match wins.
    Returns the exit signal from the first triggered strategy, or hold if none triggered.
    """

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        """Initialize chain with all strategies in priority order.

        Args:
            config: AlgoConfig instance or dict-like config object
        """
        self.config = config
        self.strategies = [
            StopLossStrategy(config),
            MinerviniBreakStrategy(config),
            RSLineBreakStrategy(config),
            TimeBasedExitStrategy(config),
            T1Strategy(config),
            T2Strategy(config),
            T3Strategy(config),
            ChandelierTrailStrategy(config),
            TDSequentialStrategy(config),
            FirstRedDayStrategy(config),
            ClimaxExhaustionStrategy(config),
            DistributionStrategy(config),
        ]

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        """Evaluate all strategies in priority order; return first triggered REAL exit signal.

        Returns:
            ExitSignal from the first triggered strategy with fraction > 0 (a real share
            reduction), or hold if none triggered.

        FIX (2026-09-07 pre-live audit): a triggered signal with fraction == 0.0 (a pure
        stop-tightening, e.g. ChandelierTrailStrategy) used to return immediately like any
        other trigger, short-circuiting evaluation of every lower-priority strategy for that
        cycle - including TDSequentialStrategy/FirstRedDayStrategy/ClimaxExhaustionStrategy,
        whose real partial/full exits are most likely to fire in exactly the strong-uptrend
        condition that also raises the chandelier trail on the same day. A routine stop
        tightening could silently starve a genuine exhaustion exit for an entire cycle. Now
        keeps scanning past a stop-raise-only trigger for a real (fraction > 0) exit among
        remaining strategies; only falls back to the stop-raise if nothing else fires.
        """
        stop_raise_signal: ExitSignal | None = None
        for strategy in self.strategies:
            signal = strategy.evaluate(ctx, cur)
            if signal.triggered:
                if signal.fraction > 0:
                    return signal
                if stop_raise_signal is None:
                    stop_raise_signal = signal

        if stop_raise_signal is not None:
            return stop_raise_signal

        return ExitSignal(
            triggered=False,
            stage="hold",
            reason="No exit conditions met",
            fraction=0.0,
        )
