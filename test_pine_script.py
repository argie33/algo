#!/usr/bin/env python3
import sys
import logging
from loadbuyselldaily import (
    get_db_connection, create_buy_sell_table, 
    process_symbol, insert_symbol_results, 
    update_swing_metrics_for_symbol,
    USE_MA_FILTER, MA_TYPE, MA_LENGTH
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Test with AAPL only
test_symbols = ['AAPL']

conn = get_db_connection()
cur = conn.cursor()

# Recreate table
logging.info("Creating buy_sell_daily table...")
create_buy_sell_table(cur)
conn.commit()

logging.info(f"Pine Script Config: MA Filter={USE_MA_FILTER}, Type={MA_TYPE}, Length={MA_LENGTH}")

for symbol in test_symbols:
    logging.info(f"=== Processing {symbol} ===")
    try:
        # Generate signals
        df = process_symbol(symbol, 'Daily', use_ma_filter=USE_MA_FILTER, ma_type=MA_TYPE, ma_length=MA_LENGTH)
        if df.empty:
            logging.warning(f"No data for {symbol}")
            continue
            
        # Insert base signals
        insert_symbol_results(cur, symbol, 'Daily', df, ma_type=MA_TYPE, ma_length=MA_LENGTH)
        conn.commit()
        logging.info(f"✅ Inserted {len(df)} rows for {symbol}")
        
        # Calculate swing metrics
        logging.info(f"Calculating swing metrics...")
        update_swing_metrics_for_symbol(cur, symbol, 'Daily')
        conn.commit()
        logging.info(f"✅ Swing metrics calculated for {symbol}")
        
        # Verify data
        cur.execute("""
            SELECT signal, buylevel, stoplevel, inposition, 
                   ma_filter_value, sata_score, stage_number, market_stage,
                   pct_from_sma_50, entry_quality_score, risk_reward_ratio
            FROM buy_sell_daily 
            WHERE symbol = %s AND timeframe = 'Daily'
            ORDER BY date DESC LIMIT 5
        """, (symbol,))
        
        results = cur.fetchall()
        logging.info(f"\n{'='*80}")
        logging.info(f"Last 5 rows for {symbol}:")
        for row in results:
            logging.info(f"  Signal: {row[0]}, BuyLvl: {row[1]}, StopLvl: {row[2]}, InPos: {row[3]}")
            logging.info(f"    MA Filter: {row[4]}, SATA: {row[5]}, Stage: {row[6]} ({row[7]})")
            logging.info(f"    %FromSMA50: {row[8]}, Quality: {row[9]}, R/R: {row[10]}")
        logging.info(f"{'='*80}\n")
        
    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        conn.rollback()

cur.close()
conn.close()
logging.info("✅ Test complete!")
