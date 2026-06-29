#!/usr/bin/env python3
"""Credit Spreads Daily Loader - High-Yield OAS tracking.

Fetches HY OAS (High-Yield Option-Adjusted Spread) from FRED API.
Data series: BAMLH0A0HYM2 (Bank of America Merrill Lynch High Yield OAS)

This is CRITICAL data for market_exposure calculation (10 points).

Run: python3 load_credit_spreads.py [--backfill-days N]
"""

import logging
import os
import sys
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

import psycopg2
import requests

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class CreditSpreadsFetcher:
    """Fetches HY OAS data from FRED API."""

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="fred_credit_spreads",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.CRITICAL,
        )
        self.fred_api_key = os.getenv("FRED_API_KEY")
        if not self.fred_api_key:
            raise ValueError("FRED_API_KEY environment variable is required for credit spreads loader")

    def fetch(self, start: date, end: date) -> dict[str, float]:
        """Fetch HY OAS data from FRED API.

        Args:
            start: Start date
            end: End date

        Returns:
            dict[date_str] -> hy_oas_value

        Raises:
            RuntimeError: If data fetch fails
        """
        # CRITICAL: No fallback for HY OAS — market exposure calculation depends on accurate spreads
        result = self.breaker.execute(
            fetch_func=lambda: self._fetch_from_fred(start, end),
            importance=DataImportance.CRITICAL,
        )

        if result is None:
            raise RuntimeError(
                "HY OAS data unavailable from FRED - circuit breaker failed. "
                "Cannot proceed without credit spread data for systemic risk assessment. "
                "This is critical data with no fallback."
            )

        if not isinstance(result, dict):
            raise RuntimeError(f"FRED fetch returned invalid data type {type(result).__name__} — expected dict")

        return result

    def _fetch_from_fred(self, start: date, end: date) -> dict[str, float]:
        """Internal FRED API fetch implementation.

        Fetches BAMLH0A0HYM2 (HY OAS) from Federal Reserve Economic Data API.
        """
        try:
            base_url = "https://api.stlouisfed.org/fred/series/data"
            params = {
                "series_id": "BAMLH0A0HYM2",  # HY OAS series
                "api_key": self.fred_api_key,
                "file_type": "json",
                "observation_start": start.isoformat(),
                "observation_end": end.isoformat(),
            }

            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            if "observations" not in data:
                raise RuntimeError(
                    f"FRED API returned unexpected response format. "
                    f"Expected 'observations' key, got keys: {list(data.keys())}"
                )

            result = {}
            skipped_count = 0
            total_count = len(data["observations"])
            for obs in data["observations"]:
                try:
                    obs_date = obs.get("date")
                    obs_value = obs.get("value")

                    if not obs_date:
                        logger.warning(f"[CREDIT_SPREADS] WARN: FRED observation missing date field: {obs}")
                        skipped_count += 1
                        continue

                    if not obs_value or obs_value == ".":
                        logger.warning(
                            f"[CREDIT_SPREADS] WARN: FRED observation {obs_date} has missing/invalid value: {obs_value}"
                        )
                        skipped_count += 1
                        continue

                    result[obs_date] = float(obs_value)
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"[CREDIT_SPREADS] WARN: Error parsing FRED observation {obs}: {e}")
                    skipped_count += 1
                    continue

            if skipped_count > 0:
                logger.warning(
                    f"[CREDIT_SPREADS] WARNING: Skipped {skipped_count}/{total_count} observations during FRED parse. "
                    f"Market exposure calculation depends on complete HY OAS data — missing observations may affect accuracy."
                )

            if not result:
                raise RuntimeError(
                    f"[CREDIT_SPREADS] CRITICAL: FRED returned no valid HY OAS observations for {start} to {end}. "
                    f"Check FRED data availability and series BAMLH0A0HYM2. "
                    f"Market exposure calculation requires credit spread data."
                )

            # Warn if significant percentage of observations were skipped
            if skipped_count > 0 and (skipped_count / total_count) > 0.1:
                logger.error(
                    f"[CREDIT_SPREADS] ERROR: {skipped_count / total_count * 100:.1f}% of FRED observations invalid. "
                    f"Market exposure calculation depends on accurate credit spreads — data quality degraded."
                )

            logger.info(f"Fetched {len(result)} HY OAS records from FRED")
            return result

        except requests.RequestException as e:
            raise RuntimeError(
                f"FRED API request failed: {e}. Cannot fetch HY OAS data for systemic stress assessment."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error fetching FRED data: {e}") from e


class CreditSpreadsDailyLoader(OptimalLoader):
    """High-Yield Credit Spread loader."""

    table_name = "credit_spreads"
    primary_key = ("date",)
    watermark_field = "date"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._fetcher = CreditSpreadsFetcher()

    def load_global(self) -> int:
        """Load HY OAS data (market-wide, not per-symbol).

        Raises:
            RuntimeError: If underlying data unavailable or computation fails.
        """
        try:
            with DatabaseContext("write") as cur:
                start = self._get_start_date(cur)
                end = self._get_end_date()

                if start > end:
                    logger.info(f"[CREDIT_SPREADS] No backfill needed (watermark {start} >= end {end})")
                    return 0

                logger.info(f"[CREDIT_SPREADS] Fetching HY OAS from FRED for {start} to {end}")

                spreads = self._fetcher.fetch(start, end)

                # Upsert into credit_spreads table
                inserted = 0
                for date_str, hy_oas in spreads.items():
                    try:
                        obs_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        logger.warning(f"[CREDIT_SPREADS] Invalid date format: {date_str}")
                        continue

                    cur.execute(
                        """
                        INSERT INTO credit_spreads (date, hy_oas, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (date)
                        DO UPDATE SET
                            hy_oas = EXCLUDED.hy_oas,
                            updated_at = NOW()
                        """,
                        (obs_date, hy_oas),
                    )
                    inserted += 1

                cur.connection.commit()
                logger.info(f"[CREDIT_SPREADS] ✓ Loaded {inserted} HY OAS records")
                return inserted

        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[CREDIT_SPREADS] Database error: {e}. Cannot store HY OAS data.") from e

    def run(
        self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """Not applicable for market-wide loader. Use load_global() instead."""
        raise NotImplementedError("CREDIT_SPREADS loader is market-wide only. Use load_global().")

    def _get_start_date(self, cur: Any) -> date:
        """Get start date from watermark or default to recent backfill.

        Returns:
            date: Start date for FRED query (next day after last record, or 90 days back if empty)

        Raises:
            RuntimeError: If watermark query fails after retry
        """
        try:
            cur.execute("SELECT MAX(date) FROM credit_spreads")
            row = cur.fetchone()
            if row and row[0] is not None:
                # Start one day after last record
                start = cast(date, row[0]) + timedelta(days=1)
                logger.info(f"[CREDIT_SPREADS] Starting from watermark: {start}")
                return start
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(
                f"[CREDIT_SPREADS] Failed to query watermark from credit_spreads table: {e}. "
                f"Falling back to default 90-day backfill."
            )

        # Default: last 90 days if table is empty (FRED data only weekly in many cases)
        default_start = date.today() - timedelta(days=90)
        logger.info(f"[CREDIT_SPREADS] Using default start date (90 days back): {default_start}")
        return default_start

    def _get_end_date(self) -> date:
        """Get end date (latest trading day in ET).

        Returns:
            date: Latest trading day, walking back from current date

        Raises:
            RuntimeError: If no trading day found within last year
        """
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        end = now_et.date()
        original_end = end

        from algo.infrastructure import MarketCalendar

        max_iterations = 365
        iterations = 0
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end) and iterations < max_iterations:
            end = end - timedelta(days=1)
            iterations += 1

        if iterations >= max_iterations:
            raise RuntimeError(
                f"[CREDIT_SPREADS] Could not find trading day within {max_iterations} days before {original_end}. "
                f"Market calendar may be corrupted or system date may be invalid."
            )

        if end <= date(2020, 1, 1):
            raise RuntimeError(
                f"[CREDIT_SPREADS] End date calculation walked back to {end}, "
                f"before acceptable range (>= 2020-01-01). System date may be invalid."
            )

        logger.info(f"[CREDIT_SPREADS] End date: {end} (latest trading day)")
        return end


if __name__ == "__main__":
    sys.exit(run_loader(CreditSpreadsDailyLoader, description="Credit spreads (HY OAS) loader", global_mode=True))
