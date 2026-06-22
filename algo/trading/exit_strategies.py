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
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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
    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        """Evaluate if this exit condition is triggered.

        Args:
            ctx: PositionContext with all position data
            cur: Database cursor (for queries if needed)

        Returns:
            ExitSignal with triggered=True if condition met, False otherwise
        """
        ...

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Get config value (supports both AlgoConfig and dict)."""
        if hasattr(self.config, "get"):
            return self.config.get(key, default)
        return self.config.get(key, default)


class StopLossStrategy(ExitStrategy):
    """Exit if current price <= active stop-loss."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
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

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_minervini_break(engine)

        if _should_exit and decision:
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", "minervini_break"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", 1.0),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class RSLineBreakStrategy(ExitStrategy):
    """Exit on RS line breaking below support."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_rs_line_break(engine)

        if _should_exit and decision:
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", "rs_breakdown"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", 1.0),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class TimeBasedExitStrategy(ExitStrategy):
    """Exit if position held >= max_hold_days."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_time_exit(engine)

        if _should_exit and decision:
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", "time"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", 1.0),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class ProfitTargetStrategy(ExitStrategy):
    """Base class for profit target exits (T1, T2, T3)."""

    target_level: int
    default_fraction: float

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
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
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", f"target_{self.target_level}"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", self.default_fraction),
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

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_chandelier_trail(engine)

        if _should_exit and decision:
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", "chandelier_trail"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", 1.0),
                new_stop=decision.get("new_stop"),
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class TDSequentialStrategy(ExitStrategy):
    """Exit on TD Sequential exhaustion (9-count 50%, 13-count 100%)."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_td_sequential(engine)

        if _should_exit and decision:
            required_fields = ["stage", "reason", "fraction"]
            missing = [f for f in required_fields if f not in decision or decision[f] is None]
            if missing:
                raise ValueError(
                    f"TD Sequential exit decision incomplete: missing {missing}. "
                    f"Cannot process exit without all required fields."
                )
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class FirstRedDayStrategy(ExitStrategy):
    """Exit 50% after 2.5R+ gain on first big down day with heavy volume."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_first_red_day(engine)

        if _should_exit and decision:
            required_fields = ["stage", "reason", "fraction"]
            missing = [f for f in required_fields if f not in decision or decision[f] is None]
            if missing:
                raise ValueError(
                    f"First red day exit decision incomplete: missing {missing}. "
                    f"Cannot process exit without all required fields."
                )
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class ClimaxExhaustionStrategy(ExitStrategy):
    """Exit 50% after 30+ days, 5R+ gain, 20%+ in last 10 days (climax run exhaustion)."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        from algo.trading.exit_engine import ExitEngine

        engine = ExitEngine(self.config)
        _should_exit, decision = ctx.check_climax_exhaustion(engine)

        if _should_exit and decision:
            required_fields = ["stage", "reason", "fraction"]
            missing = [f for f in required_fields if f not in decision or decision[f] is None]
            if missing:
                raise ValueError(
                    f"Climax exhaustion exit decision incomplete: missing {missing}. "
                    f"Cannot process exit without all required fields."
                )
            return ExitSignal(
                triggered=True,
                stage=decision["stage"],
                reason=decision["reason"],
                fraction=decision["fraction"],
            )
        return ExitSignal(triggered=False, stage="hold", reason="", fraction=0.0)


class DistributionStrategy(ExitStrategy):
    """Exit if market distribution day count exceeds configured limit."""

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
        _should_exit, decision = ctx.check_distribution()

        if _should_exit and decision:
            return ExitSignal(
                triggered=True,
                stage=decision.get("stage", "distribution"),
                reason=decision.get("reason", ""),
                fraction=decision.get("fraction", 1.0),
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

    def evaluate(self, ctx: PositionContext, cur: Any) -> ExitSignal:
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
