#!/usr/bin/env python3
# Stock info loader - fetches company information and metadata
# Enhanced data collection for comprehensive stock information analysis
# Trigger deploy-app-stocks workflow test - loadinfo update v4 - deployment trigger test
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadinfo.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def load_company_info(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading company info for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for yq_sym, orig_sym in mapping.items():
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    info = ticker.info
                    if not info:
                        raise ValueError("No info data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        continue
                    time.sleep(RETRY_DELAY)
            
            try:
                # Insert into company_profile
                cur.execute("""
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
                """, (
                    orig_sym, info.get('shortName'), info.get('longName'),
                    info.get('displayName'), info.get('quoteType'),
                    info.get('symbolType'), info.get('triggerable'),
                    info.get('hasPrePostMarketData'), info.get('priceHint'),
                    info.get('maxAge'), info.get('language'), info.get('region'),
                    info.get('financialCurrency'), info.get('currency'),
                    info.get('market'), info.get('quoteSourceName'),
                    info.get('customPriceAlertConfidence'),
                    info.get('address1'), info.get('city'), info.get('state'),
                    info.get('zip'), info.get('country'), info.get('phone'),
                    info.get('website'), info.get('irWebsite'),
                    info.get('messageBoardId'), json.dumps(info.get('corporateActions', {})),
                    info.get('sector'), info.get('sectorKey'),
                    info.get('sectorDisp'), info.get('industry'),
                    info.get('industryKey'), info.get('industryDisp'),
                    info.get('longBusinessSummary'), info.get('fullTimeEmployees'),
                    info.get('firstTradeDateEpochUtc'), info.get('gmtOffSetMilliseconds'),
                    info.get('exchange'), info.get('fullExchangeName'),
                    info.get('exchangeTimezoneName'),
                    info.get('exchangeTimezoneShortName'),
                    info.get('exchangeDataDelayedBy'),
                    info.get('postMarketTime'), info.get('regularMarketTime')
                ))

                # Insert leadership team data
                if 'companyOfficers' in info:
                    officers_data = []
                    for officer in info['companyOfficers']:
                        officers_data.append((
                            orig_sym,
                            officer.get('name'),
                            officer.get('age'),
                            officer.get('title'),
                            officer.get('yearBorn'),
                            officer.get('fiscalYear'),
                            officer.get('totalPay'),
                            officer.get('exercisedValue'),
                            officer.get('unexercisedValue'),
                            'yahoo'  # role_source
                        ))
                    
                    if officers_data:
                        execute_values(cur, """
                            INSERT INTO leadership_team (
                                ticker, person_name, age, title, birth_year,
                                fiscal_year, total_pay, exercised_value,
                                unexercised_value, role_source
                            ) VALUES %s
                            ON CONFLICT (ticker, person_name, role_source) DO UPDATE SET
                                age = EXCLUDED.age,
                                title = EXCLUDED.title,
                                total_pay = EXCLUDED.total_pay
                        """, officers_data)

                # Insert governance scores
                if any(k in info for k in ['auditRisk', 'boardRisk', 'compensationRisk']):
                    cur.execute("""
                        INSERT INTO governance_scores (
                            ticker, audit_risk, board_risk, compensation_risk,
                            shareholder_rights_risk, overall_risk,
                            governance_epoch_ms, comp_data_as_of_ms
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (ticker) DO UPDATE SET
                            audit_risk = EXCLUDED.audit_risk,
                            board_risk = EXCLUDED.board_risk,
                            compensation_risk = EXCLUDED.compensation_risk
                    """, (
                        orig_sym, info.get('auditRisk'), info.get('boardRisk'),
                        info.get('compensationRisk'),
                        info.get('shareHolderRightsRisk'),
                        info.get('overallRisk'),
                        info.get('governanceEpochDate'),
                        info.get('compensationAsOfDate')
                    ))

                # Insert market data
                cur.execute("""
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
                """, (
                    orig_sym, info.get('previousClose'),
                    info.get('regularMarketPreviousClose'),
                    info.get('open'), info.get('regularMarketOpen'),
                    info.get('dayLow'), info.get('regularMarketDayLow'),
                    info.get('dayHigh'), info.get('regularMarketDayHigh'),
                    info.get('regularMarketPrice'), info.get('currentPrice'),
                    info.get('postMarketPrice'), info.get('postMarketChange'),
                    info.get('postMarketChangePercent'), info.get('volume'),
                    info.get('regularMarketVolume'),
                    info.get('averageVolume'), info.get('averageVolume10days'),
                    info.get('averageDailyVolume10Day'),
                    info.get('averageDailyVolume3Month'),
                    info.get('bid'), info.get('ask'),
                    info.get('bidSize'), info.get('askSize'),
                    info.get('marketState'), info.get('fiftyTwoWeekLow'),
                    info.get('fiftyTwoWeekHigh'),
                    f"{info.get('fiftyTwoWeekLow')} - {info.get('fiftyTwoWeekHigh')}",
                    info.get('fiftyTwoWeekLowChange'),
                    info.get('fiftyTwoWeekLowChangePercent'),
                    info.get('fiftyTwoWeekHighChange'),
                    info.get('fiftyTwoWeekHighChangePercent'),
                    info.get('fiftyTwoWeekChangePercent'),
                    info.get('fiftyDayAverage'),
                    info.get('twoHundredDayAverage'),
                    info.get('fiftyDayAverageChange'),
                    info.get('fiftyDayAverageChangePercent'),
                    info.get('twoHundredDayAverageChange'),
                    info.get('twoHundredDayAverageChangePercent'),
                    info.get('sourceInterval'),
                    info.get('marketCap')
                ))

                # Insert key metrics
                cur.execute("""
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
                        dividend_date_ms, payout_ratio
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        trailing_pe = EXCLUDED.trailing_pe,
                        forward_pe = EXCLUDED.forward_pe,
                        eps_trailing = EXCLUDED.eps_trailing
                """, (
                    orig_sym, info.get('trailingPE'), info.get('forwardPE'),
                    info.get('priceToSalesTrailing12Months'),
                    info.get('priceToBook'), info.get('bookValue'),
                    info.get('pegRatio'), info.get('enterpriseValue'),
                    info.get('enterpriseToRevenue'),
                    info.get('enterpriseToEbitda'),
                    info.get('totalRevenue'), info.get('netIncomeToCommon'),
                    info.get('ebitda'), info.get('grossProfits'),
                    info.get('trailingEps'), info.get('forwardEps'),
                    info.get('currentYear'), info.get('priceEpsCurrentYear'),
                    info.get('earningsQuarterlyGrowth'),
                    info.get('earningsTimestamp'),
                    info.get('earningsTimestampStart'),
                    info.get('earningsTimestampEnd'),
                    info.get('earningsCallTimeStampStart'),
                    info.get('earningsCallTimeStampEnd'),
                    info.get('earningsDateIsEstimate'),
                    info.get('totalCash'), info.get('totalCashPerShare'),
                    info.get('operatingCashflow'),
                    info.get('freeCashflow'), info.get('totalDebt'),
                    info.get('debtToEquity'), info.get('quickRatio'),
                    info.get('currentRatio'), info.get('profitMargins'),
                    info.get('grossMargins'), info.get('ebitdaMargins'),
                    info.get('operatingMargins'),
                    info.get('returnOnAssets'), info.get('returnOnEquity'),
                    info.get('revenueGrowth'),
                    info.get('earningsGrowth'),
                    info.get('lastSplitFactor'),
                    info.get('lastSplitDate'), info.get('dividendRate'),
                    info.get('dividendYield'),
                    info.get('fiveYearAvgDividendYield'),
                    info.get('exDividendDate'),
                    info.get('lastAnnualDividendAmt'),
                    info.get('lastAnnualDividendYield'),
                    info.get('lastDividendValue'),
                    info.get('lastDividendDate'),
                    info.get('dividendDate'), info.get('payoutRatio')
                ))

                # Prepare averageAnalystRating
                raw_avg_rating = info.get('averageAnalystRating')
                parsed_avg_rating = None
                if isinstance(raw_avg_rating, (int, float)):
                    parsed_avg_rating = raw_avg_rating
                elif isinstance(raw_avg_rating, str):
                    try:
                        # Attempt to convert the first part of the string to a float
                        # Handles cases like "2.3 - Buy" or just "2.3" if it's a string
                        parsed_avg_rating = float(raw_avg_rating.split(' - ')[0])
                    except (ValueError, IndexError):
                        logging.warning(
                            f"Could not parse averageAnalystRating '{raw_avg_rating}' for {orig_sym}. Setting to NULL."
                        )
                        # parsed_avg_rating remains None if parsing fails
                elif raw_avg_rating is not None: # Catch other unexpected types
                    logging.warning(
                        f"Unexpected type for averageAnalystRating for {orig_sym}: {type(raw_avg_rating)}, value: '{raw_avg_rating}'. Setting to NULL."
                    )
                    # parsed_avg_rating remains None
                # If raw_avg_rating is None, parsed_avg_rating is already None

                # Insert analyst estimates
                cur.execute("""
                    INSERT INTO analyst_estimates (
                        ticker, target_high_price, target_low_price,
                        target_mean_price, target_median_price,
                        recommendation_key, recommendation_mean,
                        analyst_opinion_count, average_analyst_rating
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        target_mean_price = EXCLUDED.target_mean_price,
                        recommendation_key = EXCLUDED.recommendation_key
                """, (
                    orig_sym, info.get('targetHighPrice'),
                    info.get('targetLowPrice'), info.get('targetMeanPrice'),
                    info.get('targetMedianPrice'),
                    info.get('recommendationKey'),
                    info.get('recommendationMean'),
                    info.get('numberOfAnalystOpinions'),
                    parsed_avg_rating # Use the parsed value here
                ))

                conn.commit()
                processed += 1
                logging.info(f"Successfully processed {orig_sym}")

            except Exception as e:
                logging.error(f"Failed to process {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()

        del batch, yq_batch, mapping
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    logging.info("🎯 LOADINFO DEPLOYMENT TEST - Starting script execution")
    logging.info(f"📅 Deployment timestamp: {datetime.now().isoformat()}")
    logging.info("🔄 This is loadinfo update v2 - deployment trigger test")
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Recreate tables
    logging.info("Recreating company info tables...")
    cur.execute("""
        DROP TABLE IF EXISTS analyst_estimates CASCADE;
        DROP TABLE IF EXISTS key_metrics CASCADE;
        DROP TABLE IF EXISTS market_data CASCADE;
        DROP TABLE IF EXISTS governance_scores CASCADE;
        DROP TABLE IF EXISTS leadership_team CASCADE;
        DROP TABLE IF EXISTS company_profile CASCADE;
    """)

    # Create tables in correct order (company_profile first as it's referenced by others)
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

    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_company_info(stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_company_info(etf_syms, cur, conn)

    # Record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("✅ LOADINFO DEPLOYMENT TEST - All done! This confirms the deployment system is working.")
    logging.info(f"🚀 Deployment successful - Script version: loadinfo update v2")
    logging.info("📊 Company information processing completed successfully.")