#!/usr/bin/env python3
"""Consolidated Value + Quality + Growth Metrics Loader.

CONSOLIDATION: Merges 2 separate metric loaders into one:
  - load_yfinance_derived_metrics.py (reads yfinance_snapshot → value_metrics + others)
  - load_quality_growth_metrics.py (reads financial_statements → quality + growth)

CRITICAL DEPENDENCY: Requires these to run first:
  1. load_financial_statements.py → annual_income_statement, balance_sheet, cash_flow
  2. load_sec_valuations.py → sec_valuations (computed PE/PB/PS/PEG/FCF)
  3. load_yfinance_snapshot.py → yfinance_snapshot (as fallback/enrichment)

Data Flow:
  Phase 1: load_financial_statements.py fetches SEC data
  Phase 1: load_sec_valuations.py computes PE/PB/PS/PEG/FCF from SEC
  Phase 2: load_yfinance_snapshot.py fetches yfinance data
  Phase 3: load_value_quality_growth_metrics.py (THIS LOADER)
    ├─ Reads: sec_valuations (primary value metrics)
    ├─ Reads: financial_statements (quality + growth)
    ├─ Reads: yfinance_snapshot (fallback/enrichment: dividend, analyst, etc.)
    ├─ Computes: value_metrics (PE, PB, PS, PEG, FCF, dividend, market_cap)
    ├─ Computes: quality_metrics (ROE, margins, debt ratios)
    ├─ Computes: growth_metrics (revenue/EPS growth)
    └─ Writes: value_metrics, quality_metrics, growth_metrics (3 tables)

Benefits:
  - 1 ECS task instead of 2 (saves ~$0.05-0.10/run + 10-15 min runtime)
  - All value/quality/growth metrics computed together (atomic operation)
  - Single validation point (one fail-fast path)
  - Eliminates ~5,300 yfinance quoteSummary calls/day
  - Better data quality (SEC-audited valuations)
  - All metric families computed once from fresh SEC data
  - Easier to maintain (single loader, single error handler)

Run: python3 loaders/load_value_quality_growth_metrics.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date
from math import isnan
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


class ValueQualityGrowthMetricsLoader(OptimalLoader):
    """Consolidated value + quality + growth metrics from SEC + valuations + yfinance.

    Writes to 3 output tables in single per-symbol transaction:
    - value_metrics (PE, PB, PS, PEG, FCF from sec_valuations + yfinance dividend)
    - quality_metrics (ROE, margins, debt ratios from SEC)
    - growth_metrics (revenue/EPS growth from SEC)
    """

    table_name = "value_metrics"  # Primary table for watermarking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0  # Many stocks lack SEC filings
    exclude_etfs_from_symbols = True

    def run(self, symbols: list[str], since_date: date | None = None, parallelism: int | None = None) -> dict[str, Any]:  # type: ignore[override]
        """Override run() to write to 3 tables instead of 1."""
        from utils.loaders.config import get_default_parallelism

        value_inserts = 0
        quality_inserts = 0
        growth_inserts = 0
        symbols_succeeded = 0
        symbols_failed = 0

        parallelism = parallelism or get_default_parallelism("value_quality_growth_metrics")

        try:
            # Mark all 3 tables as RUNNING
            with DatabaseContext("write") as cur:
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_started = NOW() WHERE table_name = %s",
                        ("RUNNING", table),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                            (table, "RUNNING"),
                        )

            # Process each symbol
            for symbol in symbols:
                try:
                    # Fetch all metrics for symbol
                    metrics = self.fetch_incremental(symbol, since_date)
                    if not metrics:
                        logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: fetch_incremental returned empty list (CRITICAL BUG)")
                        symbols_failed += 1
                        continue

                    # Extract metrics tuple
                    value_row, quality_row, growth_row = metrics[0]

                    # Check if value metrics are available (CRITICAL - value metrics required for scoring)
                    if value_row and value_row.get("data_unavailable"):
                        logger.debug(f"[VALUE_QUALITY_GROWTH] {symbol}: Value metrics unavailable: {value_row.get('reason')}")
                        # Still insert unavailable marker for audit trail, but don't count as success
                        with DatabaseContext("write") as cur:
                            self._insert_value_metrics(cur, value_row)
                            value_inserts += 1
                        # Skip quality/growth if primary value metrics failed
                        symbols_failed += 1
                        continue

                    # Write to all 3 tables in single transaction
                    with DatabaseContext("write") as cur:
                        # Insert value metrics (ALWAYS present, either data or unavailable marker)
                        self._insert_value_metrics(cur, value_row)
                        value_inserts += 1

                        # Insert quality metrics (OPTIONAL - missing if balance sheet data unavailable)
                        if quality_row and not quality_row.get("data_unavailable"):
                            self._insert_quality_metrics(cur, quality_row)
                            quality_inserts += 1
                        elif quality_row and quality_row.get("data_unavailable"):
                            logger.debug(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics unavailable: {quality_row.get('reason')}")

                        # Insert growth metrics (OPTIONAL - missing if income statement history unavailable)
                        if growth_row and not growth_row.get("data_unavailable"):
                            self._insert_growth_metrics(cur, growth_row)
                            growth_inserts += 1
                        elif growth_row and growth_row.get("data_unavailable"):
                            logger.debug(f"[VALUE_QUALITY_GROWTH] {symbol}: Growth metrics unavailable: {growth_row.get('reason')}")

                    symbols_succeeded += 1

                except Exception as e:
                    logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: {type(e).__name__}: {e}")
                    symbols_failed += 1

            # Mark all 3 tables as COMPLETED
            with DatabaseContext("write") as cur:
                today = date.today()
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, latest_date = %s, last_updated = NOW(), execution_completed = NOW() WHERE table_name = %s",
                        ("COMPLETED", today, table),
                    )

            logger.info(
                f"[VALUE_QUALITY_GROWTH] Consolidated load complete: "
                f"{value_inserts} value, {quality_inserts} quality, {growth_inserts} growth"
            )

            return {
                "symbols_succeeded": symbols_succeeded,
                "symbols_failed": symbols_failed,
                "value_metrics": value_inserts,
                "quality_metrics": quality_inserts,
                "growth_metrics": growth_inserts,
            }

        except Exception as e:
            logger.error(f"[VALUE_QUALITY_GROWTH FATAL] {type(e).__name__}: {e}", exc_info=True)
            with DatabaseContext("write") as cur:
                error_msg = str(e)[:500]
                for table in ["value_metrics", "quality_metrics", "growth_metrics"]:
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_completed = NOW(), error_message = %s WHERE table_name = %s",
                        ("FAILED", error_msg, table),
                    )
            raise

    def fetch_incremental(self, symbol: str, since: date | None) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:  # type: ignore[override]
        """Fetch all metrics from SEC + valuations + yfinance for one symbol.

        Returns: List with single tuple of (value_dict, quality_dict, growth_dict)
        """
        try:
            with DatabaseContext("read") as cur:
                # Get value metrics from sec_valuations (primary source)
                cur.execute(
                    "SELECT * FROM sec_valuations WHERE symbol = %s",
                    (symbol,),
                )
                sec_val_row = cur.fetchone()

                # Get quality from SEC financials (annual balance sheet + income statement latest year)
                cur.execute(
                    """
                    SELECT abs.stockholders_equity, abs.total_liabilities,
                           ais.net_income, ais.revenue, ais.operating_income
                    FROM annual_balance_sheet abs
                    LEFT JOIN annual_income_statement ais ON abs.symbol = ais.symbol AND abs.fiscal_year = ais.fiscal_year
                    WHERE abs.symbol = %s
                    ORDER BY abs.fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                quality_row_db = cur.fetchone()

                # Get annual income statement history for growth computation (not from growth_metrics table)
                # NOTE: Filters by revenue IS NOT NULL - companies without revenue will be skipped
                cur.execute(
                    """
                    SELECT revenue, operating_income, net_income, earnings_per_share
                    FROM annual_income_statement
                    WHERE symbol = %s AND revenue IS NOT NULL
                    ORDER BY fiscal_year DESC
                    LIMIT 10
                    """,
                    (symbol,),
                )
                income_rows = cur.fetchall()
                if not income_rows:
                    logger.debug(f"[VALUE_QUALITY_GROWTH] {symbol}: No income statement rows with revenue found - growth metrics will be unavailable")

                # Get yfinance snapshot for enrichment (dividend, analyst, etc.)
                cur.execute(
                    "SELECT * FROM yfinance_snapshot WHERE symbol = %s",
                    (symbol,),
                )
                yfinance_row = cur.fetchone()

            # Construct value metrics from sec_valuations + yfinance dividend
            value_dict = self._build_value_metrics(symbol, sec_val_row, yfinance_row)
            quality_dict = self._compute_quality_metrics(symbol, quality_row_db)
            # Compute growth metrics from annual income statement history (not read from DB)
            growth_dict = self._compute_growth_metrics(symbol, income_rows)

            return [(value_dict, quality_dict, growth_dict)]

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Fetch failed: {e}")
            return [(
                self._unavailable_marker("value_metrics", symbol),
                self._unavailable_marker("quality_metrics", symbol),
                self._unavailable_marker("growth_metrics", symbol),
            )]

    def _build_value_metrics(self, symbol: str, sec_val_row: Any, yfinance_row: Any) -> dict[str, Any]:
        """Build value_metrics dict from sec_valuations + yfinance dividend."""
        if not sec_val_row or sec_val_row[2]:  # data_unavailable flag at index 2
            return self._unavailable_marker("value_metrics", symbol)

        # Extract SEC-derived valuations
        pe = sec_val_row[7]  # pe_ratio index
        pb = sec_val_row[8]  # pb_ratio
        ps = sec_val_row[9]  # ps_ratio
        peg = sec_val_row[10]  # peg_ratio
        fcf_yield = sec_val_row[11]  # fcf_yield
        market_cap = sec_val_row[6]  # market_cap

        # Validate: at least one core metric must be non-None
        core_metrics = [pe, pb, ps, fcf_yield]
        if all(m is None for m in core_metrics):
            return self._unavailable_marker("value_metrics", symbol)

        # Get dividend from yfinance if available
        dividend_yield = None
        if yfinance_row:
            try:
                dividend_yield = safe_float(yfinance_row[8], f"{symbol}.dividend_yield", allow_none=True)
            except Exception:
                pass

        return {
            "symbol": symbol,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "ps_ratio": ps,
            "peg_ratio": peg,
            "dividend_yield": dividend_yield,
            "fcf_yield": fcf_yield,
            "market_cap": market_cap,
            "data_unavailable": False,
            "data_source": "sec_audited",
            "updated_at": date.today().isoformat(),
        }

    @staticmethod
    def _nan_to_none(value: float | None) -> float | None:
        """Convert NaN to None for data integrity. NaN should never be stored in DB."""
        if value is not None and isinstance(value, float) and isnan(value):
            return None
        return value

    def _compute_quality_metrics(self, symbol: str, quality_row: Any) -> dict[str, Any]:
        """Compute quality_metrics from SEC financials (balance sheet + income statement)."""
        if not quality_row:
            return self._unavailable_marker("quality_metrics", symbol)

        try:
            stockholders_equity = self._nan_to_none(safe_float(quality_row[0], f"{symbol}.stockholders_equity", allow_none=True))
            total_liabilities = self._nan_to_none(safe_float(quality_row[1], f"{symbol}.total_liabilities", allow_none=True))
            net_income = self._nan_to_none(safe_float(quality_row[2], f"{symbol}.net_income", allow_none=True))
            revenue = self._nan_to_none(safe_float(quality_row[3], f"{symbol}.revenue", allow_none=True))
            operating_income = self._nan_to_none(safe_float(quality_row[4], f"{symbol}.operating_income", allow_none=True))

            metrics: dict[str, Any] = {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "quality_score": None,
                "data_unavailable": False,
                "data_source": "sec_audited",
                "updated_at": date.today().isoformat(),
            }

            # ROE = Net Income / Shareholders' Equity
            if net_income is not None and stockholders_equity is not None and stockholders_equity != 0:
                metrics["roe"] = float((net_income / stockholders_equity) * 100)

            # Operating Margin = Operating Income / Revenue
            if operating_income is not None and revenue is not None and revenue != 0:
                metrics["operating_margin"] = float((operating_income / revenue) * 100)

            # Net Margin = Net Income / Revenue
            if net_income is not None and revenue is not None and revenue != 0:
                metrics["net_margin"] = float((net_income / revenue) * 100)

            # Debt to Equity = Total Liabilities / Shareholders' Equity
            if total_liabilities is not None and stockholders_equity is not None and stockholders_equity != 0:
                metrics["debt_to_equity"] = float(total_liabilities / stockholders_equity)

            # Compute composite quality_score from available metrics
            # Score is average of available metrics (0-100 scale)
            quality_components = [
                metrics["roe"],
                metrics["operating_margin"],
                metrics["net_margin"],
            ]
            available_components = [m for m in quality_components if m is not None]

            # Mark unavailable if all metrics are None
            if all(metrics[k] is None for k in ["roe", "roa", "operating_margin", "net_margin", "debt_to_equity"]):
                return self._unavailable_marker("quality_metrics", symbol)

            # Mark unavailable if all available quality components are negative or zero
            # (unprofitable/break-even companies don't have meaningful "quality" scores)
            if available_components and all(m <= 0 for m in available_components):
                return self._unavailable_marker("quality_metrics", symbol)

            if available_components:
                # Normalize to 0-100 scale: ROE/margins can exceed 100, cap at 100
                # Clamp negatives to 0 only if at least one component is positive
                normalized = [min(100, max(0, m)) for m in available_components]
                metrics["quality_score"] = float(sum(normalized) / len(normalized))

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            return self._unavailable_marker("quality_metrics", symbol)

    @staticmethod
    def _cagr(latest: float, previous: float, years: int) -> float | None:
        """Compute CAGR (Compound Annual Growth Rate)."""
        try:
            latest_f = float(latest) if not isinstance(latest, float) else latest
            previous_f = float(previous) if not isinstance(previous, float) else previous
        except (ValueError, TypeError):
            return None

        if isnan(latest_f) or isnan(previous_f):
            return None
        if previous_f == 0 or previous_f is None:
            return None
        if (latest_f > 0 and previous_f < 0) or (latest_f < 0 and previous_f > 0):
            return None
        ratio = latest_f / previous_f
        return float(((ratio ** (1.0 / years)) - 1) * 100)

    def _compute_period_growth(self, symbol: str, values: list[float], offset: int, years: int, metric_key: str, metrics: dict[str, Any]) -> None:
        """Compute growth for a single period (1y, 3y, or 5y)."""
        required_count = offset + 1
        if len(values) >= required_count:
            growth = self._cagr(values[0], values[offset], years)
            if growth is not None:
                metrics[metric_key] = float(round(growth, 2))

    def _compute_growth_metrics(self, symbol: str, income_rows: list[Any]) -> dict[str, Any]:
        """Compute multi-year growth rates from annual income statement history.

        Calculates CAGR for 1y, 3y, 5y periods using compound annual growth rate formula.
        income_rows: List of (total_revenue, operating_income, net_income, earnings_per_share)
        sorted DESC by fiscal_year (most recent first).
        """
        if not income_rows or len(income_rows) < 2:
            return self._unavailable_marker("growth_metrics", symbol)

        metrics: dict[str, Any] = {
            "symbol": symbol,
            "revenue_growth_1y": None,
            "revenue_growth_3y": None,
            "revenue_growth_5y": None,
            "eps_growth_1y": None,
            "eps_growth_3y": None,
            "eps_growth_5y": None,
            "updated_at": date.today().isoformat(),
            "data_unavailable": False,
            "data_source": "sec_audited",
        }

        revenues = []
        eps_values = []
        for row in income_rows:
            try:
                rev = float(row[0]) if row[0] is not None else None
                eps = float(row[3]) if row[3] is not None else None
                rev = self._nan_to_none(rev)
                eps = self._nan_to_none(eps)
                if rev is not None and rev > 0:
                    revenues.append(rev)
                if eps is not None and eps != 0:
                    eps_values.append(eps)
            except (ValueError, TypeError):
                continue

        self._compute_period_growth(symbol, revenues, 1, 1, "revenue_growth_1y", metrics)
        self._compute_period_growth(symbol, eps_values, 1, 1, "eps_growth_1y", metrics)
        self._compute_period_growth(symbol, revenues, 3, 3, "revenue_growth_3y", metrics)
        self._compute_period_growth(symbol, eps_values, 3, 3, "eps_growth_3y", metrics)
        self._compute_period_growth(symbol, revenues, 5, 5, "revenue_growth_5y", metrics)
        self._compute_period_growth(symbol, eps_values, 5, 5, "eps_growth_5y", metrics)

        if all(metrics[k] is None for k in ["revenue_growth_1y", "revenue_growth_3y", "revenue_growth_5y", "eps_growth_1y", "eps_growth_3y", "eps_growth_5y"]):
            return self._unavailable_marker("growth_metrics", symbol)

        return metrics

    def _insert_value_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert value_metrics row."""
        cur.execute(
            """
            INSERT INTO value_metrics
            (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, market_cap, data_unavailable, data_source, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio,
                peg_ratio = EXCLUDED.peg_ratio,
                dividend_yield = EXCLUDED.dividend_yield,
                fcf_yield = EXCLUDED.fcf_yield,
                market_cap = EXCLUDED.market_cap,
                data_unavailable = EXCLUDED.data_unavailable,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (row["symbol"], row["pe_ratio"], row["pb_ratio"], row["ps_ratio"],
             row["peg_ratio"], row["dividend_yield"], row["fcf_yield"], row["market_cap"],
             row["data_unavailable"], row.get("data_source", "sec_audited"), row["updated_at"]),
        )

    def _insert_quality_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert quality_metrics row."""
        cur.execute(
            """
            INSERT INTO quality_metrics
            (symbol, roe, roa, operating_margin, net_margin, debt_to_equity, quality_score, data_unavailable, data_source, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                roe = EXCLUDED.roe,
                roa = EXCLUDED.roa,
                operating_margin = EXCLUDED.operating_margin,
                net_margin = EXCLUDED.net_margin,
                debt_to_equity = EXCLUDED.debt_to_equity,
                quality_score = EXCLUDED.quality_score,
                data_unavailable = EXCLUDED.data_unavailable,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (row["symbol"], row["roe"], row["roa"], row["operating_margin"],
             row["net_margin"], row["debt_to_equity"], row.get("quality_score"), row["data_unavailable"], row.get("data_source", "sec_audited"), row["updated_at"]),
        )

    def _insert_growth_metrics(self, cur: Any, row: dict[str, Any]) -> None:
        """Insert growth_metrics row with multi-year CAGR values."""
        cur.execute(
            """
            INSERT INTO growth_metrics
            (symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y, data_unavailable, reason, data_source, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                revenue_growth_1y = EXCLUDED.revenue_growth_1y,
                revenue_growth_3y = EXCLUDED.revenue_growth_3y,
                revenue_growth_5y = EXCLUDED.revenue_growth_5y,
                eps_growth_1y = EXCLUDED.eps_growth_1y,
                eps_growth_3y = EXCLUDED.eps_growth_3y,
                eps_growth_5y = EXCLUDED.eps_growth_5y,
                data_unavailable = EXCLUDED.data_unavailable,
                reason = EXCLUDED.reason,
                data_source = EXCLUDED.data_source,
                updated_at = EXCLUDED.updated_at
            """,
            (
                row["symbol"],
                row.get("revenue_growth_1y"),
                row.get("revenue_growth_3y"),
                row.get("revenue_growth_5y"),
                row.get("eps_growth_1y"),
                row.get("eps_growth_3y"),
                row.get("eps_growth_5y"),
                row.get("data_unavailable", False),
                row.get("reason"),
                row.get("data_source", "sec_audited"),
                row["updated_at"],
            ),
        )

    def _unavailable_marker(self, table: str, symbol: str) -> dict[str, Any]:
        """Return data_unavailable marker for a table."""
        if table == "value_metrics":
            return {
                "symbol": symbol,
                "pe_ratio": None,
                "pb_ratio": None,
                "ps_ratio": None,
                "peg_ratio": None,
                "dividend_yield": None,
                "fcf_yield": None,
                "market_cap": None,
                "data_unavailable": True,
                "data_source": "none",
                "updated_at": date.today().isoformat(),
            }
        elif table == "quality_metrics":
            return {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "quality_score": None,
                "data_unavailable": True,
                "data_source": "none",
                "updated_at": date.today().isoformat(),
            }
        else:  # growth_metrics
            return {
                "symbol": symbol,
                "revenue_growth_1y": None,
                "revenue_growth_3y": None,
                "revenue_growth_5y": None,
                "eps_growth_1y": None,
                "eps_growth_3y": None,
                "eps_growth_5y": None,
                "data_unavailable": True,
                "data_source": "none",
                "reason": "Insufficient historical data",
                "updated_at": date.today().isoformat(),
            }


if __name__ == "__main__":
    sys.exit(run_loader(ValueQualityGrowthMetricsLoader, description="Consolidated value + quality + growth metrics"))
