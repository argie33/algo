#!/usr/bin/env python3
"""
Trade Performance Auditor - Analyze exit performance for closed trades.

Called by algo_exit_engine.py after trades are closed to record:
- Exit price vs. targets/stops
- Duration held
- Realized P&L
- Win/loss classification
"""

import logging
import psycopg2
from datetime import datetime, date
from typing import Dict, Any, Optional
import os
from credential_helper import get_db_password

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = logging.getLogger(__name__)


class TradePerformanceAuditor:
    """Audit closed trades for performance metrics."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize auditor with config."""
        self.config = config
        self.conn = None

    def _get_db_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": get_db_password(),
            "database": os.getenv("DB_NAME", "stocks"),
        }

    def connect(self):
        """Connect to database if not already connected."""
        if not self.conn:
            try:
                self.conn = psycopg2.connect(**self._get_db_config())
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                self.conn = None

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def audit_exit(self, trade_id: int) -> bool:
        """
        Audit a closed trade for performance analysis.

        Records:
        - Exit classification (win/loss)
        - P&L metrics
        - Duration held
        - Exit reason accuracy

        Args:
            trade_id: ID of the closed trade

        Returns:
            True if audit successful
        """
        self.connect()
        if not self.conn:
            logger.error(f"Cannot audit trade {trade_id}: no database connection")
            return False

        try:
            cur = self.conn.cursor()

            # Fetch trade details
            cur.execute("""
                SELECT
                    t.trade_id, t.symbol, t.entry_price, t.exit_price,
                    t.entry_date, t.exit_date, t.status,
                    t.target_1_price, t.target_2_price, t.target_3_price,
                    t.stop_loss_price,
                    p.quantity, p.realized_pnl, p.realized_pnl_pct
                FROM algo_trades t
                LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.trade_id = %s
            """, (trade_id,))

            row = cur.fetchone()
            if not row:
                logger.warning(f"Trade {trade_id} not found")
                cur.close()
                return False

            (trade_id, symbol, entry_price, exit_price, entry_date, exit_date, status,
             target_1, target_2, target_3, stop_loss,
             quantity, realized_pnl, realized_pnl_pct) = row

            # Analyze trade result
            if not exit_price or not entry_price:
                logger.warning(f"Trade {trade_id} ({symbol}): missing prices, skipping audit")
                cur.close()
                return False

            entry_price = float(entry_price)
            exit_price = float(exit_price)
            quantity = int(quantity) if quantity else 0
            realized_pnl = float(realized_pnl) if realized_pnl else 0.0
            realized_pnl_pct = float(realized_pnl_pct) if realized_pnl_pct else 0.0

            # Calculate duration
            if entry_date and exit_date:
                duration_days = (exit_date - entry_date).days
            else:
                duration_days = 0

            # Classify result
            price_change_pct = ((exit_price - entry_price) / entry_price) * 100
            win_loss = "WIN" if exit_price > entry_price else "LOSS" if exit_price < entry_price else "NEUTRAL"

            # Determine which target/stop was hit (if any)
            target_hit = None
            if target_1 and exit_price >= float(target_1):
                target_hit = "TARGET_1"
            if target_2 and exit_price >= float(target_2):
                target_hit = "TARGET_2"
            if target_3 and exit_price >= float(target_3):
                target_hit = "TARGET_3"
            if stop_loss and exit_price <= float(stop_loss):
                target_hit = "STOP_LOSS"

            # Log audit result
            logger.info(
                f"[AUDIT] {symbol} (trade {trade_id}): {win_loss} | "
                f"{entry_price:.2f} → {exit_price:.2f} ({price_change_pct:+.2f}%) | "
                f"held {duration_days}d | P&L {realized_pnl:+.2f} ({realized_pnl_pct:+.2f}%)"
                f"{' | ' + target_hit if target_hit else ''}"
            )

            cur.close()
            return True

        except Exception as e:
            logger.error(f"Failed to audit trade {trade_id}: {e}")
            return False
        finally:
            self.disconnect()
