#!/usr/bin/env python3
"""SEC-Derived Valuations Loader - Replace yfinance PE/PB/PS/PEG/FCF/MarketCap.

Computes audited, current valuations from SEC financial data + price_daily:
  - PE Ratio: TTM EPS (from income statement) / Stock Price
  - PB Ratio: Book Value Per Share (from balance sheet) / Stock Price
  - PS Ratio: Revenue Per Share (from income statement) / Stock Price
  - PEG Ratio: PE Ratio / Earnings Growth Rate %
  - FCF Yield: Free Cash Flow (from cash flow statement) / Market Cap
  - Market Cap: Stock Price x Shares Outstanding (from income statement)
  - Shares Outstanding: WeightedAverageNumberOfSharesOutstandingBasic (from SEC, migration 1171),
    falling back to net_income/eps derivation, then company_info_sec, if unavailable

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
                # NOTE: Removed data_unavailable = FALSE filter to prevent premature early exit
                cur.execute(
                    """
                    SELECT
                        revenue,
                        net_income,
                        earnings_per_share,
                        operating_income,
                        depreciation_expense,
                        amortization_expense,
                        shares_outstanding_basic
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC LIMIT 2
                    """,
                    (symbol,),
                )
                income_rows = cur.fetchall()
                if not income_rows:
                    return [self._unavailable_marker(symbol, "no_income_statement")]

                (
                    ttm_revenue,
                    _ttm_net_income,
                    ttm_eps_basic,
                    operating_income,
                    depreciation_expense,
                    amortization_expense,
                    reported_shares_outstanding,
                ) = income_rows[0]
                # PEG's growth-rate leg needs a genuinely prior-year EPS, not the same TTM
                # value used twice - GOVERNANCE: this used to set `latest_eps = ttm_eps_basic`
                # (comment literally said "Use same EPS for both TTM and latest"), which made
                # _compute_valuations()'s growth_rate = (ttm_eps - latest_eps)/abs(latest_eps)
                # always exactly 0 for every symbol, so peg_ratio silently never populated
                # anywhere in the system with no marker flagging PEG specifically as broken.
                # A missing second fiscal year (new filer, gap) leaves it None, which
                # _compute_valuations already handles by leaving peg_ratio NULL.
                prior_year_eps = income_rows[1][2] if len(income_rows) > 1 else None  # Index 2 = earnings_per_share

                # Validate critical fields are not NULL (fail-fast if SEC data incomplete)
                # Allow revenue-only companies: can compute PS ratio even without EPS
                if ttm_revenue is None and ttm_eps_basic is None:
                    return [self._unavailable_marker(symbol, "income_statement_revenue_and_eps_null")]

                # Prefer the real, officially-reported weighted-average basic share count
                # (SEC XBRL WeightedAverageNumberOfSharesOutstandingBasic, migration 1171)
                # over the derived net_income/eps proxy below - EPS is reported rounded to
                # 2 decimals, so back-computing shares from it loses real precision (material
                # for large-caps with billions of shares). FIXED 2026-07-28: this concept was
                # fetched from SEC every run but silently discarded (see sec_statements.py),
                # so the derived proxy ran unconditionally despite this docstring's own claim
                # (line 11 above) that the real concept was already the source.
                shares_out = None
                if reported_shares_outstanding and reported_shares_outstanding > 0:
                    shares_out = float(reported_shares_outstanding)
                    logger.debug(f"[{symbol}] Using reported shares_outstanding_basic: {shares_out:,.0f}")

                # Fallback: compute shares outstanding from SEC financial data: shares = net_income / eps.
                # If both net_income and eps are available, we can compute shares directly from SEC audited data.
                if not shares_out and ttm_eps_basic and ttm_eps_basic != 0 and _ttm_net_income and _ttm_net_income != 0:
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
                # NOTE: Removed data_unavailable = FALSE filter to allow fallback computation
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                balance_row = cur.fetchone()
                book_value = balance_row[0] if balance_row else None
                # Note: book_value can be None for companies without balance sheets - PB ratio will be NULL

                # Get latest cash flow (for FCF - optional, may not exist for all companies)
                # NOTE: Removed data_unavailable = FALSE filter to allow partial computation
                cur.execute(
                    """
                    SELECT
                        operating_cash_flow,
                        capex,
                        dividends_paid
                    FROM annual_cash_flow
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                cash_row = cur.fetchone()
                ocf, capex, dividends_paid = cash_row if cash_row else (None, None, None)
                # Note: None values here mean FCF yield/dividend yield will be NULL (not available)

                # Get debt and cash from balance sheet (for Enterprise Value)
                # NOTE: Removed data_unavailable = FALSE filter to allow partial computation
                cur.execute(
                    """
                    SELECT
                        total_liabilities,
                        cash_and_equivalents
                    FROM annual_balance_sheet
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                debt_row = cur.fetchone()
                total_debt, total_cash = debt_row if debt_row else (None, None)
                # Note: None values mean EV metrics won't be computed

                # Session 398: Calculate EBITDA from operating income + depreciation + amortization
                # EBITDA = Operating Income + Depreciation + Amortization
                # Use operating income as base; add D&A if available (even if just one of them)
                ebitda = None
                oi = safe_float(operating_income, f"{symbol}.operating_income", allow_none=True)
                if oi is not None:
                    dep_exp = safe_float(depreciation_expense, f"{symbol}.depreciation_expense", allow_none=True)
                    amort_exp = safe_float(amortization_expense, f"{symbol}.amortization_expense", allow_none=True)

                    # Start with operating income as EBITDA base
                    ebitda_val = oi
                    if dep_exp:
                        ebitda_val += dep_exp
                    if amort_exp:
                        ebitda_val += amort_exp

                    # Set EBITDA - always use it if operating income is available
                    ebitda = ebitda_val

            # Compute valuations (convert all values to float)
            # CRITICAL: Don't convert None to 0.0 - need to preserve None for PS ratio computation
            # If revenue is None, _compute_valuations will skip PS ratio (but that's OK)
            return [
                self._compute_valuations(
                    symbol,
                    float(current_price),
                    float(shares_out),
                    float(ttm_eps_basic) if ttm_eps_basic else None,
                    float(ttm_revenue) if ttm_revenue else None,  # Changed from 0.0 to None
                    float(book_value) if book_value else None,
                    float(ocf) if ocf else 0.0,
                    float(capex) if capex else 0.0,
                    float(prior_year_eps) if prior_year_eps else None,
                    float(dividends_paid) if dividends_paid else None,
                    float(total_debt) if total_debt else None,
                    float(total_cash) if total_cash else None,
                    float(ebitda) if ebitda else None,
                )
            ]

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
            marker = handle_exception(symbol, e, "computing valuations")
            return [marker]

    def _compute_valuations(  # noqa: C901
        self,
        symbol: str,
        current_price: float,
        shares_out: float,
        ttm_eps: float | None,
        ttm_revenue: float | None,
        book_value: float | None,
        ocf: float,
        capex: float,
        prior_year_eps: float | None,
        dividends_paid: float | None,
        total_debt: float | None,
        total_cash: float | None,
        ebitda: float | None,
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
            # Balance sheet metrics
            "total_debt": total_debt,
            "total_cash": total_cash,
            "enterprise_value": None,
            "ebitda": ebitda,
            # Valuation ratios
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "forward_pe": None,
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
                logger.warning(f"[{symbol}] PE ratio out of bounds ({pe:.0f}), marking as NULL")
        elif ttm_eps == 0:
            # Company is unprofitable this TTM
            result["pe_ratio"] = None
        else:
            logger.warning(f"[{symbol}] TTM EPS missing or invalid, PE ratio unavailable")

        # PB Ratio = Price ÷ Book Value Per Share (bound to 0..1000)
        if book_value and book_value > 0:
            bvps = book_value / shares_out
            if bvps > 0:
                pb = current_price / bvps
                if pb <= 1000:  # Reasonable PB bounds
                    result["pb_ratio"] = round(pb, 2)
                else:
                    logger.warning(f"[{symbol}] PB ratio out of bounds ({pb:.0f}), marking as NULL")
        else:
            logger.warning(f"[{symbol}] Book value missing, PB ratio unavailable")

        # PS Ratio = Price ÷ Revenue Per Share (bound to 0..10000)
        if ttm_revenue and ttm_revenue > 0:
            rps = ttm_revenue / shares_out
            if rps > 0:
                ps = current_price / rps
                if ps <= 10000:  # Reasonable PS bounds
                    result["ps_ratio"] = round(ps, 2)
                else:
                    logger.warning(f"[{symbol}] PS ratio out of bounds ({ps:.0f}), marking as NULL")
        else:
            logger.warning(f"[{symbol}] TTM revenue missing, PS ratio unavailable")

        # PEG Ratio = PE ÷ Earnings Growth Rate % (bound to 0..10000)
        # Growth rate: (TTM EPS - EPS from prior fiscal year) / EPS from prior fiscal year
        # NOTE: Annual (fiscal-year over fiscal-year), not quarterly - full quarterly
        # lookback would require quarterly history this loader doesn't fetch.
        if (
            result["pe_ratio"]
            and prior_year_eps is not None
            and prior_year_eps > 0
            and ttm_eps is not None
            and ttm_eps > 0
        ):
            growth_rate = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100 if prior_year_eps != 0 else None
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

        # Dividend Yield = Dividends Paid ÷ Market Cap (stored as a decimal fraction, e.g.
        # 0.03 = 3% - matches load_stock_scores.py._score_value's existing "decimal ->
        # percent" conversion for this field; NOT the same convention as fcf_yield above,
        # which is stored as a percentage already).
        if dividends_paid and dividends_paid > 0 and result["market_cap"] and result["market_cap"] > 0:
            div_yield = dividends_paid / result["market_cap"]
            if 0 < div_yield <= 1.0:  # >100% yield indicates a data error
                result["dividend_yield"] = round(div_yield, 4)
            else:
                logger.debug(f"[{symbol}] Dividend yield out of bounds ({div_yield:.2%}), marking as NULL")

        # Enterprise Value = Market Cap + Total Debt - Cash & Equivalents
        if result["market_cap"] is not None:
            debt_val = total_debt if total_debt else 0
            cash_val = total_cash if total_cash else 0
            ev = result["market_cap"] + debt_val - cash_val
            if ev > 0:
                result["enterprise_value"] = round(ev, 2)
            else:
                logger.debug(f"[{symbol}] Enterprise value non-positive ({ev:.0f}), marking as NULL")

        # EV / EBITDA Ratio
        if result["enterprise_value"] and ebitda and ebitda > 0:
            ev_ebitda = result["enterprise_value"] / ebitda
            if 0 < ev_ebitda <= 10000:  # Reasonable bounds
                result["ev_ebitda"] = round(ev_ebitda, 2)
            else:
                logger.debug(f"[{symbol}] EV/EBITDA out of bounds ({ev_ebitda:.0f}), marking as NULL")

        # EV / Revenue Ratio
        if result["enterprise_value"] and ttm_revenue and ttm_revenue > 0:
            ev_revenue = result["enterprise_value"] / ttm_revenue
            if 0 < ev_revenue <= 10000:  # Reasonable bounds
                result["ev_revenue"] = round(ev_revenue, 2)
            else:
                logger.debug(f"[{symbol}] EV/Revenue out of bounds ({ev_revenue:.0f}), marking as NULL")

        # Forward PE Ratio removed: Requires external analyst data (Polygon/etc).
        # Removed per GOVERNANCE.md: no external fallbacks for financial metrics.
        # All metrics computed from SEC audited data only.

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
            "total_debt": None,
            "total_cash": None,
            "enterprise_value": None,
            "ebitda": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
        }


if __name__ == "__main__":
    sys.exit(run_loader(SecValuationsLoader, description="Compute valuations from SEC audited data"))
