#!/usr/bin/env python3
"""
Stock Scores Loader Script - Production Ready
Calculates and stores stock scores in the database using existing data.
Reads from stock_symbols table and calculates metrics from:
- stock_prices: price data, volume, volatility calculations
- technical_data_daily: RSI, MACD, moving averages
- earnings: PE ratios from actual EPS data
Stores calculated scores in stock_scores table for API consumption.

Production loader for ECS task definition: stock-scores
Configured for GitHub Actions workflow deployment
Updated with growth score calculation and CloudFormation IAM role fixes
Growth score integration completed - v1.1
Testing GitHub Actions workflow trigger - deployment verification
Fixed Docker image reference and database environment variables - v1.2
CloudFormation export name corrected for workflow compatibility - v1.3
Container name corrected to match workflow expectations - v1.4
AWS Secrets Manager authentication with SSL/TLS encryption - v1.5
Force Docker image rebuild with all security fixes - v1.6
Workflow path detection fixed for subdirectory loaders - v1.7
Testing with updated workflow basename fix - v1.8
"""

import os
import sys
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get database credentials from AWS Secrets Manager
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN not set; aborting")
    sys.exit(1)

def get_db_config():
    """Fetch database configuration from AWS Secrets Manager."""
    try:
        client = boto3.client("secretsmanager")
        secret = json.loads(client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
        return {
            'host': secret["host"],
            'port': int(secret.get("port", 5432)),
            'user': secret["username"],
            'password': secret["password"],
            'dbname': secret["dbname"],
            'sslmode': 'require'
        }
    except Exception as e:
        logger.error(f"❌ Failed to fetch database credentials: {e}")
        sys.exit(1)

DB_CONFIG = get_db_config()

def get_db_connection():
    """Get database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return None

def create_stock_scores_table(conn):
    """Create stock_scores table if it doesn't exist."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS stock_scores (
        symbol VARCHAR(50) PRIMARY KEY,
        composite_score DECIMAL(5,2),
        momentum_score DECIMAL(5,2),
        trend_score DECIMAL(5,2),
        value_score DECIMAL(5,2),
        quality_score DECIMAL(5,2),
        growth_score DECIMAL(5,2),
        rsi DECIMAL(5,2),
        macd DECIMAL(10,4),
        sma_20 DECIMAL(10,2),
        sma_50 DECIMAL(10,2),
        volume_avg_30d BIGINT,
        current_price DECIMAL(10,2),
        price_change_1d DECIMAL(5,2),
        price_change_5d DECIMAL(5,2),
        price_change_30d DECIMAL(5,2),
        volatility_30d DECIMAL(5,2),
        market_cap BIGINT,
        pe_ratio DECIMAL(8,2),
        score_date DATE DEFAULT CURRENT_DATE,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create index for better performance
    CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
    CREATE INDEX IF NOT EXISTS idx_stock_scores_updated ON stock_scores(last_updated);
    CREATE INDEX IF NOT EXISTS idx_stock_scores_date ON stock_scores(score_date);
    """

    try:
        cur = conn.cursor()
        cur.execute(create_table_sql)
        conn.commit()
        logger.info("✅ stock_scores table created/verified")
        cur.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to create stock_scores table: {e}")
        return False

def get_stock_symbols(conn, limit=100):
    """Get stock symbols from stock_symbols table."""
    try:
        cur = conn.cursor()
        logger.info("🔍 Executing stock symbols query...")

        # Get symbols, prioritizing non-ETF stocks and larger symbols
        # Get symbols with sufficient price data (at least 20 records)
        cur.execute("""
            SELECT symbol
            FROM stock_prices
            GROUP BY symbol
            HAVING COUNT(*) >= 20
            ORDER BY symbol
            LIMIT %s
        """, (limit,))

        logger.info("🔍 Query executed, fetching results...")
        rows = cur.fetchall()
        logger.info(f"Query returned {len(rows)} rows")

        if rows:
            logger.info(f"First row: {rows[0]}")
            symbols = [row[0] for row in rows]
        else:
            symbols = []

        cur.close()
        logger.info(f"📊 Retrieved {len(symbols)} stock symbols")
        return symbols
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to get stock symbols: {e}")
        return []

def calculate_rsi(prices, period=14):
    """Calculate RSI (Relative Strength Index)."""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def calculate_macd(prices, fast_period=12, slow_period=26):
    """Calculate MACD (Moving Average Convergence Divergence)."""
    if len(prices) < slow_period:
        return None

    prices_series = pd.Series(prices)
    ema_fast = prices_series.ewm(span=fast_period).mean()
    ema_slow = prices_series.ewm(span=slow_period).mean()
    macd = ema_fast - ema_slow
    return round(macd.iloc[-1], 4) if not macd.empty else None

def calculate_volatility(prices, period=30):
    """Calculate 30-day volatility."""
    if len(prices) < 2:
        return None

    returns = np.diff(np.log(prices))
    volatility = np.std(returns) * np.sqrt(252) * 100  # Annualized volatility
    return round(volatility, 2)

def get_stock_data_from_database(conn, symbol):
    """Get stock data from database tables and calculate all scores."""
    try:
        cur = conn.cursor()

        # Get price data from stock_prices table (last 90 days for calculations)
        cur.execute("""
            SELECT date, open, high, low, close, volume, adjusted_close
            FROM stock_prices
            WHERE symbol = %s
            AND date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY date DESC
            LIMIT 90
        """, (symbol,))

        price_data = cur.fetchall()
        if not price_data or len(price_data) < 20:
            logger.warning(f"⚠️ Insufficient price data for {symbol}: {len(price_data) if price_data else 0} records")
            cur.close()
            return None

        # Convert to pandas DataFrame for easier calculations
        df = pd.DataFrame(price_data, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'adjusted_close'])
        df = df.sort_values('date')  # Sort chronologically for calculations

        # Get current price (most recent)
        current_price = float(df['close'].iloc[-1])

        # Calculate price changes
        price_change_1d = ((current_price - float(df['close'].iloc[-2])) / float(df['close'].iloc[-2]) * 100) if len(df) >= 2 else 0
        price_change_5d = ((current_price - float(df['close'].iloc[-6])) / float(df['close'].iloc[-6]) * 100) if len(df) >= 6 else 0
        price_change_30d = ((current_price - float(df['close'].iloc[-31])) / float(df['close'].iloc[-31]) * 100) if len(df) >= 31 else 0

        # Calculate volume average (last 30 days)
        volume_avg_30d = int(df['volume'].tail(30).mean()) if len(df) >= 30 else int(df['volume'].mean())

        # Get latest technical data
        cur.execute("""
            SELECT rsi, macd, sma_20, sma_50, atr
            FROM technical_data_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))

        tech_data = cur.fetchone()
        if tech_data and len(tech_data) >= 5:
            rsi, macd, sma_20, sma_50, atr = tech_data
        else:
            # Calculate basic technical indicators from price data
            prices = df['close'].astype(float).values
            rsi = calculate_rsi(prices)
            macd = calculate_macd(prices)
            sma_20 = df['close'].tail(20).mean() if len(df) >= 20 else current_price
            sma_50 = df['close'].tail(50).mean() if len(df) >= 50 else current_price
            atr = None

        # Calculate volatility from price data
        prices = df['close'].astype(float).values
        volatility_30d = calculate_volatility(prices)

        # Get earnings data for PE ratio and growth calculation
        cur.execute("""
            SELECT actual_eps, report_date
            FROM earnings
            WHERE symbol = %s
            AND report_date >= CURRENT_DATE - INTERVAL '24 months'
            ORDER BY report_date DESC
            LIMIT 8
        """, (symbol,))

        earnings_data = cur.fetchall()
        pe_ratio = None
        earnings_growth = None

        if earnings_data:
            # Calculate trailing 12-month EPS
            eps_values = [float(row[0]) for row in earnings_data if row[0] is not None]
            if eps_values and len(eps_values) >= 4:
                trailing_eps = sum(eps_values[:4])  # Last 4 quarters
                if trailing_eps > 0:
                    pe_ratio = current_price / trailing_eps

                # Calculate earnings growth (current year vs previous year)
                if len(eps_values) >= 8:
                    current_year_eps = sum(eps_values[:4])  # Last 4 quarters
                    previous_year_eps = sum(eps_values[4:8])  # Previous 4 quarters
                    if previous_year_eps > 0:
                        earnings_growth = ((current_year_eps - previous_year_eps) / abs(previous_year_eps)) * 100

        # Market cap placeholder - we don't have this data, so set to None
        market_cap = None

        cur.close()

        # Calculate individual scores (0-100 scale)

        # Momentum Score (based on RSI)
        if rsi is not None:
            if rsi > 70:
                momentum_score = 80 + (rsi - 70) * 0.67  # 80-100 for overbought
            elif rsi > 50:
                momentum_score = 50 + (rsi - 50)  # 50-80 for moderate momentum
            elif rsi > 30:
                momentum_score = 30 + (rsi - 30)  # 30-50 for weak momentum
            else:
                momentum_score = rsi  # 0-30 for oversold
        else:
            momentum_score = 50  # Neutral if no RSI

        # Trend Score (based on price relative to moving averages)
        if sma_20 and sma_50:
            price_vs_sma20 = (current_price / float(sma_20) - 1) * 100
            price_vs_sma50 = (current_price / float(sma_50) - 1) * 100
            trend_score = 50 + (price_vs_sma20 * 2) + (price_vs_sma50 * 1)
            trend_score = max(0, min(100, trend_score))  # Cap between 0-100
        else:
            trend_score = 50  # Neutral if no moving averages

        # Value Score (based on PE ratio if available)
        if pe_ratio and pe_ratio > 0:
            if pe_ratio < 15:
                value_score = 90
            elif pe_ratio < 25:
                value_score = 70
            elif pe_ratio < 35:
                value_score = 50
            else:
                value_score = 30
        else:
            value_score = 50  # Neutral if no PE

        # Quality Score (based on volatility and volume)
        quality_score = 50
        if volatility_30d:
            if volatility_30d < 20:
                quality_score += 30
            elif volatility_30d < 40:
                quality_score += 10
            elif volatility_30d > 60:
                quality_score -= 20

        if volume_avg_30d > 1000000:
            quality_score += 20
        elif volume_avg_30d > 100000:
            quality_score += 10

        quality_score = max(0, min(100, quality_score))

        # Growth Score (based on earnings growth and price momentum)
        growth_score = 50  # Default neutral score
        if earnings_growth is not None:
            if earnings_growth > 20:
                growth_score = 90
            elif earnings_growth > 10:
                growth_score = 75
            elif earnings_growth > 0:
                growth_score = 60
            elif earnings_growth > -10:
                growth_score = 40
            else:
                growth_score = 20

        # Add price momentum to growth score
        if price_change_30d > 10:
            growth_score = min(100, growth_score + 10)
        elif price_change_30d < -10:
            growth_score = max(0, growth_score - 10)

        growth_score = max(0, min(100, growth_score))

        # Composite Score (weighted average including growth)
        composite_score = (
            momentum_score * 0.20 +
            trend_score * 0.25 +
            value_score * 0.20 +
            quality_score * 0.15 +
            growth_score * 0.20
        )

        return {
            'symbol': symbol,
            'composite_score': float(round(composite_score, 2)),
            'momentum_score': float(round(momentum_score, 2)),
            'trend_score': float(round(trend_score, 2)),
            'value_score': float(round(value_score, 2)),
            'quality_score': float(round(quality_score, 2)),
            'growth_score': float(round(growth_score, 2)),
            'rsi': float(rsi) if rsi is not None else None,
            'macd': float(macd) if macd is not None else None,
            'sma_20': float(round(float(sma_20), 2)) if sma_20 else None,
            'sma_50': float(round(float(sma_50), 2)) if sma_50 else None,
            'volume_avg_30d': int(volume_avg_30d),
            'current_price': float(round(current_price, 2)),
            'price_change_1d': float(round(price_change_1d, 2)),
            'price_change_5d': float(round(price_change_5d, 2)),
            'price_change_30d': float(round(price_change_30d, 2)),
            'volatility_30d': float(volatility_30d) if volatility_30d is not None else None,
            'market_cap': int(market_cap) if market_cap else None,
            'pe_ratio': float(round(pe_ratio, 2)) if pe_ratio else None
        }

    except Exception as e:
        logger.error(f"❌ Error calculating scores for {symbol}: {e}")
        return None

def save_stock_score(conn, score_data):
    """Save stock score to database."""
    try:
        cur = conn.cursor()

        # Upsert query
        upsert_sql = """
        INSERT INTO stock_scores (
            symbol, composite_score, momentum_score, trend_score, value_score, quality_score, growth_score,
            rsi, macd, sma_20, sma_50, volume_avg_30d, current_price,
            price_change_1d, price_change_5d, price_change_30d, volatility_30d,
            market_cap, pe_ratio, score_date, last_updated
        ) VALUES (
            %(symbol)s, %(composite_score)s, %(momentum_score)s, %(trend_score)s, %(value_score)s, %(quality_score)s, %(growth_score)s,
            %(rsi)s, %(macd)s, %(sma_20)s, %(sma_50)s, %(volume_avg_30d)s, %(current_price)s,
            %(price_change_1d)s, %(price_change_5d)s, %(price_change_30d)s, %(volatility_30d)s,
            %(market_cap)s, %(pe_ratio)s, CURRENT_DATE, CURRENT_TIMESTAMP
        ) ON CONFLICT (symbol) DO UPDATE SET
            composite_score = EXCLUDED.composite_score,
            momentum_score = EXCLUDED.momentum_score,
            trend_score = EXCLUDED.trend_score,
            value_score = EXCLUDED.value_score,
            quality_score = EXCLUDED.quality_score,
            growth_score = EXCLUDED.growth_score,
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            sma_20 = EXCLUDED.sma_20,
            sma_50 = EXCLUDED.sma_50,
            volume_avg_30d = EXCLUDED.volume_avg_30d,
            current_price = EXCLUDED.current_price,
            price_change_1d = EXCLUDED.price_change_1d,
            price_change_5d = EXCLUDED.price_change_5d,
            price_change_30d = EXCLUDED.price_change_30d,
            volatility_30d = EXCLUDED.volatility_30d,
            market_cap = EXCLUDED.market_cap,
            pe_ratio = EXCLUDED.pe_ratio,
            score_date = CURRENT_DATE,
            last_updated = CURRENT_TIMESTAMP
        """

        cur.execute(upsert_sql, score_data)
        conn.commit()
        cur.close()
        return True

    except psycopg2.Error as e:
        logger.error(f"❌ Failed to save score for {score_data['symbol']}: {e}")
        return False

def main():
    """Main function to load stock scores."""
    logger.info("🚀 Starting stock scores loader...")

    # Get database connection
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Failed to connect to database")
        return False

    try:
        # Create stock_scores table
        if not create_stock_scores_table(conn):
            return False

        # Get stock symbols
        try:
            symbols = get_stock_symbols(conn, limit=100)  # Process up to 100 symbols
            if not symbols:
                logger.error("❌ No stock symbols found")
                return False
            logger.info(f"📊 Processing {len(symbols)} symbols...")
        except Exception as e:
            logger.error(f"❌ Error getting stock symbols: {e}")
            return False

        # Process each symbol
        successful = 0
        failed = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})")

                # Calculate scores from database
                score_data = get_stock_data_from_database(conn, symbol)
                if score_data:
                    # Save to database
                    if save_stock_score(conn, score_data):
                        successful += 1
                        logger.info(f"✅ {symbol}: Composite Score = {score_data['composite_score']:.2f}, Growth Score = {score_data['growth_score']:.2f}")
                    else:
                        failed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"❌ Error processing {symbol}: {e}")
                failed += 1

            # Small delay to avoid overwhelming the database
            import time
            time.sleep(0.1)

        logger.info(f"🎯 Completed! Successful: {successful}, Failed: {failed}")
        return True

    except Exception as e:
        logger.error(f"❌ Error in main process: {e}")
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)