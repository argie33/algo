#!/usr/bin/env python3
"""Economic calendar tracking for major data releases.

Monitors FOMC, NFP, CPI, and other high-impact releases.
Can block entries 1 hour before major releases to avoid whipsaws.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from typing import Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }

# High-impact economic releases
HIGH_IMPACT_EVENTS = [
    'FOMC',
    'Non-Farm Payroll',
    'NFP',
    'CPI',
    'PPI',
    'GDP',
    'Jobless Claims',
    'ISM Manufacturing',
    'ISM Services',
    'Retail Sales',
]


class EconomicCalendar:
    """Monitor and enforce economic calendar gating."""

    def __init__(self, config=None):
        self.config = config or {}
        self.halt_minutes_before = int(self.config.get('halt_entries_before_major_release_minutes', 60))

    def check_entry_gate(self, eval_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """Check if major release is within halt window. Returns (can_enter, reason)."""
        if eval_time is None:
            eval_time = datetime.now()

        # D4: FOMC Full-Day Gate — no entries on FOMC decision days
        fomc_check = self.is_fomc_day(eval_time)
        if not fomc_check['can_enter']:
            return False, fomc_check['reason']

        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            # Check for imminent high-impact events
            halt_until = eval_time + timedelta(minutes=self.halt_minutes_before)

            cur.execute(
                """SELECT event_name, scheduled_time, impact FROM economic_calendar
                   WHERE LOWER(impact) IN ('high', 'medium')
                   AND scheduled_time >= %s
                   AND scheduled_time <= %s
                   LIMIT 1""",
                (eval_time, halt_until)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                event_name, event_time, impact = row
                minutes_until = (event_time.replace(tzinfo=None) - eval_time).total_seconds() / 60
                return False, f"{event_name} in {minutes_until:.0f}min (halting entries)"

            return True, "No major releases in halt window"
        except Exception as e:
            logger.warning(f"Economic calendar check error: {e}")
            return True, "Calendar check skipped (error)"

    def is_fomc_day(self, eval_time: Optional[datetime] = None) -> Dict[str, Any]:
        """D4: FOMC Full-Day Gate — No new entries on FOMC decision days.

        FOMC days see extreme volatility throughout the entire day, not just at announcement.
        Returns {'can_enter': bool, 'reason': str}
        """
        if eval_time is None:
            eval_time = datetime.now()

        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            # Check if today is an FOMC decision day
            eval_date = eval_time.date()
            cur.execute(
                """SELECT event_name, scheduled_time FROM economic_calendar
                   WHERE DATE(scheduled_time) = %s
                   AND (event_name ILIKE '%FOMC%' OR event_name ILIKE '%Federal Open Market%')
                   LIMIT 1""",
                (eval_date,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                event_name, event_time = row
                return {
                    'can_enter': False,
                    'reason': f'FOMC decision day ({event_name}): no new entries',
                    'is_fomc_day': True,
                }

            return {
                'can_enter': True,
                'reason': 'Not an FOMC day',
                'is_fomc_day': False,
            }
        except Exception as e:
            logger.warning(f"FOMC day check error: {e}")
            return {'can_enter': True, 'reason': 'FOMC check error (continuing)', 'is_fomc_day': False}

    def get_market_quiet_period_status(self) -> Dict[str, Any]:
        """Get status of next major release. Returns dict with details."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            cur.execute(
                """SELECT event_name, scheduled_time, impact FROM economic_calendar
                   WHERE LOWER(impact) IN ('high', 'medium')
                   AND scheduled_time >= NOW()
                   ORDER BY scheduled_time
                   LIMIT 1""",
                ()
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                return {
                    'next_release': None,
                    'minutes_until': None,
                    'is_quiet': True,
                }

            event_name, event_time, impact = row
            minutes_until = (event_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60

            return {
                'next_release': event_name,
                'scheduled_time': str(event_time),
                'minutes_until': minutes_until,
                'impact': impact,
                'is_quiet': minutes_until > 120,
            }
        except Exception as e:
            logger.warning(f"Failed to get quiet period status: {e}")
            return {'next_release': None, 'is_quiet': True}

    def populate_sample_calendar(self) -> None:
        """Populate economic calendar with sample 2026 events."""
        events = [
            ('ISM Manufacturing', datetime(2026, 5, 1, 14, 0), 'high'),
            ('ISM Services', datetime(2026, 5, 5, 14, 0), 'high'),
            ('Jobless Claims', datetime(2026, 5, 7, 13, 30), 'medium'),
            ('Non-Farm Payroll', datetime(2026, 5, 8, 13, 30), 'high'),
            ('Retail Sales', datetime(2026, 5, 15, 13, 30), 'high'),
            ('PPI', datetime(2026, 5, 14, 13, 30), 'high'),
            ('CPI', datetime(2026, 5, 12, 13, 30), 'high'),
            ('FOMC Meeting', datetime(2026, 5, 19, 18, 0), 'high'),
        ]

        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            for event_name, scheduled_time, impact in events:
                cur.execute(
                    """INSERT INTO economic_calendar (event_name, scheduled_time, impact, description)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (event_name, scheduled_time, impact, f"{event_name} economic data release")
                )

            conn.commit()
            cur.close()
            conn.close()
            logger.info("Economic calendar populated with sample events")
        except Exception as e:
            logger.warning(f"Failed to populate economic calendar: {e}")


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    ec = EconomicCalendar(config)

    can_enter, reason = ec.check_entry_gate()
    print(f"Can enter: {can_enter} ({reason})")

    status = ec.get_market_quiet_period_status()
    print(f"Quiet period status: {status}")
