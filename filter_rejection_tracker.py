#!/usr/bin/env python3
"""
Filter Pipeline Rejection Tracking

Logs every signal through all 5 tiers + advanced filters.
Captures rejection reason at each tier for explainability.

Enables:
- Rejection funnel analysis: 150 signals -> 80 pass T1 -> 30 pass T2 -> 8 qualified
- Per-gate rejection counts: "Distribution days blocked 20 signals"
- Tuning feedback: "If we loosen Tier 2, we get 5 additional trades"
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date
import logging
from typing import Dict, List, Optional

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class RejectionTracker:
    """Track signal rejections through filter pipeline for explainability."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def log_rejection(self, eval_date: date, symbol: str, entry_price: float,
                      tier_results: Dict, advanced_results: Optional[Dict] = None):
        """
        Log signal rejection with reason at each tier.

        Args:
            eval_date: Evaluation date
            symbol: Stock symbol
            entry_price: Entry price from signal
            tier_results: dict {
                1: {'pass': bool, 'reason': '...'},
                2: {'pass': bool, 'reason': '...'},
                ...
            }
            advanced_results: dict with 'reason' key (optional)
        """
        self.connect()

        try:
            # Find which tier rejected it (first tier that failed)
            rejected_at_tier = None
            for tier in [1, 2, 3, 4, 5]:
                if not tier_results.get(tier, {}).get('pass', False):
                    rejected_at_tier = tier
                    break

            rejection_reason = ''
            if rejected_at_tier:
                rejection_reason = tier_results.get(rejected_at_tier, {}).get('reason', 'Unknown')

            # Build rejection log entry
            self.cur.execute("""
                INSERT INTO filter_rejection_log
                (eval_date, symbol, entry_price, rejected_at_tier, rejection_reason,
                 tier_1_pass, tier_2_pass, tier_2_reason,
                 tier_3_pass, tier_3_reason, tier_4_pass, tier_4_reason,
                 tier_5_pass, tier_5_reason, advanced_checks_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                eval_date,
                symbol,
                entry_price,
                rejected_at_tier,
                rejection_reason,
                tier_results.get(1, {}).get('pass', False),
                tier_results.get(2, {}).get('pass', False),
                tier_results.get(2, {}).get('reason', ''),
                tier_results.get(3, {}).get('pass', False),
                tier_results.get(3, {}).get('reason', ''),
                tier_results.get(4, {}).get('pass', False),
                tier_results.get(4, {}).get('reason', ''),
                tier_results.get(5, {}).get('pass', False),
                tier_results.get(5, {}).get('reason', ''),
                advanced_results.get('reason', '') if advanced_results else None
            ))

            self.conn.commit()

        except Exception as e:
            log.error(f"Failed to log rejection for {symbol}: {e}")
            self.conn.rollback()

        finally:
            self.disconnect()

    def get_rejection_funnel(self, eval_date: date):
        """
        Get rejection counts by tier for funnel visualization.

        Returns:
            dict {
                'total_signals': 150,
                'tier_1': {'pass': 100, 'reject': 50},
                'tier_2': {'pass': 80, 'reject': 20},
                ...
            }
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN tier_1_pass THEN 1 ELSE 0 END) as t1_pass,
                    SUM(CASE WHEN tier_2_pass THEN 1 ELSE 0 END) as t2_pass,
                    SUM(CASE WHEN tier_3_pass THEN 1 ELSE 0 END) as t3_pass,
                    SUM(CASE WHEN tier_4_pass THEN 1 ELSE 0 END) as t4_pass,
                    SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as t5_pass
                FROM filter_rejection_log
                WHERE eval_date = %s
            """, (eval_date,))

            row = self.cur.fetchone()
            if not row:
                return {
                    'total_signals': 0,
                    'tiers': []
                }

            total, t1, t2, t3, t4, t5 = row
            t1 = t1 or 0
            t2 = t2 or 0
            t3 = t3 or 0
            t4 = t4 or 0
            t5 = t5 or 0

            result = {
                'total_signals': total,
                'tiers': [
                    {
                        'tier': 1,
                        'name': 'Data Quality',
                        'pass': t1,
                        'reject': total - t1
                    },
                    {
                        'tier': 2,
                        'name': 'Market Health',
                        'pass': t2,
                        'reject': t1 - t2
                    },
                    {
                        'tier': 3,
                        'name': 'Trend Confirmation',
                        'pass': t3,
                        'reject': t2 - t3
                    },
                    {
                        'tier': 4,
                        'name': 'Signal Quality',
                        'pass': t4,
                        'reject': t3 - t4
                    },
                    {
                        'tier': 5,
                        'name': 'Portfolio Health',
                        'pass': t5,
                        'reject': t4 - t5
                    },
                ]
            }

            return result

        except Exception as e:
            log.error(f"Failed to get rejection funnel: {e}")
            return {'total_signals': 0, 'tiers': []}

        finally:
            self.disconnect()

    def get_rejection_reasons(self, eval_date: date, tier: int, limit: int = 20):
        """
        Get top rejection reasons for a specific tier.

        Returns:
            list of dicts: [
                {'reason': 'Distribution days 5 > 4', 'count': 25, 'symbols': ['XYZ', 'ABC', ...]},
                ...
            ]
        """
        self.connect()

        try:
            col_name = f'tier_{tier}_reason'
            self.cur.execute(f"""
                SELECT
                    {col_name} as reason,
                    COUNT(*) as count,
                    ARRAY_AGG(symbol ORDER BY symbol) as symbols
                FROM filter_rejection_log
                WHERE eval_date = %s AND {col_name} IS NOT NULL AND {col_name} != ''
                GROUP BY reason
                ORDER BY count DESC
                LIMIT %s
            """, (eval_date, limit))

            results = []
            for row in self.cur.fetchall():
                results.append({
                    'reason': row[0],
                    'count': row[1],
                    'symbols': row[2][:5],  # First 5 symbols
                    'total_symbols': len(row[2])
                })

            return results

        except Exception as e:
            log.error(f"Failed to get rejection reasons for tier {tier}: {e}")
            return []

        finally:
            self.disconnect()

    def get_signals_by_rejection_status(self, eval_date: date):
        """
        Get summary of signals by whether they were rejected and at which tier.

        Returns:
            dict {
                'qualified': 8,
                'rejected_tier_1': 50,
                'rejected_tier_2': 20,
                ...
            }
        """
        self.connect()

        try:
            self.cur.execute("""
                SELECT
                    SUM(CASE WHEN tier_5_pass THEN 1 ELSE 0 END) as qualified,
                    SUM(CASE WHEN NOT tier_1_pass THEN 1 ELSE 0 END) as t1_reject,
                    SUM(CASE WHEN tier_1_pass AND NOT tier_2_pass THEN 1 ELSE 0 END) as t2_reject,
                    SUM(CASE WHEN tier_2_pass AND NOT tier_3_pass THEN 1 ELSE 0 END) as t3_reject,
                    SUM(CASE WHEN tier_3_pass AND NOT tier_4_pass THEN 1 ELSE 0 END) as t4_reject,
                    SUM(CASE WHEN tier_4_pass AND NOT tier_5_pass THEN 1 ELSE 0 END) as t5_reject
                FROM filter_rejection_log
                WHERE eval_date = %s
            """, (eval_date,))

            row = self.cur.fetchone()
            if not row:
                return {}

            return {
                'qualified': row[0] or 0,
                'rejected_tier_1': row[1] or 0,
                'rejected_tier_2': row[2] or 0,
                'rejected_tier_3': row[3] or 0,
                'rejected_tier_4': row[4] or 0,
                'rejected_tier_5': row[5] or 0,
            }

        except Exception as e:
            log.error(f"Failed to get rejection summary: {e}")
            return {}

        finally:
            self.disconnect()
