#!/usr/bin/env python3
"""
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
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
import sys
import time
import signal
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Dict, List, Optional
from functools import wraps
from pathlib import Path
import uuid

from dotenv import load_dotenv
import boto3
import pandas as pd
import psycopg2
import psycopg2.extensions
import numpy as np
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Load environment variables from .env.local if it exists
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Script metadata
SCRIPT_NAME = "loaddailycompanydata.py"
TICKER_INFO_TIMEOUT = 15  # seconds - yfinance ticker.info can hang indefinitely

logging.basicConfig(
    level=logging.INFO,  # Keep at INFO to avoid yfinance debug spam
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Timeout handler for hanging yfinance calls (cross-platform using threading)
class TimeoutException(Exception):
    pass

def get_ticker_with_timeout(symbol_str):
    """Get ticker object and info with timeout to prevent hanging on yfinance API.

    Uses threading-based timeout instead of signal.SIGALRM (which doesn't exist on Windows).
    """
    try:
        yf_symbol = symbol_str.replace('.', '-').replace('$', '-').upper()

        # Threading-based timeout that works on all platforms
        result = {'ticker': None}

        def fetch_ticker():
            try:
                result['ticker'] = yf.Ticker(yf_symbol)
                _ = result['ticker'].info  # Validate ticker works
            except Exception as e:
                logging.debug(f"Failed to fetch ticker for {symbol_str}: {e}")

        thread = threading.Thread(target=fetch_ticker, daemon=True)
        thread.start()
        thread.join(timeout=TICKER_INFO_TIMEOUT)

        if thread.is_alive():
            logging.warning(f"Timeout fetching ticker info for {symbol_str} after {TICKER_INFO_TIMEOUT}s")
            return None

        return result['ticker']

    except Exception as e:
        logging.error(f"Error getting ticker for {symbol_str}: {e}")
        return None

# Retry decorator for yfinance API calls (handle 500 errors, timeouts, etc.)
def retry_with_backoff(max_retries=10, base_delay=0.5):
    """Retry decorator with exponential backoff for API calls - RESILIENT to HTTP 500 errors.

    Enhanced to handle yfinance HTTP 500 errors more effectively:
    - Increased max_retries from 4 to 10
    - Longer exponential backoff (0.5s, 1s, 2s, 4s, 8s, 16s, 32s, 64s, 120s, 120s)
    - Retries ALL transient errors (HTTP 500, 503, timeouts, connection errors)
    - Rate limit errors trigger main loop backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_str = str(e).lower()
                    # Retry on transient errors: HTTP 500, 503, timeouts, connection errors
                    is_transient = any(x in error_str for x in ['500', '503', 'timeout', 'connection', 'temporarily unavailable', 'remote end closed', 'http error'])
                    # Rate limit errors should trigger main loop backoff
                    is_rate_limit = any(x in error_str for x in ['rate limit', '429'])

                    if is_rate_limit:
                        # Log rate limit and fail - main loop will space requests
                        logging.warning(f" RATE LIMITED on {func.__name__} (attempt {attempt + 1}/{max_retries}). Main loop will add spacing.")
                        raise  # Fail immediately so main loop can add delay before retry
                    elif is_transient:
                        # RESILIENT: Exponential backoff with longer delays (0.5, 1, 2, 4, 8, 16, 32, 64, 120, 120)
                        delay = base_delay * (2 ** attempt)
                        delay = min(delay, 120)  # Cap at 2 minutes for extreme cases

                        if attempt < max_retries - 1:
                            # Retry transient errors with exponential backoff
                            logging.warning(f" Transient error in {func.__name__} (attempt {attempt + 1}/{max_retries}), retrying in {delay:.1f}s: {str(e)[:80]}")
                            time.sleep(delay)
                        else:
                            logging.error(f" All {max_retries} retry attempts exhausted for {func.__name__}: {e}")
                            raise
                    else:
                        # Unknown error - log and fail
                        logging.error(f"Non-retriable error in {func.__name__}: {e}")
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
    """Get RSS memory in MB, cross-platform."""
    if not HAS_RESOURCE:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
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

    # Safety check: if info is None, return empty metrics
    if not info or not isinstance(info, dict):
        return {
            'earnings_growth': None,
            'payout_ratio': None,
            'debt_to_equity': None,
            'de_source': None,
        }

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

    def fetch_with_timeout(func, timeout_sec=30):
        """Execute a function with timeout using threading (cross-platform, no signal.SIGALRM)."""
        result = {'value': None, 'error': None}

        def wrapper():
            try:
                result['value'] = func()
            except Exception as e:
                result['error'] = e

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            raise TimeoutException(f"Operation timed out after {timeout_sec}s")

        if result['error']:
            raise result['error']

        return result['value']

    @retry_with_backoff(max_retries=5, base_delay=2)  # Retry 5 times (tolerance for Windows yfinance issues)
    def fetch_yfinance_data(yf_symbol):
        """Fetch yfinance data with delays between property accesses and timeout protection.

        CRITICAL FIX: Each yfinance property access (ticker.info, ticker.institutional_holders, etc.)
        makes a SEPARATE HTTP request. Accessing all properties in rapid succession causes
        yfinance to see them as a burst and returns 429 Rate Limited.

        Solution: Add 1.0s delay between each property access to spread requests over ~8 seconds.
        This prevents the burst detection while still completing in reasonable time.

        WINDOWS FIX: Wrap operations in thread with timeout instead of using signal.SIGALRM
        which doesn't exist on Windows.
        """
        try:
            # Create ticker with timeout protection
            def create_ticker():
                return yf.Ticker(yf_symbol)

            ticker = fetch_with_timeout(create_ticker, timeout_sec=15)
            result = {'ticker': ticker}

            # Fetch properties with 1.0s delays and timeout protection
            try:
                result['info'] = fetch_with_timeout(lambda: ticker.info, timeout_sec=15)
            except (TimeoutException, Exception):
                result['info'] = None
            time.sleep(1.0)

            try:
                result['institutional_holders'] = fetch_with_timeout(
                    lambda: ticker.institutional_holders, timeout_sec=10
                )
            except (TimeoutException, Exception):
                result['institutional_holders'] = None
            time.sleep(1.0)

            try:
                result['mutualfund_holders'] = fetch_with_timeout(
                    lambda: ticker.mutualfund_holders, timeout_sec=10
                )
            except (TimeoutException, Exception):
                result['mutualfund_holders'] = None
            time.sleep(1.0)

            try:
                result['insider_transactions'] = fetch_with_timeout(
                    lambda: ticker.insider_transactions, timeout_sec=10
                )
            except (TimeoutException, Exception):
                result['insider_transactions'] = None
            time.sleep(1.0)

            try:
                result['insider_roster'] = fetch_with_timeout(
                    lambda: ticker.insider_roster_holders, timeout_sec=10
                )
            except (TimeoutException, Exception):
                result['insider_roster'] = None
            time.sleep(1.0)

            try:
                result['earnings_estimate'] = fetch_with_timeout(
                    lambda: ticker.earnings_estimate, timeout_sec=10
                )
            except (TimeoutException, Exception):
                result['earnings_estimate'] = None
            time.sleep(1.0)

            return result
        except Exception as e:
            logging.debug(f"Error fetching yfinance data for {yf_symbol}: {e}")
            return {'ticker': None, 'info': None}

    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)
        yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()

        # SINGLE API CALL gets everything (with retry on 500 errors)
        # Retry up to 3 times to recover from transient yfinance API failures
        for attempt in range(3):
            try:
                data = fetch_yfinance_data(yf_symbol)
                break
            except Exception as e:
                if attempt < 2:
                    delay = 3 + (2 ** attempt)  # 4s, 5s, 6s delays
                    logging.debug(f"Fetch failed for {symbol}, retry {attempt + 1}/3 in {delay}s...")
                    time.sleep(delay)
                else:
                    logging.warning(f"All fetch attempts failed for {symbol}: {e}")
                    data = None
                    break

        if data is None:
            logging.warning(f"Could not fetch any data for {symbol} after 3 retries - skipping")
            return {}

        ticker = data['ticker']  # Reuse the ticker object - avoid duplicate HTTP 500 errors
        info = data['info']
        institutional_holders = data['institutional_holders']
        mutualfund_holders = data['mutualfund_holders']
        insider_transactions = data['insider_transactions']
        earnings_estimate = data['earnings_estimate']

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
                        safe_float(info.get("customPriceAlertConfidence")), info.get("address1"),
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

                # Key metrics (only columns that exist in schema)
                cur.execute(
                    """
                    INSERT INTO key_metrics (
                        ticker, trailing_pe, forward_pe, price_to_sales_ttm,
                        price_to_book, peg_ratio,
                        dividend_yield, beta, earnings_growth,
                        held_percent_insiders, held_percent_institutions,
                        shares_short, shares_short_prior_month,
                        short_ratio, short_percent_of_float,
                        implied_shares_outstanding, float_shares
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        trailing_pe = EXCLUDED.trailing_pe,
                        forward_pe = EXCLUDED.forward_pe,
                        price_to_sales_ttm = EXCLUDED.price_to_sales_ttm,
                        price_to_book = EXCLUDED.price_to_book,
                        peg_ratio = EXCLUDED.peg_ratio,
                        dividend_yield = EXCLUDED.dividend_yield,
                        beta = EXCLUDED.beta,
                        earnings_growth = EXCLUDED.earnings_growth,
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
                        safe_float(info.get("trailingPE"), max_val=150),
                        safe_float(info.get("forwardPE"), max_val=150),
                        safe_float(info.get("priceToSalesTrailing12Months"), max_val=10000, min_val=0),
                        safe_float(info.get("priceToBook"), max_val=10000, min_val=0),
                        safe_float(info.get("trailingPegRatio"), max_val=1000, min_val=0),
                        safe_float(info.get("dividendYield"), max_val=20, min_val=0),
                        safe_float(info.get("beta"), max_val=9999.99),
                        safe_float(missing_metrics.get('earnings_growth') or info.get("earningsGrowth"), max_val=100, min_val=-100),
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
                logging.error(f" CRITICAL: Failed to insert company info for {symbol}: {error_msg}")
                if "CRITICAL" not in error_msg:  # Log traceback if not already detailed
                    import traceback
                    logging.error(f"   Traceback: {traceback.format_exc()[:300]}")
                stats['info_failed'] = 1  # Track failure
                # Rollback failed transaction to reset state for next symbol
                try:
                    conn.rollback()
        except Exception:
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
            logging.error(f" CRITICAL: Failed to insert key_metrics for {symbol}: {str(e)}")
            try:
                conn.rollback()
        except Exception:
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
                logging.error(f" CRITICAL: Failed to insert institutional holders for {symbol}: {str(e)}")
                stats['institutional_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
        except Exception:
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
                logging.error(f" CRITICAL: Failed to insert mutual fund holders for {symbol}: {str(e)}")
                stats['mutualfund_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
        except Exception:
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
                logging.error(f" CRITICAL: Failed to insert insider transactions for {symbol}: {str(e)}")
                stats['insider_txns_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
        except Exception:
                    pass

        # 5. Insert insider roster (NEW!) - WITH RETRY for deadlock handling
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

            ad_rating = None  # A/D Rating calculated separately in batch mode

            # Use ON CONFLICT to ensure atomic updates - REAL DATA ONLY, NO DEFAULTS
            try:
                values = (
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
                logging.debug(f"Positioning INSERT values for {symbol}: {values}")
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
                    values
                )
                stats['positioning'] = 1
                logging.info(f" Positioning INSERT succeeded for {symbol}: inst_own={inst_own}, insider_own={insider_own}, short_pct={short_pct}")
            except Exception as e2:
                logging.error(f" CRITICAL: Failed to insert positioning metrics for {symbol}: {str(e2)[:200]}")
                stats['positioning_failed'] = 1
                # DO NOT rollback here - it would undo company_profile and other inserts
                # Only skip this symbol's positioning, but keep other data

        except Exception as e:
            logging.error(f" CRITICAL: Failed to calculate positioning metrics for {symbol}: {str(e)}")
            stats['positioning_failed'] = 1
            # DO NOT rollback here - it would undo company_profile and other inserts
            # Only skip this symbol's positioning, but keep other data

        # 7. Insert earnings estimates
        if earnings_estimate is not None and not earnings_estimate.empty:
            try:
                earnings_data = []
                for period, row in earnings_estimate.iterrows():
                    fiscal_year = str(period) if period else None
                    if not fiscal_year:
                        continue
                    earnings_data.append((
                        symbol, fiscal_year,
                        safe_float(row.get("avg"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("low"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("high"), max_val=1000000, min_val=-1000000),
                        safe_float(row.get("yearAgoEps"), max_val=1000000, min_val=-1000000),
                        safe_int(row.get("numberOfAnalysts"), max_val=10000, min_val=0),
                        safe_float(row.get("growth"), max_val=10000, min_val=-10000),
                        str(period),
                    ))

                if earnings_data:
                    # Delete existing earnings estimates for this symbol to avoid conflicts
                    cur.execute("DELETE FROM earnings_estimates WHERE symbol = %s", (symbol,))
                    execute_values(
                        cur,
                        """
                        INSERT INTO earnings_estimates (
                            symbol, quarter, avg_estimate, low_estimate,
                            high_estimate, year_ago_eps, estimate_count,
                            growth, period
                        ) VALUES %s
                        ON CONFLICT (symbol, quarter) DO UPDATE SET
                            avg_estimate = COALESCE(EXCLUDED.avg_estimate, earnings_estimates.avg_estimate),
                            low_estimate = COALESCE(EXCLUDED.low_estimate, earnings_estimates.low_estimate),
                            high_estimate = COALESCE(EXCLUDED.high_estimate, earnings_estimates.high_estimate)
                        """,
                        earnings_data
                    )
                    stats['earnings_est'] = len(earnings_data)

            except Exception as e:
                logging.error(f" CRITICAL: Failed to insert earnings estimates for {symbol}: {str(e)}")
                stats['earnings_est_failed'] = 1
                # Rollback failed transaction
                try:
                    conn.rollback()
        except Exception:
                    pass

        # 8.5. Insert earnings history (actual reported earnings - consolidated from loadearningshistory.py)
        try:
            # Retry earnings history fetch with exponential backoff (it often fails with 500 errors)
            earnings_history = None
            for attempt in range(3):
                try:
                    earnings_history = ticker.earnings_history
                    if earnings_history is not None and not earnings_history.empty:
                        break
                except Exception as eh:
                    if attempt < 2:
                        delay = 2 ** attempt  # 1s, 2s backoff
                        logging.debug(f"Earnings history fetch failed for {symbol}, retry in {delay}s...")
                        time.sleep(delay)
                    else:
                        raise

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
                    logging.info(f"  [OK] Earnings history: {len(history_data)} quarters inserted for {symbol}")
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
        except Exception:
                    pass

        # 9. Do NOT calculate liquidity metrics here - only in loadfactormetrics.py
        # This loader only loads raw yfinance data (beta, volatility, drawdown from price history)
        # All derived input calculations happen in loadfactormetrics.py
        # Note: stability_metrics table is populated entirely by loadfactormetrics.py

        try:
            conn.commit()
            logging.info(f"[OK] COMMITTED {symbol}")
        except Exception as commit_err:
            logging.error(f" COMMIT FAILED {symbol}: {str(commit_err)[:200]}")
            try:
                conn.rollback()
        except Exception:
                pass
        return stats

    except Exception as e:
        logging.error(f" CRITICAL: Complete failure loading realtime data for {symbol}: {str(e)}")
        return None


if __name__ == "__main__":
    log_mem("startup")

    # Parse CLI arguments for parallel execution
    parser = argparse.ArgumentParser(description='Load daily company data for stock symbols')
    parser.add_argument('--offset', type=int, default=0, help='Symbol offset for parallel execution')
    parser.add_argument('--limit', type=int, default=None, help='Symbol limit for parallel execution')
    parser.add_argument('--run-id', type=str, default=str(uuid.uuid4()), help='Run ID for tracking progress')
    args = parser.parse_args()

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

    conn = psycopg2.connect(**connect_params, connect_timeout=30)
    conn.autocommit = True  # Use autocommit to avoid long-running transactions
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Schema migrations - create missing tables first
    logging.info("Running schema migrations...")
    try:
        # Check if loader_run_progress table exists first (avoid timeout on expensive operations)
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'loader_run_progress'
            ) as exists
        """)
        table_exists = cur.fetchone()['exists']

        if not table_exists:
            logging.info("Creating missing tables...")
            # Create loader progress table for tracking (split into multiple statements)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS loader_run_progress (
                    run_id UUID,
                    loader_name VARCHAR(100),
                    symbol VARCHAR(20),
                    started_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP,
                    status VARCHAR(20),
                    error_msg TEXT,
                    elapsed_ms INTEGER,
                    PRIMARY KEY (run_id, loader_name, symbol)
                )
            """)
    
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_loader_run_progress_run
                ON loader_run_progress(run_id)
            """)
    
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_loader_run_progress_symbol
                ON loader_run_progress(symbol)
            """)
            conn.commit()
        else:
            logging.info("Schema tables already exist, skipping migrations")

        # Create institutional_positioning table if not exists (split statements to avoid timeout)
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
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_inst_pos_symbol ON institutional_positioning(symbol)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_inst_pos_date ON institutional_positioning(filing_date DESC)")

        # Create positioning_metrics table if not exists
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
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_metrics_symbol ON positioning_metrics(symbol)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_pos_metrics_date ON positioning_metrics(date DESC)")

        # Add missing columns to existing tables (separate statements)
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS held_percent_insiders DECIMAL(8,6)")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS held_percent_institutions DECIMAL(8,6)")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS shares_short BIGINT")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS shares_short_prior_month BIGINT")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS short_ratio DECIMAL(8,2)")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS short_percent_of_float DECIMAL(8,6)")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS implied_shares_outstanding BIGINT")
        cur.execute("ALTER TABLE key_metrics ADD COLUMN IF NOT EXISTS float_shares BIGINT")

        # Ensure positioning_metrics has all required columns
        cur.execute("ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS date DATE")
        cur.execute("ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS short_percent_of_float DECIMAL(8,6)")
        cur.execute("ALTER TABLE positioning_metrics ADD COLUMN IF NOT EXISTS ad_rating DECIMAL(5,2)")

        # Create insider_transactions table
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
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_insider_txns_symbol ON insider_transactions(symbol)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_insider_txns_date ON insider_transactions(transaction_date DESC)")

        logging.info(" Schema migrations complete")
    except Exception as e:
        logging.error(f" CRITICAL: Schema migration failed - this blocks ALL data loading: {str(e)}")
        # Don't rollback to allow partial schema fixes, but this is critical

    # Get symbols - load all non-ETF symbols with optional OFFSET/LIMIT for parallel execution
    limit_clause = ""
    if args.limit:
        limit_clause = f" LIMIT {args.limit} OFFSET {args.offset}"
    elif args.offset > 0:
        logging.warning(f"Offset {args.offset} specified but no limit; loading all remaining symbols")
        limit_clause = f" OFFSET {args.offset}"

    cur.execute(f"SELECT symbol FROM stock_symbols WHERE is_sp500 = true AND (etf IS NULL OR etf != 'Y') ORDER BY symbol{limit_clause};")
    symbols = [r["symbol"] for r in cur.fetchall()]

    run_id = args.run_id
    logging.info(f"[Run {run_id}] Loading real-time data for {len(symbols)} symbols (offset={args.offset}, limit={args.limit})")

    total_stats = {
        'info': 0, 'institutional': 0, 'mutualfund': 0,
        'insider_txns': 0, 'insider_roster': 0, 'positioning': 0,
        'earnings_est': 0, 'revenue_est': 0
    }

    processed = 0
    failed = []

    # Track symbols with persistent API errors
    api_error_symbols = {}

    # Track execution time
    start_time = time.time()
    rate_limit_consecutive = 0

    # Global rate limiter for yfinance (max 20 concurrent HTTP requests)
    rate_limiter = threading.Semaphore(20)

    def process_symbol_worker(symbol: str, attempt_num: int, connect_params: Dict) -> tuple:
        """Process a single symbol in a thread. Returns (symbol, stats, success, error_msg)"""
        symbol_start = time.time()
        stats = None
        error_msg = None

        try:
            # Get thread-local database connection
            thread_conn = psycopg2.connect(**connect_params)
            thread_conn.autocommit = False
            thread_cur = thread_conn.cursor(cursor_factory=RealDictCursor)

            # Acquire rate limiter
            rate_limiter.acquire()
            try:
                stats = load_all_realtime_data(symbol, thread_cur, thread_conn)
            finally:
                rate_limiter.release()

            elapsed_ms = int((time.time() - symbol_start) * 1000)

            if stats:
                # Track success
                try:
                    thread_cur.execute("""
                        INSERT INTO loader_run_progress (run_id, loader_name, symbol, completed_at, status, elapsed_ms)
                        VALUES (%s, %s, %s, NOW(), %s, %s)
                        ON CONFLICT (run_id, loader_name, symbol) DO UPDATE SET
                            completed_at = NOW(), status = 'success', elapsed_ms = %s
                    """, (run_id, 'loaddailycompanydata', symbol, 'success', elapsed_ms, elapsed_ms))
                    thread_conn.commit()
                except Exception as track_err:
                    logging.debug(f"Could not track progress for {symbol}: {track_err}")

                return (symbol, stats, True, None)
            else:
                error_msg = "No stats returned"
                # Track failure
                try:
                    thread_cur.execute("""
                        INSERT INTO loader_run_progress (run_id, loader_name, symbol, completed_at, status, error_msg)
                        VALUES (%s, %s, %s, NOW(), %s, %s)
                        ON CONFLICT (run_id, loader_name, symbol) DO UPDATE SET
                            completed_at = NOW(), status = 'failed', error_msg = %s
                    """, (run_id, 'loaddailycompanydata', symbol, 'failed', error_msg, error_msg))
                    thread_conn.commit()
                except Exception as track_err:
                    logging.debug(f"Could not track failure for {symbol}: {track_err}")

                return (symbol, None, False, error_msg)

        except Exception as e:
            elapsed_ms = int((time.time() - symbol_start) * 1000)
            error_msg = str(e)
            error_str = error_msg.lower()

            if '500' in error_str or 'http error' in error_str:
                api_error_symbols[symbol] = api_error_symbols.get(symbol, 0) + 1
                logging.warning(f"  {symbol}: yfinance API error (attempt {api_error_symbols[symbol]}): {str(e)[:100]}")
            else:
                logging.error(f" CRITICAL: {symbol}: {error_msg}")

            # Track failure
            try:
                thread_conn = psycopg2.connect(**connect_params)
                thread_conn.autocommit = False
                thread_cur = thread_conn.cursor(cursor_factory=RealDictCursor)
                thread_cur.execute("""
                    INSERT INTO loader_run_progress (run_id, loader_name, symbol, completed_at, status, error_msg, elapsed_ms)
                    VALUES (%s, %s, %s, NOW(), %s, %s, %s)
                    ON CONFLICT (run_id, loader_name, symbol) DO UPDATE SET
                        completed_at = NOW(), status = 'failed', error_msg = %s, elapsed_ms = %s
                """, (run_id, 'loaddailycompanydata', symbol, 'failed', error_msg, elapsed_ms, error_msg, elapsed_ms))
                thread_conn.commit()
                thread_conn.close()
            except Exception as track_err:
                logging.debug(f"Could not track error for {symbol}: {track_err}")

            return (symbol, None, False, error_msg)

        finally:
            try:
                thread_conn.close()
        except Exception:
                pass

    # MAIN LOOP: Process all symbols with automatic retries for failures
    logging.info(f" Starting PARALLELIZED data load with automatic retries for {len(symbols)} symbols")
    logging.info(f" Using ThreadPoolExecutor (max_workers=5) with global rate limiter (max 20 concurrent requests)")

    # Try each symbol up to 4 times (initial + 3 retries)
    attempt = 1
    max_attempts = 4
    symbols_to_process = symbols[:]

    # Build connection params for worker threads
    worker_connect_params = connect_params.copy()

    while symbols_to_process and attempt <= max_attempts:
        if attempt > 1:
            logging.info(f" Retry pass {attempt}/{max_attempts}: Retrying {len(symbols_to_process)} failed symbols...")

        failed_this_pass = []
        processed_this_pass = 0

        # Process symbols in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(process_symbol_worker, symbol, attempt, worker_connect_params): symbol
                for symbol in symbols_to_process
            }

            for i, future in enumerate(as_completed(futures)):
                symbol = futures[future]
                try:
                    symbol_result, stats, success, error_msg = future.result()

                    if success and stats:
                        for key in total_stats:
                            total_stats[key] += stats.get(key, 0)
                        processed += 1
                        processed_this_pass += 1
                        logging.info(f" {symbol}: {stats}")
                    else:
                        failed_this_pass.append(symbol)
                        if error_msg:
                            logging.warning(f"  {symbol}: {error_msg}")
                        else:
                            logging.warning(f"  {symbol}: No stats returned")

                    # Progress indicator every 50 symbols
                    if (i + 1) % 50 == 0:
                        elapsed_min = round((time.time() - start_time) / 60, 1)
                        logging.info(f"Progress: {processed}/{len(symbols)} loaded - Elapsed: {elapsed_min}min (Attempt {attempt})")

                except Exception as e:
                    logging.error(f"Exception in worker thread for {symbol}: {str(e)}")
                    failed_this_pass.append(symbol)

        # Update symbols to retry for next attempt
        symbols_to_process = failed_this_pass
        if not symbols_to_process:
            logging.info(f" All symbols loaded successfully on attempt {attempt}!")
            break
        else:
            logging.info(f" Processed {processed_this_pass} this pass, {len(symbols_to_process)} still failing, will retry...")

        attempt += 1

    logging.info("=" * 80)
    logging.info("REAL-TIME DATA LOADING COMPLETE")
    logging.info("=" * 80)
    success_rate = round(processed / len(symbols) * 100, 1) if symbols else 0
    logging.info(f" SUCCESS: {processed}/{len(symbols)} ({success_rate}%)")
    if failed:
        logging.info(f"  STILL FAILING: {len(failed)} ({round(len(failed)/len(symbols)*100, 1)}%) - will need manual retry")

    # Summary stats collected from individual stock loads
    logging.info(f" Component Summary:")
    logging.info(f"   - Company Info: {total_stats.get('info', 0)} stocks")
    logging.info(f"   - Positioning Metrics: {total_stats.get('positioning', 0)} stocks")
    logging.info(f"   - Insider Roster: {total_stats.get('insider_roster', 0)} records")
    logging.info(f"   - Earnings Estimates: {total_stats.get('earnings_est', 0)} records")
    logging.info(f"   - Revenue Estimates: {total_stats.get('revenue_est', 0)} records")

    if failed:
        logging.warning(f"  FAILED SYMBOLS (no data loaded): {','.join(failed[:20])}{f' +{len(failed)-20} more' if len(failed) > 20 else ''}")

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
