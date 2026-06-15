#!/usr/bin/env python3

from utils.db import DatabaseContext
from datetime import date
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class RejectionTracker:
    """Track signal rejections through filter pipeline for explainability."""

    def _with_cursor(self, operation):
        """Execute operation with cursor via DatabaseContext."""
        try:
            with DatabaseContext("write") as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            return None

    def __init__(self):
        pass

    def log_rejection(
        self,
        eval_date: date,
        symbol: str,
        entry_price: float,
        tier_results: Dict,
        advanced_results: Optional[Dict] = None,
    ):
        """Log signal rejection with reason at each tier."""

        def _log_rejection(cur):
            rejected_at_tier = None
            for tier in [1, 2, 3, 4, 5]:
                if not tier_results.get(tier, {}).get("pass", False):
                    rejected_at_tier = tier
                    break

            rejection_reason = ""
            if rejected_at_tier:
                rejection_reason = tier_results.get(rejected_at_tier, {}).get(
                    "reason", "Unknown"
                )

            cur.execute(
                """
                INSERT INTO filter_rejection_log
                (eval_date, symbol, entry_price, rejected_at_tier, rejection_reason,
                 tier_1_pass, tier_2_pass, tier_2_reason,
                 tier_3_pass, tier_3_reason, tier_4_pass, tier_4_reason,
                 tier_5_pass, tier_5_reason, advanced_checks_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    eval_date,
                    symbol,
                    entry_price,
                    rejected_at_tier,
                    rejection_reason,
                    tier_results.get(1, {}).get("pass", False),
                    tier_results.get(2, {}).get("pass", False),
                    tier_results.get(2, {}).get("reason", ""),
                    tier_results.get(3, {}).get("pass", False),
                    tier_results.get(3, {}).get("reason", ""),
                    tier_results.get(4, {}).get("pass", False),
                    tier_results.get(4, {}).get("reason", ""),
                    tier_results.get(5, {}).get("pass", False),
                    tier_results.get(5, {}).get("reason", ""),
                    advanced_results.get("reason", "") if advanced_results else None,
                ),
            )

        try:
            self._with_cursor(_log_rejection)
        except Exception as e:
            logger.error(f"Failed to log rejection for {symbol}: {e}")

    def log_pre_tier_rejection(
        self,
        eval_date: date,
        symbol: str,
        tier_0_reason: str,
        entry_price: float = None,
    ):
        """Log signal rejection at pre-tier stage (before Tier 1)."""

        def _log_pre_tier(cur):
            cur.execute(
                """
                INSERT INTO filter_rejection_log
                (eval_date, symbol, entry_price, rejected_at_tier, rejection_reason,
                 tier_0_pass, tier_0_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    eval_date,
                    symbol,
                    entry_price,
                    0,
                    tier_0_reason,
                    False,
                    tier_0_reason,
                ),
            )

        try:
            self._with_cursor(_log_pre_tier)
        except Exception as e:
            logger.error(f"Failed to log pre-tier rejection for {symbol}: {e}")

    def get_rejection_funnel(self, eval_date: date):
        """Get rejection counts by tier for funnel visualization."""

        def _get_funnel(cur):
            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
                    SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
                    SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
                    SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
                    SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
                FROM filter_rejection_log
                WHERE eval_date = %s
            """,
                (eval_date,),
            )

            row = cur.fetchone()
            if not row:
                return {"total_signals": 0, "tiers": []}

            total, t1, t2, t3, t4, t5 = row
            t1 = t1 or 0
            t2 = t2 or 0
            t3 = t3 or 0
            t4 = t4 or 0
            t5 = t5 or 0

            return {
                "total_signals": total,
                "tiers": [
                    {
                        "tier": 1,
                        "name": "Data Quality",
                        "pass": t1,
                        "reject": total - t1,
                    },
                    {"tier": 2, "name": "Market Health", "pass": t2, "reject": t1 - t2},
                    {
                        "tier": 3,
                        "name": "Trend Confirmation",
                        "pass": t3,
                        "reject": t2 - t3,
                    },
                    {
                        "tier": 4,
                        "name": "Signal Quality",
                        "pass": t4,
                        "reject": t3 - t4,
                    },
                    {
                        "tier": 5,
                        "name": "Portfolio Health",
                        "pass": t5,
                        "reject": t4 - t5,
                    },
                ],
            }

        try:
            return self._with_cursor(_get_funnel) or {"total_signals": 0, "tiers": []}
        except Exception as e:
            logger.error(f"Failed to get rejection funnel: {e}")
            return {"total_signals": 0, "tiers": []}

    def get_rejection_reasons(self, eval_date: date, tier: int, limit: int = 20):
        """Get top rejection reasons for a specific tier."""

        def _get_reasons(cur):
            col_name = f"tier_{tier}_reason"
            cur.execute(
                """
                SELECT
                    {col_name} as reason,
                    COUNT(*) as count,
                    ARRAY_AGG(symbol ORDER BY symbol) as symbols
                FROM filter_rejection_log
                WHERE eval_date = %s AND {col_name} IS NOT NULL AND {col_name} != ''
                GROUP BY reason
                ORDER BY count DESC
                LIMIT %s
            """,
                (eval_date, limit),
            )

            results = []
            for row in cur.fetchall():
                results.append(
                    {
                        "reason": row[0],
                        "count": row[1],
                        "symbols": row[2][:5],
                        "total_symbols": len(row[2]),
                    }
                )

            return results

        try:
            return self._with_cursor(_get_reasons) or []
        except Exception as e:
            logger.error(f"Failed to get rejection reasons for tier {tier}: {e}")
            return []

    def get_signals_by_rejection_status(self, eval_date: date):
        """Get summary of signals by whether they were rejected and at which tier."""

        def _get_status(cur):
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as qualified,
                    SUM(CASE WHEN NOT tier_1_pass THEN 1 ELSE 0 END) as t1_reject,
                    SUM(CASE WHEN tier_1_pass AND NOT tier_2_pass THEN 1 ELSE 0 END) as t2_reject,
                    SUM(CASE WHEN tier_2_pass AND NOT tier_3_pass THEN 1 ELSE 0 END) as t3_reject,
                    SUM(CASE WHEN tier_3_pass AND NOT tier_4_pass THEN 1 ELSE 0 END) as t4_reject,
                    SUM(CASE WHEN tier_4_pass AND NOT tier_5_pass THEN 1 ELSE 0 END) as t5_reject
                FROM filter_rejection_log
                WHERE eval_date = %s
            """,
                (eval_date,),
            )

            row = cur.fetchone()
            if not row:
                return {}

            return {
                "qualified": row[0] or 0,
                "rejected_tier_1": row[1] or 0,
                "rejected_tier_2": row[2] or 0,
                "rejected_tier_3": row[3] or 0,
                "rejected_tier_4": row[4] or 0,
                "rejected_tier_5": row[5] or 0,
            }

        try:
            return self._with_cursor(_get_status) or {}
        except Exception as e:
            logger.error(f"Failed to get rejection summary: {e}")
            return {}
