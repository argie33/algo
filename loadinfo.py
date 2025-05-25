#!/usr/bin/env python3 
import sys
import os
import time
import json
import math
import gc
import logging
import functools
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd

SCRIPT_NAME = "loadinfo.py"

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# ─── SecretsManager DB config ────────────────────────────────────────────────
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

# ─── Memory logging ─────────────────────────────────────────────────────────
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return (usage/1024) if sys.platform.startswith("linux") else (usage/(1024*1024))

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# ─── Clean NaN/None ─────────────────────────────────────────────────────────
def clean_value(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if pd.isna(v):
        return None
    return v

def safe_get(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d

# ─── Create tables ──────────────────────────────────────────────────────────
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
    role_source VARCHAR(50),
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
    last_run    TIMESTAMPTZ NOT NULL
);
""")
    conn.commit()

def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW());
        """, (SCRIPT_NAME,))
    conn.commit()

# ─── Retry decorator ───────────────────────────────────────────────────────────
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(symbol, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                attempts += 1
                try:
                    user,pwd,host,port,db = get_db_config()
                    conn = psycopg2.connect(
                        host=host, port=port,
                        user=user, password=pwd,
                        dbname=db, sslmode="require",
                        cursor_factory=DictCursor
                    )
                    res = fn(symbol, conn, *args, **kwargs)
                    conn.close()
                    return res
                except Exception as e:
                    logger.error(f"{fn.__name__}({symbol}) attempt {attempts}: {e}", exc_info=True)
                    time.sleep(delay)
                    delay *= backoff
            raise RuntimeError(f"All {max_attempts} attempts failed for {symbol}")
        return wrapper
    return deco

# ─── Core loader ──────────────────────────────────────────────────────────────
@retry()
def process_symbol(symbol, conn):
    yf_sym = symbol.upper().replace(".", "-")
    logger.info(f"→ {symbol} (YF={yf_sym})")
    try:
        info = yf.Ticker(yf_sym).get_info() or {}
    except Exception as e:
        logger.warning(f"yfinance.get_info() failed: {e}")
        info = {}

    def jdump(v):
        try: return json.dumps(v) if v is not None else None
        except: return None

    with conn.cursor() as cur:
        # 1) company_profile
        params = [
            symbol,
            clean_value(info.get("shortName")), clean_value(info.get("longName")),
            clean_value(info.get("displayName")), clean_value(info.get("quoteType")),
            clean_value(info.get("typeDisp")), clean_value(info.get("triggerable")),
            clean_value(info.get("hasPrePostMarketData")), clean_value(info.get("priceHint")),
            clean_value(info.get("maxAge")), clean_value(info.get("language")),
            clean_value(info.get("region")), clean_value(info.get("financialCurrency")),
            clean_value(info.get("currency")), clean_value(info.get("market")),
            clean_value(info.get("quoteSourceName")), clean_value(info.get("customPriceAlertConfidence")),
            clean_value(info.get("address1")), clean_value(info.get("city")),
            clean_value(info.get("state")), clean_value(info.get("zip")),
            clean_value(info.get("country")), clean_value(info.get("phone")),
            clean_value(info.get("website")), clean_value(info.get("irWebsite")),
            clean_value(info.get("messageBoardId")), jdump(info.get("corporateActions")),
            clean_value(info.get("sector")), clean_value(info.get("sectorKey")),
            clean_value(info.get("sectorDisp")), clean_value(info.get("industry")),
            clean_value(info.get("industryKey")), clean_value(info.get("industryDisp")),
            clean_value(info.get("longBusinessSummary")), clean_value(info.get("fullTimeEmployees")),
            clean_value(info.get("firstTradeDateMilliseconds")), clean_value(info.get("gmtOffSetMilliseconds")),
            clean_value(info.get("exchange")), clean_value(info.get("fullExchangeName")),
            clean_value(info.get("exchangeTimezoneName")), clean_value(info.get("exchangeTimezoneShortName")),
            clean_value(info.get("exchangeDataDelayedBy")), clean_value(info.get("postMarketTime")),
            clean_value(info.get("regularMarketTime"))
        ]
        cur.execute(f"""
INSERT INTO company_profile (
    ticker, short_name, long_name, display_name, quote_type, symbol_type,
    triggerable, has_pre_post_market_data, price_hint, max_age_sec,
    language, region, financial_currency, currency, market, quote_source_name,
    custom_price_alert_confidence, address1, city, state, postal_code, country,
    phone_number, website_url, ir_website_url, message_board_id, corporate_actions,
    sector, sector_key, sector_disp, industry, industry_key, industry_disp,
    business_summary, employee_count, first_trade_date_ms, gmt_offset_ms,
    exchange, full_exchange_name, exchange_timezone_name,
    exchange_timezone_short_name, exchange_data_delayed_by_sec,
    post_market_time_ms, regular_market_time_ms
) VALUES ({','.join(['%s']*len(params))});
""", params)

        # 2a) leadership_team
        for off in info.get("companyOfficers") or []:
            if not isinstance(off, dict) or not off.get("name"):
                continue
            oparams = [
                symbol,
                clean_value(off.get("name")),
                clean_value(off.get("age")),
                clean_value(off.get("title")),
                clean_value(off.get("yearBorn")),
                clean_value(off.get("fiscalYear")),
                clean_value(off.get("totalPay")),
                clean_value(off.get("exercisedValue")),
                clean_value(off.get("unexercisedValue")),
                "companyOfficer"
            ]
            cur.execute("""
INSERT INTO leadership_team (
    ticker, person_name, age, title, birth_year, fiscal_year,
    total_pay, exercised_value, unexercised_value, role_source
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
""", oparams)

        # 2b) governance_scores
        gs = info.get("governanceScores") or {}
        gparams = [
            symbol,
            clean_value(safe_get(gs, "auditRisk")),
            clean_value(safe_get(gs, "boardRisk")),
            clean_value(safe_get(gs, "compensationRisk")),
            clean_value(safe_get(gs, "shareHolderRightsRisk")),
            clean_value(safe_get(gs, "overallRisk")),
            clean_value(info.get("governanceEpochDate")),
            clean_value(info.get("compensationAsOfEpochDate"))
        ]
        cur.execute("""
INSERT INTO governance_scores (
    ticker, audit_risk, board_risk, compensation_risk,
    shareholder_rights_risk, overall_risk, governance_epoch_ms,
    comp_data_as_of_ms
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
""", gparams)

        # 3) market_data
        m = info
        mparams = [
            symbol,
            clean_value(m.get("previousClose")),
            clean_value(m.get("regularMarketPreviousClose")),
            clean_value(m.get("open")),
            clean_value(m.get("regularMarketOpen")),
            clean_value(m.get("dayLow")),
            clean_value(m.get("regularMarketDayLow")),
            clean_value(m.get("dayHigh")),
            clean_value(m.get("regularMarketDayHigh")),
            clean_value(m.get("regularMarketPrice")),
            clean_value(m.get("currentPrice")),
            clean_value(m.get("postMarketPrice")),
            clean_value(m.get("postMarketChange")),
            clean_value(m.get("postMarketChangePercent")),
            clean_value(m.get("volume")),
            clean_value(m.get("regularMarketVolume")),
            clean_value(m.get("averageVolume")),
            clean_value(m.get("averageVolume10days")),
            clean_value(m.get("averageDailyVolume10Day")),
            clean_value(m.get("averageDailyVolume3Month")),
            clean_value(m.get("bid")),
            clean_value(m.get("ask")),
            clean_value(m.get("bidSize")),
            clean_value(m.get("askSize")),
            clean_value(m.get("marketState")),
            clean_value(m.get("fiftyTwoWeekLow")),
            clean_value(m.get("fiftyTwoWeekHigh")),
            clean_value(m.get("fiftyTwoWeekRange")),
            clean_value(m.get("fiftyTwoWeekLowChange")),
            clean_value(m.get("fiftyTwoWeekLowChangePercent")),
            clean_value(m.get("fiftyTwoWeekHighChange")),
            clean_value(m.get("fiftyTwoWeekHighChangePercent")),
            clean_value(m.get("fiftyTwoWeekChangePercent")),
            clean_value(m.get("fiftyDayAverage")),
            clean_value(m.get("twoHundredDayAverage")),
            clean_value(m.get("fiftyDayAverageChange")),
            clean_value(m.get("fiftyDayAverageChangePercent")),
            clean_value(m.get("twoHundredDayAverageChange")),
            clean_value(m.get("twoHundredDayAverageChangePercent")),
            clean_value(m.get("sourceInterval")),
            clean_value(m.get("marketCap"))
        ]
        cur.execute(f"""
INSERT INTO market_data (
    ticker, previous_close, regular_market_previous_close, open_price,
    regular_market_open, day_low, regular_market_day_low, day_high,
    regular_market_day_high, regular_market_price, current_price,
    post_market_price, post_market_change, post_market_change_pct,
    volume, regular_market_volume, average_volume, avg_volume_10d,
    avg_daily_volume_10d, avg_daily_volume_3m, bid_price, ask_price,
    bid_size, ask_size, market_state, fifty_two_week_low,
    fifty_two_week_high, fifty_two_week_range,
    fifty_two_week_low_change, fifty_two_week_low_change_pct,
    fifty_two_week_high_change, fifty_two_week_high_change_pct,
    fifty_two_week_change_pct, fifty_day_avg, two_hundred_day_avg,
    fifty_day_avg_change, fifty_day_avg_change_pct,
    two_hundred_day_avg_change, two_hundred_day_avg_change_pct,
    source_interval_sec, market_cap
) VALUES ({','.join(['%s']*len(mparams))});
""", mparams)

        # 4) key_metrics
        km = info
        kparams = [
            symbol,
            clean_value(km.get("trailingPE")), clean_value(km.get("forwardPE")),
            clean_value(km.get("priceToSalesTrailing12Months")),
            clean_value(km.get("priceToBook")), clean_value(km.get("bookValue")),
            clean_value(km.get("trailingPegRatio")), clean_value(km.get("enterpriseValue")),
            clean_value(km.get("enterpriseToRevenue")), clean_value(km.get("enterpriseToEbitda")),
            clean_value(km.get("totalRevenue")), clean_value(km.get("netIncomeToCommon")),
            clean_value(km.get("ebitda")), clean_value(km.get("grossProfits")),
            clean_value(km.get("trailingEps")), clean_value(km.get("forwardEps")),
            clean_value(km.get("epsCurrentYear")), clean_value(km.get("priceEpsCurrentYear")),
            clean_value(km.get("earningsQuarterlyGrowth")),
            clean_value(km.get("earningsTimestamp")), clean_value(km.get("earningsTimestampStart")),
            clean_value(km.get("earningsTimestampEnd")),
            clean_value(km.get("earningsCallTimestampStart")), clean_value(km.get("earningsCallTimestampEnd")),
            clean_value(km.get("isEarningsDateEstimate")), clean_value(km.get("totalCash")),
            clean_value(km.get("totalCashPerShare")), clean_value(km.get("operatingCashflow")),
            clean_value(km.get("freeCashflow")), clean_value(km.get("totalDebt")),
            clean_value(km.get("debtToEquity")), clean_value(km.get("quickRatio")),
            clean_value(km.get("currentRatio")), clean_value(km.get("profitMargins")),
            clean_value(km.get("grossMargins")), clean_value(km.get("ebitdaMargins")),
            clean_value(km.get("operatingMargins")), clean_value(km.get("returnOnAssets")),
            clean_value(km.get("returnOnEquity")), clean_value(km.get("revenueGrowth")),
            clean_value(km.get("earningsGrowth")), clean_value(km.get("lastSplitFactor")),
            clean_value(km.get("lastSplitDate")), clean_value(km.get("dividendRate")),
            clean_value(km.get("dividendYield")), clean_value(km.get("fiveYearAvgDividendYield")),
            clean_value(km.get("exDividendDate")), clean_value(km.get("trailingAnnualDividendRate")),
            clean_value(km.get("trailingAnnualDividendYield")), clean_value(km.get("lastDividendValue")),
            clean_value(km.get("lastDividendDate")), clean_value(km.get("dividendDate")),
            clean_value(km.get("payoutRatio"))
        ]
        cur.execute(f"""
INSERT INTO key_metrics (
    ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book,
    book_value, peg_ratio, enterprise_value, ev_to_revenue, ev_to_ebitda,
    total_revenue, net_income, ebitda, gross_profit, eps_trailing,
    eps_forward, eps_current_year, price_eps_current_year,
    earnings_q_growth_pct, earnings_ts_ms, earnings_ts_start_ms,
    earnings_ts_end_ms, earnings_call_ts_start_ms, earnings_call_ts_end_ms,
    is_earnings_date_estimate, total_cash, cash_per_share, operating_cashflow,
    free_cashflow, total_debt, debt_to_equity, quick_ratio, current_ratio,
    profit_margin_pct, gross_margin_pct, ebitda_margin_pct,
    operating_margin_pct, return_on_assets_pct, return_on_equity_pct,
    revenue_growth_pct, earnings_growth_pct, last_split_factor,
    last_split_date_ms, dividend_rate, dividend_yield,
    five_year_avg_dividend_yield, ex_dividend_date_ms,
    trailing_annual_dividend_rate, trailing_annual_dividend_yield,
    last_dividend_value, last_dividend_date, dividend_date, payout_ratio
) VALUES ({','.join(['%s']*len(kparams))});
""", kparams)

        # 5) analyst_estimates
        ae = info
        aparams = [
            symbol,
            clean_value(ae.get("targetHighPrice")), clean_value(ae.get("targetLowPrice")),
            clean_value(ae.get("targetMeanPrice")), clean_value(ae.get("targetMedianPrice")),
            clean_value(ae.get("recommendationKey")), clean_value(ae.get("recommendationMean")),
            clean_value(ae.get("numberOfAnalystOpinions")), clean_value(ae.get("averageAnalystRating"))
        ]
        cur.execute("""
INSERT INTO analyst_estimates (
    ticker, target_high_price, target_low_price, target_mean_price,
    target_median_price, recommendation_key, recommendation_mean,
    analyst_opinion_count, average_analyst_rating
) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s);
""", aparams)

    conn.commit()
    logger.info(f"✔ done {symbol}")

# ─── Entrypoint ──────────────────────────────────────────────────────────────
def main():
    user,pwd,host,port,db = get_db_config()
    # 1) rebuild schema
    logger.info("Rebuilding tables…")
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd,
        dbname=db, sslmode="require", cursor_factory=DictCursor
    )
    ensure_tables(conn)
    conn.close()

    # 2) load symbols
    user,pwd,host,port,db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd,
        dbname=db, sslmode="require", cursor_factory=DictCursor
    )
    cur = conn.cursor(name="symbol_cursor")
    cur.itersize = 50
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols;")
    log_mem("symbols-opened")

    for row in cur:
        sym = row[0]
        log_mem(f"before-{sym}")
        try:
            process_symbol(sym)
        except Exception:
            logger.exception(f"✗ failed {sym}")
        gc.collect()
        time.sleep(0.05)
        log_mem(f"after-{sym}")

    cur.close()
    conn.close()

    # 3) record last run
    user,pwd,host,port,db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd,
        dbname=db, sslmode="require", cursor_factory=DictCursor
    )
    update_last_run(conn)
    conn.close()
    log_mem("complete")

if __name__ == "__main__":
    main()
