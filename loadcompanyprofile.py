#!/usr/bin/env python3
"""
Unified Company & Market Data Loader - Loads stock tickers from Yahoo Finance
Replaces deprecated loadinfo.py
Loads BOTH company_profile and market_data tables for all 5,315 stocks
Ensures data consistency by populating both from same yfinance API call
"""

import sys
import logging
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
import signal
from contextlib import contextmanager

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Suppress verbose yfinance logging
logging.getLogger('yfinance').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("API call timed out")

@contextmanager
def time_limit(seconds, symbol=""):
    """Context manager to limit execution time with timeout"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)  # Disable alarm

def get_db_connection():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def load_company_profile(symbols, cur, conn):
    """Load company profile data for all symbols from Yahoo Finance with aggressive rate limiting"""
    total = len(symbols)
    logger.info(f"Loading company profile data for {total} symbols")
    logger.info(f"Rate limiting: 1.5 second delay between symbols to avoid API timeouts")
    processed = 0
    failed = []

    # Use per-symbol processing with aggressive rate limiting (NOT batching)
    # This prevents yfinance API rate limiting that causes timeouts
    RATE_LIMIT_DELAY = 1.5

    for idx, orig_sym in enumerate(symbols, 1):
        yq_sym = orig_sym.replace('.', '-').replace('$', '-').upper()

        if idx % 50 == 0:
            logger.info(f"Processing {idx}/{total} symbols...")
        else:
            logger.debug(f"[{idx}/{total}] {orig_sym}")

        info = None
        for attempt in range(1, 4):
            try:
                logger.debug(f"[{idx}] Fetching yfinance data for {orig_sym}...")
                with time_limit(10, orig_sym):  # 10 second timeout per API call
                    ticker = yf.Ticker(yq_sym)
                    info = ticker.info
                if not info:
                    raise ValueError("No info data received")
                logger.debug(f"[{idx}] ✅ Got data for {orig_sym}")
                break
            except TimeoutException:
                logger.warning(f"[{idx}] TIMEOUT on {orig_sym} (attempt {attempt}/3)")
                if attempt == 3:
                    failed.append(orig_sym)
                else:
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"[{idx}] Attempt {attempt}/3 for {orig_sym}: {str(e)[:60]}")
                if attempt == 3:
                    failed.append(orig_sym)
                else:
                    time.sleep(0.5)  # Wait before retry

        if info is None:
            logger.error(f"[{idx}] ❌ Failed to get info for {orig_sym} after 3 retries")
            time.sleep(RATE_LIMIT_DELAY)
            continue

        try:
            # Insert into company_profile table - 44 fields
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
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (ticker) DO UPDATE SET
                    short_name = EXCLUDED.short_name,
                    long_name = EXCLUDED.long_name,
                    sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry
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
                info.get('messageBoardId'), None,
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

            # Also insert into market_data table from same API call
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
                    two_hundred_day_avg_change_pct, source_interval_sec, market_cap
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                         %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                         %s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (ticker) DO UPDATE SET
                    previous_close = EXCLUDED.previous_close,
                    regular_market_previous_close = EXCLUDED.regular_market_previous_close,
                    open_price = EXCLUDED.open_price,
                    regular_market_open = EXCLUDED.regular_market_open,
                    day_low = EXCLUDED.day_low,
                    regular_market_day_low = EXCLUDED.regular_market_day_low,
                    day_high = EXCLUDED.day_high,
                    regular_market_day_high = EXCLUDED.regular_market_day_high,
                    regular_market_price = EXCLUDED.regular_market_price,
                    current_price = EXCLUDED.current_price,
                    post_market_price = EXCLUDED.post_market_price,
                    post_market_change = EXCLUDED.post_market_change,
                    post_market_change_pct = EXCLUDED.post_market_change_pct,
                    volume = EXCLUDED.volume,
                    regular_market_volume = EXCLUDED.regular_market_volume,
                    average_volume = EXCLUDED.average_volume,
                    market_cap = EXCLUDED.market_cap
            """, (
                orig_sym,
                info.get('previousClose'), info.get('regularMarketPreviousClose'),
                info.get('open'), info.get('regularMarketOpen'),
                info.get('dayLow'), info.get('regularMarketDayLow'),
                info.get('dayHigh'), info.get('regularMarketDayHigh'),
                info.get('regularMarketPrice'), info.get('currentPrice'),
                info.get('postMarketPrice'), info.get('postMarketChange'),
                info.get('postMarketChangePercent'), info.get('volume'),
                info.get('regularMarketVolume'), info.get('averageVolume'),
                info.get('averageVolume10days'),
                info.get('averageDailyVolume10Day'),
                info.get('averageDailyVolume3Month'),
                info.get('bid'), info.get('ask'),
                info.get('bidSize'), info.get('askSize'),
                info.get('marketState'),
                info.get('fiftyTwoWeekLow'), info.get('fiftyTwoWeekHigh'),
                info.get('fiftyTwoWeekRange'),
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
                info.get('sourceInterval'), info.get('marketCap')
            ))

            conn.commit()
            processed += 1
            if processed % 100 == 0:
                logger.info(f"✅ Processed {processed}/{total} symbols")

        except Exception as e:
            logger.error(f"Failed to process {orig_sym}: {str(e)}")
            failed.append(orig_sym)
            conn.rollback()

        time.sleep(RATE_LIMIT_DELAY)

    return total, processed, failed

# Main execution
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 UNIFIED COMPANY & MARKET DATA LOADER")
    logger.info("=" * 60)
    logger.info("Loading both company_profile and market_data for all stocks")

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Load stock symbols only (5,315 stocks)
        logger.info("Querying stock symbols...")
        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Found {len(stock_syms)} stock symbols to load")

        # Load company profile for all stocks
        t_s, p_s, f_s = load_company_profile(stock_syms, cur, conn)

        # Summary
        logger.info("=" * 60)
        logger.info(f"✅ LOADING COMPLETE")
        logger.info(f"Total symbols: {t_s}")
        logger.info(f"Successfully processed: {p_s}")
        logger.info(f"Failed: {len(f_s)}")
        if p_s > 0:
            logger.info(f"Success rate: {(p_s / t_s) * 100:.1f}%")
        logger.info("=" * 60)

        cur.close()
        conn.close()

        if len(f_s) > 0:
            logger.info(f"Failed symbols: {f_s[:10]}..." if len(f_s) > 10 else f"Failed symbols: {f_s}")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
