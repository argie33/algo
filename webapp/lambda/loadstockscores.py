#!/usr/bin/env python3
"""
Stock Scores Loader Script
Calculates and stores stock scores in the database.
Reads from stock_symbols table and calculates various metrics.
"""

import os
import sys
import psycopg2
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration - simplified to work with existing setup
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': '',  # No password for local setup
    'dbname': 'stocks'
}

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
        # Get symbols, prioritizing non-ETF stocks and larger symbols
        cur.execute("""
            SELECT DISTINCT symbol
            FROM stock_symbols
            WHERE symbol IS NOT NULL
                AND length(symbol) <= 5
                AND symbol NOT LIKE '%.%'
                AND symbol NOT LIKE '%-%'
                AND (etf != 'Y' OR etf IS NULL)
            ORDER BY symbol
            LIMIT %s
        """, (limit,))

        symbols = [row[0] for row in cur.fetchall()]
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

def get_stock_data_and_calculate_scores(symbol):
    """Get stock data from yfinance and calculate all scores."""
    try:
        # Download stock data
        stock = yf.Ticker(symbol)

        # Get 3 months of historical data for calculations
        hist = stock.history(period="3mo")
        if hist.empty or len(hist) < 20:
            logger.warning(f"⚠️ Insufficient data for {symbol}")
            return None

        # Get basic info
        info = stock.info
        current_price = hist['Close'].iloc[-1]

        # Calculate price changes
        price_change_1d = ((current_price - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0
        price_change_5d = ((current_price - hist['Close'].iloc[-6]) / hist['Close'].iloc[-6] * 100) if len(hist) >= 6 else 0
        price_change_30d = ((current_price - hist['Close'].iloc[-31]) / hist['Close'].iloc[-31] * 100) if len(hist) >= 31 else 0

        # Calculate moving averages
        sma_20 = hist['Close'].tail(20).mean() if len(hist) >= 20 else current_price
        sma_50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else current_price

        # Calculate volume average
        volume_avg_30d = int(hist['Volume'].tail(30).mean()) if len(hist) >= 30 else int(hist['Volume'].mean())

        # Calculate technical indicators
        prices = hist['Close'].values
        rsi = calculate_rsi(prices)
        macd = calculate_macd(prices)
        volatility_30d = calculate_volatility(prices)

        # Get fundamental data
        market_cap = info.get('marketCap', 0) or 0
        pe_ratio = info.get('trailingPE', None)

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
        price_vs_sma20 = (current_price / sma_20 - 1) * 100
        price_vs_sma50 = (current_price / sma_50 - 1) * 100
        trend_score = 50 + (price_vs_sma20 * 2) + (price_vs_sma50 * 1)
        trend_score = max(0, min(100, trend_score))  # Cap between 0-100

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

        # Composite Score (weighted average)
        composite_score = (
            momentum_score * 0.25 +
            trend_score * 0.30 +
            value_score * 0.25 +
            quality_score * 0.20
        )

        return {
            'symbol': symbol,
            'composite_score': round(composite_score, 2),
            'momentum_score': round(momentum_score, 2),
            'trend_score': round(trend_score, 2),
            'value_score': round(value_score, 2),
            'quality_score': round(quality_score, 2),
            'rsi': rsi,
            'macd': macd,
            'sma_20': round(sma_20, 2),
            'sma_50': round(sma_50, 2),
            'volume_avg_30d': volume_avg_30d,
            'current_price': round(current_price, 2),
            'price_change_1d': round(price_change_1d, 2),
            'price_change_5d': round(price_change_5d, 2),
            'price_change_30d': round(price_change_30d, 2),
            'volatility_30d': volatility_30d,
            'market_cap': market_cap,
            'pe_ratio': pe_ratio
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
            symbol, composite_score, momentum_score, trend_score, value_score, quality_score,
            rsi, macd, sma_20, sma_50, volume_avg_30d, current_price,
            price_change_1d, price_change_5d, price_change_30d, volatility_30d,
            market_cap, pe_ratio, score_date, last_updated
        ) VALUES (
            %(symbol)s, %(composite_score)s, %(momentum_score)s, %(trend_score)s, %(value_score)s, %(quality_score)s,
            %(rsi)s, %(macd)s, %(sma_20)s, %(sma_50)s, %(volume_avg_30d)s, %(current_price)s,
            %(price_change_1d)s, %(price_change_5d)s, %(price_change_30d)s, %(volatility_30d)s,
            %(market_cap)s, %(pe_ratio)s, CURRENT_DATE, CURRENT_TIMESTAMP
        ) ON CONFLICT (symbol) DO UPDATE SET
            composite_score = EXCLUDED.composite_score,
            momentum_score = EXCLUDED.momentum_score,
            trend_score = EXCLUDED.trend_score,
            value_score = EXCLUDED.value_score,
            quality_score = EXCLUDED.quality_score,
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
        symbols = get_stock_symbols(conn, limit=50)  # Limit to 50 for initial load
        if not symbols:
            logger.error("❌ No stock symbols found")
            return False

        logger.info(f"📊 Processing {len(symbols)} symbols...")

        # Process each symbol
        successful = 0
        failed = 0

        for i, symbol in enumerate(symbols, 1):
            logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})")

            # Calculate scores
            score_data = get_stock_data_and_calculate_scores(symbol)
            if score_data:
                # Save to database
                if save_stock_score(conn, score_data):
                    successful += 1
                    logger.info(f"✅ {symbol}: Composite Score = {score_data['composite_score']:.2f}")
                else:
                    failed += 1
            else:
                failed += 1

            # Add small delay to be respectful to yfinance
            import time
            time.sleep(0.5)

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