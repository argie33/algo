#!/usr/bin/env python3
"""
Simplified Company Profile Loader
Loads ONLY company_profile table (core data) to quickly populate 9,896 symbols
Optional tables (leadership, governance, market_data, key_metrics, analyst_estimates) can be added later
"""

import logging
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
import time

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

# Database configuration from environment
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def load_company_info(symbols, cur, conn):
    """Load company info for symbols - SIMPLIFIED VERSION (company_profile only)"""
    total = len(symbols)
    logger.info(f"Loading company info for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logger.info(f"Processing batch {batch_idx+1}/{batches} ({len(batch)} symbols)")

        for yq_sym, orig_sym in mapping.items():
            info = None
            for attempt in range(1, 4):
                try:
                    ticker = yf.Ticker(yq_sym)
                    info = ticker.info
                    if not info:
                        raise ValueError("No info data received")
                    break
                except Exception as e:
                    logger.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == 3:
                        failed.append(orig_sym)
                        break
                    time.sleep(0.2)

            if info is None:
                logger.error(f"Failed to get info for {orig_sym} after all retries, skipping")
                continue

            try:
                # Insert ONLY company_profile (simplified)
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
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             %s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        short_name = EXCLUDED.short_name,
                        long_name = EXCLUDED.long_name
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
                    info.get('messageBoardId'), '',  # corporateActions as empty
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
                    logger.info(f"✅ Processed {processed} symbols successfully")

            except Exception as e:
                logger.error(f"Failed to process {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()

        time.sleep(PAUSE)

    return total, processed, failed

# Main execution
if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 SIMPLIFIED COMPANY PROFILE LOADER")
    logger.info("="*60)

    conn = get_db_connection()
    try:
        # Load stock symbols
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Found {len(stock_syms)} stock symbols")

        t_s, p_s, f_s = load_company_info(stock_syms, cur, conn)

        # Load ETF symbols
        cur.execute("SELECT symbol FROM etf_symbols;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Found {len(etf_syms)} ETF symbols")

        t_e, p_e, f_e = load_company_info(etf_syms, cur, conn)

        # Summary
        total_all = t_s + t_e
        processed_all = p_s + p_e
        failed_all = f_s + f_e

        logger.info("="*60)
        logger.info(f"✅ LOADING COMPLETE")
        logger.info(f"Total symbols: {total_all} | Processed: {processed_all} | Failed: {len(failed_all)}")
        logger.info(f"Success rate: {(processed_all/total_all)*100:.1f}%")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        conn.close()
