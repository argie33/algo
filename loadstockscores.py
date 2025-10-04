#!/usr/bin/env python3
"""
Stock Scores Loader Script - Enhanced Scoring Logic v2.1 (Updated: 2025-10-04 16:30)
Calculates and stores improved stock scores using multi-factor analysis.
Deploy stock scores calculation to populate comprehensive quality metrics.
CRITICAL FIX: Added transaction rollback to prevent cascade failures.

Data Sources:
- price_daily: Price data, volume, volatility, multi-timeframe momentum
- technical_data_daily: RSI, MACD, moving averages with alignment analysis
- earnings: PE ratios, EPS growth, earnings consistency
- earnings_history: Growth trends and earnings surprise patterns

Scoring Methodology (0-100 scale):
1. Momentum Score (20%): RSI + MACD + Price momentum across timeframes
2. Value Score (15%): PE ratio + PEG-adjusted valuation
3. Quality Score (15%): Volatility risk + Liquidity + Price stability
4. Growth Score (18%): Earnings growth + Momentum + Consistency
5. Relative Strength Score (17%): Outperformance vs S&P 500 + Sector relative performance
6. Positioning Score (10%): Institutional holdings changes + Market positioning trends
7. Sentiment Score (5%): Analyst ratings + Market sentiment indicators

Version History:
- v2.0: Enhanced multi-factor scoring with improved technical + fundamental analysis
- v1.13: Add fallback to stock_prices if stock_symbols is empty
- v1.12: Use stock_symbols table like other loaders
- v1.11: Clean slate - drop and recreate table with correct schema
- v1.10: Robust migration with step-by-step table creation
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
    try:
        cur = conn.cursor()

        # Drop existing table to start fresh
        logger.info("Dropping existing stock_scores table if it exists...")
        cur.execute("DROP TABLE IF EXISTS stock_scores CASCADE;")
        conn.commit()

        # Create table with correct schema
        logger.info("Creating stock_scores table...")
        cur.execute("""
            CREATE TABLE stock_scores (
                symbol VARCHAR(50) PRIMARY KEY,
                composite_score DECIMAL(5,2),
                momentum_score DECIMAL(5,2),
                trend_score DECIMAL(5,2),
                value_score DECIMAL(5,2),
                quality_score DECIMAL(5,2),
                growth_score DECIMAL(5,2),
                relative_strength_score DECIMAL(5,2),
                positioning_score DECIMAL(5,2),
                sentiment_score DECIMAL(5,2),
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
        """)
        conn.commit()
        logger.info("✅ stock_scores table created")

        # Create indexes
        logger.info("Creating indexes...")
        cur.execute("""
            CREATE INDEX idx_stock_scores_composite ON stock_scores(composite_score DESC);
            CREATE INDEX idx_stock_scores_date ON stock_scores(score_date);
            CREATE INDEX idx_stock_scores_updated ON stock_scores(last_updated);
        """)
        conn.commit()
        logger.info("✅ Indexes created")

        cur.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to create stock_scores table: {e}")
        return False

def get_stock_symbols(conn, limit=None):
    """Get stock symbols from stock_symbols table.
    Returns all symbols - price data availability will be checked later."""
    try:
        cur = conn.cursor()
        logger.info("🔍 Executing stock symbols query...")

        # Get all symbols from stock_symbols table
        # Price data availability is checked when processing each symbol
        limit_clause = f"LIMIT {limit}" if limit else ""
        cur.execute(f"""
            SELECT symbol
            FROM stock_symbols
            WHERE exchange IN ('NASDAQ', 'New York Stock Exchange')
            ORDER BY symbol
            {limit_clause}
        """)

        logger.info("🔍 Query executed, fetching results...")
        rows = cur.fetchall()
        logger.info(f"Query returned {len(rows)} rows from stock_symbols")

        if rows:
            logger.info(f"First row: {rows[0]}")
            symbols = [row[0] for row in rows]
        else:
            logger.error("❌ No symbols found in stock_symbols table")
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

        # Get price data from price_daily table (last 90 days for calculations)
        cur.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM price_daily
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
        df = pd.DataFrame(price_data, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close'])
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
            SELECT eps_actual, quarter
            FROM earnings_history
            WHERE symbol = %s
            AND quarter >= CURRENT_DATE - INTERVAL '24 months'
            ORDER BY quarter DESC
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

        # Get sentiment data for Sentiment Score
        cur.execute("""
            SELECT sentiment_score, total_mentions
            FROM sentiment
            WHERE symbol = %s
            AND date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))
        sentiment_data = cur.fetchone()
        sentiment_score_raw = float(sentiment_data[0]) if sentiment_data and sentiment_data[0] is not None else None
        news_count = int(sentiment_data[1]) if sentiment_data and sentiment_data[1] is not None else 0

        # Get analyst recommendations for Sentiment Score
        cur.execute("""
            SELECT rating, target_price, current_price
            FROM analyst_recommendations
            WHERE symbol = %s
            AND date_published >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY date_published DESC
            LIMIT 10
        """, (symbol,))
        analyst_recs = cur.fetchall()
        analyst_score = None
        if analyst_recs:
            # Convert ratings to numeric: Strong Buy=5, Buy=4, Hold=3, Sell=2, Strong Sell=1
            rating_map = {'strong buy': 5, 'buy': 4, 'hold': 3, 'sell': 2, 'strong sell': 1}
            ratings = [rating_map.get(row[0].lower(), 3) for row in analyst_recs if row[0]]
            if ratings:
                analyst_score = sum(ratings) / len(ratings)

        # Get institutional positioning data for Positioning Score
        cur.execute("""
            SELECT position_change_percent, market_share, institution_type
            FROM institutional_positioning
            WHERE symbol = %s
            AND filing_date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY filing_date DESC
            LIMIT 20
        """, (symbol,))
        positioning_data = cur.fetchall()
        inst_position_change = None
        inst_market_share = None
        if positioning_data:
            # Calculate average position change and market share
            position_changes = [float(row[0]) for row in positioning_data if row[0] is not None]
            market_shares = [float(row[1]) for row in positioning_data if row[1] is not None]
            if position_changes:
                inst_position_change = sum(position_changes) / len(position_changes)
            if market_shares:
                inst_market_share = sum(market_shares) / len(market_shares)

        # Calculate individual scores (0-100 scale)

        # Momentum Score (RSI + MACD + Price Momentum)
        momentum_score = 50  # Start neutral

        # RSI component (0-40 points)
        if rsi is not None:
            if rsi > 70:
                rsi_score = 35 + (min(rsi, 100) - 70) * 0.17  # 35-40 for strong
            elif rsi > 60:
                rsi_score = 30 + (rsi - 60)  # 30-35 for bullish
            elif rsi > 50:
                rsi_score = 25 + (rsi - 50) * 0.5  # 25-30 for mild bullish
            elif rsi > 40:
                rsi_score = 20 + (rsi - 40) * 0.5  # 20-25 for neutral/weak
            elif rsi > 30:
                rsi_score = 10 + (rsi - 30)  # 10-20 for oversold (potential bounce)
            else:
                rsi_score = max(0, rsi * 0.33)  # 0-10 for very oversold
        else:
            rsi_score = 20  # Default neutral

        # MACD component (0-30 points)
        macd_score = 15  # Default neutral
        if macd is not None:
            if macd > 0:
                macd_score = 20 + min(macd * 2, 10)  # 20-30 for positive MACD
            else:
                macd_score = max(0, 15 + macd * 2)  # 0-15 for negative MACD

        # Price momentum component (0-30 points)
        momentum_score = rsi_score + macd_score
        if price_change_5d > 5:
            momentum_score += min(10, price_change_5d * 0.5)
        elif price_change_5d > 0:
            momentum_score += price_change_5d
        elif price_change_5d > -5:
            momentum_score += max(-10, price_change_5d)
        else:
            momentum_score += max(-15, price_change_5d * 0.5)

        momentum_score = max(0, min(100, momentum_score))

        # Trend Score (multi-timeframe analysis + MA alignment)
        trend_score = 50  # Start neutral

        if sma_20 and sma_50:
            price_vs_sma20 = (current_price / float(sma_20) - 1) * 100
            price_vs_sma50 = (current_price / float(sma_50) - 1) * 100

            # MA alignment bonus/penalty (0-25 points)
            ma_alignment = 0
            if float(sma_20) > float(sma_50):
                # Bullish alignment
                ma_alignment = 15
                if price_vs_sma20 > 0:
                    ma_alignment += 10  # Price above both MAs
            else:
                # Bearish alignment
                ma_alignment = -15
                if price_vs_sma20 < 0:
                    ma_alignment -= 10  # Price below both MAs

            # Price position score (0-50 points)
            position_score = 25 + (price_vs_sma20 * 0.5) + (price_vs_sma50 * 0.3)
            position_score = max(0, min(50, position_score))

            # Multi-timeframe momentum (0-25 points)
            timeframe_score = 12.5
            if price_change_1d > 0 and price_change_5d > 0 and price_change_30d > 0:
                timeframe_score = 25  # Bullish across all timeframes
            elif price_change_1d < 0 and price_change_5d < 0 and price_change_30d < 0:
                timeframe_score = 0  # Bearish across all timeframes
            elif price_change_5d > 0 and price_change_30d > 0:
                timeframe_score = 18.75  # Medium-term bullish
            elif price_change_5d < 0 and price_change_30d < 0:
                timeframe_score = 6.25  # Medium-term bearish

            trend_score = position_score + ma_alignment + timeframe_score
            trend_score = max(0, min(100, trend_score))
        else:
            # Fallback to price changes only
            if price_change_5d > 0 and price_change_30d > 0:
                trend_score = 60 + min(20, (price_change_30d * 0.5))
            elif price_change_5d < 0 and price_change_30d < 0:
                trend_score = 40 + max(-20, (price_change_30d * 0.5))
            trend_score = max(0, min(100, trend_score))

        # Value Score (PE ratio with growth adjustment - PEG concept)
        value_score = 50  # Start neutral

        if pe_ratio and pe_ratio > 0:
            # Base PE score
            if pe_ratio < 10:
                pe_score = 95  # Very undervalued
            elif pe_ratio < 15:
                pe_score = 85
            elif pe_ratio < 20:
                pe_score = 70
            elif pe_ratio < 25:
                pe_score = 55
            elif pe_ratio < 30:
                pe_score = 40
            elif pe_ratio < 40:
                pe_score = 25
            else:
                pe_score = 10  # Very overvalued

            # Growth adjustment (PEG-like)
            if earnings_growth is not None and earnings_growth > 0:
                peg_ratio = pe_ratio / earnings_growth
                if peg_ratio < 1:
                    # Undervalued relative to growth
                    pe_score = min(100, pe_score + 15)
                elif peg_ratio < 1.5:
                    # Fair value
                    pe_score = min(100, pe_score + 5)
                elif peg_ratio > 2.5:
                    # Overvalued relative to growth
                    pe_score = max(0, pe_score - 15)
                elif peg_ratio > 2:
                    pe_score = max(0, pe_score - 5)

            value_score = pe_score
        else:
            value_score = 50  # Neutral if no PE

        # Quality Score (volatility risk + volume consistency + price stability)
        quality_score = 50  # Start neutral

        # Volatility component (0-40 points)
        vol_score = 20
        if volatility_30d:
            if volatility_30d < 15:
                vol_score = 40  # Very low risk
            elif volatility_30d < 25:
                vol_score = 35  # Low risk
            elif volatility_30d < 35:
                vol_score = 25  # Moderate risk
            elif volatility_30d < 50:
                vol_score = 15  # High risk
            elif volatility_30d < 70:
                vol_score = 5   # Very high risk
            else:
                vol_score = 0   # Extremely risky

        # Volume consistency (0-30 points)
        volume_score = 10
        if volume_avg_30d > 5000000:
            volume_score = 30  # Very liquid
        elif volume_avg_30d > 1000000:
            volume_score = 25  # Highly liquid
        elif volume_avg_30d > 500000:
            volume_score = 20  # Good liquidity
        elif volume_avg_30d > 100000:
            volume_score = 12  # Moderate liquidity
        elif volume_avg_30d > 50000:
            volume_score = 5   # Low liquidity
        else:
            volume_score = 0   # Very low liquidity

        # Price stability (0-30 points) - penalize wild swings
        stability_score = 15
        if abs(price_change_30d) < 5:
            stability_score = 30  # Very stable
        elif abs(price_change_30d) < 10:
            stability_score = 25  # Stable
        elif abs(price_change_30d) < 20:
            stability_score = 18  # Moderate stability
        elif abs(price_change_30d) < 30:
            stability_score = 10  # Volatile
        else:
            stability_score = 5   # Very volatile

        # Bonus for consistent uptrend (low vol + positive returns)
        if volatility_30d and volatility_30d < 25 and price_change_30d > 5:
            stability_score = min(30, stability_score + 5)

        quality_score = vol_score + volume_score + stability_score
        quality_score = max(0, min(100, quality_score))

        # Growth Score (earnings growth + consistency + forward estimates)
        growth_score = 50  # Default neutral score

        # Historical earnings growth component (0-50 points)
        earnings_component = 25
        if earnings_growth is not None:
            if earnings_growth > 30:
                earnings_component = 50  # Exceptional growth
            elif earnings_growth > 20:
                earnings_component = 45  # Very strong growth
            elif earnings_growth > 15:
                earnings_component = 40  # Strong growth
            elif earnings_growth > 10:
                earnings_component = 35  # Good growth
            elif earnings_growth > 5:
                earnings_component = 28  # Moderate growth
            elif earnings_growth > 0:
                earnings_component = 22  # Positive but weak
            elif earnings_growth > -5:
                earnings_component = 15  # Slight decline
            elif earnings_growth > -10:
                earnings_component = 8   # Declining
            else:
                earnings_component = 0   # Significant decline

        # Price momentum component (0-30 points)
        momentum_component = 15
        if price_change_30d > 15:
            momentum_component = 30
        elif price_change_30d > 10:
            momentum_component = 25
        elif price_change_30d > 5:
            momentum_component = 20
        elif price_change_30d > 0:
            momentum_component = 17
        elif price_change_30d > -5:
            momentum_component = 13
        elif price_change_30d > -10:
            momentum_component = 8
        else:
            momentum_component = 0

        # Growth consistency bonus (0-20 points)
        consistency_bonus = 10
        if len(earnings_data) >= 8:
            # Check if growth is consistent (more positive quarters than negative)
            eps_values = [float(row[0]) for row in earnings_data if row[0] is not None]
            if len(eps_values) >= 4:
                recent_positive = sum(1 for i in range(min(4, len(eps_values)-1))
                                    if eps_values[i] > eps_values[i+1])
                if recent_positive >= 3:
                    consistency_bonus = 20  # Very consistent
                elif recent_positive >= 2:
                    consistency_bonus = 15  # Moderately consistent
                elif recent_positive == 1:
                    consistency_bonus = 8   # Somewhat consistent
                else:
                    consistency_bonus = 0   # Inconsistent or declining

        growth_score = earnings_component + momentum_component + consistency_bonus
        growth_score = max(0, min(100, growth_score))

        # Relative Strength Score (Performance vs S&P 500)
        relative_strength_score = 50  # Start neutral

        # Get SPY (S&P 500) price data for comparison
        cur.execute("""
            SELECT close
            FROM price_daily
            WHERE symbol = 'SPY'
            AND date <= CURRENT_DATE
            ORDER BY date DESC
            LIMIT 30
        """)
        spy_data = cur.fetchall()

        if spy_data and len(spy_data) >= 2:
            spy_prices = [float(row[0]) for row in spy_data if row[0] is not None]

            # Calculate SPY 30-day return
            if len(spy_prices) >= 30:
                spy_return_30d = ((spy_prices[0] - spy_prices[29]) / spy_prices[29]) * 100
            elif len(spy_prices) >= 2:
                spy_return_30d = ((spy_prices[0] - spy_prices[-1]) / spy_prices[-1]) * 100
            else:
                spy_return_30d = 0

            # Calculate relative outperformance (alpha)
            alpha = price_change_30d - spy_return_30d

            # Score based on alpha (outperformance)
            # Strong outperformance: alpha > 10% = 80-100 points
            # Moderate outperformance: alpha 0-10% = 50-80 points
            # Underperformance: alpha < 0% = 0-50 points
            if alpha > 20:
                relative_strength_score = 90 + min(alpha - 20, 10)  # 90-100 for exceptional
            elif alpha > 10:
                relative_strength_score = 80 + (alpha - 10)  # 80-90 for strong
            elif alpha > 0:
                relative_strength_score = 50 + (alpha * 3)  # 50-80 for moderate
            elif alpha > -10:
                relative_strength_score = 50 + (alpha * 5)  # 0-50 for slight under
            else:
                relative_strength_score = max(0, 50 + (alpha * 2.5))  # 0 for severe under
        else:
            # Fallback: use absolute performance if SPY data unavailable
            if price_change_30d > 10:
                relative_strength_score = 70 + min(price_change_30d - 10, 30)
            elif price_change_30d > 0:
                relative_strength_score = 50 + (price_change_30d * 2)
            else:
                relative_strength_score = max(0, 50 + (price_change_30d * 2))

        relative_strength_score = max(0, min(100, relative_strength_score))

        # Positioning Score (Institutional holdings + trends)
        positioning_score = 50  # Start neutral

        if inst_position_change is not None:
            # Institutional buying (+) or selling (-) trend
            if inst_position_change > 5:
                positioning_score += min(30, inst_position_change * 2)  # Strong buying
            elif inst_position_change > 0:
                positioning_score += inst_position_change * 3  # Moderate buying
            elif inst_position_change > -5:
                positioning_score += inst_position_change * 3  # Moderate selling
            else:
                positioning_score += max(-30, inst_position_change * 2)  # Strong selling

        if inst_market_share is not None:
            # Higher institutional ownership can be positive (confidence) up to a point
            # Normalize market share to 0-20 points (assuming 0-100% range)
            market_share_component = min(20, inst_market_share * 100 * 0.2)
            positioning_score += market_share_component

        positioning_score = max(0, min(100, positioning_score))

        # Sentiment Score (Analyst ratings + Market sentiment)
        sentiment_score = 50  # Start neutral

        # Analyst sentiment component (0-50 points)
        if analyst_score is not None:
            # Scale from 1-5 to 0-50: (score-1)/4 * 50
            analyst_component = ((analyst_score - 1) / 4) * 50
            sentiment_score = analyst_component

        # News sentiment component (add up to ±25 points)
        if sentiment_score_raw is not None:
            # Assuming sentiment_score_raw is 0-1 scale, convert to -25 to +25
            news_component = (sentiment_score_raw - 0.5) * 50
            sentiment_score += news_component

        # Bonus for high news coverage (indicates interest)
        if news_count > 10:
            sentiment_score += min(10, news_count * 0.5)
        elif news_count > 5:
            sentiment_score += 5

        sentiment_score = max(0, min(100, sentiment_score))

        # Composite Score (optimized weighted average with 7 factors)
        # Weights: Momentum (20%), Growth (18%), Relative Strength (17%), Value (15%),
        #          Quality (15%), Positioning (10%), Sentiment (5%)
        composite_score = (
            momentum_score * 0.20 +                 # Short-term momentum
            growth_score * 0.18 +                   # Growth drivers
            relative_strength_score * 0.17 +        # Relative strength
            value_score * 0.15 +                    # Valuation
            quality_score * 0.15 +                  # Quality/Risk
            positioning_score * 0.10 +              # Institutional positioning
            sentiment_score * 0.05                  # Market sentiment
        )

        cur.close()

        return {
            'symbol': symbol,
            'composite_score': float(round(composite_score, 2)),
            'momentum_score': float(round(momentum_score, 2)),
            'trend_score': float(round(trend_score, 2)),
            'value_score': float(round(value_score, 2)),
            'quality_score': float(round(quality_score, 2)),
            'growth_score': float(round(growth_score, 2)),
            'relative_strength_score': float(round(relative_strength_score, 2)),
            'positioning_score': float(round(positioning_score, 2)),
            'sentiment_score': float(round(sentiment_score, 2)),
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
        conn.rollback()  # Rollback aborted transaction
        return None

def save_stock_score(conn, score_data):
    """Save stock score to database."""
    try:
        cur = conn.cursor()

        # Upsert query
        upsert_sql = """
        INSERT INTO stock_scores (
            symbol, composite_score, momentum_score, trend_score, value_score, quality_score, growth_score,
            relative_strength_score, positioning_score, sentiment_score,
            rsi, macd, sma_20, sma_50, volume_avg_30d, current_price,
            price_change_1d, price_change_5d, price_change_30d, volatility_30d,
            market_cap, pe_ratio, score_date, last_updated
        ) VALUES (
            %(symbol)s, %(composite_score)s, %(momentum_score)s, %(trend_score)s, %(value_score)s, %(quality_score)s, %(growth_score)s,
            %(relative_strength_score)s, %(positioning_score)s, %(sentiment_score)s,
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
            relative_strength_score = EXCLUDED.relative_strength_score,
            positioning_score = EXCLUDED.positioning_score,
            sentiment_score = EXCLUDED.sentiment_score,
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
        conn.rollback()  # Rollback aborted transaction
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
            symbols = get_stock_symbols(conn)  # Process all symbols
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