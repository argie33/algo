#!/usr/bin/env python3

"""
Signal Attribution Engine — Measures which swing score components predict realized P&L (IC).

Information Coefficient = Pearson r(component_score, realized_exit_r_multiple)
Identifies alpha drivers, detects signal degradation, enables dynamic weight optimization.
"""

import json
import logging
from datetime import date as _date, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

try:
    from scipy import stats
except ImportError:
    stats = None  # type: ignore[assignment]

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

class SignalAttributionEngine:
    """Computes and persists Information Coefficient per swing score component."""

    COMPONENTS = [
        'setup_quality',
        'trend_quality',
        'momentum_rs',
        'volume',
        'fundamentals',
        'sector_industry',
        'multi_timeframe',
    ]

    IC_THRESHOLDS = {
        'strong': 0.40,
        'moderate': 0.25,
        'weak': 0.10,
        'noise': 0.00,
    }

    def compute_ic(self, report_date: _date, lookback_trades: int = 40) -> Dict[str, Dict[str, float]]:
        """
        Compute Information Coefficient for each component.

        For each component:
          1. Fetch last N closed trades
          2. Get component score from swing_trader_scores.components JSONB at entry
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
        try:
            with DatabaseContext('read') as cur:
                # Fetch last N closed trades with component scores
                cur.execute(
                    """
                    SELECT
                        t.trade_id, t.swing_score, t.swing_components,
                        t.exit_r_multiple, t.exit_date,
                        t.symbol, t.signal_date
                    FROM algo_trades t
                    WHERE t.status = 'closed' AND t.exit_date <= %s
                    ORDER BY t.exit_date DESC
                    LIMIT %s
                    """,
                    (report_date, lookback_trades),
                )
                trades = cur.fetchall()

                if not trades or len(trades) < 10:
                    logger.warning(f"Insufficient closed trades ({len(trades) if trades else 0}) for IC calculation")
                    return {comp: {'ic_value': 0, 'ic_pvalue': 1.0, 'sample_size': 0} for comp in self.COMPONENTS}

                # Extract component scores and P&Ls
                ic_results = {}

                for component in self.COMPONENTS:
                    comp_scores = []
                    r_multiples = []

                    for trade in trades:
                        trade_id, swing_score, swing_components_json, r_multiple, exit_date, symbol, signal_date = trade

                        try:

                            swing_components = json.loads(swing_components_json) if swing_components_json else {}
                            comp_data = swing_components.get(component, {})
                            comp_score = comp_data.get('pts', 0)
                            r_mult = float(r_multiple) if r_multiple is not None else 0

                            if comp_score is not None and r_mult is not None:
                                comp_scores.append(float(comp_score))
                                r_multiples.append(r_mult)
                        except Exception as e:
                            logger.debug(f"Could not extract {component} from trade {trade_id}: {e}")
                            continue

                    # Calculate IC
                    if len(comp_scores) >= 10:
                        comp_scores_arr = np.array(comp_scores)
                        r_mult_arr = np.array(r_multiples)

                        # Pearson correlation
                        if comp_scores_arr.std() > 0 and r_mult_arr.std() > 0:
                            ic_value, ic_pvalue = stats.pearsonr(comp_scores_arr, r_mult_arr)
                        else:
                            ic_value, ic_pvalue = 0.0, 1.0

                        # Interpretation
                        interpretation = 'noise'
                        if ic_value >= self.IC_THRESHOLDS['strong']:
                            interpretation = 'strong'
                        elif ic_value >= self.IC_THRESHOLDS['moderate']:
                            interpretation = 'moderate'
                        elif ic_value >= self.IC_THRESHOLDS['weak']:
                            interpretation = 'weak'

                        ic_results[component] = {
                            'ic_value': round(float(ic_value), 4),
                            'ic_pvalue': round(float(ic_pvalue), 4),
                            'sample_size': len(comp_scores),
                            'avg_component_score': round(float(comp_scores_arr.mean()), 2),
                            'avg_realized_pnl': round(float(r_mult_arr.mean()), 2),
                            'interpretation': interpretation,
                        }
                    else:
                        ic_results[component] = {
                            'ic_value': 0.0,
                            'ic_pvalue': 1.0,
                            'sample_size': len(comp_scores),
                            'avg_component_score': 0,
                            'avg_realized_pnl': 0,
                            'interpretation': 'insufficient_data',
                        }

                logger.info(f"IC computation complete for {report_date}. Samples: {len(trades)}")
                return ic_results
        except Exception as e:
            logger.error(f"IC computation failed: {e}")
            return {comp: {'ic_value': 0, 'ic_pvalue': 1.0, 'sample_size': 0} for comp in self.COMPONENTS}

    def compute_ic_by_regime(self, report_date: _date, lookback_trades: int = 40) -> Dict[str, Dict]:
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
        from algo.orchestration import RegimeManager

        regime_mgr = RegimeManager()
        regime_results: Dict[str, Dict[str, Dict[str, Any]]] = {regime: {} for regime in RegimeManager.REGIMES}

        try:
            with DatabaseContext('read') as cur:
                # Fetch last N closed trades with component scores
                cur.execute(
                    """
                    SELECT
                        t.trade_id, t.swing_score, t.swing_components,
                        t.exit_r_multiple, t.exit_date, t.signal_date,
                        t.symbol
                    FROM algo_trades t
                    WHERE (t.status = 'closed' OR (t.exit_date IS NOT NULL AND t.exit_date <= %s))
                    ORDER BY t.exit_date DESC
                    LIMIT %s
                    """,
                    (report_date, lookback_trades),
                )
                trades = cur.fetchall()

                if not trades:
                    logger.info(f"No closed trades found for regime IC computation.")
                    return regime_results

                # Group trades by regime at entry date
                trades_by_regime: Dict[str, List[Tuple[Any, ...]]] = {regime: [] for regime in RegimeManager.REGIMES}

                for trade in trades:
                    trade_id, swing_score, swing_components, exit_r_multiple, exit_date, signal_date, symbol = trade

                    if not swing_components or not exit_r_multiple:
                        continue

                    # Determine regime at signal_date (entry)
                    try:
                        signal_regime = regime_mgr.get_current_regime(signal_date) or 'unknown'
                        if signal_regime not in trades_by_regime:
                            signal_regime = 'caution'  # Default if unknown
                    except Exception as e:
                        logger.debug(f"Could not determine regime for {signal_date}: {e}")
                        signal_regime = 'caution'

                    trades_by_regime[signal_regime].append((trade_id, swing_components, exit_r_multiple))

                # Compute IC for each regime
                for regime, regime_trades in trades_by_regime.items():
                    if not regime_trades:
                        continue

                    ic_data = {}
                    for component in self.COMPONENTS:
                        comp_scores = []
                        r_multiples = []

                        for trade_id, swing_components, exit_r_multiple in regime_trades:
                            try:
                                if isinstance(swing_components, str):
                                    swing_components = json.loads(swing_components)
                                comp_data = swing_components.get(component) if isinstance(swing_components, dict) else None
                                comp_value = comp_data.get('pts') if isinstance(comp_data, dict) else comp_data
                                if comp_value is not None:
                                    comp_scores.append(float(comp_value))
                                    r_multiples.append(float(exit_r_multiple))
                            except Exception as e:
                                logger.debug(f"Could not extract {component} from trade {trade_id}: {e}")
                                continue

                        # Calculate IC for this component in this regime
                        if len(comp_scores) >= 5:  # Lower threshold for regime splits
                            comp_scores_arr = np.array(comp_scores)
                            r_mult_arr = np.array(r_multiples)

                            if comp_scores_arr.std() > 0 and r_mult_arr.std() > 0:
                                ic_value, ic_pvalue = stats.pearsonr(comp_scores_arr, r_mult_arr)
                            else:
                                ic_value, ic_pvalue = 0.0, 1.0

                            # Interpretation
                            interpretation = 'noise'
                            if ic_value >= self.IC_THRESHOLDS['strong']:
                                interpretation = 'strong'
                            elif ic_value >= self.IC_THRESHOLDS['moderate']:
                                interpretation = 'moderate'
                            elif ic_value >= self.IC_THRESHOLDS['weak']:
                                interpretation = 'weak'

                            ic_data[component] = {
                                'ic_value': round(float(ic_value), 4),
                                'ic_pvalue': round(float(ic_pvalue), 4),
                                'sample_size': len(comp_scores),
                                'avg_component_score': round(float(comp_scores_arr.mean()), 2),
                                'avg_realized_pnl': round(float(r_mult_arr.mean()), 2),
                                'interpretation': interpretation,
                            }

                    regime_results[regime] = ic_data

                logger.info(f"IC by regime computation complete for {report_date}.")
                return regime_results
        except Exception as e:
            logger.error(f"IC by regime computation failed: {e}")
            return regime_results

    def compute_ic_decay(
        self, report_date: _date, horizons: Optional[List[int]] = None
    ) -> Dict[str, Dict[int, float]]:
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

        decay_results: Dict[str, Dict[int, float]] = {}

        for horizon in horizons:
            ic_results = self.compute_ic(report_date, lookback_trades=horizon)
            for component, ic_data in ic_results.items():
                if component not in decay_results:
                    decay_results[component] = {}
                decay_results[component][horizon] = ic_data['ic_value']

        return decay_results

    def persist(
        self,
        report_date: _date,
        ic_values: Dict[str, Dict[str, float]],
        regime: str = 'unknown',
    ) -> None:
        """
        Persist IC values to algo_component_attribution table.

        Also updates algo_information_coefficient for historical tracking.
        """
        try:
            with DatabaseContext('write') as cur:
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
                            ic_data.get('ic_value'),
                            ic_data.get('ic_pvalue'),
                            ic_data.get('sample_size'),
                            40,
                            ic_data.get('avg_component_score'),
                            ic_data.get('avg_realized_pnl'),
                            regime,
                        ),
                    )

                logger.info(f"Persisted IC for {len(ic_values)} components on {report_date}")
        except Exception as e:
            logger.error(f"Failed to persist IC: {e}")

    def get_trailing_ic(self, component: str, days: int = 60) -> List[Tuple[_date, float]]:
        """
        Get rolling IC for a component over last N days.

        Returns: [(date, ic_value), ...]
        """
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    """
                    SELECT report_date, ic_value FROM algo_component_attribution
                    WHERE component = %s AND report_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY report_date ASC
                    """,
                    (component, days),
                )
                return [(row[0], float(row[1])) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get trailing IC: {e}")
            return []

if __name__ == "__main__":
    engine = SignalAttributionEngine()
    ic_values = engine.compute_ic(_date.today(), lookback_trades=40)
    for comp, data in ic_values.items():
        logger.info(f"{comp}: IC={data['ic_value']:.3f} ({data['interpretation']})")
