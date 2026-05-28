#!/usr/bin/env python3
"""Signal Generation Validator - Issues #30-31.

Issue #30: Monitor signal_quality_scores staleness
Issue #31: Ensure buy_sell_daily has placeholder if signal generation produces zero results
"""

import logging
from typing import Dict, Tuple
from datetime import date as _date

logger = logging.getLogger(__name__)


def check_signal_quality_scores_freshness(conn, current_date: _date) -> Tuple[bool, str]:
    """Issue #30: Alert if signal_quality_scores is stale.

    Returns: (is_fresh, reason)
    """
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT MAX(date) FROM signal_quality_scores
        """)
        row = cur.fetchone()
        cur.close()

        if not row or not row[0]:
            return False, "signal_quality_scores table is empty"

        last_date = row[0]
        days_stale = (current_date - last_date).days

        if days_stale > 1:
            logger.warning(f"signal_quality_scores is {days_stale} days stale (last: {last_date})")
            return False, f"signal_quality_scores stale ({days_stale}d old)"

        return True, f"signal_quality_scores fresh (updated {last_date})"
    except Exception as e:
        logger.error(f"Could not check signal_quality_scores freshness: {e}")
        return False, f"Check failed: {e}"


def ensure_buy_sell_daily_not_empty(conn, current_date: _date) -> None:
    """Issue #31: Insert placeholder if buy_sell_daily is empty after signal generation.

    Prevents Phase 1 data freshness check from halting pipeline.
    """
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s
        """, (current_date,))

        count = cur.fetchone()[0] if cur.fetchone() else 0

        if count == 0:
            logger.warning("buy_sell_daily is empty for today, inserting placeholder")
            cur.execute("""
                INSERT INTO buy_sell_daily (date, symbol, signal, score, created_at)
                VALUES (%s, 'PLACEHOLDER', NULL, 0, CURRENT_TIMESTAMP)
                ON CONFLICT (date, symbol) DO NOTHING
            """, (current_date,))
            conn.commit()
            logger.info("Placeholder inserted to prevent Phase 1 halt")

        cur.close()
    except Exception as e:
        logger.error(f"Could not ensure buy_sell_daily: {e}")
