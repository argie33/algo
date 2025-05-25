#!/usr/bin/env python3 
import sys
import time
import logging
import functools
import os
import json
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd
import math

SCRIPT_NAME = "loadinfo.py"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def retry(max_attempts=3, initial_delay=2, backoff=2):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, conn, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, conn, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{f.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}",
                        exc_info=True
                    )
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}"
            )
        return wrapper
    return decorator

def clean_value(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    return value

def ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS leadership_team;")
        cur.execute("DROP TABLE IF EXISTS governance_scores;")
        cur.execute("DROP TABLE IF EXISTS market_data;")
        cur.execute("DROP TABLE IF EXISTS key_metrics;")
        cur.execute("DROP TABLE IF EXISTS analyst_estimates;")
        cur.execute("DROP TABLE IF EXISTS company_profile;")
        cur.execute("""
CREATE TABLE company_profile (
    ticker VARCHAR(10) PRIMARY KEY,
    short_name VARCHAR(100),
    long_name VARCHAR(200),
    display_name VARCHAR(200),
    quote_type VARCHAR(50),
    symbol_type VARCHAR(50),
    triggerable BOOLEAN,
    has_pre_post_market_data BOOLEAN,
    price_hint INT,
    max_age_sec INT,
    language VARCHAR(20),
    region VARCHAR(20),
    financial_currency VARCHAR(10),
    currency VARCHAR(10),
    market VARCHAR(50),
    quote_source_name VARCHAR(100),
    custom_price_alert_confidence VARCHAR(20),
    address1 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    phone_number VARCHAR(50),
    website_url VARCHAR(200),
    ir_website_url VARCHAR(200),
    message_board_id VARCHAR(100),
    corporate_actions JSONB,
    sector VARCHAR(100),
    sector_key VARCHAR(100),
    sector_disp VARCHAR(100),
    industry VARCHAR(100),
    industry_key VARCHAR(100),
    industry_disp VARCHAR(100),
    business_summary TEXT,
    employee_count INT,
    first_trade_date_ms BIGINT,
    gmt_offset_ms BIGINT,
    exchange VARCHAR(20),
    full_exchange_name VARCHAR(100),
    exchange_timezone_name VARCHAR(100),
    exchange_timezone_short_name VARCHAR(20),
    exchange_data_delayed_by_sec INT,
    post_market_time_ms BIGINT,
    regular_market_time_ms BIGINT
);
""")
        cur.execute("""
CREATE TABLE leadership_team (
    ticker VARCHAR(10) NOT NULL REFERENCES company_profile(ticker),
    person_name VARCHAR(200) NOT NULL,
    age INT,
    title VARCHAR(200),
    birth_year INT,
    fiscal_year INT,
    total_pay NUMERIC,
    exercised_value NUMERIC,
    unexercised_value NUMERIC,
    role_source VARCHAR(50) NULL,
    PRIMARY KEY(ticker, person_name, role_source)
);
""")
        cur.execute("""
CREATE TABLE governance_scores (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    audit_risk INT,
    board_risk INT,
    compensation_risk INT,
    shareholder_rights_risk INT,
    overall_risk INT,
    governance_epoch_ms BIGINT,
    comp_data_as_of_ms BIGINT
);
""")
        cur.execute("""
CREATE TABLE market_data (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    previous_close NUMERIC,
    regular_market_previous_close NUMERIC,
    open_price NUMERIC,
    regular_market_open NUMERIC,
    day_low NUMERIC,
    regular_market_day_low NUMERIC,
    day_high NUMERIC,
    regular_market_day_high NUMERIC,
    regular_market_price NUMERIC,
    current_price NUMERIC,
    post_market_price NUMERIC,
    post_market_change NUMERIC,
    post_market_change_pct NUMERIC,
    volume BIGINT,
    regular_market_volume BIGINT,
    average_volume BIGINT,
    avg_volume_10d BIGINT,
    avg_daily_volume_10d BIGINT,
    avg_daily_volume_3m BIGINT,
    bid_price NUMERIC,
    ask_price NUMERIC,
    bid_size INT,
    ask_size INT,
    market_state VARCHAR(20),
    fifty_two_week_low NUMERIC,
    fifty_two_week_high NUMERIC,
    fifty_two_week_range VARCHAR(50),
    fifty_two_week_low_change NUMERIC,
    fifty_two_week_low_change_pct NUMERIC,
    fifty_two_week_high_change NUMERIC,
    fifty_two_week_high_change_pct NUMERIC,
    fifty_two_week_change_pct NUMERIC,
    fifty_day_avg NUMERIC,
    two_hundred_day_avg NUMERIC,
    fifty_day_avg_change NUMERIC,
    fifty_day_avg_change_pct NUMERIC,
    two_hundred_day_avg_change NUMERIC,
    two_hundred_day_avg_change_pct NUMERIC,
    source_interval_sec INT,
    market_cap BIGINT
);
""")
        cur.execute("""
CREATE TABLE key_metrics (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    trailing_pe NUMERIC,
    forward_pe NUMERIC,
    price_to_sales_ttm NUMERIC,
    price_to_book NUMERIC,
    book_value NUMERIC,
    peg_ratio NUMERIC,
    enterprise_value BIGINT,
    ev_to_revenue NUMERIC,
    ev_to_ebitda NUMERIC,
    total_revenue BIGINT,
    net_income BIGINT,
    ebitda BIGINT,
    gross_profit BIGINT,
    eps_trailing NUMERIC,
    eps_forward NUMERIC,
    eps_current_year NUMERIC,
    price_eps_current_year NUMERIC,
    earnings_q_growth_pct NUMERIC,
    earnings_ts_ms BIGINT,
    earnings_ts_start_ms BIGINT,
    earnings_ts_end_ms BIGINT,
    earnings_call_ts_start_ms BIGINT,
    earnings_call_ts_end_ms BIGINT,
    is_earnings_date_estimate BOOLEAN,
    total_cash BIGINT,
    cash_per_share NUMERIC,
    operating_cashflow BIGINT,
    free_cashflow BIGINT,
    total_debt BIGINT,
    debt_to_equity NUMERIC,
    quick_ratio NUMERIC,
    current_ratio NUMERIC,
    profit_margin_pct NUMERIC,
    gross_margin_pct NUMERIC,
    ebitda_margin_pct NUMERIC,
    operating_margin_pct NUMERIC,
    return_on_assets_pct NUMERIC,
    return_on_equity_pct NUMERIC,
    revenue_growth_pct NUMERIC,
    earnings_growth_pct NUMERIC,
    last_split_factor VARCHAR(20),
    last_split_date_ms BIGINT,
    dividend_rate NUMERIC,
    dividend_yield NUMERIC,
    five_year_avg_dividend_yield NUMERIC,
    ex_dividend_date_ms BIGINT,
    last_annual_dividend_amt NUMERIC,
    last_annual_dividend_yield NUMERIC,
    last_dividend_amt NUMERIC,
    last_dividend_date_ms BIGINT,
    dividend_date_ms BIGINT,
    payout_ratio NUMERIC
);
""")
        cur.execute("""
CREATE TABLE analyst_estimates (
    ticker VARCHAR(10) PRIMARY KEY REFERENCES company_profile(ticker),
    target_high_price NUMERIC,
    target_low_price NUMERIC,
    target_mean_price NUMERIC,
    target_median_price NUMERIC,
    recommendation_key VARCHAR(50),
    recommendation_mean NUMERIC,
    analyst_opinion_count INT,
    average_analyst_rating NUMERIC
);
""")
        cur.execute("""
CREATE TABLE IF NOT EXISTS last_updated (
    script_name VARCHAR(255) PRIMARY KEY,
    last_run TIMESTAMPTZ NOT NULL
);
""")
    conn.commit()

def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

def safe_get(d, *keys, default=None):
    for k in keys:
        if d is None:
            return default
        d = d.get(k, default)
    return d


# --- Robust ECS loader pattern for process_symbol ---
@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    yf_symbol = symbol.upper().replace(".", "-")
    logger.info(f"Processing symbol: {symbol} (YF Symbol: {yf_symbol})")
    try:
        ticker = yf.Ticker(yf_symbol)
        info = ticker.get_info() or {}
        logger.debug(f"Retrieved {len(info)} info fields for {symbol}")
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}")
        info = {}

    def jdump(val):
        try:
            return json.dumps(val) if val is not None else None
        except Exception as e:
            logger.debug(f"JSON dump failed for value: {type(val)}, error: {e}")
            return None

    with conn.cursor() as cur:
        # 1. company_profile
        try:
            # Create a list with all parameters for SQL insert
            profile_params = [
                symbol,
                clean_value(info.get("shortName")),
                clean_value(info.get("longName")),
                clean_value(info.get("displayName")),
                clean_value(info.get("quoteType")),
                clean_value(info.get("typeDisp")),
                clean_value(info.get("triggerable")),
                clean_value(info.get("hasPrePostMarketData")),
                clean_value(info.get("priceHint")),
                clean_value(info.get("maxAge")),
                clean_value(info.get("language")),
                clean_value(info.get("region")),
                clean_value(info.get("financialCurrency")),
                clean_value(info.get("currency")),
                clean_value(info.get("market")),
                clean_value(info.get("quoteSourceName")),
                clean_value(info.get("customPriceAlertConfidence")),
                clean_value(info.get("address1")),
                clean_value(info.get("city")),
                clean_value(info.get("state")),
                clean_value(info.get("zip")),
                clean_value(info.get("country")),
                clean_value(info.get("phone")),
                clean_value(info.get("website")),
                clean_value(info.get("irWebsite")),
                clean_value(info.get("messageBoardId")),
                jdump(info.get("corporateActions")),
                clean_value(info.get("sector")),
                clean_value(info.get("sectorKey")),
                clean_value(info.get("sectorDisp")),
                clean_value(info.get("industry")),
                clean_value(info.get("industryKey")),
                clean_value(info.get("industryDisp")),
                clean_value(info.get("longBusinessSummary")),
                clean_value(info.get("fullTimeEmployees")),
                clean_value(info.get("firstTradeDateMilliseconds")),
                clean_value(info.get("gmtOffSetMilliseconds")),
                clean_value(info.get("exchange")),
                clean_value(info.get("fullExchangeName")),
                clean_value(info.get("exchangeTimezoneName")),
                clean_value(info.get("exchangeTimezoneShortName")),
                clean_value(info.get("exchangeDataDelayedBy")),
                clean_value(info.get("postMarketTime")),
                clean_value(info.get("regularMarketTime"))
            ]
            
            cur.execute("""
                INSERT INTO company_profile (
                    ticker, short_name, long_name, display_name, quote_type, symbol_type, triggerable, has_pre_post_market_data, price_hint, max_age_sec, language, region, financial_currency, currency, market, quote_source_name, custom_price_alert_confidence, address1, city, state, postal_code, country, phone_number, website_url, ir_website_url, message_board_id, corporate_actions, sector, sector_key, sector_disp, industry, industry_key, industry_disp, business_summary, employee_count, first_trade_date_ms, gmt_offset_ms, exchange, full_exchange_name, exchange_timezone_name, exchange_timezone_short_name, exchange_data_delayed_by_sec, post_market_time_ms, regular_market_time_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name=EXCLUDED.short_name, long_name=EXCLUDED.long_name, display_name=EXCLUDED.display_name, quote_type=EXCLUDED.quote_type, symbol_type=EXCLUDED.symbol_type, triggerable=EXCLUDED.triggerable, has_pre_post_market_data=EXCLUDED.has_pre_post_market_data, price_hint=EXCLUDED.price_hint, max_age_sec=EXCLUDED.max_age_sec, language=EXCLUDED.language, region=EXCLUDED.region, financial_currency=EXCLUDED.financial_currency, currency=EXCLUDED.currency, market=EXCLUDED.market, quote_source_name=EXCLUDED.quote_source_name, custom_price_alert_confidence=EXCLUDED.custom_price_alert_confidence, address1=EXCLUDED.address1, city=EXCLUDED.city, state=EXCLUDED.state, postal_code=EXCLUDED.postal_code, country=EXCLUDED.country, phone_number=EXCLUDED.phone_number, website_url=EXCLUDED.website_url, ir_website_url=EXCLUDED.ir_website_url, message_board_id=EXCLUDED.message_board_id, corporate_actions=EXCLUDED.corporate_actions, sector=EXCLUDED.sector, sector_key=EXCLUDED.sector_key, sector_disp=EXCLUDED.sector_disp, industry=EXCLUDED.industry, industry_key=EXCLUDED.industry_key, industry_disp=EXCLUDED.industry_disp, business_summary=EXCLUDED.business_summary, employee_count=EXCLUDED.employee_count, first_trade_date_ms=EXCLUDED.first_trade_date_ms, gmt_offset_ms=EXCLUDED.gmt_offset_ms, exchange=EXCLUDED.exchange, full_exchange_name=EXCLUDED.full_exchange_name, exchange_timezone_name=EXCLUDED.exchange_timezone_name, exchange_timezone_short_name=EXCLUDED.exchange_timezone_short_name, exchange_data_delayed_by_sec=EXCLUDED.exchange_data_delayed_by_sec, post_market_time_ms=EXCLUDED.post_market_time_ms, regular_market_time_ms=EXCLUDED.regular_market_time_ms
                ;
            """, profile_params)
            logger.debug(f"Inserted company profile for {symbol}")
        except Exception as e:
            logger.exception(f"Failed to insert company_profile for {symbol}: {e}")
            conn.rollback()
            return

        # 2a. leadership_team (companyOfficers)
        officers = info.get("companyOfficers", [])
        if officers is None:
            officers = []
            
        for officer in officers:
            try:
                if not isinstance(officer, dict):
                    logger.warning(f"Invalid officer data for {symbol}: {officer}")
                    continue
                    
                officer_params = [
                    symbol,
                    clean_value(officer.get("name")),
                    clean_value(officer.get("age")),
                    clean_value(officer.get("title")),
                    clean_value(officer.get("yearBorn")),
                    clean_value(officer.get("fiscalYear")),
                    clean_value(officer.get("totalPay")),
                    clean_value(officer.get("exercisedValue")),
                    clean_value(officer.get("unexercisedValue")),
                    "companyOfficer"
                ]
                
                if officer_params[1] is None:  # Skip if name is None
                    logger.warning(f"Skipping officer with no name for {symbol}")
                    continue
                
                cur.execute("""
                    INSERT INTO leadership_team (
                        ticker, person_name, age, title, birth_year, fiscal_year, total_pay, exercised_value, unexercised_value, role_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, person_name, role_source) DO UPDATE SET
                        age=EXCLUDED.age, title=EXCLUDED.title, birth_year=EXCLUDED.birth_year, fiscal_year=EXCLUDED.fiscal_year, total_pay=EXCLUDED.total_pay, exercised_value=EXCLUDED.exercised_value, unexercised_value=EXCLUDED.unexercised_value
                    ;
                """, officer_params)
            except Exception as e:
                logger.exception(f"Failed to insert officer for {symbol}: {e}")
                # Continue with next officer, don't abort

        # 2b. governance_scores
        gov_scores = info.get("governanceScores") or {}
        if not isinstance(gov_scores, dict):
            gov_scores = {}
            
        comp_asof = info.get("compensationAsOfEpochDate")
        try:
            governance_params = [
                symbol,
                clean_value(safe_get(info, "auditRisk")),
                clean_value(safe_get(info, "boardRisk")),
                clean_value(safe_get(info, "compensationRisk")),
                clean_value(safe_get(info, "shareHolderRightsRisk")),
                clean_value(safe_get(info, "overallRisk")),
                clean_value(info.get("governanceEpochDate")),
                clean_value(comp_asof)
            ]
            
            cur.execute("""
                INSERT INTO governance_scores (
                    ticker, audit_risk, board_risk, compensation_risk, shareholder_rights_risk, overall_risk, governance_epoch_ms, comp_data_as_of_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    audit_risk=EXCLUDED.audit_risk, board_risk=EXCLUDED.board_risk, compensation_risk=EXCLUDED.compensation_risk, shareholder_rights_risk=EXCLUDED.shareholder_rights_risk, overall_risk=EXCLUDED.overall_risk, governance_epoch_ms=EXCLUDED.governance_epoch_ms, comp_data_as_of_ms=EXCLUDED.comp_data_as_of_ms
                ;
            """, governance_params)
            logger.debug(f"Inserted governance scores for {symbol}")
        except Exception as e:
            logger.exception(f"Failed to insert governance_scores for {symbol}: {e}")
            # Continue with other tables

        # 3. market_data
        try:
            market_params = [
                symbol,
                clean_value(info.get("previousClose")),
                clean_value(info.get("regularMarketPreviousClose")),
                clean_value(info.get("open")),
                clean_value(info.get("regularMarketOpen")),
                clean_value(info.get("dayLow")),
                clean_value(info.get("regularMarketDayLow")),
                clean_value(info.get("dayHigh")),
                clean_value(info.get("regularMarketDayHigh")),
                clean_value(info.get("regularMarketPrice")),
                clean_value(info.get("currentPrice")),
                clean_value(info.get("postMarketPrice")),
                clean_value(info.get("postMarketChange")),
                clean_value(info.get("postMarketChangePercent")),
                clean_value(info.get("volume")),
                clean_value(info.get("regularMarketVolume")),
                clean_value(info.get("averageVolume")),
                clean_value(info.get("averageVolume10days")),
                clean_value(info.get("averageDailyVolume10Day")),
                clean_value(info.get("averageDailyVolume3Month")),
                clean_value(info.get("bid")),
                clean_value(info.get("ask")),
                clean_value(info.get("bidSize")),
                clean_value(info.get("askSize")),
                clean_value(info.get("marketState")),
                clean_value(info.get("fiftyTwoWeekLow")),
                clean_value(info.get("fiftyTwoWeekHigh")),
                clean_value(info.get("fiftyTwoWeekRange")),
                clean_value(info.get("fiftyTwoWeekLowChange")),
                clean_value(info.get("fiftyTwoWeekLowChangePercent")),
                clean_value(info.get("fiftyTwoWeekHighChange")),
                clean_value(info.get("fiftyTwoWeekHighChangePercent")),
                clean_value(info.get("fiftyTwoWeekChangePercent")),
                clean_value(info.get("fiftyDayAverage")),
                clean_value(info.get("twoHundredDayAverage")),
                clean_value(info.get("fiftyDayAverageChange")),
                clean_value(info.get("fiftyDayAverageChangePercent")),
                clean_value(info.get("twoHundredDayAverageChange")),
                clean_value(info.get("twoHundredDayAverageChangePercent")),
                clean_value(info.get("sourceInterval")),
                clean_value(info.get("marketCap"))
            ]
            
            cur.execute("""
                INSERT INTO market_data (
                    ticker, previous_close, regular_market_previous_close, open_price, regular_market_open, day_low, regular_market_day_low, day_high, regular_market_day_high, regular_market_price, current_price, post_market_price, post_market_change, post_market_change_pct, volume, regular_market_volume, average_volume, avg_volume_10d, avg_daily_volume_10d, avg_daily_volume_3m, bid_price, ask_price, bid_size, ask_size, market_state, fifty_two_week_low, fifty_two_week_high, fifty_two_week_range, fifty_two_week_low_change, fifty_two_week_low_change_pct, fifty_two_week_high_change, fifty_two_week_high_change_pct, fifty_two_week_change_pct, fifty_day_avg, two_hundred_day_avg, fifty_day_avg_change, fifty_day_avg_change_pct, two_hundred_day_avg_change, two_hundred_day_avg_change_pct, source_interval_sec, market_cap
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    previous_close=EXCLUDED.previous_close, regular_market_previous_close=EXCLUDED.regular_market_previous_close, open_price=EXCLUDED.open_price, regular_market_open=EXCLUDED.regular_market_open, day_low=EXCLUDED.day_low, regular_market_day_low=EXCLUDED.regular_market_day_low, day_high=EXCLUDED.day_high, regular_market_day_high=EXCLUDED.regular_market_day_high, regular_market_price=EXCLUDED.regular_market_price, current_price=EXCLUDED.current_price, post_market_price=EXCLUDED.post_market_price, post_market_change=EXCLUDED.post_market_change, post_market_change_pct=EXCLUDED.post_market_change_pct, volume=EXCLUDED.volume, regular_market_volume=EXCLUDED.regular_market_volume, average_volume=EXCLUDED.average_volume, avg_volume_10d=EXCLUDED.avg_volume_10d, avg_daily_volume_10d=EXCLUDED.avg_daily_volume_10d, avg_daily_volume_3m=EXCLUDED.avg_daily_volume_3m, bid_price=EXCLUDED.bid_price, ask_price=EXCLUDED.ask_price, bid_size=EXCLUDED.bid_size, ask_size=EXCLUDED.ask_size, market_state=EXCLUDED.market_state, fifty_two_week_low=EXCLUDED.fifty_two_week_low, fifty_two_week_high=EXCLUDED.fifty_two_week_high, fifty_two_week_range=EXCLUDED.fifty_two_week_range, fifty_two_week_low_change=EXCLUDED.fifty_two_week_low_change, fifty_two_week_low_change_pct=EXCLUDED.fifty_two_week_low_change_pct, fifty_two_week_high_change=EXCLUDED.fifty_two_week_high_change, fifty_two_week_high_change_pct=EXCLUDED.fifty_two_week_high_change_pct, fifty_two_week_change_pct=EXCLUDED.fifty_two_week_change_pct, fifty_day_avg=EXCLUDED.fifty_day_avg, two_hundred_day_avg=EXCLUDED.two_hundred_day_avg, fifty_day_avg_change=EXCLUDED.fifty_day_avg_change, fifty_day_avg_change_pct=EXCLUDED.fifty_day_avg_change_pct, two_hundred_day_avg_change=EXCLUDED.two_hundred_day_avg_change, two_hundred_day_avg_change_pct=EXCLUDED.two_hundred_day_avg_change_pct, source_interval_sec=EXCLUDED.source_interval_sec, market_cap=EXCLUDED.market_cap
                ;
            """, market_params)
            logger.debug(f"Inserted market data for {symbol}")
        except Exception as e:
            logger.exception(f"Failed to insert market_data for {symbol}: {e}")

        # 4. key_metrics
        try:
            metrics_params = [
                symbol,
                clean_value(info.get("trailingPE")),
                clean_value(info.get("forwardPE")),
                clean_value(info.get("priceToSalesTrailing12Months")),
                clean_value(info.get("priceToBook")),
                clean_value(info.get("bookValue")),
                clean_value(info.get("trailingPegRatio")),
                clean_value(info.get("enterpriseValue")),
                clean_value(info.get("enterpriseToRevenue")),
                clean_value(info.get("enterpriseToEbitda")),
                clean_value(info.get("totalRevenue")),
                clean_value(info.get("netIncomeToCommon")),
                clean_value(info.get("ebitda")),
                clean_value(info.get("grossProfits")),
                clean_value(info.get("trailingEps")),
                clean_value(info.get("forwardEps")),
                clean_value(info.get("epsCurrentYear")),
                clean_value(info.get("priceEpsCurrentYear")),
                clean_value(info.get("earningsQuarterlyGrowth")),
                clean_value(info.get("earningsTimestamp")),
                clean_value(info.get("earningsTimestampStart")),
                clean_value(info.get("earningsTimestampEnd")),
                clean_value(info.get("earningsCallTimestampStart")),
                clean_value(info.get("earningsCallTimestampEnd")),
                clean_value(info.get("isEarningsDateEstimate")),
                clean_value(info.get("totalCash")),
                clean_value(info.get("totalCashPerShare")),
                clean_value(info.get("operatingCashflow")),
                clean_value(info.get("freeCashflow")),
                clean_value(info.get("totalDebt")),
                clean_value(info.get("debtToEquity")),
                clean_value(info.get("quickRatio")),
                clean_value(info.get("currentRatio")),
                clean_value(info.get("profitMargins")),
                clean_value(info.get("grossMargins")),
                clean_value(info.get("ebitdaMargins")),
                clean_value(info.get("operatingMargins")),
                clean_value(info.get("returnOnAssets")),
                clean_value(info.get("returnOnEquity")),
                clean_value(info.get("revenueGrowth")),
                clean_value(info.get("earningsGrowth")),
                clean_value(info.get("lastSplitFactor")),
                clean_value(info.get("lastSplitDate")),
                clean_value(info.get("dividendRate")),
                clean_value(info.get("dividendYield")),
                clean_value(info.get("fiveYearAvgDividendYield")),
                clean_value(info.get("exDividendDate")),
                clean_value(info.get("trailingAnnualDividendRate")),
                clean_value(info.get("trailingAnnualDividendYield")),
                clean_value(info.get("lastDividendValue")),
                clean_value(info.get("lastDividendDate")),
                clean_value(info.get("dividendDate")),
                clean_value(info.get("payoutRatio"))
            ]
            
            cur.execute("""
                INSERT INTO key_metrics (
                    ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, book_value, peg_ratio, enterprise_value, ev_to_revenue, ev_to_ebitda, total_revenue, net_income, ebitda, gross_profit, eps_trailing, eps_forward, eps_current_year, price_eps_current_year, earnings_q_growth_pct, earnings_ts_ms, earnings_ts_start_ms, earnings_ts_end_ms, earnings_call_ts_start_ms, earnings_call_ts_end_ms, is_earnings_date_estimate, total_cash, cash_per_share, operating_cashflow, free_cashflow, total_debt, debt_to_equity, quick_ratio, current_ratio, profit_margin_pct, gross_margin_pct, ebitda_margin_pct, operating_margin_pct, return_on_assets_pct, return_on_equity_pct, revenue_growth_pct, earnings_growth_pct, last_split_factor, last_split_date_ms, dividend_rate, dividend_yield, five_year_avg_dividend_yield, ex_dividend_date_ms, last_annual_dividend_amt, last_annual_dividend_yield, last_dividend_amt, last_dividend_date_ms, dividend_date_ms, payout_ratio
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    trailing_pe=EXCLUDED.trailing_pe, forward_pe=EXCLUDED.forward_pe, price_to_sales_ttm=EXCLUDED.price_to_sales_ttm, price_to_book=EXCLUDED.price_to_book, book_value=EXCLUDED.book_value, peg_ratio=EXCLUDED.peg_ratio, enterprise_value=EXCLUDED.enterprise_value, ev_to_revenue=EXCLUDED.ev_to_revenue, ev_to_ebitda=EXCLUDED.ev_to_ebitda, total_revenue=EXCLUDED.total_revenue, net_income=EXCLUDED.net_income, ebitda=EXCLUDED.ebitda, gross_profit=EXCLUDED.gross_profit, eps_trailing=EXCLUDED.eps_trailing, eps_forward=EXCLUDED.eps_forward, eps_current_year=EXCLUDED.eps_current_year, price_eps_current_year=EXCLUDED.price_eps_current_year, earnings_q_growth_pct=EXCLUDED.earnings_q_growth_pct, earnings_ts_ms=EXCLUDED.earnings_ts_ms, earnings_ts_start_ms=EXCLUDED.earnings_ts_start_ms, earnings_ts_end_ms=EXCLUDED.earnings_ts_end_ms, earnings_call_ts_start_ms=EXCLUDED.earnings_call_ts_start_ms, earnings_call_ts_end_ms=EXCLUDED.earnings_call_ts_end_ms, is_earnings_date_estimate=EXCLUDED.is_earnings_date_estimate, total_cash=EXCLUDED.total_cash, cash_per_share=EXCLUDED.cash_per_share, operating_cashflow=EXCLUDED.operating_cashflow, free_cashflow=EXCLUDED.free_cashflow, total_debt=EXCLUDED.total_debt, debt_to_equity=EXCLUDED.debt_to_equity, quick_ratio=EXCLUDED.quick_ratio, current_ratio=EXCLUDED.current_ratio, profit_margin_pct=EXCLUDED.profit_margin_pct, gross_margin_pct=EXCLUDED.gross_margin_pct, ebitda_margin_pct=EXCLUDED.ebitda_margin_pct, operating_margin_pct=EXCLUDED.operating_margin_pct, return_on_assets_pct=EXCLUDED.return_on_assets_pct, return_on_equity_pct=EXCLUDED.return_on_equity_pct, revenue_growth_pct=EXCLUDED.revenue_growth_pct, earnings_growth_pct=EXCLUDED.earnings_growth_pct, last_split_factor=EXCLUDED.last_split_factor, last_split_date_ms=EXCLUDED.last_split_date_ms, dividend_rate=EXCLUDED.dividend_rate, dividend_yield=EXCLUDED.dividend_yield, five_year_avg_dividend_yield=EXCLUDED.five_year_avg_dividend_yield, ex_dividend_date_ms=EXCLUDED.ex_dividend_date_ms, last_annual_dividend_amt=EXCLUDED.last_annual_dividend_amt, last_annual_dividend_yield=EXCLUDED.last_annual_dividend_yield, last_dividend_amt=EXCLUDED.last_dividend_amt, last_dividend_date_ms=EXCLUDED.last_dividend_date_ms, dividend_date_ms=EXCLUDED.dividend_date_ms, payout_ratio=EXCLUDED.payout_ratio
                ;
            """, metrics_params)
            logger.debug(f"Inserted key metrics for {symbol}")
        except Exception as e:
            logger.exception(f"Failed to insert key_metrics for {symbol}: {e}")

        # 5. analyst_estimates
        try:
            analyst_params = [
                symbol,
                clean_value(info.get("targetHighPrice")),
                clean_value(info.get("targetLowPrice")),
                clean_value(info.get("targetMeanPrice")),
                clean_value(info.get("targetMedianPrice")),
                clean_value(info.get("recommendationKey")),
                clean_value(info.get("recommendationMean")),
                clean_value(info.get("numberOfAnalystOpinions")),
                clean_value(info.get("averageAnalystRating"))
            ]
            
            cur.execute("""
                INSERT INTO analyst_estimates (
                    ticker, target_high_price, target_low_price, target_mean_price, target_median_price, recommendation_key, recommendation_mean, analyst_opinion_count, average_analyst_rating
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    target_high_price=EXCLUDED.target_high_price, target_low_price=EXCLUDED.target_low_price, target_mean_price=EXCLUDED.target_mean_price, target_median_price=EXCLUDED.target_median_price, recommendation_key=EXCLUDED.recommendation_key, recommendation_mean=EXCLUDED.recommendation_mean, analyst_opinion_count=EXCLUDED.analyst_opinion_count, average_analyst_rating=EXCLUDED.average_analyst_rating
                ;
            """, analyst_params)
            logger.debug(f"Inserted analyst estimates for {symbol}")
        except Exception as e:
            logger.exception(f"Failed to insert analyst_estimates for {symbol}: {e}")

    conn.commit()
    logger.info(f"Successfully processed info for {symbol}")

def main():
    import gc
    user, pwd, host, port, dbname = get_db_config()
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=pwd,
        dbname=dbname,
        sslmode="require",
        cursor_factory=DictCursor
    )

    logger.info("Dropping and creating all info tables before data load...")
    ensure_tables(conn)
    logger.info("Table creation complete.")

    log_mem("Before fetching symbols")
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
        symbols = [r["symbol"] for r in cur.fetchall()]
    log_mem("After fetching symbols")

    total_symbols = len(symbols)
    processed = 0
    failed = 0

    for sym in symbols:
        try:
            log_mem(f"Before processing {sym} ({processed + 1}/{total_symbols})")
            process_symbol(sym, conn)
            conn.commit()
            processed += 1
            gc.collect()
            if get_rss_mb() > 800:
                time.sleep(0.5)
            else:
                time.sleep(0.05)
            log_mem(f"After processing {sym}")
        except Exception:
            logger.exception(f"Failed to process {sym}")
            failed += 1
            if failed > total_symbols * 0.2:
                logger.error("Too many failures, stopping process")
                break

    update_last_run(conn)
    try:
        conn.close()
    except Exception:
        logger.exception("Error closing database connection")
    log_mem("End of script")
    logger.info("loadinfo complete.")

if __name__ == "__main__":
    main()
