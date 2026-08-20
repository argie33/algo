#!/usr/bin/env python3
"""yfinance financial-statement fallback for SEC EDGAR XBRL gaps.

GOVERNANCE: SEC EDGAR is and stays the primary/preferred source for financial
statements - loaders/helpers/sec_base.py::SecEdgarStatementLoader only reaches for this
module when SEC genuinely has nothing for a symbol (cik_not_found, or a 404/empty-facts
response from every taxonomy - see that file's fetch_incremental). This is a fallback for
the ~500-650 symbols (out of ~4,922, confirmed live 2026-08-16) where that's true - REITs/
trusts/SPVs with no traditional XBRL filings, recent IPOs SEC hasn't indexed yet, foreign
filers with sparse coverage - never a competing/parallel source queried for every symbol.
Every row this module returns is tagged data_source='yfinance' downstream (never blended
anonymously with SEC data) per the same discipline
tests/unit/test_company_info_sec_no_yfinance_pollution.py enforces elsewhere.

Uses the SHARED cross-ECS-task IP circuit breaker (utils/external/yfinance_circuit_breaker.py),
same as utils/external/yfinance_analyst_ratings.py - both modules can be called for
thousands of symbols across a full pipeline run, so they must coordinate the same shared-IP
rate-limit state rather than each tracking their own.

Output shape mirrors utils/external/sec_statements.py's row format (dicts keyed by the same
snake_cased XBRL-concept names load_financial_statements.py's field_mapping already expects
- "revenues", "net_income_loss", "assets", "stockholders_equity", etc.) so a yfinance-sourced
row flows through the exact same transform()/precision-check/schema pipeline as a real SEC
row, with zero special-casing downstream.
"""

import logging
import math
import socket
from typing import Any

from utils.external.fx_rates import MAJOR_CURRENCIES, FxRateCache
from utils.external.yfinance_circuit_breaker import YFinanceStillBannedError, get_circuit_breaker
from utils.external.yfinance_symbol import to_yfinance_symbol

logger = logging.getLogger(__name__)

# FIXED 2026-08-19 (goal: A/D rating + DCF accuracy audit): unlike utils/external/
# sec_statements.py's XBRL path, this module applied ZERO currency handling - yfinance
# reports financial-statement DataFrames in the filer's OWN reporting currency
# (`Ticker.info["financialCurrency"]`), not necessarily USD, and this codebase's price/
# shares-outstanding data for the same symbol is always USD/ADR-denominated. Live-
# confirmed via direct DB query: GGAL (Grupo Financiero Galicia, ARS reporter)'s
# operating_cash_flow was -1.6 TRILLION for FY2025 (data_source='yfinance', raw ARS
# stored as if it were USD); SKM/KT (Korea Telecom/KT Corp, KRW reporters) had a ~1,300x
# jump between their sec_audited row (already correctly FX-converted via the mechanism
# below) and their yfinance row for the very next fiscal year - same company, same
# order-of-magnitude business, one row silently in KRW. This fed directly into
# load_sec_valuations.py's DCF (fcf_base = ocf - capex): dividing a local-currency
# numerator by a USD-denominated shares_out produced nonsense like $91,705/share
# "intrinsic value" for SUPV, or -960% "margin of safety" for names whose real FCF was
# merely modest. Reuses the same historical-date ECB rate lookup and MAJOR_CURRENCIES
# fail-closed discipline as the SEC path: a convertible major currency gets divided by
# that period's real rate, anything else gets rejected rather than stored unconverted.
_fx_rate_cache = FxRateCache()

# Share COUNTS, not currency amounts - must never be divided by an FX rate even when the
# rest of the income-statement row is being converted.
_SHARE_COUNT_FIELDS = frozenset(
    {
        "weighted_average_number_of_shares_outstanding_basic",
        "weighted_average_number_of_diluted_shares_outstanding",
    }
)


def _get_financial_currency(ticker: Any, symbol: str) -> str | None:
    """Best-effort lookup of the currency yfinance reports `symbol`'s statements in.

    Returns None ("unknown - assume USD, proceed unchanged") rather than raising: this is
    an enrichment on top of the statement fetch, not a hard requirement. The vast majority
    of symbols genuinely report in USD, and a `.info` call failing for an unrelated reason
    (network blip, yfinance schema change) must not lose otherwise-valid USD data over
    this alone. Only a POSITIVELY IDENTIFIED non-USD currency should change downstream
    behavior - same "fail open on unknown, fail closed on confirmed-bad" posture already
    used elsewhere in this codebase (e.g. has_annual_report_filing IS NOT FALSE).
    """
    try:
        info = ticker.info
        currency = info.get("financialCurrency") if isinstance(info, dict) else None
    except Exception as e:
        logger.debug(f"[YFINANCE_FALLBACK] {symbol}: financialCurrency lookup failed: {e}")
        return None
    return currency if isinstance(currency, str) else None


_RATE_LIMIT_KEYWORDS = ("429", "rate", "too many", "invalid crumb", "unauthorized")


def _is_rate_limit_error(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(keyword in error_str for keyword in _RATE_LIMIT_KEYWORDS)


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False


# yf.Ticker attribute name for each (statement_type, period) combo this codebase loads.
# No "ttm" entry - load_financial_statements.py's SecEdgarStatementLoader already rejects
# period='ttm' at init (see get_all_statement_configs()'s comment), so this fallback never
# needs to support it either.
_STATEMENT_ATTR = {
    ("income", "annual"): "income_stmt",
    ("income", "quarterly"): "quarterly_income_stmt",
    ("balance", "annual"): "balance_sheet",
    ("balance", "quarterly"): "quarterly_balance_sheet",
    ("cashflow", "annual"): "cashflow",
    ("cashflow", "quarterly"): "quarterly_cashflow",
}

# yfinance row label -> target key (same snake_cased XBRL-concept vocabulary
# load_financial_statements.py's _INCOME_FIELD_MAPPING already maps to DB columns).
# Live-confirmed against real AAPL/MSFT DataFrames (2026-08-16) - see this module's
# companion investigation notes. Deliberately narrower than the full SEC concept list:
# only the fields load_financial_statements.py's REQUIRED_METRICS check
# (revenue/net_income, total_assets/stockholders_equity, operating_cash_flow) plus the
# other mapped/scored fields need, not yfinance's full ~70-row statement dump.
_INCOME_FIELD_MAP = {
    "Total Revenue": "revenues",
    "Cost Of Revenue": "cost_of_revenue",
    "Gross Profit": "gross_profit",
    "Operating Income": "operating_income_loss",
    "Net Income": "net_income_loss",
    "Basic EPS": "earnings_per_share_basic",
    "Diluted EPS": "earnings_per_share_diluted",
    "Basic Average Shares": "weighted_average_number_of_shares_outstanding_basic",
    "Diluted Average Shares": "weighted_average_number_of_diluted_shares_outstanding",
    "Interest Expense": "interest_expense",
    "Reconciled Depreciation": "depreciation",
    "Tax Provision": "income_tax_expense_benefit",
    "Pretax Income": (
        "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest"
    ),
}

_BALANCE_FIELD_MAP = {
    "Total Assets": "assets",
    "Current Assets": "assets_current",
    "Total Liabilities Net Minority Interest": "liabilities",
    "Current Liabilities": "liabilities_current",
    "Stockholders Equity": "stockholders_equity",
    "Cash And Cash Equivalents": "cash_and_cash_equivalents_at_carrying_value",
    "Accounts Receivable": "accounts_receivable_net_current",
    "Inventory": "inventory_net",
    "Net PPE": "property_plant_and_equipment_net",
    "Goodwill": "goodwill",
    "Long Term Debt": "long_term_debt",
}

# yfinance reports these as signed outflows/contra-items (negative) for some filers; the
# SEC XBRL concepts they map to are always positive magnitudes in this codebase's real
# data (live-confirmed via direct DB query 2026-08-16: annual_income_statement.
# depreciation_expense is 100% positive across every SEC-sourced row). Also live-confirmed
# the sign flip itself: AAPL/MSFT capex and dividends negative in yfinance's cashflow
# DataFrame; WRB (an insurer)'s "Reconciled Depreciation" goes negative for 3 of 5 fiscal
# years while AAPL/MSFT/JNJ stay positive - not a fixed per-symbol convention, so abs() is
# applied uniformly rather than guessed per-filer. Without this, a negative depreciation
# value would SUBTRACT from EBITDA (operating_income + depreciation + amortization)
# instead of adding it back, and free_cash_flow = ocf - capex would add capex back instead
# of subtracting it - both silently wrong in the opposite direction from a missing value.
_ABS_MAGNITUDE_FIELDS = frozenset(
    {
        "payments_to_acquire_property_plant_and_equipment",
        "payments_of_dividends",
        "depreciation",
    }
)

_CASHFLOW_FIELD_MAP = {
    "Operating Cash Flow": "net_cash_provided_by_used_in_operating_activities",
    "Investing Cash Flow": "net_cash_provided_by_used_in_investing_activities",
    "Financing Cash Flow": "net_cash_provided_by_used_in_financing_activities",
    "Capital Expenditure": "payments_to_acquire_property_plant_and_equipment",
    "Cash Dividends Paid": "payments_of_dividends",
}

_FIELD_MAPS = {
    "income": _INCOME_FIELD_MAP,
    "balance": _BALANCE_FIELD_MAP,
    "cashflow": _CASHFLOW_FIELD_MAP,
}


def fetch_financial_statement(
    symbol: str,
    statement_type: str,
    period: str,
    timeout_sec: float = 15.0,
) -> list[dict[str, Any]] | None:
    """Fetch one statement/period combo from yfinance, shaped like sec_statements.py's output.

    Args:
        symbol: Stock ticker (yfinance takes tickers directly, no CIK lookup needed -
            this recovers the ~140/4,922 symbols SEC's cik_not_found case loses entirely).
        statement_type: 'income', 'balance', or 'cashflow'.
        period: 'annual' or 'quarterly'.
        timeout_sec: Per-request socket timeout.

    Returns:
        List of row dicts (symbol, fiscal_year, [fiscal_period for quarterly], plus
        whichever mapped concept keys yfinance actually reported non-NaN values for -
        same partial-coverage contract as sec_statements.py, unmapped/NaN cells are
        simply absent, not zero-filled), or None if yfinance has nothing usable either
        (empty/missing DataFrame, or every period had zero mapped fields with real data).

    Raises:
        RuntimeError: on a real fetch failure (network, rate limit, parse error) - the
        caller falls back to the standard SEC-unavailable marker, per this codebase's
        fail-explicit governance (never silently return an empty list on error).
    """
    attr = _STATEMENT_ATTR.get((statement_type, period))
    if attr is None:
        raise ValueError(f"Unsupported statement_type/period combo for yfinance fallback: {statement_type}/{period}")

    circuit_breaker = get_circuit_breaker()
    try:
        circuit_breaker.wait_or_raise()
    except YFinanceStillBannedError as e:
        raise RuntimeError(f"yfinance shared IP ban active: {e}") from e

    import yfinance as yf

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_sec)
    try:
        ticker = yf.Ticker(to_yfinance_symbol(symbol))
        df = getattr(ticker, attr)
    except TimeoutError:
        raise RuntimeError(f"yfinance {attr} fetch timeout for {symbol} (>{timeout_sec}s)") from None
    except Exception as e:
        if _is_rate_limit_error(e):
            circuit_breaker.report_rate_limit_error()
        raise RuntimeError(f"yfinance {attr} fetch failed for {symbol}: {e}") from e
    finally:
        socket.setdefaulttimeout(old_timeout)

    circuit_breaker.report_success()

    if df is None or df.empty:
        return None

    # Currency guard (see module docstring above _fx_rate_cache): reject outright rather
    # than store a confirmed non-USD, non-convertible currency's raw magnitudes as if they
    # were USD. A currency we can't identify (financial_currency is None) falls through
    # unconverted, same as before this fix - the common, correct case for the many
    # domestic filers this fallback also serves.
    financial_currency = _get_financial_currency(ticker, symbol)
    if financial_currency and financial_currency != "USD" and financial_currency not in MAJOR_CURRENCIES:
        logger.info(
            f"[YFINANCE_FALLBACK] {symbol}: financialCurrency={financial_currency} has no USD conversion "
            f"available - rejecting yfinance {statement_type} fallback rather than storing raw "
            f"{financial_currency} magnitudes mislabeled as USD."
        )
        return None

    field_map = _FIELD_MAPS[statement_type]
    rows: list[dict[str, Any]] = []
    for period_end in df.columns:
        try:
            fiscal_year = int(period_end.year)
        except (AttributeError, ValueError, TypeError):
            # Malformed/unexpected column (not a real period Timestamp) - skip rather
            # than fail the whole symbol; other columns may still be usable.
            continue

        # For a confirmed major non-USD currency, convert every monetary value in this
        # period using that period's own historical rate (never a guessed/current rate -
        # matches sec_statements.py's discipline). If no rate is available for this exact
        # date, skip the whole period rather than mix converted and unconverted fields.
        fx_rate: float | None = None
        if financial_currency and financial_currency != "USD" and financial_currency in MAJOR_CURRENCIES:
            date_str = period_end.strftime("%Y-%m-%d")
            fx_rate = _fx_rate_cache.get_usd_rate(financial_currency, date_str)
            if fx_rate is None or fx_rate == 0:
                logger.debug(
                    f"[YFINANCE_FALLBACK] {symbol}: no USD rate for {financial_currency}/{date_str}, "
                    f"skipping this period rather than storing unconverted {financial_currency} values"
                )
                continue

        row: dict[str, Any] = {"symbol": symbol, "fiscal_year": fiscal_year}
        if period == "quarterly":
            # Best-effort calendar-quarter label, not a real fiscal-period tag like SEC's
            # fp field (which is filer-fiscal-calendar-relative, e.g. Apple's Q1 ends in
            # December). Acceptable here because this fallback only ever fires when SEC
            # returned NOTHING for the whole symbol/statement (see this module's
            # docstring) - there's no existing SEC quarterly row for this symbol to
            # collide with, and fiscal_quarter is used for chronological ordering /
            # "latest" lookups downstream, not exact fiscal-period matching.
            row["fiscal_period"] = f"Q{((period_end.month - 1) // 3) + 1}"

        has_data = False
        for yf_label, target_key in field_map.items():
            if yf_label not in df.index:
                continue
            value = df.loc[yf_label, period_end]
            if value is None or _is_nan(value):
                continue
            value = float(value)
            if target_key in _ABS_MAGNITUDE_FIELDS:
                value = abs(value)
            if fx_rate is not None and target_key not in _SHARE_COUNT_FIELDS:
                value = value / fx_rate
            row[target_key] = value
            has_data = True

        if has_data:
            rows.append(row)

    if not rows:
        return None
    return rows
