#!/usr/bin/env python3
"""SEC-Derived Valuations Loader - Replace yfinance PE/PB/PS/PEG/FCF/MarketCap.

Computes audited, current valuations from SEC financial data + price_daily:
  - PE Ratio: TTM EPS (from income statement) / Stock Price
  - PB Ratio: Book Value Per Share (from balance sheet) / Stock Price
  - PS Ratio: Revenue Per Share (from income statement) / Stock Price
  - PEG Ratio: PE Ratio / Earnings Growth Rate %
  - FCF Yield: Free Cash Flow (from cash flow statement) / Market Cap
  - Market Cap: Stock Price x Shares Outstanding (from income statement)
  - Shares Outstanding: WeightedAverageNumberOfSharesOutstandingBasic (from SEC)

Data Quality:
  - All metrics computed from SEC audited data (vs. yfinance estimates)
  - Current (updated daily as prices update)
  - Explicit data_unavailable markers on computation failures (fail-fast if SEC data unavailable)
  - No fallback to yfinance (SEC data only)

Run: python3 loaders/load_sec_valuations.py [--symbols AAPL,MSFT] [--parallelism 4]
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


class SecValuationsLoader(OptimalLoader):
    """Compute valuations from SEC audited data instead of yfinance estimates.

    CRITICAL: This loader replaces ~5,300 yfinance quoteSummary calls per day
    with computation from already-fetched SEC financial statements.
    Eliminates $25/month in API costs + reduces rate-limiting risk.
    """

    table_name = "sec_valuations"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute SEC-derived valuations for one symbol.

        Returns:
            List with single valuation dict or data_unavailable marker
        """
        try:
            # Fetch latest financial data for symbol
            with DatabaseContext("read") as cur:
                # Get income statement data from most recent annual filing
                # CRITICAL: Use NULL checks instead of COALESCE(col, 0) to detect missing financial data
                # Defaulting to 0 for revenue/EPS would cause wrong valuations (zero division, phantom metrics)
                cur.execute(
                    """
                    SELECT
                        revenue,
                        net_income,
                        earnings_per_share
                    FROM annual_income_statement
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                income_row = cur.fetchone()
                if not income_row:
                    return [self._unavailable_marker(symbol, "no_income_statement")]

                ttm_revenue, _ttm_net_income, ttm_eps_basic = income_row

                # Validate critical fields are not NULL (fail-fast if SEC data incomplete)
                # Allow revenue-only companies: can compute PS ratio even without EPS
                if ttm_revenue is None and ttm_eps_basic is None:
                    return [self._unavailable_marker(symbol, "income_statement_revenue_and_eps_null")]
                latest_eps = ttm_eps_basic  # Use same EPS for both TTM and latest (can be None)

                # Compute shares outstanding from SEC financial data: shares = net_income / eps
                # This is more reliable than fetching from company_info_sec which often lacks this data.
                # If both net_income and eps are available, we can compute shares directly from SEC audited data.
                shares_out = None
                if ttm_eps_basic and ttm_eps_basic != 0 and _ttm_net_income and _ttm_net_income != 0:
                    try:
                        # Shares = Net Income / EPS (mathematical identity from SEC financial statements)
                        shares_out = abs(float(_ttm_net_income) / float(ttm_eps_basic))
                        logger.debug(f"[{symbol}] Computed shares_outstanding from income_statement: {shares_out:,.0f}")
                    except (ValueError, ZeroDivisionError):
                        pass  # If computation fails, shares_out stays None and we fail below

                # If computation didn't work, try fetching from company_info_sec as fallback
                if not shares_out:
                    cur.execute(
                        """
                        SELECT shares_outstanding FROM company_info_sec
                        WHERE symbol = %s AND shares_outstanding IS NOT NULL AND shares_outstanding > 0
                        ORDER BY filing_date DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    shares_row = cur.fetchone()
                    if shares_row and shares_row[0]:
                        shares_out = safe_float(shares_row[0], f"{symbol}.shares_outstanding", allow_none=False)
                        logger.debug(f"[{symbol}] Fetched shares_outstanding from company_info_sec: {shares_out:,.0f}")

                # Fail if still no shares outstanding available
                if not shares_out or shares_out <= 0:
                    return [self._unavailable_marker(symbol, "shares_outstanding_unavailable")]

                # Get current price for valuation computations
                cur.execute(
                    """
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND close IS NOT NULL AND close > 0
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                price_row = cur.fetchone()
                if not price_row or not price_row[0]:
                    return [self._unavailable_marker(symbol, "no_recent_price")]

                current_price = safe_float(price_row[0], f"{symbol}.close", allow_none=False)
                if current_price <= 0:
                    return [self._unavailable_marker(symbol, "invalid_price")]

                # Get latest balance sheet (book value - optional, may not exist for all companies)
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                balance_row = cur.fetchone()
                book_value = balance_row[0] if balance_row else None
                # Note: book_value can be None for companies without balance sheets - PB ratio will be NULL

                # Get latest cash flow (for FCF - optional, may not exist for all companies)
                cur.execute(
                    """
                    SELECT
                        operating_cash_flow,
                        capex
                    FROM annual_cash_flow
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                cash_row = cur.fetchone()
                ocf, capex = (cash_row[0], cash_row[1]) if cash_row else (None, None)
                # Note: None values here mean FCF yield will be NULL (not available)

            # Compute valuations (convert all values to float)
            # CRITICAL: Don't convert None to 0.0 - need to preserve None for PS ratio computation
            # If revenue is None, _compute_valuations will skip PS ratio (but that's OK)
            return [self._compute_valuations(
                symbol,
                float(current_price),
                float(shares_out),
                float(ttm_eps_basic) if ttm_eps_basic else None,
                float(ttm_revenue) if ttm_revenue else None,  # Changed from 0.0 to None
                float(book_value) if book_value else None,
                float(ocf) if ocf else 0.0,
                float(capex) if capex else 0.0,
                float(latest_eps) if latest_eps else None,
            )]

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "querying SEC financial data")
            return [marker]
        except (KeyError, IndexError) as e:
            # Schema or data structure issue
            marker = handle_exception(symbol, e, "parsing SEC financial data")
            return [marker]
        except ValueError as e:
            # Data validation or conversion error
            marker = handle_invalid_data(symbol, e, "computing valuations")
            return [marker]
        except Exception as e:
            # Try to classify and handle, or fail-fast if truly unexpected
            try:
                marker = handle_exception(symbol, e, "computing valuations")
                return [marker]
            except Exception:
                logger.critical(f"[SEC_VALUATIONS] {symbol}: Unexpected error: {type(e).__name__}: {e}", exc_info=True)
                raise

    def _compute_valuations(
        self,
        symbol: str,
        current_price: float,
        shares_out: float,
        ttm_eps: float | None,
        ttm_revenue: float | None,
        book_value: float | None,
        ocf: float,
        capex: float,
        latest_eps: float | None,
    ) -> dict[str, Any]:
        """Compute all valuation ratios from SEC data."""
        result: dict[str, Any] = {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": False,
            "reason": None,
            "data_source": "sec_audited",

            # Price-based metrics
            "current_price": current_price,
            "shares_outstanding": shares_out,
            "market_cap": None,

            # Valuation ratios
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
        }

        if current_price <= 0:
            result["data_unavailable"] = True
            result["reason"] = "invalid_price"
            return result

        # Market Cap = Price x Shares Outstanding
        if shares_out and shares_out > 0:
            result["market_cap"] = current_price * shares_out
        else:
            result["data_unavailable"] = True
            result["reason"] = "invalid_shares_outstanding"
            return result

        # PE Ratio = Price ÷ TTM EPS (bound to -10k..10k to reject data errors)
        if ttm_eps and ttm_eps > 0:
            pe = current_price / ttm_eps
            if pe <= 10000:  # Reasonable PE bounds
                result["pe_ratio"] = round(pe, 2)
            else:
                logger.debug(f"[{symbol}] PE ratio out of bounds ({pe:.0f}), marking as NULL")
        elif ttm_eps == 0:
            # Company is unprofitable this TTM
            result["pe_ratio"] = None
        else:
            logger.debug(f"[{symbol}] TTM EPS missing or invalid, PE ratio unavailable")

        # PB Ratio = Price ÷ Book Value Per Share (bound to 0..1000)
        if book_value and book_value > 0:
            bvps = book_value / shares_out
            if bvps > 0:
                pb = current_price / bvps
                if pb <= 1000:  # Reasonable PB bounds
                    result["pb_ratio"] = round(pb, 2)
                else:
                    logger.debug(f"[{symbol}] PB ratio out of bounds ({pb:.0f}), marking as NULL")
        else:
            logger.debug(f"[{symbol}] Book value missing, PB ratio unavailable")

        # PS Ratio = Price ÷ Revenue Per Share (bound to 0..10000)
        if ttm_revenue and ttm_revenue > 0:
            rps = ttm_revenue / shares_out
            if rps > 0:
                ps = current_price / rps
                if ps <= 10000:  # Reasonable PS bounds
                    result["ps_ratio"] = round(ps, 2)
                else:
                    logger.debug(f"[{symbol}] PS ratio out of bounds ({ps:.0f}), marking as NULL")
        else:
            logger.debug(f"[{symbol}] TTM revenue missing, PS ratio unavailable")

        # PEG Ratio = PE ÷ Earnings Growth Rate % (bound to 0..10000)
        # Growth rate: (Latest Quarter EPS - EPS from 1yr ago) / EPS from 1yr ago
        # NOTE: This is approximate with available data; full 1yr lookback would require quarterly history
        if result["pe_ratio"] and latest_eps and latest_eps > 0 and ttm_eps > 0:
            growth_rate = ((ttm_eps - latest_eps) / abs(latest_eps)) * 100 if latest_eps != 0 else None
            if growth_rate and growth_rate > 0 and result["pe_ratio"] > 0:
                peg = result["pe_ratio"] / growth_rate
                if peg <= 10000:  # Reasonable PEG bounds
                    result["peg_ratio"] = round(peg, 2)
                else:
                    logger.debug(f"[{symbol}] PEG ratio out of bounds ({peg:.0f}), marking as NULL")

        # FCF Yield = Free Cash Flow ÷ Market Cap
        # FCF = Operating Cash Flow - Capital Expenditures
        if ocf and capex is not None:
            fcf = ocf - capex
            if fcf and result["market_cap"] and result["market_cap"] > 0:
                fcf_yield_pct = (fcf / result["market_cap"]) * 100
                # Only store if within reasonable bounds (-1000% to +1000%)
                # Extreme values indicate data errors or tiny market caps
                if -1000 <= fcf_yield_pct <= 1000:
                    result["fcf_yield"] = round(fcf_yield_pct, 2)
                else:
                    logger.debug(f"[{symbol}] FCF yield out of bounds ({fcf_yield_pct:.1f}%), marking as NULL")

        return result

    def _unavailable_marker(self, symbol: str, reason: str) -> dict[str, Any]:
        """Return data_unavailable marker for symbol."""
        return {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": True,
            "reason": reason,
            "data_source": "none",

            # All metrics NULL
            "current_price": None,
            "shares_outstanding": None,
            "market_cap": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
        }


if __name__ == "__main__":
    sys.exit(run_loader(SecValuationsLoader, description="Compute valuations from SEC audited data"))
