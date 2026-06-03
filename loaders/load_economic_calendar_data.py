#!/usr/bin/env python3
"""Economic Calendar Loader — Upcoming macro events (FOMC, CPI, NFP, GDP)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

FOMC_DATES_2026 = [
    ("2026-01-28", "FOMC Meeting Decision"),
    ("2026-03-18", "FOMC Meeting Decision"),
    ("2026-05-06", "FOMC Meeting Decision"),
    ("2026-06-17", "FOMC Meeting Decision"),
    ("2026-07-29", "FOMC Meeting Decision"),
    ("2026-09-16", "FOMC Meeting Decision"),
    ("2026-11-04", "FOMC Meeting Decision"),
    ("2026-12-16", "FOMC Meeting Decision"),
]

def _load_economic_calendar(today: date) -> int:
    """Load economic calendar events: FOMC, CPI, NFP, GDP, etc."""
    end = today + timedelta(days=90)
    records = []

    events_config = [
        {"event_id": "JOBLESS_20260604", "event_date": date(2026, 6, 4), "event_time": "08:30",
         "event_name": "Initial Jobless Claims", "category": "Economic", "importance": "MEDIUM",
         "forecast_value": 235000, "previous_value": 238000},
        {"event_id": "CPI_20260605", "event_date": date(2026, 6, 5), "event_time": "08:30",
         "event_name": "CPI - Consumer Price Index (YoY)", "category": "Economic", "importance": "HIGH",
         "forecast_value": 3.4, "previous_value": 3.5},
        {"event_id": "NFP_20260605", "event_date": date(2026, 6, 5), "event_time": "08:30",
         "event_name": "Nonfarm Payrolls (NFP)", "category": "Economic", "importance": "HIGH",
         "forecast_value": 180000, "previous_value": 175000},
        {"event_id": "UNEMPLOYMENT_20260605", "event_date": date(2026, 6, 5), "event_time": "08:30",
         "event_name": "Unemployment Rate", "category": "Economic", "importance": "HIGH",
         "forecast_value": 4.0, "previous_value": 3.9},
        {"event_id": "RETAIL_SALES_20260612", "event_date": date(2026, 6, 12), "event_time": "08:30",
         "event_name": "Retail Sales (MoM)", "category": "Economic", "importance": "HIGH",
         "forecast_value": 0.3, "previous_value": 0.0},
        {"event_id": "PPI_20260612", "event_date": date(2026, 6, 12), "event_time": "08:30",
         "event_name": "Producer Price Index (YoY)", "category": "Economic", "importance": "MEDIUM",
         "forecast_value": 2.1, "previous_value": 2.2},
        {"event_id": "GDP_Q1_20260625", "event_date": date(2026, 6, 25), "event_time": "08:30",
         "event_name": "GDP (Advance Estimate)", "category": "Economic", "importance": "HIGH",
         "forecast_value": 2.4, "previous_value": 2.7},
    ]

    for event_config in events_config:
        if today <= event_config["event_date"] <= end:
            records.append({
                "event_id": event_config["event_id"],
                "event_date": event_config["event_date"],
                "event_time": event_config.get("event_time"),
                "event_name": event_config["event_name"],
                "category": event_config["category"],
                "importance": event_config["importance"],
                "country": "US",
                "forecast_value": event_config.get("forecast_value"),
                "actual_value": None,
                "previous_value": event_config.get("previous_value"),
            })

    for fomc_date_str, fomc_name in FOMC_DATES_2026:
        fomc_date = date.fromisoformat(fomc_date_str)
        if today <= fomc_date <= end:
            records.append({
                "event_id": f"FOMC_{fomc_date_str}",
                "event_date": fomc_date,
                "event_time": "18:00",
                "event_name": fomc_name,
                "category": "FOMC",
                "importance": "HIGH",
                "country": "US",
                "forecast_value": None,
                "actual_value": None,
                "previous_value": None,
            })

    if not records:
        logger.warning("No economic calendar events to load")
        return 0

    with DatabaseContext('write') as cur:
        try:
            cur.executemany("""
                INSERT INTO economic_calendar
                    (event_id, event_date, event_time, event_name, category, importance, country,
                     forecast_value, actual_value, previous_value, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (event_id, event_date) DO UPDATE SET
                    event_name = EXCLUDED.event_name,
                    event_time = EXCLUDED.event_time,
                    importance = EXCLUDED.importance,
                    forecast_value = EXCLUDED.forecast_value,
                    previous_value = EXCLUDED.previous_value,
                    updated_at = NOW()
            """, [
                (r["event_id"], r["event_date"], r["event_time"], r["event_name"],
                 r["category"], r["importance"], r["country"],
                 r["forecast_value"], r["actual_value"], r["previous_value"])
                for r in records
            ])

            count = len(records)
            logger.info(f"Upserted {count} economic calendar events through {end}")

            try:
                cur.execute("""
                    INSERT INTO data_loader_status (table_name, row_count, latest_date, last_updated)
                    VALUES ('economic_calendar', %s, %s, NOW())
                    ON CONFLICT (table_name) DO UPDATE SET
                        row_count = EXCLUDED.row_count,
                        latest_date = EXCLUDED.latest_date,
                        last_updated = EXCLUDED.last_updated
                """, (count, end))
            except Exception as e:
                logger.warning(f"Could not update loader status: {e}")

            return count
        except Exception as e:
            logger.error(f"Failed to upsert economic calendar events: {e}")
            raise

def main():
    today = date.today()
    try:
        count = _load_economic_calendar(today)
        if count > 0:
            logger.info(f"SUCCESS: {count} economic calendar events loaded")
            return 0
        else:
            logger.warning("COMPLETED: No economic calendar events loaded")
            return 0
    except Exception as e:
        logger.error(f"Economic calendar loader failed: {e}")
        return 1

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sys.exit(main())
