#!/usr/bin/env python3
"""Momentum Metrics Loader - 1m/3m/6m/12m trailing returns from price_daily.

Computes momentum as percentage return over lookback periods:
- 1-month (21 trading days)
- 3-month (63 trading days)
- 6-month (126 trading days)
- 12-month (252 trading days)

Requires: price_daily table populated with daily OHLCV data.
Returns explicit data_unavailable markers when insufficient price history.
"""

import psycopg2

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class MomentumMetricsLoader(OptimalLoader):
    """Compute momentum metrics from historical prices."""

    table_name = "momentum_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute momentum metrics for this symbol.

        Returns explicit data_unavailable marker if insufficient price history.
        Momentum requires at least 252 trading days of data for 12-month lookback.
        """
        try:
            metrics = self._compute_momentum_metrics(symbol)
            return [metrics]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[MOMENTUM_METRICS] Database error for {symbol}: {e}")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"database_error: {str(e)[:100]}",
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        except (RuntimeError, ValueError) as e:
            logger.debug(f"[MOMENTUM_METRICS] {symbol}: {e} — insufficient price history (optional enrichment)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": str(e)[:150],
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        except Exception as e:
            logger.warning(
                f"[MOMENTUM_METRICS] Unexpected error for {symbol}: {type(e).__name__}: {e}"
            )
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"unexpected_error: {type(e).__name__}",
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "created_at": datetime.now(timezone.utc),
                }
            ]

    def _compute_momentum_metrics(self, symbol: str) -> dict[str, Any]:
        """Compute 1m/3m/6m/12m momentum from price_daily.

        Raises RuntimeError if insufficient price history (< 252 days).
        """
        with DatabaseContext("read") as cur:
            # Get historical prices (most recent first)
            cur.execute(
                """
                SELECT date, close FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 252
                """,
                (symbol,),
            )
            rows = cur.fetchall()

            if len(rows) < 252:
                raise RuntimeError(f"Insufficient price history: {len(rows)} days (need 252 for 12m momentum)")

            prices = {row["date"]: float(row["close"]) for row in rows}
            sorted_dates = sorted(prices.keys())

            if len(sorted_dates) < 252:
                raise RuntimeError(f"Not enough price data: {len(sorted_dates)} dates (need 252)")

            today = sorted_dates[-1]

            # Define lookback periods (trading days)
            lookback_configs = [
                ("1m", 21),
                ("3m", 63),
                ("6m", 126),
                ("12m", 252),
            ]

            momentum = {}
            for period_name, days_back in lookback_configs:
                # Calculate price from N days ago (as close as possible)
                target_idx = len(sorted_dates) - days_back - 1
                if target_idx < 0:
                    momentum[f"momentum_{period_name}"] = None
                    continue

                price_old = prices[sorted_dates[target_idx]]
                price_new = prices[today]

                if price_old is None or price_old == 0:
                    momentum[f"momentum_{period_name}"] = None
                    continue

                # Return as percentage
                ret_pct = ((price_new - price_old) / price_old) * 100
                momentum[f"momentum_{period_name}"] = round(ret_pct, 4)

            return {
                "symbol": symbol,
                "momentum_1m": momentum.get("momentum_1m"),
                "momentum_3m": momentum.get("momentum_3m"),
                "momentum_6m": momentum.get("momentum_6m"),
                "momentum_12m": momentum.get("momentum_12m"),
                "data_unavailable": False,
                "created_at": datetime.now(timezone.utc),
            }


if __name__ == "__main__":
    run_loader(MomentumMetricsLoader)
