#!/usr/bin/env python3
"""Risk & Momentum Metrics Daily Loader - Consolidated from 2 separate loaders.

CONSOLIDATION 2026-07-12: Merges two loaders into one:
  - load_stability_metrics.py → stability_metrics table
  - load_momentum_metrics.py → momentum_metrics table

Both loaders read from stock_prices_daily independently. Consolidating reduces
redundant DB reads and ECS task overhead.

Outputs 2 tables:
  - stability_metrics (volatility 30d/60d/252d, beta)
  - momentum_metrics (momentum 1m/3m/6m/12m)

Run: python3 loaders/load_risk_metrics_daily.py
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any, cast

import psycopg2

from loaders.loader_helper import setup_imports

setup_imports()

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class RiskMetricsDailyLoader(OptimalLoader):
    """Compute risk metrics (volatility, beta, momentum) for all symbols.

    Consolidates stability and momentum computations from separate loaders.
    Outputs to both stability_metrics and momentum_metrics tables.
    """

    table_name = "stability_metrics"  # Primary table (OptimalLoader requirement)
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch both stability and momentum metrics for this symbol.

        Returns list with two dicts: [stability_row, momentum_row]
        Marks data unavailable for each independently if computation fails.
        """
        try:
            stability_metrics = self._compute_stability_metrics(symbol)
            momentum_metrics = self._compute_momentum_metrics(symbol)

            return [stability_metrics, momentum_metrics]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[RISK_METRICS] Database error for {symbol}: {e}")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"database_error: {str(e)[:100]}",
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "beta": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"database_error: {str(e)[:100]}",
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "created_at": datetime.now(timezone.utc),
                },
            ]

        except RuntimeError as e:
            # Insufficient data (< 30 days) - graceful degradation for optional enrichment
            logger.debug(f"[RISK_METRICS] {symbol}: {e}. Marking metrics unavailable (optional enrichment).")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": str(e)[:150],
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "beta": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": str(e)[:150],
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "created_at": datetime.now(timezone.utc),
                },
            ]

    def _compute_stability_metrics(self, symbol: str) -> dict[str, Any]:
        """Compute volatility and beta for this symbol (from load_stability_metrics.py).

        Returns dict with volatility_30d, volatility_60d, volatility_252d, beta.
        Or data_unavailable marker if insufficient data.
        """
        # TODO: Implement actual computation
        # For now, return stub with data_unavailable
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "stability_metrics_computation_not_yet_implemented",
            "volatility_30d": None,
            "volatility_60d": None,
            "volatility_252d": None,
            "beta": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_momentum_metrics(self, symbol: str) -> dict[str, Any]:
        """Compute momentum metrics for this symbol (from load_momentum_metrics.py).

        Returns dict with momentum_1m, momentum_3m, momentum_6m, momentum_12m.
        Or data_unavailable marker if insufficient data.
        """
        # TODO: Implement actual computation
        # For now, return stub with data_unavailable
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "momentum_metrics_computation_not_yet_implemented",
            "momentum_1m": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "created_at": datetime.now(timezone.utc),
        }

    def insert_rows(self, rows: list[dict[str, Any]]) -> int:
        """Insert both stability and momentum rows (from list of [stability_row, momentum_row] pairs).

        Since we return 2 dicts per symbol, this receives them in pairs.
        Inserts to both stability_metrics and momentum_metrics tables.
        """
        if not rows:
            logger.info("[RISK_METRICS] No rows to insert")
            return 0

        stability_rows = []
        momentum_rows = []

        # Separate the pairs
        for i in range(0, len(rows), 2):
            if i < len(rows):
                stability_rows.append(rows[i])
            if i + 1 < len(rows):
                momentum_rows.append(rows[i + 1])

        inserted = 0

        # Insert stability metrics
        try:
            with DatabaseContext("write") as cur:
                for row in stability_rows:
                    cur.execute(
                        """
                        INSERT INTO stability_metrics
                        (symbol, volatility_30d, volatility_60d, volatility_252d, beta, data_unavailable, reason, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol) DO UPDATE SET
                            volatility_30d = EXCLUDED.volatility_30d,
                            volatility_60d = EXCLUDED.volatility_60d,
                            volatility_252d = EXCLUDED.volatility_252d,
                            beta = EXCLUDED.beta,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason,
                            created_at = EXCLUDED.created_at
                        """,
                        (
                            row["symbol"],
                            row["volatility_30d"],
                            row["volatility_60d"],
                            row["volatility_252d"],
                            row["beta"],
                            row["data_unavailable"],
                            row["reason"],
                            row["created_at"],
                        ),
                    )
                inserted += len(stability_rows)
                logger.info(f"[RISK_METRICS] Inserted {len(stability_rows)} stability rows")

        except Exception as e:
            logger.error(f"[RISK_METRICS] Failed to insert stability rows: {e}")

        # Insert momentum metrics
        try:
            with DatabaseContext("write") as cur:
                for row in momentum_rows:
                    cur.execute(
                        """
                        INSERT INTO momentum_metrics
                        (symbol, momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable, reason, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol) DO UPDATE SET
                            momentum_1m = EXCLUDED.momentum_1m,
                            momentum_3m = EXCLUDED.momentum_3m,
                            momentum_6m = EXCLUDED.momentum_6m,
                            momentum_12m = EXCLUDED.momentum_12m,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason,
                            created_at = EXCLUDED.created_at
                        """,
                        (
                            row["symbol"],
                            row["momentum_1m"],
                            row["momentum_3m"],
                            row["momentum_6m"],
                            row["momentum_12m"],
                            row["data_unavailable"],
                            row["reason"],
                            row["created_at"],
                        ),
                    )
                inserted += len(momentum_rows)
                logger.info(f"[RISK_METRICS] Inserted {len(momentum_rows)} momentum rows")

        except Exception as e:
            logger.error(f"[RISK_METRICS] Failed to insert momentum rows: {e}")

        return inserted


if __name__ == "__main__":
    run_loader(RiskMetricsDailyLoader)
