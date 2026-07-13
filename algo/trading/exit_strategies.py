#!/usr/bin/env python3
"""Exit strategies for automated position exit decision-making.

Implements Strategy pattern for evaluating exit conditions. Each strategy
represents a specific exit rule (stop-loss, profit target, technical break, etc).
Strategies are evaluated in priority order; first match wins.

Exit hierarchy (by priority):
1. Stop-loss (price <= active stop)
2. Minervini break (close < 21-EMA)
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

        CRITICAL: Raises KeyError if key missing. NO defaults allowed — exit strategy
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
                "Exit strategy parameters must be explicitly configured in algo_config — no implicit defaults allowed."
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
                kwargs["new_stop"] = decision.get("new_stop")
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
    """Exit on Minervini break: close < 21-EMA on volume > 50d avg (or cleanly below 50-DMA)."""

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
    default_fraction: float

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
    default_fraction = 0.5


class T2Strategy(ProfitTargetStrategy):
    """Exit 25% at target 2 (3R), raise stop to T1 area."""

    target_level = 2
    default_fraction = 0.25


class T3Strategy(ProfitTargetStrategy):
    """Exit final 25% at target 3 (4R)."""

    target_level = 3
    default_fraction = 0.25


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
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_first_red_day(engine)

        if _should_exit and decision:
            self._validate_decision(decision)
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class ClimaxExhaustionStrategy(ExitStrategy):
    """Exit 50% after 30+ days, 5R+ gain, 20%+ in last 10 days (climax run exhaustion)."""

    def evaluate(self, ctx: PositionContext, cur: PsycopgCursor[Any]) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_climax_exhaustion(engine)

        if _should_exit and decision:
            self._validate_decision(decision)
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


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
        """Evaluate all strategies in priority order; return first triggered signal.

        Args:
            ctx: PositionContext with all position data
            cur: Database cursor

        Returns:
            ExitSignal from first triggered strategy, or hold if none triggered
        """
        for strategy in self.strategies:
            signal = strategy.evaluate(ctx, cur)
            if signal.triggered:
                return signal

        return ExitSignal(
            triggered=False,
            stage="hold",
            reason="No exit conditions met",
            fraction=0.0,
        )
