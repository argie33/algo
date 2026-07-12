#!/usr/bin/env python3
"""Quality + Growth Metrics Consolidated Loader.

Consolidates two separate SEC-based loaders into one:
- quality_metrics (ROE, margins, debt ratios)
- growth_metrics (revenue/EPS growth)

Both fetch from SEC EDGAR, so consolidating eliminates one SEC API round-trip
and allows computing both metrics in parallel from the same financial data.

Run: python3 loaders/load_quality_growth_metrics.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from typing import Any

from psycopg2.extensions import cursor as pg_cursor

from loaders.runner import run_loader
from loaders.sec_financials_loader import SecFinancialsLoader

logger = logging.getLogger(__name__)


class QualityGrowthMetricsLoader(SecFinancialsLoader):
    """Consolidated quality + growth metrics from SEC financials.

    Previously 2 separate loaders that both fetched SEC data independently.
    Now consolidated to fetch once and compute both metrics.
    """

    table_name = "quality_metrics"  # For watermarking; actually writes to quality_metrics and growth_metrics
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def run(self, symbols: list[str], since_date: date | None = None, parallelism: int | None = None) -> dict[str, Any]:  # type: ignore[override]
        """Override run() to insert to TWO tables instead of one."""
        quality_inserts = 0
        growth_inserts = 0
        symbols_succeeded = 0
        symbols_failed = 0

        try:
            with self._db_write_context() as cur:
                for symbol in symbols:
                    try:
                        result = self.fetch_incremental(symbol, since_date)
                        if result and len(result) > 0:
                            # result is list[(quality_dict, growth_dict)], so unpack the tuple inside the list
                            quality_row, growth_row = result[0]

                            # Insert quality metrics
                            self._insert_record(cur, "quality_metrics", quality_row)
                            quality_inserts += 1

                            # Insert growth metrics if computed
                            if growth_row:
                                self._insert_record(cur, "growth_metrics", growth_row)
                                growth_inserts += 1

                            symbols_succeeded += 1
                    except Exception as e:
                        logger.warning(f"Failed to compute metrics for {symbol}: {e}")
                        symbols_failed += 1

            logger.info(
                f"[QUALITY_GROWTH] Consolidated load complete: {quality_inserts} quality, {growth_inserts} growth"
            )
            return {
                "symbols_succeeded": symbols_succeeded,
                "symbols_failed": symbols_failed,
                "quality_metrics": quality_inserts,
                "growth_metrics": growth_inserts,
            }

        except Exception as e:
            logger.error(f"[QUALITY_GROWTH FATAL] {type(e).__name__}: {e!s}", exc_info=True)
            raise

    def fetch_incremental(self, symbol: str, since: date | None) -> list[tuple[dict[str, Any], dict[str, Any]]]:  # type: ignore[override]
        """Fetch SEC data once and compute BOTH quality and growth metrics.

        Returns tuple of (quality_dict, growth_dict).
        """
        # Fetch SEC financials once
        income_rows = self._fetch_annual_income_statement_history(symbol, years=10)
        balance_row = self._fetch_annual_balance_sheet(symbol)

        # No data = return unavailable for both
        if not income_rows:
            return [
                (
                    {
                        "symbol": symbol,
                        "data_unavailable": True,
                        "reason": "No SEC filing data",
                        "updated_at": date.today().isoformat(),
                    },
                    {
                        "symbol": symbol,
                        "data_unavailable": True,
                        "reason": "No SEC filing data",
                        "updated_at": date.today().isoformat(),
                    },
                )
            ]

        # Compute both from same data
        quality = self._compute_quality_metrics(symbol, income_rows[0], balance_row)
        growth = self._compute_growth_metrics(symbol, income_rows)

        return [(quality, growth)]

    def _compute_quality_metrics(
        self, symbol: str, income_row: tuple[Any, ...], balance_row: tuple[Any, ...] | None
    ) -> dict[str, Any]:
        """Compute quality metrics from current year financials."""
        revenue, operating_income, net_income = income_row[0:3] if income_row else (None, None, None)

        if balance_row:
            total_assets, stockholders_equity, _current_assets, total_liabilities, _current_liabilities, _inventory = (
                balance_row
            )
        else:
            total_assets = stockholders_equity = total_liabilities = None

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "operating_margin": None,
            "net_margin": None,
            "roe": None,
            "roa": None,
            "debt_to_equity": None,
            "updated_at": date.today().isoformat(),
            "data_unavailable": False,
        }

        # Operating margin
        if revenue and revenue > 0 and operating_income is not None:
            metrics["operating_margin"] = float(round((operating_income / revenue) * 100, 2))

        # Net margin
        if revenue and revenue > 0 and net_income is not None:
            metrics["net_margin"] = float(round((net_income / revenue) * 100, 2))

        # ROE
        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            metrics["roe"] = float(round((net_income / stockholders_equity) * 100, 2))

        # ROA
        if total_assets and total_assets > 0 and net_income is not None:
            metrics["roa"] = float(round((net_income / total_assets) * 100, 2))

        # Debt to Equity
        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            metrics["debt_to_equity"] = float(round(total_liabilities / stockholders_equity, 2))

        return metrics

    def _compute_growth_metrics(self, symbol: str, income_rows: list[tuple[Any, ...]]) -> dict[str, Any]:
        """Compute growth metrics from historical financials."""
        if not income_rows or len(income_rows) < 2:
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "Insufficient historical data",
                "updated_at": date.today().isoformat(),
            }

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "updated_at": date.today().isoformat(),
            "data_unavailable": False,
        }

        # Extract revenue from rows (first element of each tuple)
        revenues = [row[0] for row in income_rows if row[0] is not None and row[0] > 0]
        [row[1] for row in income_rows if row[1] is not None]

        # 1-year growth
        if len(revenues) >= 2:
            rev_growth = ((revenues[0] - revenues[1]) / abs(revenues[1]) * 100) if revenues[1] != 0 else None
            metrics["revenue_growth_1y"] = float(round(rev_growth, 2)) if rev_growth else None

        # 3-year growth
        if len(revenues) >= 4:
            rev_growth = ((revenues[0] - revenues[3]) / abs(revenues[3]) * 100) if revenues[3] != 0 else None
            metrics["revenue_growth_3y"] = float(round(rev_growth, 2)) if rev_growth else None

        return metrics

    def _insert_record(self, cur: Any, table: str, record: dict[str, Any]) -> None:
        """Insert a single record to table."""
        if not record:
            return

        columns = ", ".join(record.keys())
        placeholders = ", ".join(["%s"] * len(record))
        query = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            ON CONFLICT (symbol) DO UPDATE SET
                updated_at = EXCLUDED.updated_at
        """
        values = tuple(record.values())
        cur.execute(query, values)

    @contextmanager
    def _db_write_context(self) -> Generator[pg_cursor, None, None]:
        """Context manager for DB writes."""
        from utils.db.context import DatabaseContext

        with DatabaseContext("write") as cur:
            yield cur


def main() -> int:
    return run_loader(QualityGrowthMetricsLoader)


if __name__ == "__main__":
    sys.exit(main())
