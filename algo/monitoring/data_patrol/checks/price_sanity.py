#!/usr/bin/env python3
"""Price sanity checks - extreme moves, corporate actions, sequence continuity."""

import logging

import psycopg2

from utils.safe_data_conversion import safe_float

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN


logger = logging.getLogger(__name__)


class PriceSanityChecker(BaseCheck):
    """Check price data for extreme moves, corporate actions, and sequence gaps."""

    def run(self, cur) -> list[CheckResult]:
        """Execute all price sanity checks."""
        self.results = []

        self.check_price_moves(cur)
        self.check_corporate_actions(cur)
        self.check_sequence_continuity(cur)

        return self.results

    def check_price_moves(self, cur) -> None:
        """Check for extreme day-over-day price moves."""
        try:
            price_cfg = self.config.get_price_sanity_config()
            max_move_pct = price_cfg["max_daily_move_pct"]

            cur.execute(
                """
                WITH d AS (
                    SELECT pd.symbol, pd.date, pd.close,
                           LAG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev
                    FROM price_daily pd
                    WHERE pd.date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '5 days'
                )
                SELECT symbol, date, close, prev,
                       ABS(close - prev) / NULLIF(prev, 0) * 100 AS pct_change
                FROM d
                WHERE prev IS NOT NULL
                  AND ABS(close - prev) / NULLIF(prev, 0) > %s
                  AND date = (SELECT MAX(date) FROM price_daily)
                ORDER BY pct_change DESC
                LIMIT 20
            """,
                (max_move_pct,),
            )
            extreme = cur.fetchall()

            if len(extreme) > 10:
                self.log(
                    "price_sanity",
                    WARN,
                    "price_daily",
                    f"{len(extreme)} symbols with >{max_move_pct * 100:.0f}% day-over-day move",
                    {
                        "count": len(extreme),
                        "samples": [{"symbol": r[0], "pct_change": safe_float(r[4], default=0.0, context="r[4]")} for r in extreme[:5]],
                    },
                )
            elif extreme:
                self.log(
                    "price_sanity",
                    INFO,
                    "price_daily",
                    f"{len(extreme)} extreme moves (likely real events)",
                    {"samples": [{"symbol": r[0], "pct_change": safe_float(r[4], default=0.0, context="r[4]")} for r in extreme[:5]]},
                )
            else:
                self.log(
                    "price_sanity",
                    INFO,
                    "price_daily",
                    "No extreme moves detected",
                    None,
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            self.log("price_sanity", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_corporate_actions(self, cur) -> None:
        """Detect likely corporate actions (splits, halts, delistings)."""
        try:
            corp_cfg = self.config.get_corporate_actions_config()
            lookback_days = corp_cfg["lookback_days"]
            drop_ratio = corp_cfg["drop_ratio"]

            cur.execute(
                f"""
                WITH d AS (
                    SELECT pd.symbol, pd.date, pd.close,
                           LAG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev,
                           LAG(pd.date) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS prev_date
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
                )
                SELECT symbol, date, close, prev,
                       (close - prev) / NULLIF(prev, 0) * 100 AS pct_change
                FROM d
                WHERE prev IS NOT NULL
                  AND date = prev_date + INTERVAL '1 day'
                  AND (close - prev) / NULLIF(prev, 0) < {drop_ratio}
                ORDER BY pct_change ASC
                LIMIT 50
            """
            )
            extreme_drops = cur.fetchall()

            if extreme_drops:
                self.log(
                    "corporate_action",
                    WARN,
                    "price_daily",
                    f"{len(extreme_drops)} symbols with >{drop_ratio * -100:.0f}% single-day drop (likely corporate action)",
                    {
                        "count": len(extreme_drops),
                        "samples": [
                            {
                                "symbol": r[0],
                                "date": str(r[1]),
                                "pct_drop": round(r[4], 1),
                            }
                            for r in extreme_drops[:10]
                        ],
                    },
                )
            else:
                self.log(
                    "corporate_action",
                    INFO,
                    "price_daily",
                    "No extreme drops detected (no obvious corporate actions)",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("corporate_action", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_sequence_continuity(self, cur) -> None:
        """Check trading-day sequence for gaps."""
        try:
            cur.execute("""
                WITH d AS (
                    SELECT date, LAG(date) OVER (ORDER BY date) AS prev
                    FROM price_daily
                    WHERE symbol = 'SPY'
                      AND date >= CURRENT_DATE - INTERVAL '60 days'
                )
                SELECT date, prev, (date - prev) AS gap_days
                FROM d
                WHERE prev IS NOT NULL AND (date - prev) > 4
                ORDER BY date DESC
                LIMIT 5
            """)
            gaps = cur.fetchall()

            if gaps:
                self.log(
                    "sequence",
                    WARN,
                    "price_daily",
                    f"{len(gaps)} sequence gaps in SPY (last 60 days)",
                    {"gaps": [{"date": str(r[0]), "days": int(r[2])} for r in gaps]},
                )
            else:
                self.log(
                    "sequence",
                    INFO,
                    "price_daily",
                    "SPY price sequence contiguous",
                    None,
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            self.log("sequence", ERROR, "price_daily", f"Check failed: {e}", None)
