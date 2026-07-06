#!/usr/bin/env python3
"""
Signal Attribution Engine (DEPRECATED).

Previously measured which swing score components predict realized P&L (IC).
Swing scores have been removed; this module is deprecated and returns unavailable data.
"""

import logging
from datetime import date as _date
from typing import Any, cast

import psycopg2

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]
try:
    from scipy import stats
except ImportError:
    stats = cast(Any, None)

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class SignalAttributionEngine:
    """DEPRECATED: Computed Information Coefficient per swing score component (no longer used)."""

    COMPONENTS = [
        "setup_quality",
        "trend_quality",
        "momentum_rs",
        "volume",
        "fundamentals",
        "sector_industry",
        "multi_timeframe",
    ]

    IC_THRESHOLDS = {
        "strong": 0.40,
        "moderate": 0.25,
        "weak": 0.10,
        "noise": 0.00,
    }

    def compute_ic(self, report_date: _date, lookback_trades: int = 40) -> dict[str, dict[str, Any]]:
        """
        Compute Information Coefficient for each component (DEPRECATED).

        This method is deprecated because swing_trader_scores has been removed.
        Historical algorithm:
          1. Fetch last N closed trades
          2. Get component score from swing_trader_scores.components JSONB at entry (no longer available)
          3. Get realized exit_r_multiple from algo_trades
          4. Compute Pearson r(component_score, exit_r_multiple)
          5. Compute p-value and sample size

        Args:
            report_date: Date to report
            lookback_trades: # of closed trades to analyze (default 40)

        Returns:
            {
                'component_name': {
                    'ic_value': float (-1 to +1),
                    'ic_pvalue': float (0 to 1),
                    'sample_size': int,
                    'avg_component_score': float,
                    'avg_realized_pnl': float,
                    'interpretation': str ('strong'|'moderate'|'weak'|'noise'),
                }
            }
        """
        # Swing components deprecated - return unavailable data
        logger.warning(
            "[ATTRIBUTION] Swing score components are deprecated. Signal attribution analysis is no longer available."
        )
        return {
            comp: {
                "ic_value": None,
                "ic_pvalue": None,
                "sample_size": 0,
                "data_unavailable": True,
                "reason": "swing_components_deprecated",
            }
            for comp in self.COMPONENTS
        }

    def compute_ic_by_regime(self, report_date: _date, lookback_trades: int = 40) -> dict[str, dict[str, Any]]:
        """
        Compute IC broken down by market regime.

        Shows which components work in bull vs bear vs sideways.

        Returns:
            {
                'confirmed_uptrend': {component: ic_data},
                'uptrend_under_pressure': {component: ic_data},
                'caution': {component: ic_data},
                'correction': {component: ic_data},
            }
        """
        # Swing components deprecated - return unavailable data
        logger.warning(
            "[ATTRIBUTION] Swing score components are deprecated. "
            "Regime-specific signal attribution analysis is no longer available."
        )
        from algo.orchestration import RegimeManager

        regime_results: dict[str, dict[str, dict[str, Any]]] = {}
        for regime in RegimeManager.REGIMES:
            regime_results[regime] = {
                comp: {
                    "ic_value": None,
                    "ic_pvalue": None,
                    "sample_size": 0,
                    "data_unavailable": True,
                    "reason": "swing_components_deprecated",
                }
                for comp in self.COMPONENTS
            }
        return regime_results

    def compute_ic_decay(self, report_date: _date, horizons: list[int] | None = None) -> dict[str, dict[int, float]]:
        """
        Compute IC at different lookback horizons.

        Shows if signal degrades with lookback horizon (signal half-life).

        Returns:
            {
                'setup_quality': {10: 0.35, 20: 0.28, 40: 0.15},  # IC degrading with horizon
                ...
            }
        """
        if horizons is None:
            horizons = [10, 20, 40]

        decay_results: dict[str, dict[int, float]] = {}

        for horizon in horizons:
            ic_results = self.compute_ic(report_date, lookback_trades=horizon)
            for component, ic_data in ic_results.items():
                if component not in decay_results:
                    decay_results[component] = {}
                decay_results[component][horizon] = ic_data["ic_value"]

        return decay_results

    def persist(
        self,
        report_date: _date,
        ic_values: dict[str, dict[str, float]],
        regime: str = "unknown",
    ) -> None:
        """
        Persist IC values to algo_component_attribution table.

        Also updates algo_information_coefficient for historical tracking.
        """
        try:
            with DatabaseContext("write") as cur:
                for component, ic_data in ic_values.items():
                    cur.execute(
                        """
                        INSERT INTO algo_component_attribution
                        (report_date, component, ic_value, ic_pvalue, sample_size,
                         lookback_trades, avg_component_score, avg_realized_pnl, regime)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (report_date, component) DO UPDATE SET
                            ic_value = EXCLUDED.ic_value,
                            ic_pvalue = EXCLUDED.ic_pvalue,
                            sample_size = EXCLUDED.sample_size,
                            avg_realized_pnl = EXCLUDED.avg_realized_pnl
                        """,
                        (
                            report_date,
                            component,
                            ic_data.get("ic_value"),
                            ic_data.get("ic_pvalue"),
                            ic_data.get("sample_size"),
                            40,
                            ic_data.get("avg_component_score"),
                            ic_data.get("avg_realized_pnl"),
                            regime,
                        ),
                    )

                logger.info(f"Persisted IC for {len(ic_values)} components on {report_date}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to persist IC: {e}")

    def get_trailing_ic(self, component: str, days: int = 60) -> list[tuple[_date, float]]:
        """
        Get rolling IC for a component over last N days.

        Returns: [(date, ic_value), ...]
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT report_date, ic_value FROM algo_component_attribution
                    WHERE component = %s AND report_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY report_date ASC
                    """,
                    (component, days),
                )
                return [(row[0], float(row[1])) for row in cur.fetchall()]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Cannot retrieve trailing IC for attribution analysis: {e}") from e


if __name__ == "__main__":
    engine = SignalAttributionEngine()
    ic_values = engine.compute_ic(_date.today(), lookback_trades=40)
    for comp, data in ic_values.items():
        logger.info(f"{comp}: IC={data['ic_value']:.3f} ({data['interpretation']})")
