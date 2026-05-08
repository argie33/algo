#!/usr/bin/env python3
"""Safeguard audit logging and performance metrics tracking.

Records every safeguard decision (block/allow) for:
- Compliance audit trail
- Performance analysis
- False positive rate calculation
- Threshold optimization
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class SafeguardAudit:
    """Log and track safeguard decisions for audit and metrics."""

    def __init__(self, config=None):
        self.config = config
        self._ensure_tables_exist()

    def _ensure_tables_exist(self) -> None:
        """Create audit tables if they don't exist."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Safeguard decisions log
            cur.execute("""
                CREATE TABLE IF NOT EXISTS safeguard_audit_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    signal_date DATE,
                    symbol VARCHAR(10),
                    safeguard VARCHAR(50),
                    decision VARCHAR(20),  -- ALLOW, BLOCK
                    reason TEXT,
                    details JSONB,
                    entry_price NUMERIC(10, 2),
                    magnitude FLOAT,  -- How close to threshold?
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Performance metrics
            cur.execute("""
                CREATE TABLE IF NOT EXISTS safeguard_metrics (
                    id SERIAL PRIMARY KEY,
                    date DATE DEFAULT CURRENT_DATE,
                    safeguard VARCHAR(50),
                    total_signals INT DEFAULT 0,
                    allowed INT DEFAULT 0,
                    blocked INT DEFAULT 0,
                    block_rate FLOAT DEFAULT 0.0,
                    false_positive_count INT DEFAULT 0,
                    accuracy_pct FLOAT DEFAULT 0.0,
                    avg_magnitude FLOAT DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, safeguard)
                )
            """)

            # Create indexes for performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_symbol_date
                ON safeguard_audit_log(symbol, signal_date)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_safeguard_date
                ON safeguard_audit_log(safeguard, timestamp)
            """)

            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to create audit tables: {e}")

    def log_decision(self, signal_date: date, symbol: str, safeguard: str,
                     decision: str, reason: str, details: Dict[str, Any] = None,
                     entry_price: float = None, magnitude: float = None) -> bool:
        """Log a safeguard decision (ALLOW or BLOCK)."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO safeguard_audit_log
                (signal_date, symbol, safeguard, decision, reason, details, entry_price, magnitude)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                signal_date,
                symbol,
                safeguard,
                decision.upper(),
                reason,
                str(details or {}),
                entry_price,
                magnitude,
            ))

            conn.commit()
            cur.close()
            conn.close()

            logger.debug(f"Logged {decision} decision for {symbol} ({safeguard})")
            return True
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
            return False

    def get_audit_trail(self, symbol: str = None, safeguard: str = None,
                        days: int = 30, decision: str = None) -> List[Dict[str, Any]]:
        """Retrieve audit trail for analysis."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            query = """
                SELECT id, timestamp, symbol, safeguard, decision, reason, entry_price, magnitude
                FROM safeguard_audit_log
                WHERE timestamp > NOW() - INTERVAL '%s days'
            """
            params = [days]

            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)

            if safeguard:
                query += " AND safeguard = %s"
                params.append(safeguard)

            if decision:
                query += " AND decision = %s"
                params.append(decision.upper())

            query += " ORDER BY timestamp DESC LIMIT 1000"

            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            return [
                {
                    'id': row[0],
                    'timestamp': str(row[1]),
                    'symbol': row[2],
                    'safeguard': row[3],
                    'decision': row[4],
                    'reason': row[5],
                    'entry_price': float(row[6]) if row[6] else None,
                    'magnitude': float(row[7]) if row[7] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve audit trail: {e}")
            return []

    def calculate_daily_metrics(self, eval_date: date = None) -> bool:
        """Calculate daily metrics for all safeguards."""
        if eval_date is None:
            eval_date = date.today()

        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Get unique safeguards from audit log
            cur.execute("""
                SELECT DISTINCT safeguard
                FROM safeguard_audit_log
                WHERE signal_date = %s
            """, (eval_date,))

            safeguards = [row[0] for row in cur.fetchall()]

            for safeguard in safeguards:
                # Count signals
                cur.execute("""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN decision = 'ALLOW' THEN 1 ELSE 0 END) as allowed,
                           SUM(CASE WHEN decision = 'BLOCK' THEN 1 ELSE 0 END) as blocked,
                           AVG(magnitude) as avg_magnitude
                    FROM safeguard_audit_log
                    WHERE signal_date = %s AND safeguard = %s
                """, (eval_date, safeguard))

                row = cur.fetchone()
                total, allowed, blocked, avg_mag = row

                if total == 0:
                    continue

                block_rate = (blocked / total) * 100 if total > 0 else 0

                # Upsert metrics
                cur.execute("""
                    INSERT INTO safeguard_metrics
                    (date, safeguard, total_signals, allowed, blocked, block_rate, avg_magnitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (date, safeguard) DO UPDATE SET
                        total_signals = EXCLUDED.total_signals,
                        allowed = EXCLUDED.allowed,
                        blocked = EXCLUDED.blocked,
                        block_rate = EXCLUDED.block_rate,
                        avg_magnitude = EXCLUDED.avg_magnitude
                """, (eval_date, safeguard, total, allowed, blocked, block_rate, avg_mag))

            conn.commit()
            cur.close()
            conn.close()

            logger.info(f"Daily metrics calculated for {eval_date}")
            return True
        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            return False

    def get_performance_report(self, safeguard: str = None, days: int = 30) -> Dict[str, Any]:
        """Generate performance report for safeguards."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            query = """
                SELECT safeguard, SUM(total_signals) as signals,
                       SUM(blocked) as blocks,
                       AVG(block_rate) as avg_block_rate,
                       MAX(block_rate) as max_block_rate,
                       MIN(block_rate) as min_block_rate
                FROM safeguard_metrics
                WHERE date > NOW()::DATE - INTERVAL '%s days'
            """
            params = [days]

            if safeguard:
                query += " AND safeguard = %s"
                params.append(safeguard)

            query += " GROUP BY safeguard ORDER BY signals DESC"

            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            report = {
                'period_days': days,
                'generated_at': datetime.now().isoformat(),
                'safeguards': [],
                'summary': {
                    'total_signals': 0,
                    'total_blocks': 0,
                    'overall_block_rate': 0.0,
                }
            }

            for row in rows:
                sg_name, signals, blocks, avg_rate, max_rate, min_rate = row
                report['safeguards'].append({
                    'name': sg_name,
                    'signals': signals or 0,
                    'blocks': blocks or 0,
                    'block_rate_avg': round(avg_rate or 0, 2),
                    'block_rate_max': round(max_rate or 0, 2),
                    'block_rate_min': round(min_rate or 0, 2),
                })
                report['summary']['total_signals'] += signals or 0
                report['summary']['total_blocks'] += blocks or 0

            if report['summary']['total_signals'] > 0:
                report['summary']['overall_block_rate'] = round(
                    (report['summary']['total_blocks'] / report['summary']['total_signals']) * 100, 2
                )

            return report
        except Exception as e:
            logger.error(f"Failed to generate performance report: {e}")
            return {}


if __name__ == "__main__":
    audit = SafeguardAudit()

    # Test logging
    audit.log_decision(
        signal_date=date.today(),
        symbol='AAPL',
        safeguard='earnings_blackout',
        decision='BLOCK',
        reason='Within earnings blackout window (1 day before)',
        details={'days_until_earnings': 1},
        entry_price=150.25,
        magnitude=0.14
    )

    print("Audit log entry created")
