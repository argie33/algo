#!/usr/bin/env python3
# TRIGGER: 2026-01-28 - CRITICAL DATA LOSS FIX DEPLOYED - Rerun required immediately
"""
# CRITICAL: 2026-01-28 - DROP TABLE vulnerability patched - data now safely preserved
Daily Company Data Loader - Enhanced Positioning Analytics
Consolidates daily-update loaders into single efficient loader

Loads company info, positioning data, analyst estimates, and earnings history with one API call per symbol.
Updated: 2025-12-03 - Added earnings history consolidation from loadearningshistory.py
Consolidation: Now loads both analyst estimates AND historical earnings in single loader

PERFORMANCE NOTE (AWS): This loader experiences timeout issues with yfinance API calls.
- Known issue: yfinance hangs on certain ticker.info() calls
- Recommendation: Implement parallel processing with concurrent futures
- Current status: Works locally but times out under AWS load
- Last stable run: 2026-01-23

Replaces:
- loadinfo.py (ticker.info)
- loadpositioning.py (institutional/mutual fund holders)
- loadearningsestimate.py (earnings estimates)
- loadrevenueestimate.py (revenue estimates)
- loadearningshistory.py (historical earnings actuals) ← NEW

Data Loaded:
- Company profile & market data (from ticker.info)
- Institutional & mutual fund holdings with type classification
- Insider transactions & roster (buy/sell activity + current holdings)
- Positioning metrics (institutional/insider ownership, short interest)
- Earnings & revenue estimates (analyst forecasts)
- Earnings history (actual reported earnings by quarter)

NEW POSITIONING DATA AVAILABLE:
- insider_transactions: Individual insider buy/sell events (90-day window for analysis)
- insider_roster: Current insider holdings roster with position details
- institutional_positioning: Enhanced with institution_type (MUTUAL_FUND, HEDGE_FUND, PENSION_FUND)
- positioning_metrics: Core positioning metrics (institutional ownership, short interest, etc.)

These tables power the enhanced 4-component positioning score:
1. Institutional Quality (25 pts): ownership % + institution diversity
2. Insider Conviction (25 pts): ownership % + recent buy/sell activity
3. Short Interest (25 pts): level + trend analysis
4. Smart Money Flow (25 pts): mutual fund + hedge fund positioning

Author: Financial Dashboard System
Updated: 2025-10-11
Trigger: 20251227-120600-AWS-ECS - Load company data and key metrics to AWS RDS
"""

import gc
import json
import logging
import os
import resource
import sys
import time
from datetime import date, datetime
from typing import Dict, List, Optional
from functools import wraps

import boto3
import pandas as pd
import psycopg2
import psycopg2.extensions
import numpy as np
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Script metadata
SCRIPT_NAME = "loaddailycompanydata.py"
logging.basicConfig(
    level=logging.INFO,  # Keep at INFO to avoid yfinance debug spam
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Retry decorator for yfinance API calls (handle 500 errors, timeouts, etc.)
def retry_with_backoff(max_retries=2, base_delay=2):
    """Retry decorator with exponential backoff for API calls - handles rate limiting, HTTP errors, timeouts, etc."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    # Retry on rate limits, HTTP 500, 503, timeouts, and network errors
                    is_retriable = any(x in error_str for x in ['rate limit', '429', '500', '503', 'timeout', 'connection', 'temporarily unavailable', 'remote end closed'])

                    # For rate limit errors, use much longer delay
                    if 'rate limit' in error_str or '429' in error_str:
                        delay = 5 * (2 ** attempt)  # 5s, 10s - much longer for rate limits
                        logging.warning(f"⚠️ RATE LIMITED on {func.__name__}. Waiting {delay}s before retry...")
                    else:
                        delay = base_delay * (2 ** attempt)  # 2s, 4s for other errors
                        logging.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay}s...")

                    if attempt < max_retries - 1 and is_retriable:
                        time.sleep(delay)
                    else:
                        logging.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")
                        raise
        return wrapper
    return decorator

# Register numpy type adapters
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables.

    Tries AWS Secrets Manager first (DB_SECRET_ARN + AWS_REGION), then falls back to environment variables.
    Uses sensible defaults for local development.
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"Loaded database credentials from AWS Secrets Manager: {db_secret_arn}")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to load from Secrets Manager: {e}")

    # Fallback to environment variables with sensible defaults for local development
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    logging.info(f"Using database credentials from environment (with defaults): {db_user}@{db_host}/{db_name}")
    return {
        "host": db_host,
        "port": int(db_port),
        "user": db_user,
        "password": db_password,
        "dbname": db_name
    }


def safe_float(value, default=None, max_val=None, min_val=None):
    """Safely convert to float with optional bounds checking"""
    if value is None or pd.isna(value):
        return default
    try:
        f = float(value)
        # Handle NaN/Inf
        if np.isnan(f) or np.isinf(f):
            return default
        # Clamp to bounds if provided
        if max_val is not None and f > max_val:
            f = max_val
        if min_val is not None and f < min_val:
            f = min_val
        return f
    except (ValueError, TypeError):
        return default


def calculate_ad_rating(inst_ownership, insider_ownership, short_interest, cur, symbol):
    """
    Placeholder for A/D Rating calculation.

    IBD A/D Rating is calculated separately in batch after all data is loaded.
    Uses volume analysis over 13 weeks to generate A-E grades.

    This function returns None during load phase.
    """
    return None


def safe_int(value, default=None, max_val=None, min_val=None):
    """Safely convert to int with optional bounds checking"""
    if value is None or pd.isna(value):
        return default
    try:
        i = int(value)
        # Clamp to bounds if provided
        if max_val is not None and i > max_val:
            i = max_val
        if min_val is not None and i < min_val:
            i = min_val
        return i
    except (ValueError, TypeError):
        return default


def safe_str(value, default=None, max_len=None):
    """Safely convert to string with optional length truncation"""
    if value is None or pd.isna(value):
        return default
    try:
        s = str(value).strip()
        if not s:
            return default
        if max_len is not None and len(s) > max_len:
            s = s[:max_len]
        return s
    except (ValueError, TypeError, AttributeError):
        return default


def safe_date(value, default=None):
    """Safely convert pandas Timestamp to date, handling NaT"""
    if value is None or pd.isna(value):
        return default
    try:
        if hasattr(value, 'date'):
            return value.date()
        return value
    except (ValueError, TypeError, AttributeError):
        return default


def pyval(val):
    """Convert numpy types to native Python types"""
    if isinstance(val, (np.generic,)):
        return val.item()
    return val






def calculate_missing_metrics(symbol: str, info: dict, ticker) -> dict:
    """REAL DATA ONLY - Get metrics directly from yfinance, no calculations or fallbacks"""

    metrics = {
        'earnings_growth': info.get('earningsGrowth'),
        'payout_ratio': info.get('payoutRatio'),
        'debt_to_equity': info.get('debtToEquity'),
        'de_source': 'YFINANCE',
    }

    # NO FALLBACK CALCULATIONS
    # If yfinance doesn't provide a metric, it stays NULL (not calculated)
    # Do not calculate from:
    #  - earnings_estimate (causes estimation bias)
    #  - dividend/EPS ratios (approximations)
    #  - balance sheet components (too much data quality variation)

    return metrics


def load_all_realtime_data(symbol: str, cur, conn) -> Dict:
    """Load ALL daily data from single yfinance API call"""

    @retry_with_backoff(max_retries=2, base_delay=1)  # Reduce retries from 5 to 2 (delisted stocks won't recover)
    def fetch_yfinance_data(yf_symbol):
        """Fetch yfinance data with retry logic for temporary errors only"""
        ticker = yf.Ticker(yf_symbol)
        return {
            'ticker': ticker,  # Return the ticker object itself
            'info': ticker.info,
            'institutional_holders': ticker.institutional_holders,
            'mutualfund_holders': ticker.mutualfund_holders,
            'insider_transactions': ticker.insider_transactions,
            'insider_roster': ticker.insider_roster_holders,
            'major_holders': ticker.major_holders,
            'earnings_estimate': ticker.earnings_estimate,
            'revenue_estimate': ticker.revenue_estimate
        }

    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)
        yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()

        # SINGLE API CALL gets everything (with retry)
        data = fetch_yfinance_data(yf_symbol)
        ticker = data['ticker']  # Reuse the ticker object - avoid duplicate HTTP 500 errors
        info = data['info']
        institutional_holders = data['institutional_holders']
        mutualfund_holders = data['mutualfund_holders']
        insider_transactions = data['insider_transactions']
        insider_roster = data['insider_roster']
        major_holders = data['major_holders']
        earnings_estimate = data['earnings_estimate']
        revenue_estimate = data['revenue_estimate']

        # Calculate missing metrics
        missing_metrics = calculate_missing_metrics(symbol, info, ticker)

        stats = {
            'info': 0,
            'institutional': 0,
            'mutualfund': 0,
            'insider_txns': 0,
            'insider_roster': 0,
            'positioning': 0,
            'earnings_est': 0,
            'revenue_est': 0,
            'volatility': 0,
            'drawdown': 0,
            'beta': 0,
        }

        # NOTE: volatility and drawdown calculations moved to loadfactormetrics.py
        # This loader only loads raw yfinance data

        # 1. Insert company_profile, market_data, key_metrics (from ticker.info)
        # ONLY attempt insert if we have real data from yfinance
        if info and isinstance(info, dict) and len(info) > 5:
            try:
                # Company profile
                cur.execute(
                    """
                    INSERT INTO company_profile (
                        ticker, short_name, long_name, display_name, quote_type,
                        symbol_type, triggerable, has_pre_post_market_data, price_hint,
                        max_age_sec, language, region, financial_currency, currency,
                        market, quote_source_name, custom_price_alert_confidence,
                        address1, city, state, postal_code, country, phone_number,
                        website_url, ir_website_url, message_board_id, corporate_actions,
                        sector, sector_key, sector_disp, industry, industry_key,
                        industry_disp, business_summary, employee_count,
                        first_trade_date_ms, gmt_offset_ms, exchange,
                        full_exchange_name, exchange_timezone_name,
                        exchange_timezone_short_name, exchange_data_delayed_by_sec,
                        post_market_time_ms, regular_market_time_ms
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        short_name = EXCLUDED.short_name,
                        long_name = EXCLUDED.long_name,
                        display_name = EXCLUDED.display_name,
                        quote_type = EXCLUDED.quote_type
                """,
                    (
                        symbol, info.get("shortName"), info.get("longName"),
                        info.get("displayName"), info.get("quoteType"),
                        info.get("symbolType"), info.get("triggerable"),
                        info.get("hasPrePostMarketData"), info.get("priceHint"),
                        info.get("maxAge"), info.get("language"), info.get("region"),
                        info.get("financialCurrency"), info.get("currency"),
                        info.get("market"), info.get("quoteSourceName"),
                        info.get("customPriceAlertConfidence"), info.get("address1"),
                        info.get("city"), info.get("state"), info.get("zip"),
                        info.get("country"), info.get("phone"), info.get("website"),
                        info.get("irWebsite"), info.get("messageBoardId"),
                        json.dumps(info.get("corporateActions", {})),
                        info.get("sector"), info.get("sectorKey"),
                        info.get("sectorDisp"), info.get("industry"),
                        info.get("industryKey"), info.get("industryDisp"),
                        info.get("longBusinessSummary"),
                        info.get("fullTimeEmployees"),
                        info.get("firstTradeDateEpochUtc"),
                        info.get("gmtOffSetMilliseconds"), info.get("exchange"),
                        info.get("fullExchangeName"),
                        info.get("exchangeTimezoneName"),
                        info.get("exchangeTimezoneShortName"),
                        info.get("exchangeDataDelayedBy"),
                        info.get("postMarketTime"),
                        info.get("regularMarketTime"),
                    ),
                )

                # Key metrics (with valuation data from yfinance)
                cur.execute(
                    """
                    INSERT INTO key_metrics (
                        ticker, trailing_pe, forward_pe, price_to_sales_ttm,
                        price_to_book, book_value, peg_ratio, enterprise_value,
                        ev_to_revenue, ev_to_ebitda, total_revenue, net_income,
                        ebitda, gross_profit, eps_trailing, eps_forward,
                        eps_current_year, price_eps_current_year,
                        earnings_q_growth_pct, earnings_ts_ms,
                        earnings_ts_start_ms, earnings_ts_end_ms,
                        earnings_call_ts_start_ms, earnings_call_ts_end_ms,
                        is_earnings_date_estimate, total_cash, cash_per_share,
                        operating_cashflow, free_cashflow, total_debt,
                        debt_to_equity, quick_ratio, current_ratio,
                        profit_margin_pct, gross_margin_pct, ebitda_margin_pct,
                        operating_margin_pct, return_on_assets_pct,
                        return_on_equity_pct, revenue_growth_pct,
                        earnings_growth_pct,
                        last_split_date_ms, dividend_rate, dividend_yield,
                        five_year_avg_dividend_yield, ex_dividend_date_ms,
                        last_annual_dividend_amt, last_annual_dividend_yield,
                        last_dividend_amt, last_dividend_date_ms,
                        dividend_date_ms, payout_ratio,
                        held_percent_insiders, held_percent_institutions,
                        shares_short, shares_short_prior_month,
                        short_ratio, short_percent_of_float,
                        implied_shares_outstanding, float_shares
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        trailing_pe = EXCLUDED.trailing_pe,
                        forward_pe = EXCLUDED.forward_pe,
                        price_to_sales_ttm = EXCLUDED.price_to_sales_ttm,
                        price_to_book = EXCLUDED.price_to_book,
                        book_value = EXCLUDED.book_value,
                        peg_ratio = EXCLUDED.peg_ratio,
                        enterprise_value = EXCLUDED.enterprise_value,
                        ev_to_revenue = EXCLUDED.ev_to_revenue,
                        ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                        total_revenue = EXCLUDED.total_revenue,
                        net_income = EXCLUDED.net_income,
                        ebitda = EXCLUDED.ebitda,
                        gross_profit = EXCLUDED.gross_profit,
                        eps_trailing = EXCLUDED.eps_trailing,
                        eps_forward = EXCLUDED.eps_forward,
                        eps_current_year = EXCLUDED.eps_current_year,
                        price_eps_current_year = EXCLUDED.price_eps_current_year,
                        earnings_q_growth_pct = EXCLUDED.earnings_q_growth_pct,
                        earnings_ts_ms = EXCLUDED.earnings_ts_ms,
                        earnings_ts_start_ms = EXCLUDED.earnings_ts_start_ms,
                        earnings_ts_end_ms = EXCLUDED.earnings_ts_end_ms,
                        earnings_call_ts_start_ms = EXCLUDED.earnings_call_ts_start_ms,
                        earnings_call_ts_end_ms = EXCLUDED.earnings_call_ts_end_ms,
                        is_earnings_date_estimate = EXCLUDED.is_earnings_date_estimate,
                        total_cash = EXCLUDED.total_cash,
                        cash_per_share = EXCLUDED.cash_per_share,
                        operating_cashflow = EXCLUDED.operating_cashflow,
                        free_cashflow = EXCLUDED.free_cashflow,
                        total_debt = EXCLUDED.total_debt,
                        debt_to_equity = EXCLUDED.debt_to_equity,
                        quick_ratio = EXCLUDED.quick_ratio,
                        current_ratio = EXCLUDED.current_ratio,
                        profit_margin_pct = EXCLUDED.profit_margin_pct,
                        gross_margin_pct = EXCLUDED.gross_margin_pct,
                        ebitda_margin_pct = EXCLUDED.ebitda_margin_pct,
                        operating_margin_pct = EXCLUDED.operating_margin_pct,
                        return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                        return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                        revenue_growth_pct = EXCLUDED.revenue_growth_pct,
                        earnings_growth_pct = EXCLUDED.earnings_growth_pct,
                        last_split_date_ms = EXCLUDED.last_split_date_ms,
                        dividend_rate = EXCLUDED.dividend_rate,
                        dividend_yield = EXCLUDED.dividend_yield,
                        five_year_avg_dividend_yield = EXCLUDED.five_year_avg_dividend_yield,
                        ex_dividend_date_ms = EXCLUDED.ex_dividend_date_ms,
                        last_annual_dividend_amt = EXCLUDED.last_annual_dividend_amt,
                        last_annual_dividend_yield = EXCLUDED.last_annual_dividend_yield,
                        last_dividend_amt = EXCLUDED.last_dividend_amt,
                        last_dividend_date_ms = EXCLUDED.last_dividend_date_ms,
                        dividend_date_ms = EXCLUDED.dividend_date_ms,
                        payout_ratio = EXCLUDED.payout_ratio,
                        held_percent_insiders = EXCLUDED.held_percent_insiders,
                        held_percent_institutions = EXCLUDED.held_percent_institutions,
                        shares_short = EXCLUDED.shares_short,
                        shares_short_prior_month = EXCLUDED.shares_short_prior_month,
                        short_ratio = EXCLUDED.short_ratio,
                        short_percent_of_float = EXCLUDED.short_percent_of_float,
                        implied_shares_outstanding = EXCLUDED.implied_shares_outstanding,
                        float_shares = EXCLUDED.float_shares
                """,
                    (
                        symbol,
                        safe_float(info.get("trailingPE"), max_val=9999.99),
                        safe_float(info.get("forwardPE"), max_val=9999.99),
                        safe_float(info.get("priceToSalesTrailing12Months"), max_val=9999.99),
                        safe_float(info.get("priceToBook"), max_val=9999.99),
                        safe_int(info.get("bookValue")),
                        safe_float(info.get("trailingPegRatio"), max_val=100, min_val=0),
                        safe_int(info.get("enterpriseValue")),
                        safe_float(info.get("enterpriseToRevenue"), max_val=9999.99),
                        safe_float(info.get("enterpriseToEbitda"), max_val=9999.99),
                        safe_int(info.get("totalRevenue")),
                        safe_int(info.get("netIncomeToCommon")),
                        safe_int(info.get("ebitda")),
                        safe_int(info.get("grossProfits")),
                        safe_float(info.get("trailingEps"), max_val=9999.99),
                        safe_float(info.get("forwardEps"), max_val=9999.99),
                        safe_float(info.get("epsCurrentYear"), max_val=9999.99),
                        safe_float(info.get("priceEpsCurrentYear"), max_val=9999.99),
                        safe_float(info.get("earningsQuarterlyGrowth"), max_val=100, min_val=-100),
                        safe_int(info.get("earningsTimestamp")),
                        safe_int(info.get("earningsTimestampStart")),
                        safe_int(info.get("earningsTimestampEnd")),
                        safe_int(info.get("earningsCallTimeStampStart")),
                        safe_int(info.get("earningsCallTimeStampEnd")),
                        info.get("earningsDateIsEstimate"),
                        safe_int(info.get("totalCash")),
                        safe_float(info.get("totalCashPerShare"), max_val=9999.99),
                        safe_int(info.get("operatingCashflow")),
                        safe_int(info.get("freeCashflow")),
                        safe_int(info.get("totalDebt")),
                        safe_float(missing_metrics.get('debt_to_equity'), max_val=9999.99),
                        safe_float(info.get("quickRatio"), max_val=999.99),
                        safe_float(info.get("currentRatio"), max_val=999.99),
                        safe_float(info.get("profitMargins"), max_val=100, min_val=-100),
                        safe_float(info.get("grossMargins"), max_val=100, min_val=-100),
                        safe_float(info.get("ebitdaMargins"), max_val=100, min_val=-100),
                        safe_float(info.get("operatingMargins"), max_val=100, min_val=-100),
                        safe_float(info.get("returnOnAssets"), max_val=100, min_val=-100),
                        safe_float(info.get("returnOnEquity"), max_val=100, min_val=-100),
                        safe_float(info.get("revenueGrowth"), max_val=100, min_val=-100),
                        safe_float(missing_metrics.get('earnings_growth') or info.get("earningsGrowth"), max_val=100, min_val=-100),
                        safe_int(info.get("lastSplitDate")),
                        safe_float(info.get("dividendRate"), max_val=9999.99),
                        safe_float(info.get("dividendYield"), max_val=99.99, min_val=0),
                        safe_float(info.get("fiveYearAvgDividendYield"), max_val=99.99, min_val=0),
                        safe_int(info.get("exDividendDate")),
                        safe_float(info.get("trailingAnnualDividendRate"), max_val=9999.99),
                        safe_float(info.get("trailingAnnualDividendYield"), max_val=99.99, min_val=0),
                        safe_float(info.get("lastDividendValue"), max_val=9999.99),
                        safe_int(info.get("lastDividendDate")),
                        safe_int(info.get("dividendDate")),
                        safe_float(missing_metrics.get('payout_ratio') or info.get("payoutRatio"), max_val=100, min_val=0),
                        safe_float(info.get("heldPercentInsiders"), max_val=99.99, min_val=0),
                        safe_float(info.get("heldPercentInstitutions"), max_val=99.99, min_val=0),
                        safe_int(info.get("sharesShort")),
                        safe_int(info.get("sharesShortPriorMonth")),
                        safe_float(info.get("shortRatio"), max_val=9999.99),
                        safe_float(info.get("shortPercentOfFloat"), max_val=99.99, min_val=0),
                        safe_int(info.get("impliedSharesOutstanding") or info.get("sharesOutstanding")),
                        safe_int(info.get("floatShares")),
                    ),
                )

                stats['info'] = 1
                conn.commit()  # Commit company_profile immediately - critical data

            except Exception as e:
                error_msg = str(e)[:500]  # Get full error message
                logging.error(f"❌ CRITICAL: Failed to insert company info for {symbol}: {error_msg}")
                if "CRITICAL" not in error_msg:  # Log traceback if not already detailed
                    import traceback
                    logging.error(f"   Traceback: {traceback.format_exc()[:300]}")
                stats['info_failed'] = 1  # Track failure
                # Rollback failed transaction to reset state for next symbol
                try:
                    conn.rollback()
                except:
                    pass

        # CRITICAL: Always insert key_metrics - commit immediately to guarantee persistence
        # This is separate from company_profile to prevent rollback
        try:
            cur.execute(
                "INSERT INTO key_metrics (ticker) VALUES (%s) ON CONFLICT (ticker) DO NOTHING",
                (symbol,),
            )
            conn.commit()  # Commit immediately - DO NOT wait for final commit
            stats['key_metrics'] = 1
        except Exception as e:
            logging.error(f"❌ CRITICAL: Failed to insert key_metrics for {symbol}: {str(e)[:200]}")
            try:
                conn.rollback()
            except:
                pass

        # 2. Insert institutional holders
        if institutional_holders is not None and not institutional_holders.empty:
            try:
                inst_data = []
                for _, row in institutional_holders.iterrows():
                    # Get filing date - SKIP if not provided (no fake dates)
                    date_reported = row.get('Date Reported')
                    if date_reported is None or pd.isna(date_reported):
                        # SKIP records with missing filing dates - do not insert fake data
                        continue

                    year = date_reported.year
                    quarter_num = (date_reported.month - 1) // 3 + 1
                    quarter = f"{year}Q{quarter_num}"
                    filing_date = date_reported

                    inst_name = safe_str(row.get('Holder', ''), max_len=300)
                    # Skip if institution name is empty or None
                    if not inst_name:
                        continue

                    if any(x in inst_name.lower() for x in ['vanguard', 'fidelity', 'blackrock', 'state street']):
                        inst_type = 'MUTUAL_FUND'
                    elif any(x in inst_name.lower() for x in ['berkshire', 'hedge', 'capital', 'partners']):
                        inst_type = 'HEDGE_FUND'
                    elif any(x in inst_name.lower() for x in ['pension', 'retirement', 'insurance']):
                        inst_type = 'PENSION_FUND'
                    else:
                        inst_type = 'INSTITUTIONAL'

                    inst_data.append((
                        symbol, inst_type, inst_name,
                        safe_float(row.get('Value'), max_val=999999999999),
                        safe_float(row.get('pctChange'), max_val=100, min_val=-100) if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld'), max_val=100, min_val=0),
                        filing_date, quarter,
                    ))

                if inst_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO institutional_positioning (
                            symbol, institution_type, institution_name, position_size,
                            position_change_percent, market_share, filing_date, quarter
                        ) VALUES %s
                        ON CONFLICT (symbol, institution_name, filing_date) DO UPDATE SET
                            position_size = EXCLUDED.position_size,
                            position_change_percent = EXCLUDED.position_change_percent,
                            market_share = EXCLUDED.market_share,
                            institution_type = EXCLUDED.institution_type,
                            quarter = EXCLUDED.quarter
                        """,
                        inst_data
                    )
                    stats['institutional'] = len(inst_data)

            except Exception as e:
                logging.error(f"❌ CRITICAL: Failed to insert institutional holders for {symbol}: {str(e)[:200]}")
                stats['institutional_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 3. Insert mutual fund holders (NEW!)
        if mutualfund_holders is not None and not mutualfund_holders.empty:
            try:
                mf_data = []
                for _, row in mutualfund_holders.iterrows():
                    # Get filing date - SKIP if not provided (no fake dates)
                    date_reported = row.get('Date Reported')
                    if date_reported is None or pd.isna(date_reported):
                        # SKIP records with missing filing dates - do not insert fake data
                        continue

                    year = date_reported.year
                    quarter_num = (date_reported.month - 1) // 3 + 1
                    quarter = f"{year}Q{quarter_num}"
                    filing_date = date_reported

                    mf_name = safe_str(row.get('Holder', ''), max_len=300)
                    # Skip if fund name is empty or None
                    if not mf_name:
                        continue

                    mf_data.append((
                        symbol, 'MUTUAL_FUND',
                        mf_name,
                        safe_float(row.get('Value'), max_val=999999999999),
                        safe_float(row.get('pctChange'), max_val=100, min_val=-100) if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld'), max_val=100, min_val=0),
                        filing_date, quarter,
                    ))

                if mf_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO institutional_positioning (
                            symbol, institution_type, institution_name, position_size,
                            position_change_percent, market_share, filing_date, quarter
                        ) VALUES %s
                        ON CONFLICT (symbol, institution_name, filing_date) DO UPDATE SET
                            position_size = EXCLUDED.position_size,
                            position_change_percent = EXCLUDED.position_change_percent,
                            market_share = EXCLUDED.market_share,
                            institution_type = EXCLUDED.institution_type,
                            quarter = EXCLUDED.quarter
                        """,
                        mf_data
                    )
                    stats['mutualfund'] = len(mf_data)

            except Exception as e:
                logging.error(f"❌ CRITICAL: Failed to insert mutual fund holders for {symbol}: {str(e)[:200]}")
                stats['mutualfund_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 4. Insert insider transactions (NEW!)
        if insider_transactions is not None and not insider_transactions.empty:
            try:
                insider_txn_data = []
                for _, row in insider_transactions.iterrows():
                    insider_txn_data.append((
                        symbol,
                        safe_str(row.get('Insider'), max_len=200),
                        safe_str(row.get('Position'), max_len=200),
                        safe_str(row.get('Transaction'), max_len=50),
                        safe_int(row.get('Shares')),
                        safe_float(row.get('Value')),
                        safe_date(row.get('Start Date')),
                        safe_str(row.get('Ownership'), max_len=10),
                        safe_str(row.get('Text'), max_len=500),
                        safe_str(row.get('URL'), max_len=1000),
                    ))

                if insider_txn_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO insider_transactions (
                            symbol, insider_name, position, transaction_type,
                            shares, value, transaction_date, ownership_type,
                            transaction_text, url
                        ) VALUES %s
                        """,
                        insider_txn_data
                    )
                    stats['insider_txns'] = len(insider_txn_data)

            except Exception as e:
                logging.error(f"❌ CRITICAL: Failed to insert insider transactions for {symbol}: {str(e)[:200]}")
                stats['insider_txns_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 5. Insert insider roster (NEW!) - WITH RETRY for deadlock handling
        if insider_roster is not None and not insider_roster.empty:
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Create table if not exists
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS insider_roster (
                            id SERIAL PRIMARY KEY,
                            symbol VARCHAR(20),
                            insider_name VARCHAR(200),
                            position VARCHAR(200),
                            most_recent_transaction VARCHAR(50),
                            latest_transaction_date DATE,
                            shares_owned_directly BIGINT,
                            position_direct_date DATE,
                            url TEXT,
                            created_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE(symbol, insider_name)
                        );
                        CREATE INDEX IF NOT EXISTS idx_insider_roster_symbol ON insider_roster(symbol);
                    """)

                    roster_data = []
                    for _, row in insider_roster.iterrows():
                        roster_data.append((
                            symbol,
                            safe_str(row.get('Name'), max_len=200),
                            safe_str(row.get('Position'), max_len=200),
                            safe_str(row.get('Most Recent Transaction'), max_len=50),
                            safe_date(row.get('Latest Transaction Date')),
                            safe_int(row.get('Shares Owned Directly')),
                            safe_date(row.get('Position Direct Date')),
                            safe_str(row.get('URL'), max_len=1000),
                        ))

                    if roster_data:
                        execute_values(
                            cur,
                            """
                            INSERT INTO insider_roster (
                                symbol, insider_name, position, most_recent_transaction,
                                latest_transaction_date, shares_owned_directly,
                                position_direct_date, url
                            ) VALUES %s
                            ON CONFLICT (symbol, insider_name) DO UPDATE SET
                                position = EXCLUDED.position,
                                most_recent_transaction = EXCLUDED.most_recent_transaction,
                                latest_transaction_date = EXCLUDED.latest_transaction_date,
                                shares_owned_directly = EXCLUDED.shares_owned_directly
                            """,
                            roster_data
                        )
                        stats['insider_roster'] = len(roster_data)
                    break  # Success - exit retry loop

                except Exception as e:
                    error_str = str(e).lower()
                    is_deadlock = "deadlock" in error_str

                    if is_deadlock and retry_count < max_retries - 1:
                        # Deadlock detected - retry with backoff
                        retry_count += 1
                        wait_time = 0.1 * (2 ** (retry_count - 1))  # 0.1s, 0.2s, 0.4s
                        logging.warning(f"Deadlock on insider roster for {symbol}, retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                        try:
                            conn.rollback()
                        except:
                            pass
                        time.sleep(wait_time)
                    else:
                        # Not a deadlock or max retries exceeded - give up
                        logging.error(f"Error inserting insider roster for {symbol}: {e}")
                        try:
                            conn.rollback()
                        except:
                            pass
                        break

        # 6. Insert positioning metrics - ALWAYS INSERT (with real data or NULLs, NEVER defaults)
        # Log what data we have from yfinance for debugging coverage
        has_inst_own = info.get('heldPercentInstitutions') is not None if info else False
        has_insider_own = info.get('heldPercentInsiders') is not None if info else False
        has_short_ratio = info.get('shortRatio') is not None if info else False
        has_short_pct = info.get('shortPercentOfFloat') is not None if info else False

        data_sources = []
        if has_inst_own: data_sources.append('inst_own')
        if has_insider_own: data_sources.append('insider_own')
        if has_short_ratio: data_sources.append('short_ratio')
        if has_short_pct: data_sources.append('short_pct')

        # Log positioning data availability
        if data_sources:
            logging.info(f"Positioning data for {symbol}: {','.join(data_sources)}")
        else:
            logging.warning(f"Positioning data MISSING for {symbol}: yfinance returned no positioning fields")

        # REAL DATA ONLY - No fallbacks, no calculations
        # Use only direct yfinance values, return NULL if unavailable
        try:
            # Get institutional, insider, and short data ONLY from yfinance info dict
            # DO NOT calculate from holder DataFrames (causes > 100% values and double-counting)
            inst_own = safe_float(info.get('heldPercentInstitutions')) if info else None
            insider_own = safe_float(info.get('heldPercentInsiders')) if info else None
            short_pct = safe_float(info.get('shortPercentOfFloat')) if info else None
            short_ratio = safe_float(info.get('shortRatio')) if info else None

            # If data is missing from yfinance, store as NULL (not a calculated fallback)
            # institutional_holders and major_holders DataFrames are NOT used
            # because summing individual holders' percentages causes > 100% values

            ad_rating = calculate_ad_rating(inst_own, insider_own, short_pct, cur, symbol)

            # Use ON CONFLICT to ensure atomic updates - REAL DATA ONLY, NO DEFAULTS
            try:
                cur.execute(
                    """
                    INSERT INTO positioning_metrics (
                        symbol, date, institutional_ownership_pct,
                        institutional_holders_count, insider_ownership_pct,
                        short_ratio, short_interest_pct, short_percent_of_float, ad_rating
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        date = EXCLUDED.date,
                        institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                        institutional_holders_count = EXCLUDED.institutional_holders_count,
                        insider_ownership_pct = EXCLUDED.insider_ownership_pct,
                        short_ratio = EXCLUDED.short_ratio,
                        short_interest_pct = EXCLUDED.short_interest_pct,
                        short_percent_of_float = EXCLUDED.short_percent_of_float,
                        ad_rating = EXCLUDED.ad_rating,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        symbol,
                        datetime.now().date(),
                        inst_own,
                        safe_int(info.get('institutionsCount')) if info else None,
                        insider_own,
                        short_ratio,
                        short_pct,
                        short_pct,
                        ad_rating,
                    )
                )
                stats['positioning'] = 1
                logging.debug(f"{symbol}: Positioning metrics inserted - inst_own={inst_own}, insider_own={insider_own}, short_pct={short_pct}")
            except Exception as e2:
                logging.error(f"❌ CRITICAL: Failed to insert positioning metrics for {symbol}: {str(e2)[:200]}")
                stats['positioning_failed'] = 1
                # DO NOT rollback here - it would undo company_profile and other inserts
                # Only skip this symbol's positioning, but keep other data

        except Exception as e:
            logging.error(f"❌ CRITICAL: Failed to calculate positioning metrics for {symbol}: {str(e)[:200]}")
            stats['positioning_failed'] = 1
            # DO NOT rollback here - it would undo company_profile and other inserts
            # Only skip this symbol's positioning, but keep other data

        # 7. Insert earnings estimates
        if earnings_estimate is not None and not earnings_estimate.empty:
            try:
                earnings_data = []
                for period, row in earnings_estimate.iterrows():
                    earnings_data.append((
                        symbol, str(period),
                        safe_float(row.get("avg"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("low"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("high"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("yearAgoEps"), max_val=1000000, min_val=-1000000),
                        safe_int(row.get("numberOfAnalysts"), max_val=10000, min_val=0),
                        safe_float(row.get("growth"), max_val=10000, min_val=-10000),
                    ))

                if earnings_data:
                    # Delete existing earnings estimates for this symbol to avoid conflicts
                    cur.execute("DELETE FROM earnings_estimates WHERE symbol = %s", (symbol,))
                    execute_values(
                        cur,
                        """
                        INSERT INTO earnings_estimates (
                            symbol, period, avg_estimate, low_estimate,
                            high_estimate, year_ago_eps, number_of_analysts,
                            growth
                        ) VALUES %s
                        """,
                        earnings_data
                    )
                    stats['earnings_est'] = len(earnings_data)

            except Exception as e:
                logging.error(f"❌ CRITICAL: Failed to insert earnings estimates for {symbol}: {str(e)[:200]}")
                stats['earnings_est_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 8. Insert revenue estimates
        if revenue_estimate is not None and not revenue_estimate.empty:
            try:
                revenue_data = []
                for period, row in revenue_estimate.iterrows():
                    revenue_data.append((
                        symbol, str(period),
                        safe_float(row.get("avg"), max_val=1e15, min_val=0),
                        safe_float(row.get("low"), max_val=1e15, min_val=0),
                        safe_float(row.get("high"), max_val=1e15, min_val=0),
                        safe_int(row.get("numberOfAnalysts"), max_val=10000, min_val=0),
                        safe_float(row.get("yearAgoRevenue"), max_val=1e15, min_val=0),
                        safe_float(row.get("growth"), max_val=10000, min_val=-10000),
                    ))

                if revenue_data:
                    # Delete existing revenue estimates for this symbol to avoid conflicts
                    cur.execute("DELETE FROM revenue_estimates WHERE symbol = %s", (symbol,))
                    execute_values(
                        cur,
                        """
                        INSERT INTO revenue_estimates (
                            symbol, period, avg_estimate, low_estimate,
                            high_estimate, number_of_analysts, year_ago_revenue,
                            growth
                        ) VALUES %s
                        """,
                        revenue_data
                    )
                    stats['revenue_est'] = len(revenue_data)

            except Exception as e:
                logging.error(f"❌ CRITICAL: Failed to insert revenue estimates for {symbol}: {str(e)[:200]}")
                stats['revenue_est_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 8.5. Insert earnings history (actual reported earnings - consolidated from loadearningshistory.py)
        try:
            earnings_history = ticker.earnings_history
            if earnings_history is not None and not earnings_history.empty:
                history_data = []
                for quarter, row in earnings_history.iterrows():
                    quarter_date = str(quarter)
                    history_data.append((
                        symbol, quarter_date,
                        safe_float(row.get('epsActual'), max_val=100000, min_val=-100000),
                        safe_float(row.get('epsEstimate'), max_val=100000, min_val=-100000),
                        safe_float(row.get('epsDifference'), max_val=100000, min_val=-100000),
                        safe_float(row.get('surprisePercent'), max_val=10000, min_val=-10000)
                    ))

                if history_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO earnings_history (
                            symbol, quarter, eps_actual, eps_estimate,
                            eps_difference, surprise_percent
                        ) VALUES %s
                        ON CONFLICT (symbol, quarter) DO UPDATE SET
                            eps_actual = EXCLUDED.eps_actual,
                            eps_estimate = EXCLUDED.eps_estimate,
                            eps_difference = EXCLUDED.eps_difference,
                            surprise_percent = EXCLUDED.surprise_percent,
                            fetched_at = CURRENT_TIMESTAMP
                        """,
                        history_data
                    )
                    stats['earnings_history'] = len(history_data)
                    logging.info(f"  ✓ Earnings history: {len(history_data)} quarters inserted for {symbol}")
        except Exception as e:
            logging.debug(f"No earnings history available for {symbol}: {e}")
            stats['earnings_history'] = 0

        # 8. Insert beta into beta_yfinance table (for loadfactormetrics consumption)
        if info and info.get('beta') is not None:
            try:
                beta_value = safe_float(info.get('beta'), max_val=100, min_val=-10)
                if beta_value is not None:
                    cur.execute("""
                        INSERT INTO beta_yfinance (symbol, beta, source, last_updated)
                        VALUES (%s, %s, 'yfinance_ticker_info', CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            beta = EXCLUDED.beta,
                            source = EXCLUDED.source,
                            last_updated = EXCLUDED.last_updated
                    """, (symbol, beta_value))
                    stats['beta'] = 1
                    logging.debug(f"{symbol}: Inserted beta = {beta_value}")
            except Exception as e:
                logging.debug(f"Could not insert beta for {symbol}: {e}")
                stats['beta'] = 0
                # Rollback failed transaction
                try:
                    conn.rollback()
                except:
                    pass

        # 9. Do NOT calculate liquidity metrics here - only in loadfactormetrics.py
        # This loader only loads raw yfinance data (beta, volatility, drawdown from price history)
        # All derived input calculations happen in loadfactormetrics.py
        # Note: stability_metrics table is populated entirely by loadfactormetrics.py

        try:
            conn.commit()
            logging.info(f"✓ COMMITTED {symbol}")
        except Exception as commit_err:
            logging.error(f"❌ COMMIT FAILED {symbol}: {str(commit_err)[:200]}")
            try:
                conn.rollback()
            except:
                pass
        return stats

    except Exception as e:
        logging.error(f"❌ CRITICAL: Complete failure loading realtime data for {symbol}: {str(e)[:200]}")
        return None


if __name__ == "__main__":
    log_mem("startup")

    cfg = get_db_config()

    # Build connection parameters, handling both socket and TCP connections
    connect_params = {
        "dbname": cfg["dbname"],
        "user": cfg["user"],
    }

    # Only add host/port if not using socket connection
    if cfg.get("host"):
        connect_params["host"] = cfg["host"]
        connect_params["port"] = cfg.get("port", 5432)

    # Only add password if provided
    if cfg.get("password"):
        connect_params["password"] = cfg["password"]

    conn = psycopg2.connect(**connect_params)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Schema migrations - create missing tables first
    logging.info("Running schema migrations...")
    try:
        # Create institutional_positioning table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS institutional_positioning (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20),
                institution_type VARCHAR(20),
                institution_name VARCHAR(200),
                position_size NUMERIC,
                position_change_percent DECIMAL(8,2),
                market_share DECIMAL(8,6),
                filing_date DATE,
                quarter VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, institution_name, filing_date)
            );
            CREATE INDEX IF NOT EXISTS idx_inst_pos_symbol ON institutional_positioning(symbol);
            CREATE INDEX IF NOT EXISTS idx_inst_pos_date ON institutional_positioning(filing_date DESC);
        """)

        # Create positioning_metrics table if not exists
        # Note: shares_short fields belong in key_metrics, not here
        cur.execute("""
            CREATE TABLE IF NOT EXISTS positioning_metrics (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20),
                date DATE,
                institutional_ownership_pct DECIMAL(8,6),
                institutional_holders_count INTEGER,
                insider_ownership_pct DECIMAL(8,6),
                short_ratio DECIMAL(8,2),
                short_interest_pct DECIMAL(8,6),
                short_percent_of_float DECIMAL(8,6),
                ad_rating DECIMAL(5,2),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_pos_metrics_symbol ON positioning_metrics(symbol);
            CREATE INDEX IF NOT EXISTS idx_pos_metrics_date ON positioning_metrics(date DESC);
        """)

        # Add missing columns to existing tables
        cur.execute("""
            ALTER TABLE key_metrics
            ADD COLUMN IF NOT EXISTS held_percent_insiders DECIMAL(8,6),
            ADD COLUMN IF NOT EXISTS held_percent_institutions DECIMAL(8,6),
            ADD COLUMN IF NOT EXISTS shares_short BIGINT,
            ADD COLUMN IF NOT EXISTS shares_short_prior_month BIGINT,
            ADD COLUMN IF NOT EXISTS short_ratio DECIMAL(8,2),
            ADD COLUMN IF NOT EXISTS short_percent_of_float DECIMAL(8,6),
            ADD COLUMN IF NOT EXISTS implied_shares_outstanding BIGINT,
            ADD COLUMN IF NOT EXISTS float_shares BIGINT;
        """)

        # Ensure positioning_metrics has all required columns (in case table was created without them)
        cur.execute("""
            ALTER TABLE positioning_metrics
            ADD COLUMN IF NOT EXISTS date DATE,
            ADD COLUMN IF NOT EXISTS short_percent_of_float DECIMAL(8,6),
            ADD COLUMN IF NOT EXISTS ad_rating DECIMAL(5,2);
        """)

        # Create insider_transactions with correct schema (CREATE IF NOT EXISTS - avoids DROP hang)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS insider_transactions (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20),
                insider_name VARCHAR(200),
                position VARCHAR(200),
                transaction_type VARCHAR(50),
                shares BIGINT,
                value NUMERIC,
                transaction_date DATE,
                ownership_type VARCHAR(10),
                transaction_text TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_insider_txns_symbol ON insider_transactions(symbol);
            CREATE INDEX IF NOT EXISTS idx_insider_txns_date ON insider_transactions(transaction_date DESC);
        """)

        conn.commit()
        logging.info("✅ Schema migrations complete")
    except Exception as e:
        logging.error(f"❌ CRITICAL: Schema migration failed - this blocks ALL data loading: {str(e)[:200]}")
        # Don't rollback to allow partial schema fixes, but this is critical

    # Get symbols - load all non-ETF symbols (LIMIT removed to load all 5,476 stocks)
    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') ORDER BY symbol;")
    symbols = [r["symbol"] for r in cur.fetchall()]

    logging.info(f"Loading real-time data for {len(symbols)} symbols")

    total_stats = {
        'info': 0, 'institutional': 0, 'mutualfund': 0,
        'insider_txns': 0, 'insider_roster': 0, 'positioning': 0,
        'earnings_est': 0, 'revenue_est': 0
    }

    processed = 0
    failed = []

    # Track symbols with persistent API errors
    api_error_symbols = {}

    for symbol in symbols:
        try:
            stats = load_all_realtime_data(symbol, cur, conn)
            if stats:
                for key in total_stats:
                    total_stats[key] += stats.get(key, 0)
                processed += 1
                logging.info(f"✅ {symbol}: {stats}")
            else:
                failed.append(symbol)

        except Exception as e:
            error_str = str(e).lower()
            # Track HTTP 500 errors for this symbol
            if '500' in error_str or 'http error' in error_str:
                api_error_symbols[symbol] = api_error_symbols.get(symbol, 0) + 1
                if api_error_symbols[symbol] <= 1:  # Only log first occurrence per symbol
                    logging.warning(f"⚠️  {symbol}: yfinance API error (will skip if persistent): {str(e)[:100]}")
            else:
                logging.error(f"❌ CRITICAL: Complete failure for {symbol}: {str(e)[:200]}")
            failed.append(symbol)
            # Don't rollback - aborts entire transaction, but error is logged

        finally:
            time.sleep(1.5)  # Rate limiting - INCREASED to avoid yfinance rate limiting

    logging.info("=" * 80)
    logging.info("REAL-TIME DATA LOADING COMPLETE")
    logging.info("=" * 80)
    logging.info(f"Processed: {processed}/{len(symbols)}")
    logging.info(f"Failed: {len(failed)}")

    # Summary stats collected from individual stock loads
    logging.info(f"📊 Component Summary:")
    logging.info(f"   - Company Info: {total_stats.get('info', 0)} stocks")
    logging.info(f"   - Positioning Metrics: {total_stats.get('positioning', 0)} stocks")
    logging.info(f"   - Insider Roster: {total_stats.get('insider_roster', 0)} records")
    logging.info(f"   - Earnings Estimates: {total_stats.get('earnings_est', 0)} records")
    logging.info(f"   - Revenue Estimates: {total_stats.get('revenue_est', 0)} records")

    if failed:
        logging.warning(f"⚠️  FAILED SYMBOLS (no data loaded): {','.join(failed[:20])}{f' +{len(failed)-20} more' if len(failed) > 20 else ''}")

    cur.execute(
        """
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """,
        (SCRIPT_NAME,),
    )
    conn.commit()

    cur.close()
    conn.close()
    logging.info(f"Peak memory: {get_rss_mb():.1f} MB")
