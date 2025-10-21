#!/usr/bin/env python3
"""
Fixed Company Profile Loader - Loads all 9,896 symbols' company data
Minimal version focusing on company_profile table with proper JSON handling
"""

import logging, os, sys, psycopg2, yfinance as yf, time
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    try:
        return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        sys.exit(1)

def load_company_info(symbols, cur, conn):
    total = len(symbols)
    logger.info(f"Loading {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE = 20
    
    for batch_idx in range(0, total, CHUNK_SIZE):
        batch = symbols[batch_idx:batch_idx+CHUNK_SIZE]
        logger.info(f"Batch {batch_idx//CHUNK_SIZE + 1}/{(total + CHUNK_SIZE - 1)//CHUNK_SIZE} ({len(batch)} symbols)")
        
        for orig_sym in batch:
            yq_sym = orig_sym.replace('.', '-').replace('$', '-').upper()
            info = None
            
            for attempt in range(3):
                try:
                    ticker = yf.Ticker(yq_sym)
                    info = ticker.info
                    if info:
                        break
                except:
                    if attempt == 2:
                        failed.append(orig_sym)
                    time.sleep(0.2)
            
            if not info:
                logger.warning(f"Skipped {orig_sym}: no data")
                continue
            
            try:
                # Insert with proper NULL handling for corporate_actions (JSON field)
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
                    info.get('messageBoardId'), None,  # NULL for JSON field instead of empty string
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
                if processed % 500 == 0:
                    logger.info(f"✅ {processed} symbols loaded")
            except Exception as e:
                logger.error(f"Failed {orig_sym}: {str(e)[:100]}")
                failed.append(orig_sym)
                conn.rollback()
        
        time.sleep(0.1)
    
    return total, processed, failed

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 COMPANY PROFILE LOADER - FIXED JSON")
    logger.info("="*60)
    
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Load stocks
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Found {len(stock_syms)} stocks")
        t_s, p_s, f_s = load_company_info(stock_syms, cur, conn)
        
        # Load ETFs
        cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol;")
        etf_syms = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Found {len(etf_syms)} ETFs")
        t_e, p_e, f_e = load_company_info(etf_syms, cur, conn)
        
        # Summary
        total_all = t_s + t_e
        processed_all = p_s + p_e
        failed_all = len(f_s) + len(f_e)
        
        logger.info("="*60)
        logger.info(f"✅ COMPLETE: {processed_all}/{total_all} loaded ({(processed_all/total_all*100):.1f}%)")
        logger.info(f"Failed: {failed_all}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)
    finally:
        conn.close()
