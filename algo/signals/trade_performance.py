#!/usr/bin/env python3

"""
Signal Trade Performance Populator — extract component scores + realized P&L from closed trades.

Reads closed algo_trades (with swing_components JSONB + exit_r_multiple),
computes per-trade attribution, persists to signal_trade_performance.

Enables Information Coefficient (IC) calculation per component.
"""

import json
import logging
from datetime import date as _date
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from utils.db import DatabaseContext


try:
    from scipy.stats import pearsonr
except ImportError:

    def pearsonr(x, y):
        return (float("nan"), float("nan"))


logger = logging.getLogger(__name__)


class SignalTradePerformancePopulator:
    """Extract component attribution from closed trades."""

    def populate_closed_trades(self, lookback_days: int = 7) -> Dict[str, Any]:
        try:
            with DatabaseContext("write") as cur:
                # Find closed trades not yet in signal_trade_performance
                cutoff_date = _date.today() - timedelta(days=lookback_days)

                cur.execute(
                    """
                    SELECT t.id, t.symbol, t.signal_date, t.exit_date,
                           t.entry_price, t.exit_price, t.entry_quantity,
                           t.exit_r_multiple, t.profit_loss_dollars, t.swing_score,
                           t.swing_components, t.trend_template_score,
                           COALESCE((t.exit_date::date - t.trade_date::date), 0) AS holding_days
                    FROM algo_trades t
                    WHERE t.status = 'closed'
                      AND t.exit_date >= %s
                      AND NOT EXISTS (
                          SELECT 1 FROM signal_trade_performance stp
                          WHERE stp.trade_id = t.id
                      )
                    ORDER BY t.exit_date DESC
                    """,
                    (cutoff_date,),
                )
                closed_trades = cur.fetchall()

                if not closed_trades:
                    return {
                        "success": True,
                        "trades_processed": 0,
                        "message": f"No new closed trades to populate (lookback {lookback_days}d)",
                    }

                inserted_count = 0
                component_returns: Dict[str, List[Tuple[float, float]]] = {
                    comp: []
                    for comp in [
                        "setup_quality",
                        "trend_quality",
                        "momentum_rs",
                        "volume",
                        "fundamentals",
                        "sector_industry",
                        "multi_timeframe",
                    ]
                }

                for row in closed_trades:
                    (
                        trade_id_int,
                        symbol,
                        signal_date,
                        exit_date,
                        entry_price,
                        exit_price,
                        entry_qty,
                        exit_r_multiple,
                        pnl_dollars,
                        swing_score,
                        swing_components_json,
                        trend_score,
                        holding_days,
                    ) = row

                    # Parse swing_components JSONB
                    try:
                        swing_comp = (
                            json.loads(swing_components_json)
                            if swing_components_json
                            else {}
                        )
                    except (json.JSONDecodeError, TypeError):
                        swing_comp = {}

                    # Extract component scores (normalize to 0-1 scale: pts/max)
                    component_scores = {}
                    for comp_name, comp_data in swing_comp.items():
                        if isinstance(comp_data, dict):
                            pts = float(comp_data.get("pts", 0))
                            max_pts = float(comp_data.get("max", 1))
                            normalized_score = (pts / max_pts) if max_pts > 0 else 0
                            component_scores[comp_name] = normalized_score

                            # Track for IC calculation
                            if (
                                comp_name in component_returns
                                and exit_r_multiple is not None
                            ):
                                component_returns[comp_name].append(
                                    (normalized_score, float(exit_r_multiple))
                                )

                    # Insert into signal_trade_performance (only columns that exist in schema)
                    try:
                        cur.execute(
                            """
                            INSERT INTO signal_trade_performance (
                                trade_id, symbol, signal_date, exit_date,
                                entry_price, exit_price,
                                realized_pnl, realized_pnl_pct,
                                hold_days, swing_score, trend_score,
                                r_multiple, win,
                                created_at
                            ) VALUES (
                                %s, %s, %s, %s,
                                %s, %s,
                                %s, %s,
                                %s, %s, %s,
                                %s, %s,
                                CURRENT_TIMESTAMP
                            )
                            ON CONFLICT (trade_id) DO NOTHING
                            """,
                            (
                                trade_id_int,
                                symbol,
                                signal_date,
                                exit_date,
                                float(entry_price) if entry_price else 0,
                                float(exit_price) if exit_price else 0,
                                float(pnl_dollars) if pnl_dollars else 0,
                                (
                                    (
                                        float(pnl_dollars)
                                        / float(entry_price * entry_qty)
                                    )
                                    if (
                                        pnl_dollars is not None
                                        and entry_price
                                        and entry_qty
                                        and entry_price * entry_qty != 0
                                    )
                                    else 0
                                ),
                                int(holding_days) if holding_days else 0,
                                float(swing_score) if swing_score else 0,
                                float(trend_score) if trend_score else 0,
                                float(exit_r_multiple) if exit_r_multiple else 0,
                                (
                                    bool(exit_r_multiple and exit_r_multiple > 0)
                                    if exit_r_multiple
                                    else False
                                ),
                            ),
                        )
                        inserted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert trade {trade_id_int}: {e}")
                        continue

            # Compute IC values for all components with 2+ data points
            ic_values = {}
            for comp_name, data_points in component_returns.items():
                if len(data_points) >= 2:
                    scores = [x[0] for x in data_points]
                    returns = [x[1] for x in data_points]
                    try:
                        ic, pvalue = pearsonr(scores, returns)
                        ic_values[comp_name] = {
                            "ic": round(float(ic), 4),
                            "pvalue": round(float(pvalue), 4),
                            "sample_size": len(data_points),
                        }
                    except Exception as e:
                        logger.debug(f"IC calculation failed for {comp_name}: {e}")

            logger.info(
                f"Populated {inserted_count} closed trades to signal_trade_performance"
            )
            return {
                "success": True,
                "trades_processed": inserted_count,
                "ic_values": ic_values,
                "message": f"Inserted {inserted_count} trades, computed IC for {len(ic_values)} components",
            }

        except Exception as e:
            logger.error(
                f"Signal trade performance population failed: {e}", exc_info=True
            )
            return {
                "success": False,
                "trades_processed": 0,
                "message": f"Error: {str(e)[:100]}",
            }

    _VALID_COMPONENTS = frozenset(
        {
            "setup_quality",
            "trend_quality",
            "momentum_rs",
            "volume",
            "fundamentals",
            "sector_industry",
            "multi_timeframe",
        }
    )

    def get_trailing_ic(self, component: str, days: int = 60) -> List[Dict[str, Any]]:
        """
        Get rolling IC for a component over trailing period.

        Returns:
            [{'date': date, 'ic': float, 'sample_size': int, 'pvalue': float}, ...]
        """
        if component not in self._VALID_COMPONENTS:
            logger.warning(f"get_trailing_ic: unknown component '{component}'")
            return []
        col = f"{component}_score"
        try:
            with DatabaseContext("read") as cur:
                cutoff = _date.today() - timedelta(days=days)

                # For each exit_date, compute IC using trades exited on/before that date
                cur.execute(
                    """
                    WITH daily_ic AS (
                        SELECT
                            exit_date,
                            COUNT(*) as sample_size,
                            CORR({col}, exit_r_multiple) as ic_corr
                        FROM signal_trade_performance
                        WHERE exit_date >= %s
                        GROUP BY exit_date
                    )
                    SELECT exit_date, ic_corr, sample_size
                    FROM daily_ic
                    WHERE ic_corr IS NOT NULL
                    ORDER BY exit_date DESC
                    """,
                    (cutoff,),
                )
                rows = cur.fetchall()

                return [
                    {
                        "date": str(row[0]),
                        "ic": round(float(row[1]), 4) if row[1] else 0,
                        "sample_size": int(row[2]),
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.warning(f"Rolling IC calculation failed for {component}: {e}")
            return []
