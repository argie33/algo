#!/usr/bin/env python3
"""
Economic Calendar Loader - Fetches scheduled economic event dates.

Populates calendar_events table with FRED release dates for major
economic indicators (NFP, CPI, GDP, Fed decisions, etc).

Sources:
- FRED API (St. Louis Fed) for release dates
- https://api.stlouisfed.org/fred/releases/dates

Run:
    python3 loadcalendar.py [--days-ahead 90]
"""

import argparse
import logging
import os
import sys
import psycopg2
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from credential_helper import get_db_password

# dotenv-autoload
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parent / '.env.local'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class EconomicCalendarLoader:
    """Load economic calendar events from FRED."""

    # Major economic indicators to track
    FRED_INDICATORS = {
        'NONFARM_PAYROLL': {
            'series_id': 'NONFARM',  # Non-Farm Payroll
            'name': 'Non-Farm Payroll',
            'category': 'Employment',
            'importance': 'high',
        },
        'CPI': {
            'series_id': 'CPIAUCSL',  # CPI All Items
            'name': 'CPI - All Items',
            'category': 'Inflation',
            'importance': 'high',
        },
        'PPI': {
            'series_id': 'PPIAUCSL',  # PPI Finished Goods
            'name': 'PPI - Finished Goods',
            'category': 'Inflation',
            'importance': 'medium',
        },
        'UNEMPLOYMENT': {
            'series_id': 'UNRATE',  # Unemployment Rate
            'name': 'Unemployment Rate',
            'category': 'Employment',
            'importance': 'high',
        },
        'RETAIL_SALES': {
            'series_id': 'RSXFS',  # Retail Sales
            'name': 'Retail Sales',
            'category': 'Consumer',
            'importance': 'high',
        },
        'HOUSING_STARTS': {
            'series_id': 'HOUST',  # Housing Starts
            'name': 'Housing Starts',
            'category': 'Housing',
            'importance': 'medium',
        },
        'ISM_MANUFACTURING': {
            'series_id': 'MMNRNJ',  # ISM Manufacturing
            'name': 'ISM Manufacturing PMI',
            'category': 'Manufacturing',
            'importance': 'high',
        },
        'CONSUMER_SENTIMENT': {
            'series_id': 'MMNRNJ',  # University of Michigan Consumer Sentiment
            'name': 'Consumer Sentiment',
            'category': 'Consumer',
            'importance': 'medium',
        },
    }

    def __init__(self):
        self.conn = None
        self.cur = None
        self.db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": get_db_password(),
            "database": os.getenv("DB_NAME", "stocks"),
        }
        self.fred_api_key = os.getenv("FRED_API_KEY", "")

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cur = self.conn.cursor()
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def fetch_fred_releases(self, series_id: str, days_ahead: int = 90) -> List[Dict[str, Any]]:
        """
        Fetch upcoming FRED release dates for a series.

        Note: Full FRED release calendar requires API key and complex parsing.
        For now, return stub events based on typical release schedules.
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests library not available, using stub calendar")
            return self._get_stub_calendar(series_id, days_ahead)

        if not self.fred_api_key:
            logger.warning(f"FRED_API_KEY not set, using stub calendar for {series_id}")
            return self._get_stub_calendar(series_id, days_ahead)

        try:
            # Get release date for a series
            url = "https://api.stlouisfed.org/fred/releases/dates"
            params = {
                "api_key": self.fred_api_key,
                "file_type": "json",
                "limit": 20,
            }
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()

            events = []
            for release in response.json().get("release_dates", []):
                release_date = release.get("date")
                if not release_date:
                    continue

                try:
                    event_date = date.fromisoformat(release_date)
                    if event_date < date.today():
                        continue
                    if (event_date - date.today()).days > days_ahead:
                        continue

                    events.append({
                        'event_id': release.get('id', 'UNKNOWN'),
                        'event_date': event_date,
                        'event_time': None,  # FRED doesn't provide time
                        'event_name': release.get('name', 'Economic Release'),
                        'category': 'Economic',
                        'importance': self._estimate_importance(release.get('name', '')),
                        'forecast': None,
                        'previous': None,
                    })
                except (ValueError, KeyError):
                    continue

            return events

        except Exception as e:
            logger.warning(f"FRED API fetch failed for {series_id}: {e}, using stub calendar")
            return self._get_stub_calendar(series_id, days_ahead)

    def _get_stub_calendar(self, series_id: str, days_ahead: int) -> List[Dict[str, Any]]:
        """Return stub calendar events based on typical release schedules."""
        # These are typical release dates (stubbed for now)
        events = []
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Create stub events for major indicators
        stub_events = [
            ("First Friday of month", "Employment", "high", "Non-Farm Payroll"),
            ("Second week", "Employment", "high", "Jobless Claims"),
            ("Mid-month", "Inflation", "high", "CPI Release"),
            ("Mid-month", "Inflation", "medium", "PPI Release"),
            ("Last Friday", "Consumer", "medium", "Consumer Sentiment"),
        ]

        return events  # Return empty for now until FRED API is fully configured

    def _estimate_importance(self, event_name: str) -> str:
        """Estimate event importance based on name."""
        high_impact = ["nonfarm payroll", "cpi", "fomc", "fed decision", "gdp"]
        medium_impact = ["retail sales", "ppi", "unemployment", "housing starts", "ism"]

        name_lower = event_name.lower()
        if any(h in name_lower for h in high_impact):
            return "high"
        elif any(m in name_lower for m in medium_impact):
            return "medium"
        return "low"

    def load_calendar(self, days_ahead: int = 90) -> int:
        """Load economic calendar for all indicators."""
        total_loaded = 0

        for indicator_key, indicator_info in self.FRED_INDICATORS.items():
            try:
                events = self.fetch_fred_releases(indicator_info['series_id'], days_ahead)

                for event in events:
                    try:
                        self.cur.execute("""
                            INSERT INTO calendar_events
                            (event_id, event_date, event_time, event_name, category, importance,
                             forecast, previous, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (event_id, event_date) DO UPDATE SET
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            event.get('event_id'),
                            event.get('event_date'),
                            event.get('event_time'),
                            event.get('event_name'),
                            event.get('category'),
                            event.get('importance'),
                            event.get('forecast'),
                            event.get('previous'),
                        ))
                        total_loaded += 1
                    except Exception as e:
                        logger.debug(f"Failed to insert calendar event {event}: {e}")

                if events:
                    logger.info(f"{indicator_key}: Loaded {len(events)} events")

            except Exception as e:
                logger.warning(f"Failed to load calendar for {indicator_key}: {e}")

        # Commit all changes
        try:
            self.conn.commit()
            logger.info(f"[OK] Committed {total_loaded} calendar events")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to commit calendar: {e}")
            return 0

        return total_loaded

    def run(self, days_ahead: int = 90):
        """Run the loader."""
        try:
            self.connect()
            count = self.load_calendar(days_ahead)
            logger.info(f"Economic calendar load complete: {count} records")
            return count
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description="Load economic calendar events for market awareness"
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=90,
        help="Number of days to look ahead (default: 90)",
    )

    args = parser.parse_args()

    loader = EconomicCalendarLoader()
    count = loader.run(args.days_ahead)

    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
