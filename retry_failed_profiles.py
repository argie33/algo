#!/usr/bin/env python3
"""
Retry loader for failed company profile symbols
Uses aggressive rate limiting to avoid yfinance API timeouts
"""

import sys
import logging
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

# Failed symbols from the loader
FAILED_SYMBOLS = ['BSET', 'BSLK', 'BSRR', 'BSVN', 'BSY', 'BTAI', 'BTBD', 'BTBT', 'BTCS', 'BTCT',
    'BTDR', 'CRWS', 'CRWV', 'CSAI', 'CSBR', 'CSCO', 'CSGP', 'CSGS', 'CSIQ', 'CSPI',
    'CSTE', 'CSTL', 'FBNC', 'FBRX', 'FBYD', 'FCAP', 'FCBC', 'FCCO', 'FCEL', 'FCFS',
    'FCHL', 'FCNCA', 'FCUV', 'FDBC', 'FDMT', 'FDSB', 'FEAM', 'FEBO', 'FEIM', 'FELE',
    'FEMY', 'FENC', 'FER', 'FFAI', 'FFBC', 'FFIC', 'FFIN', 'FFIV', 'FGBI', 'FGEN',
    'FGI', 'FGL', 'FGMC', 'FGNX', 'FHB', 'FHTX', 'FIBK', 'FIEE', 'FIGR', 'FINW',
    'FIP', 'FISI', 'FITB', 'FIVE', 'FIVN', 'FIZZ', 'FKWL', 'FLD', 'FLEX', 'FLGC',
    'FLGT', 'FLL', 'FLNC', 'FLNT', 'FLUX', 'FLWS', 'FLX', 'FLXS', 'FLY', 'FLYE',
    'FLYW', 'FMAO', 'FMBH', 'FMFC', 'FMNB', 'FMST', 'FNGR', 'FNKO', 'FNLC', 'FNWB',
    'FNWD', 'FOFO', 'FOLD', 'FONR', 'FORA', 'FORD', 'FORM', 'FORR', 'FORTY', 'FOSL']

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

def retry_failed_symbols():
    """Retry loading failed symbols with aggressive rate limiting"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    logger.info(f"Retrying {len(FAILED_SYMBOLS)} failed symbols with rate limiting")
    logger.info("Rate limiting: 1.5 second delay between symbols")
    
    success = 0
    failed = 0
    still_failing = []
    
    for i, symbol in enumerate(FAILED_SYMBOLS, 1):
        try:
            info = None
            # Single attempt with retry logic
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                if not info:
                    raise ValueError("No info data received")
            except Exception as e:
                logger.warning(f"Failed to get info for {symbol}: {e}")
                still_failing.append(symbol)
                failed += 1
                # Aggressive rate limiting
                time.sleep(1.5)
                continue
            
            if info:
                try:
                    # Try to insert
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
                        symbol, info.get('shortName'), info.get('longName'),
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
                        info.get('exchangeDataDelayedBy'), info.get('postMarketTime'),
                        info.get('regularMarketTime')
                    ))
                    conn.commit()
                    success += 1
                    logger.info(f"✅ {i:4}/{len(FAILED_SYMBOLS)} {symbol:8} SUCCESS")
                except Exception as e:
                    conn.rollback()
                    logger.warning(f"❌ {i:4}/{len(FAILED_SYMBOLS)} {symbol:8} DB Error: {str(e)[:50]}")
                    still_failing.append(symbol)
                    failed += 1
        
        except Exception as e:
            logger.error(f"Unexpected error for {symbol}: {e}")
            still_failing.append(symbol)
            failed += 1
        
        # Aggressive rate limiting between every symbol
        time.sleep(1.5)
    
    cur.close()
    conn.close()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("RETRY COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Successful: {success}/{len(FAILED_SYMBOLS)}")
    logger.info(f"Failed: {failed}/{len(FAILED_SYMBOLS)}")
    if still_failing:
        logger.info(f"\nStill failing ({len(still_failing)} symbols):")
        for sym in still_failing[:20]:
            logger.info(f"  - {sym}")
        if len(still_failing) > 20:
            logger.info(f"  ... and {len(still_failing) - 20} more")

if __name__ == "__main__":
    retry_failed_symbols()
