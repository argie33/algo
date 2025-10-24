#!/usr/bin/env python3
"""
Calculate and populate missing momentum metrics from technical_data_daily and price_daily.
This fills the momentum_metrics table with calculated momentum for all stocks.
"""

import psycopg2
from psycopg2.extras import execute_values
import logging
import os
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration from environment"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "dbname": os.getenv("DB_NAME", "stocks"),
    }

def main():
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        cursor = conn.cursor()

        logging.info("=" * 80)
        logging.info("FILLING MOMENTUM METRICS FROM TECHNICAL DATA")
        logging.info("=" * 80)
        logging.info("")

        # Step 1: Get all symbols that need momentum data
        logging.info("Step 1: Identifying symbols needing momentum data...")
        cursor.execute("""
            SELECT DISTINCT symbol FROM stock_symbols
            WHERE symbol NOT IN (
                SELECT symbol FROM momentum_metrics WHERE momentum_12m_1 IS NOT NULL
            )
            ORDER BY symbol
        """)
        missing_symbols = [row[0] for row in cursor.fetchall()]
        logging.info(f"  Found {len(missing_symbols)} symbols needing momentum calculation")

        # Step 2: Calculate momentum from technical data for each symbol
        logging.info("")
        logging.info("Step 2: Calculating momentum metrics...")

        updates = []
        for idx, symbol in enumerate(missing_symbols):
            if (idx + 1) % 100 == 0:
                logging.info(f"  Processing {idx + 1}/{len(missing_symbols)}...")

            # Get price data for this symbol (252 days of history)
            cursor.execute("""
                SELECT
                    symbol,
                    date,
                    close
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 252
            """, (symbol,))

            price_data = cursor.fetchall()
            if not price_data or len(price_data) < 20:
                continue  # Skip symbols with insufficient data

            # Get technical indicators (RSI, MACD, etc.)
            cursor.execute("""
                SELECT
                    symbol,
                    date,
                    rsi,
                    macd,
                    macd_signal,
                    sma_50,
                    sma_200
                FROM technical_data_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 252
            """, (symbol,))

            tech_data = cursor.fetchall()

            # Extract price history
            prices = [row[2] for row in price_data]
            current_price = prices[0] if prices else None

            # Calculate momentum metrics
            # 12-month momentum (or available data)
            momentum_12m = None
            if len(prices) >= 252:
                momentum_12m = ((prices[0] - prices[251]) / prices[251]) * 100
            elif len(prices) > 20:
                momentum_12m = ((prices[0] - prices[-1]) / prices[-1]) * 100

            # 6-month momentum
            momentum_6m = None
            if len(prices) >= 126:
                momentum_6m = ((prices[0] - prices[125]) / prices[125]) * 100

            # 3-month momentum
            momentum_3m = None
            if len(prices) >= 63:
                momentum_3m = ((prices[0] - prices[62]) / prices[62]) * 100

            # Risk-adjusted momentum (simple RSI-based)
            risk_adj = None
            if tech_data and tech_data[0][2] is not None:  # RSI
                rsi = tech_data[0][2]
                risk_adj = (rsi - 50) / 50  # Convert 0-100 RSI to -1 to 1

            # Get latest technical indicators for price comparisons
            if tech_data:
                latest_tech = tech_data[0]
                sma_50 = latest_tech[5]
                sma_200 = latest_tech[6]
            else:
                sma_50 = None
                sma_200 = None

            # Calculate price vs SMA ratios
            price_vs_sma_50 = None
            price_vs_sma_200 = None
            if current_price and sma_50:
                price_vs_sma_50 = (current_price / sma_50) - 1
            if current_price and sma_200:
                price_vs_sma_200 = (current_price / sma_200) - 1

            # Volatility calculation from price returns
            volatility = None
            if len(prices) > 1:
                returns = []
                for i in range(1, min(252, len(prices))):
                    if prices[i] > 0:
                        ret = (prices[i-1] - prices[i]) / prices[i]
                        returns.append(ret)
                if returns and len(returns) > 1:
                    import statistics
                    volatility = statistics.stdev(returns) * 100  # Annualized roughly

            updates.append((
                symbol,
                date.today(),
                momentum_12m,
                momentum_6m,
                momentum_3m,
                risk_adj,
                price_vs_sma_50,
                price_vs_sma_200,
                None,  # price_vs_52w_high (not in technical_data_daily)
                current_price,
                volatility
            ))

        # Step 3: Insert/update momentum data
        logging.info("")
        logging.info(f"Step 3: Inserting {len(updates)} momentum records...")

        if updates:
            execute_values(cursor, """
                INSERT INTO momentum_metrics
                (symbol, date, momentum_12m_1, momentum_6m, momentum_3m,
                 risk_adjusted_momentum, price_vs_sma_50, price_vs_sma_200,
                 price_vs_52w_high, current_price, volatility_12m)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    momentum_12m_1 = EXCLUDED.momentum_12m_1,
                    momentum_6m = EXCLUDED.momentum_6m,
                    momentum_3m = EXCLUDED.momentum_3m,
                    risk_adjusted_momentum = EXCLUDED.risk_adjusted_momentum,
                    price_vs_sma_50 = EXCLUDED.price_vs_sma_50,
                    price_vs_sma_200 = EXCLUDED.price_vs_sma_200,
                    price_vs_52w_high = EXCLUDED.price_vs_52w_high,
                    current_price = EXCLUDED.current_price,
                    volatility_12m = EXCLUDED.volatility_12m
            """, updates)
            conn.commit()
            logging.info(f"  ✅ Inserted {len(updates)} momentum records")

        # Step 4: Verify results
        logging.info("")
        logging.info("Step 4: Verifying momentum_metrics population...")
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN momentum_12m_1 IS NOT NULL THEN 1 END) as with_momentum,
                ROUND(100.0 * COUNT(CASE WHEN momentum_12m_1 IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct
            FROM momentum_metrics
        """)

        total, with_momentum, pct = cursor.fetchone()
        logging.info(f"  Total momentum_metrics rows: {total}")
        logging.info(f"  Rows with momentum data: {with_momentum}")
        logging.info(f"  Coverage: {pct}%")

        logging.info("")
        logging.info("=" * 80)
        logging.info("✅ MOMENTUM METRICS FILLED!")
        logging.info("=" * 80)

        cursor.close()
        conn.close()
        return 0

    except Exception as e:
        logging.error(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
