#!/usr/bin/env python3
"""
Daily Company Data Loader - Enhanced Positioning Analytics
Consolidates daily-update loaders into single efficient loader

Loads company info, positioning data, and analyst estimates with one API call per symbol.

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


def safe_float(value, default=None):
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=None):
    if value is None or pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def pyval(val):
    """Convert numpy types to native Python types"""
    if isinstance(val, (np.generic,)):
        return val.item()
    return val


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

        stats = {
            'info': 0,
            'institutional': 0,
            'mutualfund': 0,
            'insider_txns': 0,
            'insider_roster': 0,
            'positioning': 0,
            'earnings_est': 0,
            'revenue_est': 0,
        }

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
                        info.get("pegRatio"), info.get("enterpriseValue"),
                        info.get("enterpriseToRevenue"),
                        info.get("enterpriseToEbitda"),
                        info.get("totalRevenue"),
                        info.get("netIncomeToCommon"),
                        info.get("ebitda"), info.get("grossProfits"),
                        info.get("trailingEps"), info.get("forwardEps"),
                        info.get("currentYear"),
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
                        info.get("totalDebt"), info.get("debtToEquity"),
                        info.get("quickRatio"), info.get("currentRatio"),
                        info.get("profitMargins"), info.get("grossMargins"),
                        info.get("ebitdaMargins"),
                        info.get("operatingMargins"),
                        info.get("returnOnAssets"),
                        info.get("returnOnEquity"),
                        info.get("revenueGrowth"),
                        info.get("earningsGrowth"),
                        info.get("lastSplitFactor"),
                        info.get("lastSplitDate"),
                        info.get("dividendRate"), info.get("dividendYield"),
                        info.get("fiveYearAvgDividendYield"),
                        info.get("exDividendDate"),
                        info.get("lastAnnualDividendAmt"),
                        info.get("lastAnnualDividendYield"),
                        info.get("lastDividendValue"),
                        info.get("lastDividendDate"),
                        info.get("dividendDate"), info.get("payoutRatio"),
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
                        symbol, inst_type, inst_name,
                        safe_float(row.get('Value')),
                        safe_float(row.get('pctChange')) * 100 if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld')),
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
                        str(row.get('Holder', '')),
                        safe_float(row.get('Value')),
                        safe_float(row.get('pctChange')) * 100 if row.get('pctChange') else None,
                        safe_float(row.get('pctHeld')),
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
                # Create table if not exists
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

                insider_txn_data = []
                for _, row in insider_transactions.iterrows():
                    insider_txn_data.append((
                        symbol,
                        str(row.get('Insider', '')),
                        str(row.get('Position', '')),
                        str(row.get('Transaction', '')),
                        safe_int(row.get('Shares')),
                        safe_float(row.get('Value')),
                        row.get('Start Date'),
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
                        row.get('Latest Transaction Date'),
                        safe_int(row.get('Shares Owned Directly')),
                        row.get('Position Direct Date'),
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
                    'institutional_ownership': safe_float(info.get('heldPercentInstitutions')),
                    'institutional_float_held': safe_float(info.get('institutionsFloatPercentHeld')),
                    'institution_count': safe_int(info.get('institutionsCount')),
                    'insider_ownership': safe_float(info.get('heldPercentInsiders')),
                    'shares_short': safe_int(info.get('sharesShort')),
                    'shares_short_prior_month': safe_int(info.get('sharesShortPriorMonth')),
                    'short_ratio': safe_float(info.get('shortRatio')),
                    'short_percent_of_float': safe_float(info.get('shortPercentOfFloat')),
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
                        symbol, date, institutional_ownership, institutional_float_held,
                        institution_count, insider_ownership, shares_short, shares_short_prior_month,
                        short_ratio, short_percent_of_float, short_interest_change,
                        short_interest_date, float_shares, shares_outstanding
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        institutional_ownership = EXCLUDED.institutional_ownership,
                        institutional_float_held = EXCLUDED.institutional_float_held,
                        institution_count = EXCLUDED.institution_count,
                        insider_ownership = EXCLUDED.insider_ownership,
                        shares_short = EXCLUDED.shares_short,
                        short_ratio = EXCLUDED.short_ratio,
                        short_percent_of_float = EXCLUDED.short_percent_of_float,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        pos_data['symbol'], pos_data['date'],
                        pos_data.get('institutional_ownership'),
                        pos_data.get('institutional_float_held'),
                        pos_data.get('institution_count'),
                        pos_data.get('insider_ownership'),
                        pos_data.get('shares_short'),
                        pos_data.get('shares_short_prior_month'),
                        pos_data.get('short_ratio'),
                        pos_data.get('short_percent_of_float'),
                        pos_data.get('short_interest_change'),
                        pos_data.get('short_interest_date'),
                        pos_data.get('float_shares'),
                        pos_data.get('shares_outstanding'),
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
                        pyval(row.get("avg")),
                        pyval(row.get("low")),
                        pyval(row.get("high")),
                        pyval(row.get("yearAgoEps")),
                        pyval(row.get("numberOfAnalysts")),
                        pyval(row.get("growth")),
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
                        pyval(row.get("avg")),
                        pyval(row.get("low")),
                        pyval(row.get("high")),
                        pyval(row.get("numberOfAnalysts")),
                        pyval(row.get("yearAgoRevenue")),
                        pyval(row.get("growth")),
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

    # Get symbols
    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') LIMIT 10;")
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
