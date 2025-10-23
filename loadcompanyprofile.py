#!/usr/bin/env python3
"""
Unified Company Profile Loader - Loads stock tickers from Yahoo Finance
Replaces deprecated loadinfo.py
Loads ONLY company_profile table with core data for all 5,315 stocks
"""

import sys
import logging
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

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

        if idx % 100 == 0:
            logger.info(f"Processing {idx}/{total} symbols...")

        info = None
        for attempt in range(1, 4):
            try:
                ticker = yf.Ticker(yq_sym)
                info = ticker.info
                if not info:
                    raise ValueError("No info data received")
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt}/3 for {orig_sym}: {str(e)[:60]}")
                if attempt == 3:
                    failed.append(orig_sym)
                else:
                    time.sleep(0.5)  # Wait before retry

        if info is None:
            logger.error(f"Failed to get info for {orig_sym} after 3 retries, skipping")
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
    logger.info("🚀 UNIFIED COMPANY PROFILE LOADER - STOCKS ONLY")
    logger.info("=" * 60)

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
