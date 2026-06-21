#!/usr/bin/env python3
"""
Dynamic Weight Optimizer — Adapts swing score component weights based on realized IC.

Reads Information Coefficient, optimizes weights (constrained), blends smoothly to avoid whip-saw,
persists to algo_config (live reloading via SwingTraderScore._load_config_weights).
"""
from __future__ import (
    annotations,
)  # Defer annotation evaluation so np.ndarray doesn't fail when np=None

import logging
from datetime import date as _date
from typing import Any, ClassVar


try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    from scipy.optimize import minimize
except ImportError:
    minimize = None

from algo.signals.attribution import SignalAttributionEngine
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class WeightOptimizer:
    """Dynamically optimize swing score component weights based on IC."""

    COMPONENT_KEYS: ClassVar[dict[str, str]] = {
        "setup_quality": "swing_weight_setup",
        "trend_quality": "swing_weight_trend",
        "momentum_rs": "swing_weight_momentum",
        "volume": "swing_weight_volume",
        "fundamentals": "swing_weight_fundamentals",
        "sector_industry": "swing_weight_sector",
        "multi_timeframe": "swing_weight_multi_timeframe",
    }

    COMPONENTS: ClassVar[list[str]] = list(COMPONENT_KEYS.keys())

    MIN_WEIGHT: ClassVar[int] = 3  # No component below 3%
    MAX_WEIGHT: ClassVar[int] = 40  # No component above 40%
    MIN_TRADES: ClassVar[int] = 20  # Don't optimize if < 20 closed trades

    # Regime-specific blending factors (how fast to adapt)
    BLEND_FACTORS: ClassVar[dict[str, float]] = {
        "confirmed_uptrend": 0.10,
        "uptrend_under_pressure": 0.05,
        "caution": 0.05,
        "correction": 0.0,  # Freeze weights during crisis
    }

    def __init__(self, config):
        if config is None:
            raise ValueError("WeightOptimizer requires explicit config parameter (dependency injection)")
        self.config = config

    def get_current_weights(self) -> dict[str, int]:
        """Fetch current weights from algo_config."""
        weights = {}
        for component, key in self.COMPONENT_KEYS.items():
            val = self.config.get(key)  # uses AlgoConfig DEFAULTS as fallback, avoids mismatch warning
            weights[component] = int(val) if val is not None else 0
        return weights

    def optimize(self, report_date: _date, lookback_trades: int = 40) -> dict[str, int] | None:
        """
        Compute optimal weights from IC values.

        Algorithm:
          1. Fetch IC for each component
          2. Normalize to [0, 1]
          3. Solve: max(sum(w_i * IC_i)) s.t. sum(w) == 100, MIN_WEIGHT <= w_i <= MAX_WEIGHT
          4. Return integer weights

        Args:
            report_date: Date to optimize for
            lookback_trades: # trades to use for IC calculation

        Returns:
            {component: weight (int 0-100)} or None if insufficient data
        """
        try:
            # Get IC values
            attribution = SignalAttributionEngine()
            ic_values = attribution.compute_ic(report_date, lookback_trades)

            # Validate IC data structure
            if not ic_values:
                raise ValueError("No IC values computed for weight optimization")

            # Extract and validate sample size from first component
            first_comp_data = ic_values.get(self.COMPONENTS[0])
            if not first_comp_data or "sample_size" not in first_comp_data:
                raise ValueError(
                    f"IC data missing sample_size for {self.COMPONENTS[0]} component. "
                    "Cannot validate data sufficiency for weight optimization."
                )

            sample_size = first_comp_data["sample_size"]
            if sample_size < self.MIN_TRADES:
                raise ValueError(
                    f"Insufficient trades ({sample_size} < {self.MIN_TRADES}) for weight optimization. "
                    "Weights cannot be optimized without sufficient closed trade history."
                )

            ic_list: list[float] = []
            for comp in self.COMPONENTS:
                comp_data = ic_values.get(comp)
                if not comp_data or "ic_value" not in comp_data:
                    raise ValueError(
                        f"Missing IC data for {comp} component. "
                        "Cannot optimize weights without complete IC attribution data."
                    )
                ic = comp_data["ic_value"]
                ic_list.append(float(ic))

            ic_array = np.array(ic_list)

            # Normalize to [0, 1] (shift negatives up)
            if ic_array.min() < 0:
                ic_array = ic_array - ic_array.min()
            ic_max = ic_array.max()
            if ic_max > 0:
                ic_array = ic_array / ic_max
            else:
                # All ICs are zero/negative, use equal weights
                return self._equal_weights()

            # Optimize weights
            optimal = self._solve_weights(ic_array)
            logger.info(f"Optimal weights on {report_date}: {optimal}")
            return optimal

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _solve_weights(self, ic_array: np.ndarray) -> dict[str, int] | None:
        """
        Solve constrained optimization for weights.

        Objective: maximize sum(w_i * IC_i)
        Constraints: sum(w) == 100, MIN_WEIGHT <= w_i <= MAX_WEIGHT

        Returns: {component: weight}
        """
        try:
            n = len(self.COMPONENTS)

            def objective(w):
                return -np.dot(w, ic_array)  # Negative because we minimize

            # Constraints
            constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 100}

            # Bounds
            bounds = [(self.MIN_WEIGHT, self.MAX_WEIGHT) for _ in range(n)]

            # Initial guess (equal weights)
            x0 = np.full(n, 100 / n)

            result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)

            if not result.success:
                raise RuntimeError(
                    f"Weight optimization solver failed: {result.message}. Cannot compute optimal portfolio weights."
                )

            # Round to integers while maintaining sum=100
            weights_float = result.x
            weights_int = np.round(weights_float).astype(int)

            # Clamp to bounds first, then fix sum so the final sum is always 100
            weights_int = np.clip(weights_int, self.MIN_WEIGHT, self.MAX_WEIGHT)

            # Fix sum if rounding/clamping caused drift — adjust an unclamped weight
            delta = 100 - weights_int.sum()
            if delta != 0:
                not_at_bounds = [
                    i for i in range(len(weights_int)) if self.MIN_WEIGHT < weights_int[i] < self.MAX_WEIGHT
                ]
                idx = (
                    not_at_bounds[int(np.argmax(weights_float[not_at_bounds]))]
                    if not_at_bounds
                    else int(np.argmax(weights_float))
                )
                weights_int[idx] += delta

            result_dict = {comp: int(w) for comp, w in zip(self.COMPONENTS, weights_int, strict=False)}
            return result_dict

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _equal_weights(self) -> dict[str, int]:
        """Return equal weights (7 components → ~14.3% each)."""
        base = 100 // len(self.COMPONENTS)
        remainder = 100 % len(self.COMPONENTS)
        weights = {}
        for i, comp in enumerate(self.COMPONENTS):
            weights[comp] = base + (1 if i < remainder else 0)
        return weights

    def apply(
        self,
        report_date: _date,
        regime: str = "confirmed_uptrend",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Run full optimization cycle: compute → blend → persist.

        Algorithm:
          1. Get optimal weights
          2. Get current weights
          3. Blend: new = (1-alpha)*current + alpha*optimal (alpha from regime)
          4. Write to algo_config if not dry_run
          5. Log to algo_weight_history

        Args:
            report_date: Date for optimization
            regime: Market regime (affects blend speed)
            dry_run: If True, compute but don't persist

        Returns:
            {
                'old_weights': dict,
                'new_weights': dict,
                'optimal_weights': dict,
                'ic_values': dict,
                'changes': [list of (component, old, new) tuples],
                'blending_factor': float,
            }
        """
        try:
            # Compute optimal
            optimal = self.optimize(report_date)
            if not optimal:
                logger.warning(f"Optimization failed on {report_date}, keeping current weights")
                return {
                    "old_weights": self.get_current_weights(),
                    "new_weights": self.get_current_weights(),
                    "optimal_weights": None,
                    "ic_values": {},
                    "changes": [],
                    "blending_factor": 0,
                    "reason": "insufficient_data",
                }

            # Get current weights
            current = self.get_current_weights()

            # Get blend factor from regime (fail-fast if regime unknown)
            if regime not in self.BLEND_FACTORS:
                raise ValueError(
                    f"Unknown market regime '{regime}' has no defined blending factor. "
                    f"Valid regimes: {list(self.BLEND_FACTORS.keys())}"
                )
            blend_alpha = self.BLEND_FACTORS[regime]

            # Blend
            blended = {}
            for comp in self.COMPONENTS:
                old_w = float(current[comp])
                opt_w = float(optimal[comp])
                new_w = (1 - blend_alpha) * old_w + blend_alpha * opt_w
                blended[comp] = round(new_w)

            # Fix sum to 100
            delta = 100 - sum(blended.values())
            if delta != 0:
                # Adjust largest component
                largest_comp = max(blended, key=blended.get)  # type: ignore[arg-type]
                blended[largest_comp] += delta

            # Track changes as dicts (consumed by phase7 as change['component'] etc.)
            changes = []
            for comp in self.COMPONENTS:
                if current[comp] != blended[comp]:
                    changes.append(
                        {
                            "component": comp,
                            "old_weight": current[comp],
                            "new_weight": blended[comp],
                        }
                    )

            logger.info(f"Weight optimization {report_date}: {len(changes)} changes, alpha={blend_alpha:.2f}")

            if not dry_run and changes:
                # Persist to algo_config
                for comp, new_w in blended.items():
                    key = self.COMPONENT_KEYS[comp]
                    self.config.set(key, str(new_w), "int", changed_by="weight_optimizer")

                # Log to algo_weight_history
                self._log_changes(report_date, current, blended, regime, blend_alpha)

            return {
                "old_weights": current,
                "new_weights": blended,
                "optimal_weights": optimal,
                "changes": changes,
                "blending_factor": blend_alpha,
                "regime": regime,
                "dry_run": dry_run,
            }

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Weight application failed: {e}")
            return {
                "old_weights": self.get_current_weights(),
                "new_weights": self.get_current_weights(),
                "error": str(e),
            }

    def _log_changes(
        self,
        report_date: _date,
        old_weights: dict[str, int],
        new_weights: dict[str, int],
        regime: str,
        blend_alpha: float,
    ) -> None:
        """Log weight changes to algo_weight_history."""
        try:
            with DatabaseContext("write") as cur:
                for comp in self.COMPONENTS:
                    old_w = old_weights[comp]
                    new_w = new_weights[comp]
                    if old_w != new_w:
                        cur.execute(
                            """
                            INSERT INTO algo_weight_history
                            (change_date, component, old_weight, new_weight, reason,
                             blending_factor, regime)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                report_date,
                                comp,
                                old_w,
                                new_w,
                                "ic_optimization",
                                blend_alpha,
                                regime,
                            ),
                        )
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Failed to log weight changes: {e}")


if __name__ == "__main__":
    from algo.infrastructure import get_config

    opt = WeightOptimizer(config=get_config())
    result = opt.apply(_date.today(), regime="confirmed_uptrend", dry_run=True)
    logger.info(f"Optimization result: {result}")
