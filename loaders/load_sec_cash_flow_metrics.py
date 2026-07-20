#!/usr/bin/env python3
"""SEC-Derived Cash Flow Metrics Loader - Working Capital, CapEx, Free Cash Flow.

Computes cash flow health metrics from SEC financial statements:
  - Working Capital: Current Assets - Current Liabilities
  - CapEx (Capital Expenditures): Purchases of Property, Plant, Equipment
  - Free Cash Flow: Operating Cash Flow - CapEx
  - Operating Cash Flow: Direct from cash flow statement
  - Cash Conversion Rate: Operating Cash Flow / Net Income

Data Quality:
  - All metrics computed from SEC audited financial statements
  - Annual and quarterly data available
  - Explicit data_unavailable markers on computation failures
  - No fallback to estimates

Run: python3 loaders/load_sec_cash_flow_metrics.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.exception_handler import handle_exception, handle_invalid_data
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


class SecCashFlowMetricsLoader(OptimalLoader):
    """Compute cash flow health metrics from SEC audited financial statements.

    Provides working capital, capex, and free cash flow analysis for stock scoring.
    All metrics are derived from SEC-filed financial statements (not estimates).
    """

    table_name = "sec_cash_flow_metrics"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute cash flow metrics for one symbol from SEC statements.

        Returns:
            List with single metrics dict or data_unavailable marker
        """
        try:
            with DatabaseContext("read") as cur:
                # Get latest annual cash flow statement
                cur.execute(
                    """
                    SELECT
                        operating_cash_flow,
                        capex,
                        data_unavailable
                    FROM annual_cash_flow
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                cash_flow_row = cur.fetchone()

                # Get latest annual balance sheet for working capital
                cur.execute(
                    """
                    SELECT
                        current_assets,
                        current_liabilities,
                        data_unavailable
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                balance_row = cur.fetchone()

                # Get latest income statement for cash conversion rate
                cur.execute(
                    """
                    SELECT net_income
                    FROM annual_income_statement
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                income_row = cur.fetchone()

            # Validate data availability
            if not cash_flow_row or cash_flow_row[2]:  # data_unavailable flag
                return [self._unavailable_marker(symbol, "no_annual_cash_flow")]

            if not balance_row or balance_row[2]:
                return [self._unavailable_marker(symbol, "no_annual_balance_sheet")]

            operating_cf = safe_float(cash_flow_row[0], f"{symbol}.operating_cash_flow")
            capex = safe_float(cash_flow_row[1], f"{symbol}.capex")
            current_assets = safe_float(balance_row[0], f"{symbol}.current_assets")
            current_liabilities = safe_float(balance_row[1], f"{symbol}.current_liabilities")
            net_income = safe_float(income_row[0], f"{symbol}.net_income") if income_row else None

            # Compute metrics
            working_capital = None
            if current_assets is not None and current_liabilities is not None:
                working_capital = current_assets - current_liabilities

            free_cash_flow = None
            if operating_cf is not None and capex is not None:
                free_cash_flow = operating_cf - capex

            cash_conversion_rate = None
            if operating_cf is not None and net_income is not None and net_income != 0:
                cash_conversion_rate = operating_cf / net_income

            # Mark unavailable if no metrics computed
            all_metrics_missing = all([working_capital is None, free_cash_flow is None, cash_conversion_rate is None])

            return [
                {
                    "symbol": symbol,
                    "working_capital": working_capital,
                    "capex": capex,
                    "free_cash_flow": free_cash_flow,
                    "operating_cash_flow": operating_cf,
                    "cash_conversion_rate": cash_conversion_rate,
                    "data_unavailable": all_metrics_missing,
                    "reason": "no_computable_metrics" if all_metrics_missing else None,
                    "computed_at": date.today(),
                }
            ]

        except Exception as e:
            return [handle_exception(symbol, e, "sec_cash_flow_metrics")]


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(SecCashFlowMetricsLoader)
    except Exception as e:
        logger.error(f"[SEC_CASH_FLOW FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
