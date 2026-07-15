#!/usr/bin/env python3
"""Quality + Growth Metrics Computed from SEC Financials.

Consolidates two separate SEC-based metric loaders into one:
- quality_metrics (ROE, margins, debt ratios)
- growth_metrics (revenue/EPS growth)

CRITICAL DEPENDENCY: Requires load_financial_statements.py to populate:
  - annual_income_statement (via financials_annual_income task)
  - annual_balance_sheet (via financials_annual_balance task)

Data Flow in Orchestrator:
  1. load_financial_statements.py → SEC EDGAR API → annual_income_statement, annual_balance_sheet tables
  2. load_quality_growth_metrics.py → Reads tables from step 1 → Computes quality/growth metrics
  3. Orchestrator must ensure step 1 runs BEFORE step 2

This two-step approach (fetch raw → compute metrics) avoids duplicate SEC API calls:
  - Financial statements cached in DB (reused for fundamentals, quality, growth)
  - Quality/growth computed via in-DB joins (cheaper than re-fetching)

Run: python3 loaders/load_quality_growth_metrics.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from typing import Any

from psycopg2.extensions import cursor as pg_cursor

from loaders.helpers.sec_base import SecFinancialsLoader
from loaders.runner import run_loader

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
        """Override run() to insert to TWO tables instead of one.

        CRITICAL FIX: Use per-symbol transactions to prevent cascade failures.
        If one symbol's INSERT fails (data_unavailable etc), don't abort entire loader.
        Each symbol gets its own transaction so failures don't cascade.
        """
        quality_inserts = 0
        growth_inserts = 0
        symbols_succeeded = 0
        symbols_failed = 0

        try:
            for symbol in symbols:
                try:
                    # Per-symbol transaction: commit/rollback independently
                    # Prevents one bad symbol from failing all remaining symbols
                    with self._db_write_context() as cur:
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
                        "reason_type": "not_applicable",
                        "updated_at": date.today().isoformat(),
                    },
                    {
                        "symbol": symbol,
                        "data_unavailable": True,
                        "reason": "No SEC filing data",
                        "reason_type": "not_applicable",
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

        # Operating margin - validate result is reasonable (margins typically -100% to +100%)
        if revenue and revenue > 0 and operating_income is not None:
            om = float(round((operating_income / revenue) * 100, 2))
            if -1000 <= om <= 1000:  # Reasonable range for any margin
                metrics["operating_margin"] = om
            else:
                logger.warning(f"[{symbol}] Operating margin {om}% out of range, marking unavailable")
                metrics["data_unavailable"] = True
                metrics["reason"] = f"Operating margin calculation invalid: {om}%"
                return metrics

        # Net margin - validate result is reasonable
        if revenue and revenue > 0 and net_income is not None:
            nm = float(round((net_income / revenue) * 100, 2))
            if -1000 <= nm <= 1000:
                metrics["net_margin"] = nm
            else:
                logger.warning(f"[{symbol}] Net margin {nm}% out of range, marking unavailable")
                metrics["data_unavailable"] = True
                metrics["reason"] = f"Net margin calculation invalid: {nm}%"
                return metrics

        # ROE - validate result is reasonable (ROE typically -300% to +300%)
        if stockholders_equity and stockholders_equity > 0 and net_income is not None:
            roe = float(round((net_income / stockholders_equity) * 100, 2))
            if -1000 <= roe <= 1000:
                metrics["roe"] = roe
            else:
                logger.warning(f"[{symbol}] ROE {roe}% out of range, marking unavailable")
                metrics["data_unavailable"] = True
                metrics["reason"] = f"ROE calculation invalid: {roe}%"
                return metrics

        # ROA - validate result is reasonable (ROA typically -100% to +100%)
        if total_assets and total_assets > 0 and net_income is not None:
            roa = float(round((net_income / total_assets) * 100, 2))
            if -1000 <= roa <= 1000:
                metrics["roa"] = roa
            else:
                logger.warning(f"[{symbol}] ROA {roa}% out of range, marking unavailable")
                metrics["data_unavailable"] = True
                metrics["reason"] = f"ROA calculation invalid: {roa}%"
                return metrics

        # Debt to Equity - validate result is reasonable (D/E typically 0 to 10)
        if stockholders_equity and stockholders_equity > 0 and total_liabilities is not None:
            de = float(round(total_liabilities / stockholders_equity, 2))
            if 0 <= de <= 100:  # Reasonable range for debt-to-equity
                metrics["debt_to_equity"] = de
            else:
                logger.warning(f"[{symbol}] Debt/Equity {de} out of range, marking unavailable")
                metrics["data_unavailable"] = True
                metrics["reason"] = f"Debt/Equity calculation invalid: {de}"
                return metrics

        return metrics

    def _compute_growth_metrics(self, symbol: str, income_rows: list[tuple[Any, ...]]) -> dict[str, Any]:
        if not income_rows or len(income_rows) < 2:
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "Insufficient historical data",
                "reason_type": "not_applicable",
                "updated_at": date.today().isoformat(),
            }

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "revenue_growth_5y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "eps_growth_5y": None,
            "revenue_growth_1y_unavailable_reason": None,
            "revenue_growth_3y_unavailable_reason": None,
            "revenue_growth_5y_unavailable_reason": None,
            "eps_growth_1y_unavailable_reason": None,
            "eps_growth_3y_unavailable_reason": None,
            "eps_growth_5y_unavailable_reason": None,
            "updated_at": date.today().isoformat(),
            "data_unavailable": False,
        }

        # Extract revenue from rows (first element of each tuple)
        # Convert to float safely (DB returns Decimal)
        revenues = []
        eps_values = []
        for row in income_rows:
            try:
                rev = float(row[0]) if row[0] is not None else None
                eps = float(row[1]) if row[1] is not None else None
                if rev is not None and rev > 0:
                    revenues.append(rev)
                if eps is not None and eps != 0:
                    eps_values.append(eps)
            except (ValueError, TypeError):
                continue

        def _cagr(latest: float, previous: float, years: int) -> float | None:
            """Compute CAGR (Compound Annual Growth Rate) for multi-year growth.

            Handles sign changes (positive→negative revenue) by returning None.
            Returns annualized growth rate as percentage.
            Safely converts Decimal from DB to float.
            """
            from decimal import Decimal

            try:
                latest_f = float(latest) if not isinstance(latest, float) else latest
                previous_f = float(previous) if not isinstance(previous, float) else previous
            except (ValueError, TypeError):
                return None

            if previous_f == 0 or previous_f is None:
                return None
            if (latest_f > 0 and previous_f < 0) or (latest_f < 0 and previous_f > 0):
                # Sign change: traditional CAGR doesn't apply
                return None
            ratio = latest_f / previous_f
            return ((ratio ** (1.0 / years)) - 1) * 100

        # 1-year revenue growth (CAGR)
        if len(revenues) >= 2:
            rev_growth = _cagr(revenues[0], revenues[1], 1)
            if rev_growth is not None:
                metrics["revenue_growth_1y"] = float(round(rev_growth, 2))
            else:
                metrics["revenue_growth_1y_unavailable_reason"] = "insufficient_data" if revenues[1] == 0 else "sign_change"
        else:
            metrics["revenue_growth_1y_unavailable_reason"] = "insufficient_history"

        # 1-year EPS growth (CAGR)
        if len(eps_values) >= 2:
            eps_growth = _cagr(eps_values[0], eps_values[1], 1)
            if eps_growth is not None:
                metrics["eps_growth_1y"] = float(round(eps_growth, 2))
            else:
                metrics["eps_growth_1y_unavailable_reason"] = "insufficient_data" if eps_values[1] == 0 else "sign_change"
        else:
            metrics["eps_growth_1y_unavailable_reason"] = "insufficient_history"

        # 3-year revenue growth (CAGR from 3 years ago)
        if len(revenues) >= 4:
            rev_growth = _cagr(revenues[0], revenues[3], 3)
            if rev_growth is not None:
                metrics["revenue_growth_3y"] = float(round(rev_growth, 2))
            else:
                metrics["revenue_growth_3y_unavailable_reason"] = "insufficient_data" if revenues[3] == 0 else "sign_change"
        else:
            metrics["revenue_growth_3y_unavailable_reason"] = "insufficient_history"

        # 3-year EPS growth (CAGR from 3 years ago)
        if len(eps_values) >= 4:
            eps_growth = _cagr(eps_values[0], eps_values[3], 3)
            if eps_growth is not None:
                metrics["eps_growth_3y"] = float(round(eps_growth, 2))
            else:
                metrics["eps_growth_3y_unavailable_reason"] = "insufficient_data" if eps_values[3] == 0 else "sign_change"
        else:
            metrics["eps_growth_3y_unavailable_reason"] = "insufficient_history"

        # 5-year revenue growth (CAGR from 5 years ago)
        if len(revenues) >= 6:
            rev_growth = _cagr(revenues[0], revenues[5], 5)
            if rev_growth is not None:
                metrics["revenue_growth_5y"] = float(round(rev_growth, 2))
            else:
                metrics["revenue_growth_5y_unavailable_reason"] = "insufficient_data" if revenues[5] == 0 else "sign_change"
        else:
            metrics["revenue_growth_5y_unavailable_reason"] = "insufficient_history"

        # 5-year EPS growth (CAGR from 5 years ago)
        if len(eps_values) >= 6:
            eps_growth = _cagr(eps_values[0], eps_values[5], 5)
            if eps_growth is not None:
                metrics["eps_growth_5y"] = float(round(eps_growth, 2))
            else:
                metrics["eps_growth_5y_unavailable_reason"] = "insufficient_data" if eps_values[5] == 0 else "sign_change"
        else:
            metrics["eps_growth_5y_unavailable_reason"] = "insufficient_history"

        return metrics

    def _insert_record(self, cur: Any, table: str, record: dict[str, Any]) -> None:
        """Upsert a single record to table.

        BUGFIX: ON CONFLICT previously updated only updated_at, silently discarding every
        recomputed metric value for symbols that already had a row — the table was
        effectively write-once while its updated_at looked fresh. Now every non-key column
        is updated from EXCLUDED so daily recomputes actually land.
        """
        if not record:
            return

        columns = ", ".join(record.keys())
        placeholders = ", ".join(["%s"] * len(record))
        update_cols = [col for col in record if col != "symbol"]
        if not update_cols:
            return
        set_clause = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
        query = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            ON CONFLICT (symbol) DO UPDATE SET
                {set_clause}
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
