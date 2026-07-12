#!/usr/bin/env python3
"""
Dynamic Weight Optimizer — Adapts component weights based on realized Information Coefficient.

Reads Information Coefficient, optimizes weights (constrained), blends smoothly to avoid whip-saw,
persists to algo_config for live reloading.
"""

from __future__ import (
    annotations,
)  # Defer annotation evaluation so np.ndarray doesn't fail when np=None

import logging
from datetime import date as _date
from typing import Any, ClassVar, cast

try:
    import numpy as np
except ImportError:
    np = cast(Any, None)
try:
    from scipy.optimize import minimize
except ImportError:
    minimize = cast(Any, None)

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

    def __init__(self, config: Any) -> None:
        """Initialize WeightOptimizer with config dependency.

        Args:
            config: AlgoConfig instance for reading/writing weights

        Raises:
            ValueError: If config is None or invalid
        """
        if config is None:
            raise ValueError("WeightOptimizer requires explicit config parameter (dependency injection)")
        if not hasattr(config, "get") or not hasattr(config, "set"):
            raise ValueError("config must have get() and set() methods (AlgoConfig interface)")
        self.config = config

        # Validate class configuration
        if not self.COMPONENTS:
            raise ValueError("COMPONENTS list is empty, class is misconfigured")
        if self.MIN_WEIGHT < 0 or self.MAX_WEIGHT < 0:
            raise ValueError(f"MIN_WEIGHT ({self.MIN_WEIGHT}) and MAX_WEIGHT ({self.MAX_WEIGHT}) must be non-negative")
        if self.MIN_WEIGHT > self.MAX_WEIGHT:
            raise ValueError(f"MIN_WEIGHT ({self.MIN_WEIGHT}) cannot exceed MAX_WEIGHT ({self.MAX_WEIGHT})")
        if self.MIN_TRADES <= 0:
            raise ValueError(f"MIN_TRADES must be positive, got {self.MIN_TRADES}")
        if len(self.COMPONENT_KEYS) != len(self.COMPONENTS):
            raise ValueError(
                f"COMPONENT_KEYS ({len(self.COMPONENT_KEYS)} items) "
                f"and COMPONENTS ({len(self.COMPONENTS)} items) must have same length"
            )

    def get_current_weights(self) -> dict[str, int]:
        """Fetch current weights from algo_config.

        Raises:
            ValueError: If any weight is invalid or missing
        """
        weights = {}
        for component, key in self.COMPONENT_KEYS.items():
            val = self.config.get(key)  # uses AlgoConfig DEFAULTS as fallback, avoids mismatch warning
            if val is None:
                raise ValueError(f"Weight config key '{key}' for component '{component}' returned None")
            try:
                w = int(val)
                if not (0 <= w <= 100):
                    raise ValueError(f"Component '{component}' weight {w}% is out of valid range [0, 100]")
                weights[component] = w
            except (ValueError, TypeError) as e:
                raise ValueError(f"Cannot convert weight for component '{component}': {val}") from e

        # Validate all components are present
        if len(weights) != len(self.COMPONENTS):
            missing = set(self.COMPONENTS) - set(weights.keys())
            raise ValueError(f"Missing weights for components: {missing}")

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
            # Validate inputs
            if not isinstance(report_date, _date):
                raise ValueError(f"report_date must be a date object, got {type(report_date)}")
            if lookback_trades <= 0:
                raise ValueError(f"lookback_trades must be positive, got {lookback_trades}")

            # Get IC values
            attribution = SignalAttributionEngine()
            ic_values = attribution.compute_ic(report_date, lookback_trades)

            # Validate IC data structure
            if not ic_values:
                raise ValueError("No IC values computed for weight optimization")

            # Validate all required components are present
            missing_components = [c for c in self.COMPONENTS if c not in ic_values]
            if missing_components:
                raise ValueError(
                    f"Missing IC data for components: {missing_components}. "
                    "Cannot optimize weights without complete IC attribution data."
                )

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
                try:
                    ic = float(comp_data["ic_value"])
                    if not (-1e10 < ic < 1e10):  # Detect NaN, inf, extreme values
                        raise ValueError(f"IC value for {comp} is out of valid range: {ic}")
                    ic_list.append(ic)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid IC value for {comp}: {comp_data['ic_value']}") from e

            # Validate we have IC data
            if not ic_list:
                raise ValueError("No valid IC values extracted for any component")

            ic_array = np.array(ic_list)

            # Normalize to [0, 1] (shift negatives up)
            ic_min = ic_array.min()
            if ic_min < 0:
                ic_array = ic_array - ic_min

            ic_max = ic_array.max()
            if ic_max <= 0:
                # All ICs are zero or became zero after shift, use equal weights
                logger.warning(f"All IC values <= 0 on {report_date}, using equal weights")
                return self._equal_weights()

            # Normalize to [0, 1]
            ic_array = ic_array / ic_max

            # Optimize weights
            optimal = self._solve_weights(ic_array)
            if optimal is None:
                raise ValueError("Weight optimization solver returned None")
            logger.info(f"Optimal weights on {report_date}: {optimal}")
            return optimal

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _solve_weights(self, ic_array: np.ndarray[Any, Any]) -> dict[str, int] | None:
        """
        Solve constrained optimization for weights.

        Objective: maximize sum(w_i * IC_i)
        Constraints: sum(w) == 100, MIN_WEIGHT <= w_i <= MAX_WEIGHT

        Returns: {component: weight}
        """
        try:
            # Input validation
            if ic_array is None:
                raise ValueError("ic_array cannot be None")
            if len(ic_array) == 0:
                raise ValueError("ic_array is empty, cannot optimize weights")
            if len(ic_array) != len(self.COMPONENTS):
                raise ValueError(
                    f"ic_array length ({len(ic_array)}) must match COMPONENTS length ({len(self.COMPONENTS)})"
                )

            # Validate ic_array contains valid numbers
            if np.any(np.isnan(ic_array)):
                raise ValueError("ic_array contains NaN values")
            if np.any(np.isinf(ic_array)):
                raise ValueError("ic_array contains infinite values")

            n = len(self.COMPONENTS)

            # Special case: single component (should not happen, but handle gracefully)
            if n == 1:
                return {self.COMPONENTS[0]: 100}

            def objective(w: Any) -> Any:
                return -np.dot(w, ic_array)  # Negative because we minimize

            # Constraints
            constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 100}

            # Bounds - validate that constraints are satisfiable
            total_min = self.MIN_WEIGHT * n
            total_max = self.MAX_WEIGHT * n
            if total_min > 100 or total_max < 100:
                raise ValueError(
                    f"Constraints unsatisfiable: MIN_WEIGHT={self.MIN_WEIGHT}, MAX_WEIGHT={self.MAX_WEIGHT}, "
                    f"n_components={n}. Total min={total_min}, total max={total_max}, target=100"
                )

            bounds = [(self.MIN_WEIGHT, self.MAX_WEIGHT) for _ in range(n)]

            # Initial guess (equal weights)
            x0 = np.full(n, 100.0 / n)

            result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)

            if not result.success:
                raise RuntimeError(
                    f"Weight optimization solver failed: {result.message}. Cannot compute optimal portfolio weights."
                )

            # Round to integers while maintaining sum=100
            weights_float = result.x
            if weights_float is None or len(weights_float) != n:
                raise ValueError("Solver returned invalid weights array")

            weights_int = np.round(weights_float).astype(int)

            # Clamp to bounds first, then fix sum so the final sum is always 100
            weights_int = np.clip(weights_int, self.MIN_WEIGHT, self.MAX_WEIGHT)

            # Fix sum if rounding/clamping caused drift — adjust an unclamped weight
            delta = 100 - int(weights_int.sum())
            if delta != 0:
                # Find weights that can be adjusted (not at bounds)
                not_at_bounds = [
                    i for i in range(len(weights_int)) if self.MIN_WEIGHT < weights_int[i] < self.MAX_WEIGHT
                ]

                if not_at_bounds:
                    # Adjust the one with highest original weight among non-bound weights
                    idx = not_at_bounds[int(np.argmax(weights_float[not_at_bounds]))]
                else:
                    # All at bounds, adjust the one with highest original weight
                    # Check if adjustment is valid
                    idx = int(np.argmax(weights_float))
                    new_val = weights_int[idx] + delta
                    if not (self.MIN_WEIGHT <= new_val <= self.MAX_WEIGHT):
                        # Can't make valid adjustment at bounds, try all positions
                        for i in range(len(weights_int)):
                            new_val = weights_int[i] + delta
                            if self.MIN_WEIGHT <= new_val <= self.MAX_WEIGHT:
                                idx = i
                                break
                        else:
                            # Last resort: adjust largest weight component
                            idx = int(np.argmax(weights_int))

                weights_int[idx] += delta

            # Final validation
            final_sum = int(weights_int.sum())
            if final_sum != 100:
                raise ValueError(f"Final weights sum to {final_sum}, not 100. weights={weights_int}")

            result_dict = {comp: int(w) for comp, w in zip(self.COMPONENTS, weights_int, strict=False)}
            return result_dict

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _equal_weights(self) -> dict[str, int]:
        """Return equal weights (7 components -> ~14.3% each).

        Raises:
            ValueError: If COMPONENTS is empty or misconfigured
        """
        if not self.COMPONENTS:
            raise ValueError("COMPONENTS list is empty, cannot create equal weights")

        n = len(self.COMPONENTS)
        base = 100 // n
        remainder = 100 % n

        # Validate that equal weights respect MIN/MAX constraints
        if base < self.MIN_WEIGHT and n > 1:
            raise ValueError(
                f"Cannot create equal weights: base weight {base}% < MIN_WEIGHT {self.MIN_WEIGHT}% with {n} components"
            )

        weights = {}
        for i, comp in enumerate(self.COMPONENTS):
            w = base + (1 if i < remainder else 0)
            # Clamp to bounds
            w = max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, w))
            weights[comp] = w

        # Validate final sum
        total = sum(weights.values())
        if total != 100:
            # Adjust largest component to fix sum
            largest = max(weights.items(), key=lambda item: item[1])[0]
            weights[largest] += 100 - total

        return weights

    def apply(  # noqa: C901
        self,
        report_date: _date,
        regime: str = "confirmed_uptrend",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Run full optimization cycle: compute -> blend -> persist.

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
            # Input validation
            if not isinstance(report_date, _date):
                raise ValueError(f"report_date must be a date object, got {type(report_date)}")
            if not isinstance(regime, str):
                raise ValueError(f"regime must be a string, got {type(regime)}")
            if not isinstance(dry_run, bool):
                raise ValueError(f"dry_run must be a bool, got {type(dry_run)}")

            # Validate regime before processing
            if regime not in self.BLEND_FACTORS:
                raise ValueError(
                    f"Unknown market regime '{regime}' has no defined blending factor. "
                    f"Valid regimes: {list(self.BLEND_FACTORS.keys())}"
                )

            # Get current weights (validates config)
            current = self.get_current_weights()

            # Compute optimal
            try:
                optimal = self.optimize(report_date)
            except (RuntimeError, ValueError) as e:
                logger.warning(f"Optimization failed on {report_date}: {e}, keeping current weights")
                return {
                    "old_weights": current,
                    "new_weights": current,
                    "optimal_weights": None,
                    "changes": [],
                    "blending_factor": 0,
                    "reason": "optimization_failed",
                    "error": str(e),
                    "success": True,
                }

            if not optimal:
                logger.warning(f"Optimization returned None on {report_date}, keeping current weights")
                return {
                    "old_weights": current,
                    "new_weights": current,
                    "optimal_weights": None,
                    "changes": [],
                    "blending_factor": 0,
                    "reason": "insufficient_data",
                    "success": True,
                }

            # Validate optimal weights structure
            if not isinstance(optimal, dict):
                raise ValueError(f"optimal weights must be dict, got {type(optimal)}")
            if len(optimal) != len(self.COMPONENTS):
                raise ValueError(f"optimal weights dict has {len(optimal)} components, expected {len(self.COMPONENTS)}")

            blend_alpha = self.BLEND_FACTORS[regime]
            if not (0 <= blend_alpha <= 1):
                raise ValueError(f"blend_alpha must be in [0, 1], got {blend_alpha}")

            # Blend
            blended = {}
            for comp in self.COMPONENTS:
                if comp not in current:
                    raise ValueError(f"Component '{comp}' missing from current weights")
                if comp not in optimal:
                    raise ValueError(f"Component '{comp}' missing from optimal weights")

                old_w = float(current[comp])
                opt_w = float(optimal[comp])

                # Validate weight values
                if not (0 <= old_w <= 100):
                    raise ValueError(f"Current weight for '{comp}' out of range: {old_w}")
                if not (0 <= opt_w <= 100):
                    raise ValueError(f"Optimal weight for '{comp}' out of range: {opt_w}")

                new_w = (1 - blend_alpha) * old_w + blend_alpha * opt_w
                blended[comp] = max(0, min(100, round(new_w)))  # Clamp to [0, 100]

            # Fix sum to 100
            current_sum = sum(blended.values())
            delta = 100 - current_sum
            if delta != 0:
                # Adjust largest component (most stable)
                if not blended:
                    raise ValueError("blended weights dict is empty after blending")
                largest_comp = max(blended.items(), key=lambda item: item[1])[0]
                new_val = blended[largest_comp] + delta
                if not (0 <= new_val <= 100):
                    raise ValueError(f"Cannot fix sum: adjusting '{largest_comp}' to {new_val} exceeds bounds [0, 100]")
                blended[largest_comp] = new_val

            # Final validation
            final_sum = sum(blended.values())
            if final_sum != 100:
                raise ValueError(f"Final blended weights sum to {final_sum}, expected 100. weights={blended}")

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
                "success": True,
            }

        except (RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Weight application failed: {e}")
            try:
                current = self.get_current_weights()
            except (RuntimeError, ValueError, TypeError):
                current = {}
            return {
                "old_weights": current,
                "new_weights": current,
                "error": str(e),
                "success": False,
            }

    def _log_changes(
        self,
        report_date: _date,
        old_weights: dict[str, int],
        new_weights: dict[str, int],
        regime: str,
        blend_alpha: float,
    ) -> None:
        """Log weight changes to algo_weight_history.

        Raises RuntimeError if logging fails so caller knows optimization needs retry.

        Args:
            report_date: Date of optimization
            old_weights: Previous weights {component: weight}
            new_weights: New weights {component: weight}
            regime: Market regime
            blend_alpha: Blending factor used

        Raises:
            ValueError: If input validation fails
            RuntimeError: If database operations fail
        """
        try:
            # Input validation
            if not isinstance(report_date, _date):
                raise ValueError(f"report_date must be a date, got {type(report_date)}")
            if not isinstance(old_weights, dict) or not old_weights:
                raise ValueError("old_weights must be a non-empty dict")
            if not isinstance(new_weights, dict) or not new_weights:
                raise ValueError("new_weights must be a non-empty dict")
            if not isinstance(regime, str):
                raise ValueError(f"regime must be a string, got {type(regime)}")
            if not (0 <= blend_alpha <= 1):
                raise ValueError(f"blend_alpha must be in [0, 1], got {blend_alpha}")

            # Validate keys match
            old_keys = set(old_weights.keys())
            new_keys = set(new_weights.keys())
            if old_keys != new_keys:
                raise ValueError(
                    f"old_weights and new_weights have different keys. "
                    f"Missing in new: {old_keys - new_keys}, extra in new: {new_keys - old_keys}"
                )

            with DatabaseContext("write") as cur:
                for comp in self.COMPONENTS:
                    if comp not in old_weights or comp not in new_weights:
                        raise ValueError(f"Component '{comp}' missing from weights dicts")

                    old_w = old_weights[comp]
                    new_w = new_weights[comp]

                    # Validate weight values
                    if not isinstance(old_w, int) or not (0 <= old_w <= 100):
                        raise ValueError(f"Invalid old weight for '{comp}': {old_w} (must be int in [0, 100])")
                    if not isinstance(new_w, int) or not (0 <= new_w <= 100):
                        raise ValueError(f"Invalid new weight for '{comp}': {new_w} (must be int in [0, 100])")

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
        except ValueError as e:
            logger.error(f"Invalid input to _log_changes: {e}")
            raise ValueError(f"Weight optimization logging input validation failed: {e}") from e
        except (OSError, RuntimeError) as e:
            # FIX: Don't silent-fail on database errors - re-raise so caller knows
            logger.error(f"Failed to log weight changes to database: {e}")
            raise RuntimeError(f"Weight optimization logging failed (weight changes NOT persisted): {e}") from e


if __name__ == "__main__":
    from algo.infrastructure import get_config

    opt = WeightOptimizer(config=get_config())
    result = opt.apply(_date.today(), regime="confirmed_uptrend", dry_run=True)
    logger.info(f"Optimization result: {result}")
