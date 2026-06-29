#!/usr/bin/env python3
"""Price data validation and auditing for position reconciliation.

Extracted from DailyReconciliation to handle price quality checks and
stale data detection.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


class PriceAuditor:
    """Validates price data freshness and quality.

    Responsibilities:
    - Check for stale estimated prices
    - Validate price data age
    - Alert on stale data
    """

    def __init__(self, config: Any):
        """Initialize with configuration."""
        self.config = config
        # Stale price threshold: if no update in 2 hours, consider stale
        self.STALE_THRESHOLD = timedelta(hours=2)

    def audit_stale_estimated_prices(self, cur: Any) -> dict[str, Any]:
        """Check if estimated prices for open positions are stale.

        Returns dict with:
        - stale_count: number of positions with stale prices
        - stale_symbols: list of symbols with stale prices
        - details: per-symbol stale status {symbol: {age_hours, is_stale}}

        Raises:
            RuntimeError: If query fails (database error)
        """
        result: dict[str, Any] = {
            "stale_count": 0,
            "stale_symbols": [],
            "details": {},
        }

        try:
            # Query estimated prices for open positions
            cur.execute("""
                SELECT DISTINCT
                    at.symbol,
                    at.estimated_exit_price,
                    at.exit_price_reconciled_at,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - at.exit_price_reconciled_at)) / 3600.0 as age_hours
                FROM algo_trades at
                WHERE at.status IN ('open', 'filled', 'active', 'partially_filled')
                  AND at.exit_date IS NULL
                  AND at.estimated_exit_price IS NOT NULL
                ORDER BY at.symbol
            """)
            rows = cur.fetchall()

            stale_count = 0
            stale_symbols = []

            for row in rows:
                symbol = row[0]
                estimated_price = row[1]
                reconciled_at = row[2]
                age_hours = float(row[3]) if row[3] is not None else None

                if estimated_price is None or reconciled_at is None or age_hours is None:
                    # Price not estimated yet, not stale
                    result["details"][symbol] = {
                        "age_hours": age_hours,
                        "is_stale": False,
                        "reason": "price not estimated",
                    }
                    continue

                is_stale = age_hours > self.STALE_THRESHOLD.total_seconds() / 3600.0
                if is_stale:
                    stale_count += 1
                    stale_symbols.append(symbol)

                result["details"][symbol] = {
                    "age_hours": round(age_hours, 1),
                    "is_stale": is_stale,
                    "threshold_hours": self.STALE_THRESHOLD.total_seconds() / 3600.0,
                    "estimated_price": float(estimated_price),
                }

            result["stale_count"] = stale_count
            result["stale_symbols"] = stale_symbols

            if stale_count > 0:
                logger.warning(f"[PRICE_AUDIT] Found {stale_count} positions with stale estimated prices: {stale_symbols}")
            else:
                logger.info("[PRICE_AUDIT] All estimated prices are fresh")

        except Exception as e:
            logger.error(f"[PRICE_AUDIT] Failed to audit stale estimated prices: {e}")
            raise RuntimeError(f"[PRICE_AUDIT] Price audit failed: {e}") from e

        return result

    def validate_price_freshness(self, price_timestamp: datetime) -> bool:
        """Check if price data is fresh enough for reconciliation.

        Args:
            price_timestamp: Last update time of price data (must be timezone-aware)

        Returns:
            True if fresh, False if stale
        """
        if price_timestamp is None:
            return False
        age = datetime.now(timezone.utc) - price_timestamp
        return age < self.STALE_THRESHOLD
