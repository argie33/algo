#!/usr/bin/env python3
"""
Daily Company Data Loader - Enhanced Positioning Analytics
Consolidates daily-update loaders into single efficient loader

Loads company info, positioning data, and analyst estimates with one API call per symbol.
Updated: 2025-10-25 17:15 - FIXED: Direct yfinance field → database column mapping for positioning metrics
Fixed Issue: Column mapping error - changed from intermediate dictionary lookups to direct field mapping
Result: All symbols now load successfully with 'positioning': 1 (no INSERT errors)

Replaces:
- loadinfo.py (ticker.info)
- loadpositioning.py (institutional/mutual fund holders)
- loadearningsestimate.py (earnings estimates)
- loadrevenueestimate.py (revenue estimates)

Data Loaded:
- Company profile & market data (from ticker.info)
- Institutional & mutual fund holdings with type classification
- Insider transactions & roster (buy/sell activity + current holdings)
- Positioning metrics (institutional/insider ownership, short interest)
- Earnings & revenue estimates

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
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

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
    """Get database configuration - works in AWS and locally"""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
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


def calculate_volatility_and_drawdown(symbol: str, ticker) -> Dict:
    """
    Calculate 12-month volatility and 52-week maximum drawdown from price history.

    Returns:
        Dict with 'volatility_12m_pct' and 'max_drawdown_52w_pct' (or None if insufficient data)
    """
    result = {
        'volatility_12m_pct': None,
        'max_drawdown_52w_pct': None
    }

    try:
        # Fetch 2 years of daily price data to get 12M volatility
        hist = ticker.history(period="2y")

        if hist is None or hist.empty or len(hist) < 252:
            logging.warning(f"Insufficient price history for {symbol} (need ≥252 days, got {len(hist) if hist is not None else 0})")
            return result

        # Calculate returns (yfinance uses 'Close' with capital C)
        closes = hist['Close'].dropna()
        if len(closes) < 2:
            return result

        daily_returns = closes.pct_change().dropna()

        # 12-month volatility (annualized)
        if len(daily_returns) >= 252:
            volatility_12m = daily_returns.std() * np.sqrt(252) * 100
            if not np.isnan(volatility_12m) and not np.isinf(volatility_12m):
                result['volatility_12m_pct'] = float(volatility_12m)

        # 52-week maximum drawdown
        if len(closes) >= 252:
            prices_52w = closes.iloc[-252:]  # Last 252 trading days
            running_max = prices_52w.expanding().max()
            drawdown = (prices_52w - running_max) / running_max * 100
            max_dd = drawdown.min()
            if not np.isnan(max_dd) and not np.isinf(max_dd):
                result['max_drawdown_52w_pct'] = float(abs(max_dd))  # Store as positive value

    except Exception as e:
        logging.warning(f"Error calculating volatility/drawdown for {symbol}: {e}")

    return result


def calculate_missing_metrics(symbol: str, info: dict, ticker) -> dict:
    """Calculate missing earnings_growth_pct, payout_ratio, and debt_to_equity when not provided by yfinance"""

    metrics = {
        'earnings_growth': info.get('earningsGrowth'),
        'payout_ratio': info.get('payoutRatio'),
        'debt_to_equity': info.get('debtToEquity'),
        'de_source': 'YFINANCE',  # Track source: YFINANCE or CALCULATED
    }

    # If earningsGrowth is missing, try to calculate from earnings_estimate
    if not metrics['earnings_growth']:
        try:
            earnings_est = ticker.earnings_estimate
            if earnings_est is not None and not earnings_est.empty:
                # Get current year and previous year estimates
                current_eps = info.get('epsCurrentYear')
                trailing_eps = info.get('trailingEps')
                if current_eps and trailing_eps and trailing_eps > 0:
                    metrics['earnings_growth'] = (current_eps - trailing_eps) / trailing_eps
        except:
            pass

    # If payoutRatio is missing, try to calculate from dividend and earnings data (REAL DATA ONLY)
    if metrics['payout_ratio'] is None or metrics['payout_ratio'] == 0:
        try:
            annual_dividend = info.get('trailingAnnualDividendRate')  # None if missing (NOT fake 0)
            trailing_eps = info.get('trailingEps')
            if annual_dividend is not None and annual_dividend > 0 and trailing_eps and trailing_eps > 0:
                metrics['payout_ratio'] = min(1.0, annual_dividend / trailing_eps)
        except:
            pass

    # NEW: If debt_to_equity missing from yfinance, calculate from balance sheet
    # debt_to_equity = total_debt / book_value (shareholder equity)
    if metrics['debt_to_equity'] is None:
        try:
            total_debt = safe_float(info.get('totalDebt'), min_val=0)
            book_value = safe_float(info.get('bookValue'), min_val=0.01)

            if total_debt is not None and book_value is not None and book_value > 0:
                calculated_de = total_debt / book_value
                # Sanity check: D/E should typically be between 0 and 10 for most companies
                if 0 <= calculated_de <= 1000:  # Allow up to 1000:1 for extreme cases
                    metrics['debt_to_equity'] = calculated_de
                    metrics['de_source'] = 'CALCULATED'
                    logging.info(f"{symbol}: Calculated D/E = {calculated_de:.2f} (debt={total_debt:,.0f} / book_value={book_value:,.0f})")
        except Exception as e:
            logging.debug(f"{symbol}: Could not calculate D/E: {e}")

    return metrics


def load_all_realtime_data(symbol: str, cur, conn) -> Dict:
    """Load ALL daily data from single yfinance API call"""

    try:
        # SINGLE API CALL gets everything
        ticker = yf.Ticker(symbol)

        # Get all data sources
        info = ticker.info
        institutional_holders = ticker.institutional_holders
        mutualfund_holders = ticker.mutualfund_holders
        insider_transactions = ticker.insider_transactions
        insider_roster = ticker.insider_roster_holders
        major_holders = ticker.major_holders
        earnings_estimate = ticker.earnings_estimate
        revenue_estimate = ticker.revenue_estimate

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
            'beta': None,
        }

        # Calculate volatility and drawdown from price history (REAL DATA ONLY - no fallbacks)
        vol_dd = calculate_volatility_and_drawdown(symbol, ticker)

        # 1. Insert company_profile, market_data, key_metrics (from ticker.info)
        if info:
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

                # Market data
                cur.execute(
                    """
                    INSERT INTO market_data (
                        ticker, previous_close, regular_market_previous_close,
                        open_price, regular_market_open, day_low,
                        regular_market_day_low, day_high, regular_market_day_high,
                        regular_market_price, current_price, post_market_price,
                        post_market_change, post_market_change_pct, volume,
                        regular_market_volume, average_volume, avg_volume_10d,
                        avg_daily_volume_10d, avg_daily_volume_3m, bid_price,
                        ask_price, bid_size, ask_size, market_state,
                        fifty_two_week_low, fifty_two_week_high,
                        fifty_two_week_range, fifty_two_week_low_change,
                        fifty_two_week_low_change_pct, fifty_two_week_high_change,
                        fifty_two_week_high_change_pct, fifty_two_week_change_pct,
                        fifty_day_avg, two_hundred_day_avg, fifty_day_avg_change,
                        fifty_day_avg_change_pct, two_hundred_day_avg_change,
                        two_hundred_day_avg_change_pct, source_interval_sec,
                        market_cap
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        current_price = EXCLUDED.current_price,
                        volume = EXCLUDED.volume,
                        market_cap = EXCLUDED.market_cap
                """,
                    (
                        symbol, info.get("previousClose"),
                        info.get("regularMarketPreviousClose"),
                        info.get("open"), info.get("regularMarketOpen"),
                        info.get("dayLow"), info.get("regularMarketDayLow"),
                        info.get("dayHigh"), info.get("regularMarketDayHigh"),
                        info.get("regularMarketPrice"), info.get("currentPrice"),
                        info.get("postMarketPrice"),
                        info.get("postMarketChange"),
                        info.get("postMarketChangePercent"),
                        info.get("volume"), info.get("regularMarketVolume"),
                        info.get("averageVolume"),
                        info.get("averageVolume10days"),
                        info.get("averageDailyVolume10Day"),
                        info.get("averageDailyVolume3Month"),
                        info.get("bid"), info.get("ask"),
                        info.get("bidSize"), info.get("askSize"),
                        info.get("marketState"),
                        info.get("fiftyTwoWeekLow"),
                        info.get("fiftyTwoWeekHigh"),
                        f"{info.get('fiftyTwoWeekLow')} - {info.get('fiftyTwoWeekHigh')}",
                        info.get("fiftyTwoWeekLowChange"),
                        info.get("fiftyTwoWeekLowChangePercent"),
                        info.get("fiftyTwoWeekHighChange"),
                        info.get("fiftyTwoWeekHighChangePercent"),
                        info.get("fiftyTwoWeekChangePercent"),
                        info.get("fiftyDayAverage"),
                        info.get("twoHundredDayAverage"),
                        info.get("fiftyDayAverageChange"),
                        info.get("fiftyDayAverageChangePercent"),
                        info.get("twoHundredDayAverageChange"),
                        info.get("twoHundredDayAverageChangePercent"),
                        info.get("sourceInterval"),
                        info.get("marketCap"),
                    ),
                )

                # Key metrics (with new positioning fields)
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
                        earnings_growth_pct, last_split_factor,
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
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        trailing_pe = EXCLUDED.trailing_pe,
                        forward_pe = EXCLUDED.forward_pe,
                        eps_trailing = EXCLUDED.eps_trailing,
                        eps_current_year = EXCLUDED.eps_current_year,
                        gross_margin_pct = EXCLUDED.gross_margin_pct,
                        ebitda_margin_pct = EXCLUDED.ebitda_margin_pct,
                        profit_margin_pct = EXCLUDED.profit_margin_pct,
                        operating_margin_pct = EXCLUDED.operating_margin_pct,
                        return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                        return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                        earnings_growth_pct = EXCLUDED.earnings_growth_pct,
                        earnings_q_growth_pct = EXCLUDED.earnings_q_growth_pct,
                        revenue_growth_pct = EXCLUDED.revenue_growth_pct,
                        payout_ratio = EXCLUDED.payout_ratio,
                        debt_to_equity = EXCLUDED.debt_to_equity,
                        last_annual_dividend_amt = EXCLUDED.last_annual_dividend_amt,
                        last_annual_dividend_yield = EXCLUDED.last_annual_dividend_yield,
                        held_percent_insiders = EXCLUDED.held_percent_insiders,
                        held_percent_institutions = EXCLUDED.held_percent_institutions,
                        shares_short = EXCLUDED.shares_short,
                        short_ratio = EXCLUDED.short_ratio,
                        short_percent_of_float = EXCLUDED.short_percent_of_float
                """,
                    (
                        symbol, info.get("trailingPE"), info.get("forwardPE"),
                        info.get("priceToSalesTrailing12Months"),
                        info.get("priceToBook"), info.get("bookValue"),
                        info.get("trailingPegRatio"), info.get("enterpriseValue"),
                        info.get("enterpriseToRevenue"),
                        info.get("enterpriseToEbitda"),
                        info.get("totalRevenue"),
                        info.get("netIncomeToCommon"),
                        info.get("ebitda"), info.get("grossProfits"),
                        info.get("trailingEps"), info.get("forwardEps"),
                        info.get("epsCurrentYear"),
                        info.get("priceEpsCurrentYear"),
                        info.get("earningsQuarterlyGrowth"),
                        info.get("earningsTimestamp"),
                        info.get("earningsTimestampStart"),
                        info.get("earningsTimestampEnd"),
                        info.get("earningsCallTimeStampStart"),
                        info.get("earningsCallTimeStampEnd"),
                        info.get("earningsDateIsEstimate"),
                        info.get("totalCash"),
                        info.get("totalCashPerShare"),
                        info.get("operatingCashflow"),
                        info.get("freeCashflow"),
                        info.get("totalDebt"), missing_metrics.get('debt_to_equity'),  # Use calculated D/E if yfinance didn't provide
                        info.get("quickRatio"), info.get("currentRatio"),
                        info.get("profitMargins"), info.get("grossMargins"),
                        info.get("ebitdaMargins"),
                        info.get("operatingMargins"),
                        info.get("returnOnAssets"),
                        info.get("returnOnEquity"),
                        info.get("revenueGrowth"),
                        missing_metrics.get('earnings_growth') or info.get("earningsGrowth"),
                        info.get("lastSplitFactor"),
                        info.get("lastSplitDate"),
                        info.get("dividendRate"), info.get("dividendYield"),
                        info.get("fiveYearAvgDividendYield"),
                        info.get("exDividendDate"),
                        info.get("trailingAnnualDividendRate"),
                        info.get("trailingAnnualDividendYield"),
                        info.get("lastDividendValue"),
                        info.get("lastDividendDate"),
                        info.get("dividendDate"), missing_metrics.get('payout_ratio') or info.get("payoutRatio"),
                        info.get("heldPercentInsiders"),
                        info.get("heldPercentInstitutions"),
                        info.get("sharesShort"),
                        info.get("sharesShortPriorMonth"),
                        info.get("shortRatio"),
                        info.get("shortPercentOfFloat"),
                        info.get("impliedSharesOutstanding"),
                        info.get("floatShares"),
                    ),
                )

                stats['info'] = 1

            except Exception as e:
                logging.error(f"Error inserting info data for {symbol}: {e}")
                conn.rollback()

        # 2. Insert institutional holders
        if institutional_holders is not None and not institutional_holders.empty:
            try:
                inst_data = []
                for _, row in institutional_holders.iterrows():
                    date_reported = row.get('Date Reported')
                    if date_reported:
                        year = date_reported.year
                        quarter_num = (date_reported.month - 1) // 3 + 1
                        quarter = f"{year}Q{quarter_num}"
                    else:
                        quarter = None

                    inst_name = str(row.get('Holder', ''))
                    if any(x in inst_name.lower() for x in ['vanguard', 'fidelity', 'blackrock', 'state street']):
                        inst_type = 'MUTUAL_FUND'
                    elif any(x in inst_name.lower() for x in ['berkshire', 'hedge', 'capital', 'partners']):
                        inst_type = 'HEDGE_FUND'
                    elif any(x in inst_name.lower() for x in ['pension', 'retirement', 'insurance']):
                        inst_type = 'PENSION_FUND'
                    else:
                        inst_type = 'INSTITUTIONAL'

                    inst_data.append((
                        symbol, inst_type, safe_str(inst_name, max_len=300),
                        safe_float(row.get('Value'), max_val=999999999999),
                        safe_float(row.get('pctChange'), max_val=1000, min_val=-100) * 100 if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld'), max_val=100, min_val=0),
                        date_reported, quarter,
                    ))

                if inst_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO institutional_positioning (
                            symbol, institution_type, institution_name, position_size,
                            position_change_percent, market_share, filing_date, quarter
                        ) VALUES %s
                        ON CONFLICT (id) DO NOTHING
                        """,
                        inst_data
                    )
                    stats['institutional'] = len(inst_data)

            except Exception as e:
                logging.error(f"Error inserting institutional holders for {symbol}: {e}")
                conn.rollback()

        # 3. Insert mutual fund holders (NEW!)
        if mutualfund_holders is not None and not mutualfund_holders.empty:
            try:
                mf_data = []
                for _, row in mutualfund_holders.iterrows():
                    date_reported = row.get('Date Reported')
                    if date_reported:
                        year = date_reported.year
                        quarter_num = (date_reported.month - 1) // 3 + 1
                        quarter = f"{year}Q{quarter_num}"
                    else:
                        quarter = None

                    mf_data.append((
                        symbol, 'MUTUAL_FUND',
                        safe_str(row.get('Holder', ''), max_len=300),
                        safe_float(row.get('Value'), max_val=999999999999),
                        safe_float(row.get('pctChange'), max_val=1000, min_val=-100) * 100 if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld'), max_val=100, min_val=0),
                        date_reported, quarter,
                    ))

                if mf_data:
                    execute_values(
                        cur,
                        """
                        INSERT INTO institutional_positioning (
                            symbol, institution_type, institution_name, position_size,
                            position_change_percent, market_share, filing_date, quarter
                        ) VALUES %s
                        ON CONFLICT (id) DO NOTHING
                        """,
                        mf_data
                    )
                    stats['mutualfund'] = len(mf_data)

            except Exception as e:
                logging.error(f"Error inserting mutual fund holders for {symbol}: {e}")
                conn.rollback()

        # 4. Insert insider transactions (NEW!)
        if insider_transactions is not None and not insider_transactions.empty:
            try:
                insider_txn_data = []
                for _, row in insider_transactions.iterrows():
                    insider_txn_data.append((
                        symbol,
                        str(row.get('Insider', '')),
                        str(row.get('Position', '')),
                        str(row.get('Transaction', '')),
                        safe_int(row.get('Shares')),
                        safe_float(row.get('Value')),
                        safe_date(row.get('Start Date')),
                        str(row.get('Ownership', '')),
                        str(row.get('Text', '')),
                        str(row.get('URL', '')),
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
                logging.error(f"Error inserting insider transactions for {symbol}: {e}")
                conn.rollback()

        # 5. Insert insider roster (NEW!)
        if insider_roster is not None and not insider_roster.empty:
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
                        str(row.get('Name', '')),
                        str(row.get('Position', '')),
                        str(row.get('Most Recent Transaction', '')),
                        safe_date(row.get('Latest Transaction Date')),
                        safe_int(row.get('Shares Owned Directly')),
                        safe_date(row.get('Position Direct Date')),
                        str(row.get('URL', '')),
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

            except Exception as e:
                logging.error(f"Error inserting insider roster for {symbol}: {e}")
                conn.rollback()

        # 6. Insert positioning metrics
        if info:
            try:
                pos_data = {
                    'symbol': symbol,
                    'date': date.today(),
                    'institutional_ownership_pct': safe_float(info.get('heldPercentInstitutions')),
                    'top_10_institutions_pct': safe_float(info.get('institutionsFloatPercentHeld')),
                    'institutional_holders_count': safe_int(info.get('institutionsCount')),
                    'insider_ownership_pct': safe_float(info.get('heldPercentInsiders')),
                    'shares_short': safe_int(info.get('sharesShort')),
                    'shares_short_prior_month': safe_int(info.get('sharesShortPriorMonth')),
                    'short_ratio': safe_float(info.get('shortRatio')),
                    'short_interest_pct': safe_float(info.get('shortPercentOfFloat')),
                    'short_interest_date': info.get('dateShortInterest'),
                    'float_shares': safe_int(info.get('floatShares')),
                    'shares_outstanding': safe_int(info.get('sharesOutstanding')),
                }

                if pos_data['shares_short'] and pos_data['shares_short_prior_month']:
                    pos_data['short_interest_change'] = (
                        (pos_data['shares_short'] - pos_data['shares_short_prior_month']) /
                        pos_data['shares_short_prior_month']
                    )
                else:
                    pos_data['short_interest_change'] = None

                cur.execute(
                    """
                    INSERT INTO positioning_metrics (
                        symbol, date, institutional_ownership_pct, top_10_institutions_pct,
                        institutional_holders_count, insider_ownership_pct,
                        short_ratio, short_interest_pct
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                        top_10_institutions_pct = EXCLUDED.top_10_institutions_pct,
                        institutional_holders_count = EXCLUDED.institutional_holders_count,
                        insider_ownership_pct = EXCLUDED.insider_ownership_pct,
                        short_ratio = EXCLUDED.short_ratio,
                        short_interest_pct = EXCLUDED.short_interest_pct,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        symbol, date.today(),
                        safe_float(info.get('heldPercentInstitutions')),
                        safe_float(info.get('institutionsFloatPercentHeld')),
                        safe_int(info.get('institutionsCount')),
                        safe_float(info.get('heldPercentInsiders')),
                        safe_float(info.get('shortRatio')),
                        safe_float(info.get('shortPercentOfFloat')),
                    )
                )
                stats['positioning'] = 1

            except Exception as e:
                logging.error(f"Error inserting positioning metrics for {symbol}: {e}")
                conn.rollback()

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
                    execute_values(
                        cur,
                        """
                        INSERT INTO earnings_estimates (
                            symbol, period, avg_estimate, low_estimate,
                            high_estimate, year_ago_eps, number_of_analysts,
                            growth
                        ) VALUES %s
                        ON CONFLICT (symbol, period) DO UPDATE SET
                            avg_estimate = EXCLUDED.avg_estimate,
                            low_estimate = EXCLUDED.low_estimate,
                            high_estimate = EXCLUDED.high_estimate,
                            year_ago_eps = EXCLUDED.year_ago_eps,
                            number_of_analysts = EXCLUDED.number_of_analysts,
                            growth = EXCLUDED.growth,
                            fetched_at = CURRENT_TIMESTAMP
                        """,
                        earnings_data
                    )
                    stats['earnings_est'] = len(earnings_data)

            except Exception as e:
                logging.error(f"Error inserting earnings estimates for {symbol}: {e}")
                conn.rollback()

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
                    execute_values(
                        cur,
                        """
                        INSERT INTO revenue_estimates (
                            symbol, period, avg_estimate, low_estimate,
                            high_estimate, number_of_analysts, year_ago_revenue,
                            growth
                        ) VALUES %s
                        ON CONFLICT (symbol, period) DO UPDATE SET
                            avg_estimate = EXCLUDED.avg_estimate,
                            low_estimate = EXCLUDED.low_estimate,
                            high_estimate = EXCLUDED.high_estimate,
                            number_of_analysts = EXCLUDED.number_of_analysts,
                            year_ago_revenue = EXCLUDED.year_ago_revenue,
                            growth = EXCLUDED.growth,
                            fetched_at = CURRENT_TIMESTAMP
                        """,
                        revenue_data
                    )
                    stats['revenue_est'] = len(revenue_data)

            except Exception as e:
                logging.error(f"Error inserting revenue estimates for {symbol}: {e}")
                conn.rollback()

        # 9. Insert risk metrics into risk_metrics (volatility, drawdown, beta - REAL DATA ONLY)
        try:
            beta = safe_float(info.get('beta'))
            volatility_12m_pct = vol_dd.get('volatility_12m_pct')
            max_drawdown_52w_pct = vol_dd.get('max_drawdown_52w_pct')

            # Only insert if we have at least one real metric
            if beta is not None or volatility_12m_pct is not None or max_drawdown_52w_pct is not None:
                cur.execute(
                    """
                    INSERT INTO risk_metrics (
                        symbol, date,
                        volatility_12m_pct, max_drawdown_52w_pct, beta
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        volatility_12m_pct = EXCLUDED.volatility_12m_pct,
                        max_drawdown_52w_pct = EXCLUDED.max_drawdown_52w_pct,
                        beta = EXCLUDED.beta,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (symbol, date.today(), volatility_12m_pct, max_drawdown_52w_pct, beta)
                )
                stats['beta'] = 1 if beta is not None else 0
                stats['volatility'] = 1 if volatility_12m_pct is not None else 0
                stats['drawdown'] = 1 if max_drawdown_52w_pct is not None else 0
                logging.debug(f"  ✓ Risk metrics: vol={volatility_12m_pct}, dd={max_drawdown_52w_pct}, beta={beta}")
            else:
                logging.debug(f"  ⚠ No risk metrics available for {symbol} (all None)")
                stats['beta'] = 0
                stats['volatility'] = 0
                stats['drawdown'] = 0
        except Exception as e:
            logging.error(f"Error inserting risk metrics for {symbol}: {e}")
            conn.rollback()
            stats['beta'] = 0
            stats['volatility'] = 0
            stats['drawdown'] = 0

        conn.commit()
        return stats

    except Exception as e:
        logging.error(f"Error loading realtime data for {symbol}: {e}")
        conn.rollback()
        return None


if __name__ == "__main__":
    log_mem("startup")

    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
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
                top_10_institutions_pct DECIMAL(8,6),
                institutional_holders_count INTEGER,
                insider_ownership_pct DECIMAL(8,6),
                short_ratio DECIMAL(8,2),
                short_interest_pct DECIMAL(8,6),
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
        logging.error(f"Schema migration error: {e}")
        conn.rollback()

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

            time.sleep(0.5)  # Rate limiting

        except Exception as e:
            logging.error(f"Failed {symbol}: {e}")
            failed.append(symbol)
            conn.rollback()

    logging.info("=" * 80)
    logging.info("REAL-TIME DATA LOADING COMPLETE")
    logging.info("=" * 80)
    logging.info(f"Processed: {processed}/{len(symbols)}")
    logging.info(f"Failed: {len(failed)}")
    logging.info(f"Stats: {total_stats}")

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
