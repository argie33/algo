#!/usr/bin/env python3
"""
Calculate missing beta values using SPY (S&P 500) as market index.
Beta calculation: covariance(stock_returns, market_returns) / variance(market_returns)

Industry Standard Approach:
- Use last 252 trading days (~1 year) for beta calculation
- Minimum 60 trading days required
- Beta = covariance / market variance (levered to market)
"""

import os
import sys
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'bed0elAn')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    """Create database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def calculate_beta(stock_returns, market_returns):
    """
    Calculate beta from returns series
    Beta = covariance(stock, market) / variance(market)
    """
    # Align the series
    aligned = pd.DataFrame({
        'stock': stock_returns,
        'market': market_returns
    }).dropna()

    if len(aligned) < 60:  # Minimum 60 trading days
        return None

    # Calculate covariance and variance
    covariance = np.cov(aligned['stock'], aligned['market'])[0, 1]
    market_variance = np.var(aligned['market'], ddof=1)

    if market_variance == 0:
        return None

    beta = covariance / market_variance

    # Sanity check: beta should be between -2 and 5 for most stocks
    if beta < -2 or beta > 5:
        return None  # Suspicious value, likely calculation error

    return beta

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    logger.info("🚀 Beta Calculation from SPY Market Index")

    try:
        # Load SPY price data
        logger.info("📊 Loading SPY (S&P 500) price data...")
        cur.execute("""
            SELECT date, adj_close FROM price_daily
            WHERE symbol = 'SPY'
            ORDER BY date DESC
            LIMIT 252
        """)
        spy_data = cur.fetchall()

        if not spy_data:
            logger.error("❌ No SPY data found!")
            sys.exit(1)

        # Reverse to chronological order
        spy_data = list(reversed(spy_data))
        spy_df = pd.DataFrame(spy_data, columns=['date', 'close_price'])
        spy_df['date'] = pd.to_datetime(spy_df['date'])
        spy_df['returns'] = spy_df['close_price'].pct_change()

        logger.info(f"✅ Loaded {len(spy_df)} SPY daily prices")

        # Get symbols with missing beta
        logger.info("📊 Finding stocks with missing beta values...")
        cur.execute("""
            SELECT DISTINCT symbol FROM stability_metrics
            WHERE beta IS NULL OR beta <= 0 OR beta > 5
            ORDER BY symbol
        """)
        missing_symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"📊 Found {len(missing_symbols)} stocks with missing/invalid beta")

        # Calculate beta for each missing symbol
        updated_count = 0
        batch_size = 100
        batch_updates = []

        for idx, symbol in enumerate(missing_symbols, 1):
            try:
                # Load stock price data (last 252 days)
                cur.execute("""
                    SELECT date, adj_close FROM price_daily
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 252
                """, (symbol,))

                stock_data = cur.fetchall()

                if not stock_data:
                    continue

                # Reverse to chronological order
                stock_data = list(reversed(stock_data))
                stock_df = pd.DataFrame(stock_data, columns=['date', 'close_price'])
                stock_df['date'] = pd.to_datetime(stock_df['date'])
                stock_df['returns'] = stock_df['close_price'].pct_change()

                # Align dates between stock and SPY
                aligned = stock_df.merge(
                    spy_df[['date', 'returns']],
                    on='date',
                    suffixes=('_stock', '_spy')
                ).dropna()

                if len(aligned) < 60:
                    continue

                # Calculate beta
                beta = calculate_beta(aligned['returns_stock'], aligned['returns_spy'])

                if beta is not None:
                    batch_updates.append((beta, symbol))  # Note: swapped order for UPDATE statement
                    updated_count += 1

                    if len(batch_updates) >= batch_size or idx == len(missing_symbols):
                        # Batch update
                        try:
                            cur.executemany("""
                                UPDATE stability_metrics
                                SET beta = %s
                                WHERE symbol = %s
                            """, batch_updates)
                            conn.commit()
                            logger.info(f"✅ Updated {updated_count}/{len(missing_symbols)} beta values ({idx}/{len(missing_symbols)} processed)")
                        except Exception as e:
                            logger.debug(f"Batch update error: {e}")
                            conn.rollback()
                        batch_updates = []

            except Exception as e:
                logger.debug(f"Could not calculate beta for {symbol}: {e}")
                continue

        # Final batch update if any remaining
        if batch_updates:
            try:
                cur.executemany("""
                    UPDATE stability_metrics
                    SET beta = %s
                    WHERE symbol = %s
                """, batch_updates)
                conn.commit()
            except Exception as e:
                logger.debug(f"Final batch error: {e}")
                conn.rollback()

        logger.info(f"✅ Beta calculation COMPLETED - {updated_count} stocks updated")

        # Report new coverage
        cur.execute("SELECT COUNT(*) FROM stability_metrics WHERE beta IS NOT NULL AND beta > 0 AND beta <= 5")
        valid_beta_count = cur.fetchone()[0]
        logger.info(f"📊 Now have {valid_beta_count} stocks with valid beta values (was {len(missing_symbols)} missing)")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
