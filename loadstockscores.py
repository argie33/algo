#!/usr/bin/env python3
"""
Stock Scores Loader Script - Enhanced Scoring Logic v2.2 (Updated: 2025-10-16)
Trigger: 20251016_143200 - Populate all stock scores and quality metrics to AWS
Calculates and stores improved stock scores using multi-factor analysis.
Deploy stock scores calculation to populate comprehensive quality metrics.
FIX: Trigger rebuild - Docker image has old code with scoring_engine import error.
CRITICAL FIX: Wrapped sentiment, analyst_recommendations, and institutional_positioning
queries in try-except blocks to handle missing tables gracefully with rollback.
Trigger: Force rebuild to test AWS deployment with correct environment variables.

Data Sources:
- price_daily: Price data, volume, volatility, multi-timeframe momentum
- technical_data_daily: RSI, MACD, moving averages with alignment analysis
- earnings: PE ratios, EPS growth, earnings consistency
- earnings_history: Growth trends and earnings surprise patterns

Scoring Methodology (0-100 scale) - 6 Factor Model:
1. Momentum Score (21%): RSI + MACD + Price momentum across timeframes
2. Trend Score (15%): Multi-timeframe trend analysis + MA alignment
3. Growth Score (19%): Earnings growth + Momentum + Consistency
4. Value Score (15%): PE ratio + PEG-adjusted valuation
5. Quality Score (15%): Volatility risk + Liquidity + Price stability
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

# Get database credentials - support both AWS and local modes
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")

def get_db_config():
    """Fetch database configuration from AWS Secrets Manager or environment variables."""
    if DB_SECRET_ARN:
        # AWS mode - use Secrets Manager
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
    else:
        # Local mode - use environment variables
        logger.info("Using local database configuration from environment variables")
        return {
            'host': os.environ.get("DB_HOST", "localhost"),
            'port': int(os.environ.get("DB_PORT", 5432)),
            'user': os.environ.get("DB_USER", "postgres"),
            'password': os.environ.get("DB_PASSWORD", "password"),
            'dbname': os.environ.get("DB_NAME", "stocks")
        }

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

        # Create table with correct schema (if not exists - preserves loadvaluemetrics data)
        logger.info("Creating stock_scores table if it doesn't exist...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_scores (
                symbol VARCHAR(50) PRIMARY KEY,
                composite_score DECIMAL(5,2),
                momentum_score DECIMAL(5,2),
                trend_score DECIMAL(5,2),
                value_score DECIMAL(5,2),
                quality_score DECIMAL(5,2),
                growth_score DECIMAL(5,2),
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
                -- Momentum component breakdown (6-component system)
                momentum_intraweek DECIMAL(5,2),
                momentum_short_term DECIMAL(5,2),
                momentum_medium_term DECIMAL(5,2),
                momentum_long_term DECIMAL(5,2),
                momentum_consistency DECIMAL(5,2),
                roc_10d DECIMAL(8,2),
                roc_20d DECIMAL(8,2),
                roc_60d DECIMAL(8,2),
                roc_120d DECIMAL(8,2),
                roc_252d DECIMAL(8,2),
                mom DECIMAL(10,2),
                mansfield_rs DECIMAL(8,2),
                -- Positioning component: Accumulation/Distribution Rating
                acc_dist_rating DECIMAL(5,2),
                -- Value metrics inputs (percentile-ranked from loadvaluemetrics.py)
                value_inputs JSONB,
                score_date DATE DEFAULT CURRENT_DATE,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        logger.info("✅ stock_scores table ready")

        # Add value_inputs column if it doesn't exist (for existing tables)
        try:
            cur.execute("""
                ALTER TABLE stock_scores
                ADD COLUMN IF NOT EXISTS value_inputs JSONB;
            """)
            conn.commit()
            logger.info("✅ value_inputs column ready")
        except psycopg2.Error as e:
            logger.warning(f"⚠️ Could not add value_inputs column: {e}")
            conn.rollback()

        # Create indexes (if not exists)
        logger.info("Creating indexes...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_stock_scores_date ON stock_scores(score_date);
            CREATE INDEX IF NOT EXISTS idx_stock_scores_updated ON stock_scores(last_updated);
        """)
        conn.commit()
        logger.info("✅ Indexes ready")

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

        # Get symbols that have price data (optimize for local testing)
        # Only process symbols with sufficient price history
        # Changed INNER to LEFT JOIN to include symbols without key_metrics (e.g., SPY)
        limit_clause = f"LIMIT {limit}" if limit else ""
        cur.execute(f"""
            SELECT DISTINCT s.symbol
            FROM stock_symbols s
            INNER JOIN price_daily p ON s.symbol = p.symbol
            LEFT JOIN key_metrics km ON s.symbol = km.ticker
            WHERE s.exchange IN ('NASDAQ', 'N', 'A', 'P')
              AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
            GROUP BY s.symbol
            HAVING COUNT(p.date) >= 20
            ORDER BY s.symbol
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

def calculate_downside_volatility(prices):
    """
    Calculate downside volatility (volatility only on negative return days).
    This measures risk more conservatively than total volatility.

    Industry standard used by Sortino ratio and downside risk metrics.
    """
    if len(prices) < 2:
        return None

    returns = np.diff(np.log(prices))
    # Only take negative returns (downside)
    downside_returns = returns[returns < 0]

    if len(downside_returns) == 0:
        return 0  # No downside, perfect case

    # Annualized downside volatility
    downside_vol = np.std(downside_returns) * np.sqrt(252) * 100
    return round(downside_vol, 2)

def calculate_beta(conn, symbol, stock_returns):
    """
    Calculate Beta - correlation of stock returns to S&P 500.

    Beta = Covariance(Stock Returns, Market Returns) / Variance(Market Returns)

    Industry standard for systematic risk measurement.
    Uses 252-day lookback (1 year of trading days).
    """
    if len(stock_returns) < 20:
        return None

    try:
        # Get S&P 500 returns for the same period
        cur = conn.cursor()
        cur.execute("""
            SELECT close
            FROM price_daily
            WHERE symbol = 'SPY'
            AND date >= CURRENT_DATE - INTERVAL '260 days'
            ORDER BY date DESC
            LIMIT 252
        """)

        spy_data = cur.fetchall()
        cur.close()

        if not spy_data or len(spy_data) < 20:
            return None

        # Convert to prices array (reverse order for chronological)
        spy_prices = np.array([float(row[0]) for row in reversed(spy_data)])

        # Calculate S&P 500 returns
        if len(spy_prices) != len(stock_returns):
            # Align to shorter series
            min_len = min(len(spy_prices), len(stock_returns))
            spy_prices = spy_prices[-min_len:]
            stock_returns_aligned = stock_returns[-min_len:]
        else:
            stock_returns_aligned = stock_returns

        spy_returns = np.diff(np.log(spy_prices))

        # Calculate covariance and variance
        covariance = np.cov(stock_returns_aligned, spy_returns)[0][1]
        market_variance = np.var(spy_returns, ddof=1)

        if market_variance == 0:
            return 1.0  # Neutral beta if no market variance

        beta = covariance / market_variance
        return round(beta, 3)

    except Exception as e:
        logger.warning(f"Could not calculate beta for {symbol}: {e}")
        return None

def calculate_liquidity_risk(volume_avg_30d, current_price, shares_outstanding=None):
    """
    Calculate Liquidity Risk based on daily volume relative to market cap.

    Liquidity Risk = Average Daily Volume / Market Cap (as %)
    Higher = Better liquidity (lower risk)
    Lower = Worse liquidity (higher risk)

    REQUIRES: volume_avg_30d must be present, will return None if not
    """
    if not volume_avg_30d or volume_avg_30d <= 0:
        return None  # FAIL: No volume data available

    # For now, use volume threshold as proxy
    # Higher daily volume = lower liquidity risk
    if volume_avg_30d > 10_000_000:
        return 100  # Excellent liquidity (mega-cap)
    elif volume_avg_30d > 1_000_000:
        return 80   # Very liquid
    elif volume_avg_30d > 500_000:
        return 60   # Good liquidity
    elif volume_avg_30d > 100_000:
        return 40   # Moderate liquidity
    elif volume_avg_30d > 50_000:
        return 20   # Poor liquidity
    else:
        return 0    # Very poor liquidity (illiquid)

def calculate_percentile_rank(value, all_values):
    """
    Calculate percentile rank of a value within a list of values.
    Returns a score from 0-100 representing the percentile.
    Returns None if data is insufficient.

    REQUIRES: Both value and all_values with sufficient data
    """
    if value is None or all_values is None or len(all_values) == 0:
        return None  # FAIL: No data available

    # Remove None values and convert to float
    valid_values = []
    for v in all_values:
        if v is not None:
            try:
                valid_values.append(float(v))
            except (ValueError, TypeError):
                # Skip non-numeric values
                continue

    if len(valid_values) == 0:
        return None  # FAIL: All values are None or non-numeric

    try:
        value_float = float(value)
    except (ValueError, TypeError):
        return None  # FAIL: Cannot convert value to float

    # Count how many values are less than or equal to this value
    rank = sum(1 for v in valid_values if v is not None and v <= value_float)

    # Calculate percentile (0-100)
    percentile = (rank / len(valid_values)) * 100

    return round(percentile, 2)

def fetch_all_quality_metrics(conn):
    """
    Fetch quality metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each metric.
    """
    try:
        cur = conn.cursor()

        # Fetch quality metrics from key_metrics and price_daily tables
        cur.execute("""
            SELECT
                km.return_on_equity_pct,
                km.return_on_assets_pct,
                km.gross_margin_pct,
                km.debt_to_equity,
                km.current_ratio,
                km.free_cashflow,
                km.net_income,
                pd.symbol
            FROM key_metrics km
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON km.ticker = pd.symbol
            WHERE km.return_on_equity_pct IS NOT NULL
               OR km.return_on_assets_pct IS NOT NULL
               OR km.gross_margin_pct IS NOT NULL
        """)

        rows = cur.fetchall()

        # Also fetch volatility data for all stocks
        cur.execute("""
            SELECT symbol, close, date
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '120 days'
            ORDER BY symbol, date
        """)

        price_rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary
        metrics = {
            'roe': [],
            'roa': [],
            'gross_margin': [],
            'debt_to_equity': [],
            'current_ratio': [],
            'fcf_to_ni': [],
            'volatility': []
        }

        # Process key metrics
        for row in rows:
            roe, roa, gross_margin, debt_to_equity, current_ratio, fcf, net_income, symbol = row

            if roe is not None:
                metrics['roe'].append(float(roe))
            if roa is not None:
                metrics['roa'].append(float(roa))
            if gross_margin is not None:
                metrics['gross_margin'].append(float(gross_margin))
            if debt_to_equity is not None:
                metrics['debt_to_equity'].append(float(debt_to_equity))
            if current_ratio is not None:
                metrics['current_ratio'].append(float(current_ratio))

            # Calculate FCF/NI ratio
            if fcf is not None and net_income is not None and net_income != 0:
                fcf_to_ni = (float(fcf) / float(net_income)) * 100
                metrics['fcf_to_ni'].append(fcf_to_ni)

        # Process volatility data (calculate for each symbol)
        symbol_prices = {}
        for row in price_rows:
            symbol, close, date = row
            if symbol not in symbol_prices:
                symbol_prices[symbol] = []
            symbol_prices[symbol].append(float(close))

        for symbol, prices in symbol_prices.items():
            if len(prices) >= 30:
                vol = calculate_volatility(prices[-30:])
                if vol is not None:
                    metrics['volatility'].append(vol)

        logger.info(f"📊 Loaded quality metrics for percentile calculation:")
        logger.info(f"   ROE: {len(metrics['roe'])} stocks")
        logger.info(f"   ROA: {len(metrics['roa'])} stocks")
        logger.info(f"   Gross Margin: {len(metrics['gross_margin'])} stocks")
        logger.info(f"   Debt/Equity: {len(metrics['debt_to_equity'])} stocks")
        logger.info(f"   Current Ratio: {len(metrics['current_ratio'])} stocks")
        logger.info(f"   FCF/NI: {len(metrics['fcf_to_ni'])} stocks")
        logger.info(f"   Volatility: {len(metrics['volatility'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch quality metrics for percentile ranking: {e}")
        return None

def fetch_all_growth_metrics(conn):
    """
    Fetch growth metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each metric.
    """
    try:
        cur = conn.cursor()

        # Fetch growth metrics from key_metrics table
        cur.execute("""
            SELECT
                km.revenue_growth_pct,
                km.earnings_growth_pct,
                km.earnings_q_growth_pct,
                km.gross_margin_pct,
                km.operating_margin_pct,
                km.return_on_equity_pct,
                km.payout_ratio,
                pd.symbol
            FROM key_metrics km
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON km.ticker = pd.symbol
            WHERE km.revenue_growth_pct IS NOT NULL
               OR km.earnings_growth_pct IS NOT NULL
               OR km.gross_margin_pct IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary
        metrics = {
            'revenue_growth': [],
            'earnings_growth': [],
            'earnings_q_growth': [],
            'gross_margin': [],
            'operating_margin': [],
            'margin_expansion': [],  # Combined gross + operating margin percentiles
            'sustainable_growth': []  # ROE × (1 - payout_ratio)
        }

        # Process growth metrics
        for row in rows:
            rev_growth, earn_growth, earn_q_growth, gross_margin, op_margin, roe, payout, symbol = row

            if rev_growth is not None:
                metrics['revenue_growth'].append(float(rev_growth))
            if earn_growth is not None:
                metrics['earnings_growth'].append(float(earn_growth))
            if earn_q_growth is not None:
                metrics['earnings_q_growth'].append(float(earn_q_growth))
            if gross_margin is not None:
                metrics['gross_margin'].append(float(gross_margin))
            if op_margin is not None:
                metrics['operating_margin'].append(float(op_margin))

            # Calculate sustainable growth rate: ROE × (1 - payout_ratio)
            if roe is not None and payout is not None:
                # If payout_ratio is > 1 (payout > 100%), cap it at 1
                payout_ratio = min(float(payout), 1.0)
                sustainable_growth = float(roe) * (1 - payout_ratio)
                metrics['sustainable_growth'].append(sustainable_growth)

        logger.info(f"📊 Loaded growth metrics for percentile calculation:")
        logger.info(f"   Revenue Growth: {len(metrics['revenue_growth'])} stocks")
        logger.info(f"   Earnings Growth: {len(metrics['earnings_growth'])} stocks")
        logger.info(f"   Earnings Q Growth: {len(metrics['earnings_q_growth'])} stocks")
        logger.info(f"   Gross Margin: {len(metrics['gross_margin'])} stocks")
        logger.info(f"   Operating Margin: {len(metrics['operating_margin'])} stocks")
        logger.info(f"   Sustainable Growth: {len(metrics['sustainable_growth'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch growth metrics for percentile ranking: {e}")
        return None

def calculate_accumulation_distribution(df, lookback_days=65):
    """
    Calculate IBD-style Accumulation/Distribution Rating (0-100 scale).
    Measures institutional buying/selling patterns over past 13 weeks (~65 trading days).

    Returns:
        float: 0-100 score where:
               80-100 = Heavy Accumulation (institutions buying aggressively)
               60-80  = Moderate Accumulation
               40-60  = Neutral
               20-40  = Moderate Distribution
               0-20   = Heavy Distribution (institutions selling)
    """
    if len(df) < lookback_days:
        return None

    # Get last N days
    recent_data = df.tail(lookback_days).copy()

    # Calculate average volume for threshold
    avg_volume = recent_data['volume'].mean()
    if avg_volume == 0:
        return None

    # Calculate daily accumulation/distribution scores
    acc_dist_score = 0
    total_weight = 0

    for i, (idx, row) in enumerate(recent_data.iterrows()):
        # Recency weight (more recent = higher weight)
        # Last 20 days = 2x weight, previous 45 days = 1x weight
        days_from_end = len(recent_data) - i - 1
        if days_from_end < 20:
            weight = 2.0
        else:
            weight = 1.0

        # Price change
        price_change = float(row['close']) - float(row['open'])

        # Volume above average?
        volume_ratio = float(row['volume']) / avg_volume if avg_volume > 0 else 1

        # Closing position (close near high = stronger)
        high = float(row['high'])
        low = float(row['low'])
        close = float(row['close'])

        if high > low:
            close_position = (close - low) / (high - low)
        else:
            close_position = 0.5

        # Daily score calculation
        daily_score = 0

        # ACCUMULATION SIGNALS (Institutions Buying)
        if price_change > 0 and volume_ratio > 1.25:
            # Strong accumulation - up day with heavy volume
            daily_score = 2.0 * weight
            # Bonus if close near high
            if close_position > 0.8:
                daily_score += 0.5 * weight

        elif price_change > 0 and volume_ratio > 1.0:
            # Moderate accumulation - up day with above-avg volume
            daily_score = 1.0 * weight

        elif price_change > 0 and volume_ratio < 0.8:
            # Weak buying (not institutional)
            daily_score = 0.3 * weight

        # DISTRIBUTION SIGNALS (Institutions Selling)
        elif price_change < 0 and volume_ratio > 1.25:
            # Strong distribution - down day with heavy volume
            daily_score = -2.0 * weight
            # Extra penalty if close near low
            if close_position < 0.2:
                daily_score -= 0.5 * weight

        elif price_change < 0 and volume_ratio > 1.0:
            # Moderate distribution - down day with above-avg volume
            daily_score = -1.0 * weight

        elif price_change < 0 and volume_ratio < 0.8:
            # Weak selling (not significant)
            daily_score = -0.3 * weight

        acc_dist_score += daily_score
        total_weight += weight

    # Normalize to 0-100 scale
    # Maximum possible score ≈ 2.5 * total_weight (all strong accumulation)
    max_possible = 2.5 * total_weight

    # Convert to 0-100 scale (50 = neutral)
    normalized_score = 50 + (acc_dist_score / max_possible) * 50
    normalized_score = max(0, min(100, normalized_score))

    return round(normalized_score, 2)

def get_stock_data_from_database(conn, symbol, quality_metrics=None, growth_metrics=None):
    """Get stock data from database tables and calculate all scores."""
    try:
        cur = conn.cursor()

        # Get price data from price_daily table (last 120 days for calculations to ensure 65+ trading days)
        cur.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM price_daily
            WHERE symbol = %s
            AND date >= CURRENT_DATE - INTERVAL '120 days'
            ORDER BY date DESC
            LIMIT 120
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

        # Get latest technical data including momentum indicators
        cur.execute("""
            SELECT rsi, macd, macd_hist, sma_20, sma_50, atr, mom, roc,
                   roc_20d, roc_60d, roc_120d, roc_252d, mansfield_rs
            FROM technical_data_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))

        tech_data = cur.fetchone()
        if tech_data and len(tech_data) >= 13:
            rsi, macd, macd_hist, sma_20, sma_50, atr, mom_10d, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d, mansfield_rs = tech_data
        else:
            # Calculate basic technical indicators from price data
            prices = df['close'].astype(float).values
            rsi = calculate_rsi(prices)
            macd = calculate_macd(prices)
            macd_hist = None
            sma_20 = df['close'].tail(20).mean() if len(df) >= 20 else current_price
            sma_50 = df['close'].tail(50).mean() if len(df) >= 50 else current_price
            sma_200 = df['close'].tail(200).mean() if len(df) >= 200 else current_price
            atr = None
            mom_10d = None
            roc_10d = None
            roc_20d = None
            roc_60d = None
            roc_120d = None
            roc_252d = None
            mansfield_rs = None

            # Calculate ROC for multiple timeframes if not in technical_data_daily
            if len(df) >= 21:
                roc_20d = ((prices[-1] - prices[-21]) / prices[-21]) * 100
            if len(df) >= 61:
                roc_60d = ((prices[-1] - prices[-61]) / prices[-61]) * 100
            if len(df) >= 121:
                roc_120d = ((prices[-1] - prices[-121]) / prices[-121]) * 100
            if len(df) >= 253:
                roc_252d = ((prices[-1] - prices[-253]) / prices[-253]) * 100

        # Get dual momentum metrics from momentum_metrics table
        cur.execute("""
            SELECT momentum_12m_1, momentum_6m, momentum_3m, risk_adjusted_momentum,
                   price_vs_sma_50, price_vs_sma_200, price_vs_52w_high,
                   volatility_12m
            FROM momentum_metrics
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))

        momentum_data = cur.fetchone()
        if momentum_data and len(momentum_data) >= 8:
            momentum_12m_1, momentum_6m, momentum_3m, risk_adjusted_momentum, \
            price_vs_sma_50, price_vs_sma_200, price_vs_52w_high, volatility_12m = momentum_data
        else:
            # No dual momentum data available
            momentum_12m_1 = None
            momentum_6m = None
            momentum_3m = None
            risk_adjusted_momentum = None
            price_vs_sma_50 = None
            price_vs_sma_200 = None
            price_vs_52w_high = None
            volatility_12m = None

        prices = df['close'].astype(float).values
        volatility_30d = calculate_volatility(prices)

        # Calculate IBD-style Accumulation/Distribution Rating
        acc_dist_rating = calculate_accumulation_distribution(df, lookback_days=65)

        # Get earnings data for PE ratio calculation only
        cur.execute("""
            SELECT eps_actual, quarter
            FROM earnings_history
            WHERE symbol = %s
            AND quarter >= CURRENT_DATE - INTERVAL '24 months'
            ORDER BY quarter DESC
            LIMIT 4
        """, (symbol,))

        earnings_data = cur.fetchall()
        pe_ratio = None

        if earnings_data:
            # Calculate trailing 12-month EPS for PE ratio
            eps_values = [float(row[0]) for row in earnings_data if row[0] is not None]
            if eps_values and len(eps_values) >= 4:
                trailing_eps = sum(eps_values[:4])  # Last 4 quarters
                if trailing_eps > 0:
                    pe_ratio = current_price / trailing_eps

        # Market cap placeholder - we don't have this data, so set to None
        market_cap = None

        # Get sentiment data for Sentiment Score
        try:
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
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Sentiment table query failed for {symbol}: {e}")
            sentiment_score_raw = None
            news_count = 0

        # Get analyst recommendations for Sentiment Score
        try:
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
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Analyst recommendations table query failed for {symbol}: {e}")
            analyst_score = None

        # Get real positioning data from positioning_metrics table
        try:
            cur.execute("""
                SELECT
                    institutional_ownership,
                    insider_ownership,
                    short_percent_of_float,
                    institution_count
                FROM positioning_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))
            positioning_data = cur.fetchone()
            institutional_ownership = None
            insider_ownership = None
            short_percent_of_float = None
            institution_count = None
            if positioning_data:
                institutional_ownership = float(positioning_data[0]) if positioning_data[0] is not None else None
                insider_ownership = float(positioning_data[1]) if positioning_data[1] is not None else None
                short_percent_of_float = float(positioning_data[2]) if positioning_data[2] is not None else None
                institution_count = int(positioning_data[3]) if positioning_data[3] is not None else None
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Positioning metrics table query failed for {symbol}: {e}")
            institutional_ownership = None
            insider_ownership = None
            short_percent_of_float = None
            institution_count = None

        # ============================================================
        # Risk Score Calculation - Best-in-Class Framework
        # Pure Risk Minimization Model (Option A - Defensive Focus)
        # Formula: 30% volatility + 25% downside_vol + 25% drawdown + 15% beta + 5% liquidity
        # LOWER volatility/drawdown/beta = HIGHER score (safer stocks)
        # REQUIRES ALL DATA or None - NO NEUTRAL DEFAULTS
        # ============================================================
        risk_score = None
        risk_inputs = {
            'volatility_12m_pct': None,
            'downside_volatility_pct': None,
            'max_drawdown_52w_pct': None,
            'beta': None,
            'liquidity_risk': None
        }

        try:
            # Calculate risk components with graceful fallbacks
            prices = df['close'].astype(float).values

            # Calculate volatility directly from price data (30-day)
            volatility_12m_pct = calculate_volatility(prices)  # Annualized
            if volatility_12m_pct is None:
                logger.warning(f"{symbol}: Cannot calculate volatility - insufficient price data")
                volatility_12m_pct = 50  # Default to mid-range if missing

            # Calculate downside volatility (only on down days)
            downside_volatility = calculate_downside_volatility(prices)
            if downside_volatility is None:
                logger.warning(f"{symbol}: Cannot calculate downside volatility")
                downside_volatility = volatility_12m_pct * 0.7  # Estimate as 70% of total vol

            # Calculate beta (correlation to S&P 500) with fallback
            price_returns = np.diff(np.log(prices))
            beta = calculate_beta(conn, symbol, price_returns)
            if beta is None:
                logger.warning(f"{symbol}: Cannot calculate beta - SPY data missing, using neutral 1.0")
                beta = 1.0  # Neutral beta if SPY data unavailable

            # Calculate liquidity risk (based on volume) with fallback
            liquidity_risk = calculate_liquidity_risk(volume_avg_30d, current_price)
            if liquidity_risk is None:
                logger.warning(f"{symbol}: Cannot calculate liquidity risk - no volume data, using 50 (neutral)")
                liquidity_risk = 50  # Neutral liquidity score if no volume

            # Try to get drawdown from risk_metrics table with fallback calculation
            max_drawdown_52w_pct = None
            try:
                cur.execute("""
                    SELECT max_drawdown_52w_pct
                    FROM risk_metrics
                    WHERE symbol = %s
                    ORDER BY date DESC LIMIT 1
                """, (symbol,))
                drawdown_data = cur.fetchone()
                if drawdown_data and drawdown_data[0] is not None:
                    max_drawdown_52w_pct = float(drawdown_data[0])
            except:
                logger.warning(f"{symbol}: risk_metrics table not accessible, calculating drawdown from price data")

            # Fallback: Calculate drawdown from price data if not in risk_metrics
            if max_drawdown_52w_pct is None:
                try:
                    # Find high in last 252 trading days (~1 year)
                    prices_array = df['close'].astype(float).values
                    if len(prices_array) >= 20:
                        max_price = prices_array.max()
                        current_price_val = prices_array[-1]
                        if max_price > 0:
                            max_drawdown_52w_pct = ((max_price - current_price_val) / max_price) * 100
                        else:
                            max_drawdown_52w_pct = 20  # Default
                    else:
                        max_drawdown_52w_pct = 20  # Default if insufficient data
                except:
                    max_drawdown_52w_pct = 20  # Default

            logger.info(f"{symbol}: Calculated risk components - Vol={volatility_12m_pct:.1f}%, Downside={downside_volatility:.1f}%, Drawdown={max_drawdown_52w_pct:.1f}%, Beta={beta:.2f}, Liquidity={liquidity_risk:.0f}")

            # All components available (with fallbacks) - calculate risk score
            # Convert all to 0-100 scale for risk components
            vol_percentile = max(0, min(100, 100 - (volatility_12m_pct * 2)))  # Inverted: lower vol = higher score
            downside_percentile = max(0, min(100, 100 - (downside_volatility * 3)))  # Inverted
            drawdown_percentile = max(0, min(100, 100 - max_drawdown_52w_pct))  # Inverted: lower drawdown = higher score
            beta_percentile = max(0, min(100, 100 - (beta * 50)))  # Scale: 1.0=50, 0.5=75, 1.5=25
            liquidity_percentile = liquidity_risk

            # Calculate composite risk score with new weighting
            # 30% vol + 25% downside + 25% drawdown + 15% beta + 5% liquidity
            risk_score = (
                vol_percentile * 0.30 +
                downside_percentile * 0.25 +
                drawdown_percentile * 0.25 +
                beta_percentile * 0.15 +
                liquidity_percentile * 0.05
            )
            risk_score = max(0, min(100, risk_score))

            # Store risk inputs for display
            risk_inputs['volatility_12m_pct'] = round(volatility_12m_pct, 4)
            risk_inputs['downside_volatility_pct'] = round(downside_volatility, 2)
            risk_inputs['max_drawdown_52w_pct'] = round(max_drawdown_52w_pct, 2)
            risk_inputs['beta'] = round(beta, 3)
            risk_inputs['liquidity_risk'] = round(liquidity_percentile, 1)

            logger.info(f"{symbol} Risk Score: {risk_score:.1f} (Vol_pct={vol_percentile:.0f}, Downside_pct={downside_percentile:.0f}, Drawdown_pct={drawdown_percentile:.0f}, Beta_pct={beta_percentile:.0f}, Liquidity_pct={liquidity_percentile:.0f})")

        except Exception as e:
            import traceback
            logger.error(f"{symbol}: Risk calculation failed: {e}")
            logger.error(traceback.format_exc())
            conn.rollback()
            # Use neutral/default risk score rather than failing
            risk_score = 50
            logger.warning(f"{symbol}: Using neutral default risk_score of 50")

        # Get quality metrics from key_metrics table for percentile-based quality score
        stock_roe = None
        stock_roa = None
        stock_gross_margin = None
        stock_debt_to_equity = None
        stock_current_ratio = None
        stock_fcf_to_ni = None

        try:
            cur.execute("""
                SELECT
                    return_on_equity_pct,
                    return_on_assets_pct,
                    gross_margin_pct,
                    debt_to_equity,
                    current_ratio,
                    free_cashflow,
                    net_income
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            km_data = cur.fetchone()
            if km_data:
                roe, roa, gross_margin, debt_to_equity, current_ratio, fcf, net_income = km_data
                stock_roe = float(roe) if roe is not None else None
                stock_roa = float(roa) if roa is not None else None
                stock_gross_margin = float(gross_margin) if gross_margin is not None else None
                stock_debt_to_equity = float(debt_to_equity) if debt_to_equity is not None else None
                stock_current_ratio = float(current_ratio) if current_ratio is not None else None

                # Calculate FCF/NI ratio
                if fcf is not None and net_income is not None and net_income != 0:
                    stock_fcf_to_ni = (float(fcf) / float(net_income)) * 100
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Key metrics table query failed for {symbol}: {e}")

        # Get growth metrics from key_metrics table for percentile-based growth score
        stock_revenue_growth = None
        stock_earnings_growth = None
        stock_earnings_q_growth = None
        stock_gross_margin_growth = None
        stock_operating_margin_growth = None
        stock_sustainable_growth = None

        try:
            cur.execute("""
                SELECT
                    revenue_growth_pct,
                    earnings_growth_pct,
                    earnings_q_growth_pct,
                    gross_margin_pct,
                    operating_margin_pct,
                    return_on_equity_pct,
                    payout_ratio
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            growth_data = cur.fetchone()
            if growth_data:
                rev_growth, earn_growth, earn_q_growth, gross_margin, op_margin, roe_for_growth, payout = growth_data
                stock_revenue_growth = float(rev_growth) if rev_growth is not None else None
                stock_earnings_growth = float(earn_growth) if earn_growth is not None else None
                stock_earnings_q_growth = float(earn_q_growth) if earn_q_growth is not None else None
                stock_gross_margin_growth = float(gross_margin) if gross_margin is not None else None
                stock_operating_margin_growth = float(op_margin) if op_margin is not None else None

                # Calculate sustainable growth rate: ROE × (1 - payout_ratio)
                if roe_for_growth is not None and payout is not None:
                    payout_ratio = min(float(payout), 1.0)  # Cap at 1.0
                    stock_sustainable_growth = float(roe_for_growth) * (1 - payout_ratio)
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Growth metrics query failed for {symbol}: {e}")

        # Calculate individual scores (0-100 scale)

        # ============================================================
        # Momentum Score - 6-Component Industry-Standard System
        # Based on academic momentum research (Jegadeesh & Titman, AQR, Dimensional)
        # ============================================================

        # Component 1: Intraweek Trend Confirmation (10 points) - Technical Indicators
        # Confirms current momentum through RSI, MACD, and price vs SMA50
        intraweek_confirmation = 5  # Start neutral

        # RSI sub-component (0-4 points) - overbought/oversold detection
        rsi_score = 2  # Default neutral
        if rsi is not None:
            if rsi > 70:
                rsi_score = 3.5 + (min(rsi, 100) - 70) * 0.05  # 3.5-4 for strong overbought
            elif rsi > 60:
                rsi_score = 2.75 + (rsi - 60) * 0.025  # 2.75-3 for bullish
            elif rsi > 50:
                rsi_score = 2.25 + (rsi - 50) * 0.01  # 2.25-2.5 for mild bullish
            elif rsi > 40:
                rsi_score = 1.75 + (rsi - 40) * 0.005  # 1.75-2 for neutral
            elif rsi > 30:
                rsi_score = 0.5 + (rsi - 30) * 0.025  # 0.5-1.25 for oversold
            else:
                rsi_score = max(0, rsi * 0.033)  # 0-1 for very oversold

        # MACD sub-component (0-3 points) - momentum acceleration
        macd_score = 1.5  # Default neutral
        if macd is not None and macd_hist is not None:
            if macd > 0:
                macd_score = 1.5 + min(abs(macd) * 0.5, 1.5)  # 1.5-3 for positive
            else:
                macd_score = max(0, 1.5 + macd * 0.5)  # 0-1.5 for negative

            # Bonus for MACD histogram (momentum acceleration)
            if macd_hist and macd_hist > 0:
                macd_score = min(3, macd_score + 0.25)

        # Price vs SMA50 sub-component (0-3 points) - trend confirmation
        sma50_score = 1.5  # Default neutral
        if price_vs_sma_50 is not None:
            if price_vs_sma_50 > 5:
                sma50_score = 2.5 + min(price_vs_sma_50 * 0.2, 0.5)  # 2.5-3 for strong above
            elif price_vs_sma_50 > 0:
                sma50_score = 1.5 + (price_vs_sma_50 * 0.2)  # 1.5-2.5 for above
            elif price_vs_sma_50 > -5:
                sma50_score = 0.5 + (price_vs_sma_50 + 5) * 0.2  # 0.5-1.5 for slightly below
            else:
                sma50_score = max(0, 0.5 + (price_vs_sma_50 + 5) * 0.1)  # 0-0.5 for well below

        intraweek_confirmation = rsi_score + macd_score + sma50_score

        # Component 2: Short-Term Momentum (25 points) - Days/Weeks
        # Primary: 3-month return from momentum_metrics (industry standard shortest window)
        short_term_momentum = 12.5  # Start neutral

        if momentum_3m is not None:
            # Use 3-month return from momentum_metrics
            # 3M return thresholds: >10%=excellent, >5%=strong, >0%=positive
            if momentum_3m > 10:
                short_term_momentum = 25  # Excellent 3M performance
            elif momentum_3m > 5:
                short_term_momentum = 18 + (momentum_3m - 5) * 1.4
            elif momentum_3m > 0:
                short_term_momentum = 12.5 + (momentum_3m) * 1.0
            elif momentum_3m > -5:
                short_term_momentum = 6.5 + (momentum_3m + 5) * 1.2
            elif momentum_3m > -10:
                short_term_momentum = 1.5 + (momentum_3m + 10) * 1.0
            else:
                short_term_momentum = 0  # Poor 3M performance

        # Component 3: Medium-Term Momentum (25 points) - Weeks/Months
        # Primary: 6-month return from momentum_metrics (industry standard)
        medium_term_momentum = 12.5  # Start neutral

        if momentum_6m is not None:
            # Use 6-month return from momentum_metrics (primary)
            # 6M return thresholds: >15%=excellent, >10%=strong, >5%=good, >0%=positive
            if momentum_6m > 15:
                medium_term_momentum = 25  # Excellent 6M performance
            elif momentum_6m > 10:
                medium_term_momentum = 20 + (momentum_6m - 10) * 1.0
            elif momentum_6m > 5:
                medium_term_momentum = 15 + (momentum_6m - 5) * 1.0
            elif momentum_6m > 0:
                medium_term_momentum = 12.5 + (momentum_6m) * 0.5
            elif momentum_6m > -5:
                medium_term_momentum = 8 + (momentum_6m + 5) * 0.9
            elif momentum_6m > -10:
                medium_term_momentum = 4 + (momentum_6m + 10) * 0.8
            elif momentum_6m > -15:
                medium_term_momentum = 1 + (momentum_6m + 15) * 0.6
            else:
                medium_term_momentum = 0  # Poor 6M performance

        # Component 4: Long-Term Momentum (15 points) - Months
        # Primary: 12-month return excluding last month from momentum_metrics (academic standard)
        longer_term_momentum = 7.5  # Start neutral

        if momentum_12m_1 is not None:
            # Use 12M-1 return from momentum_metrics (academic standard for momentum factor)
            # 12M-1 thresholds: >25%=excellent, >15%=strong, >10%=good, >0%=positive
            if momentum_12m_1 > 25:
                longer_term_momentum = 15  # Excellent 12M performance
            elif momentum_12m_1 > 15:
                longer_term_momentum = 12 + (momentum_12m_1 - 15) * 0.3
            elif momentum_12m_1 > 10:
                longer_term_momentum = 9.5 + (momentum_12m_1 - 10) * 0.5
            elif momentum_12m_1 > 0:
                longer_term_momentum = 7.5 + (momentum_12m_1) * 0.2
            elif momentum_12m_1 > -10:
                longer_term_momentum = 4.5 + (momentum_12m_1 + 10) * 0.3
            elif momentum_12m_1 > -15:
                longer_term_momentum = 2.5 + (momentum_12m_1 + 15) * 0.4
            elif momentum_12m_1 > -25:
                longer_term_momentum = 0.5 + (momentum_12m_1 + 25) * 0.1
            else:
                longer_term_momentum = 0  # Poor 12M performance

        # Component 5: Momentum Consistency (10 points) - Multi-timeframe alignment
        # Primary: Check alignment across 3M, 6M, 12M returns from momentum_metrics
        # Fallback: Check alignment across ROC timeframes from technical indicators
        consistency_score = 5  # Start neutral

        # Check alignment across timeframes
        timeframe_signals = []

        # Use dual momentum metrics if available (preferred)
        if momentum_3m is not None and momentum_6m is not None and momentum_12m_1 is not None:
            timeframe_signals.append(1 if momentum_3m > 0 else -1)
            timeframe_signals.append(1 if momentum_6m > 0 else -1)
            timeframe_signals.append(1 if momentum_12m_1 > 0 else -1)

            # Bonus for trend strength alignment (price vs MA alignment)
            trend_alignment_bonus = 0
            if price_vs_sma_50 is not None and price_vs_sma_200 is not None:
                if price_vs_sma_50 > 0 and price_vs_sma_200 > 0:
                    trend_alignment_bonus = 2  # Price above both MAs
                elif price_vs_sma_50 < 0 and price_vs_sma_200 < 0:
                    trend_alignment_bonus = -1  # Price below both MAs (bearish consistency)
        else:
            # Fallback to ROC-based signals
            if roc_10d is not None:
                timeframe_signals.append(1 if roc_10d > 0 else -1)
            if roc_60d is not None:
                timeframe_signals.append(1 if roc_60d > 0 else -1)
            if roc_120d is not None:
                timeframe_signals.append(1 if roc_120d > 0 else -1)
            trend_alignment_bonus = 0

        if len(timeframe_signals) >= 2:
            signal_sum = sum(timeframe_signals)
            signal_count = len(timeframe_signals)

            if abs(signal_sum) == signal_count:
                # All timeframes agree (all positive or all negative)
                consistency_score = 8 + trend_alignment_bonus
            elif abs(signal_sum) == signal_count - 1:
                # Mostly aligned (2 out of 3 agree)
                consistency_score = 6 + (trend_alignment_bonus * 0.5)
            elif signal_sum == 0:
                # Mixed signals - conflicting momentum
                consistency_score = 3
            else:
                consistency_score = 5

            consistency_score = max(0, min(10, consistency_score))

        # Calculate final momentum score (0-100 scale)
        # Components: 10 + 25 + 25 + 15 + 10 = 85 pts (scaled to 100)
        raw_momentum_score = (intraweek_confirmation + short_term_momentum + medium_term_momentum +
                             longer_term_momentum + consistency_score)
        # Scale from 85-point scale to 100-point scale
        momentum_score = (raw_momentum_score / 85) * 100
        momentum_score = max(0, min(100, momentum_score))

        # Trend Score (multi-timeframe analysis + MA alignment)
        # REQUIRE trend_score - must calculate from data
        trend_score = None

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

        # ============================================================
        # Value Score - Percentile-Based Valuation Analysis (Industry Standard)
        # 4-component system using percentile ranking for value metrics
        # Components: P/E (35%), P/B (25%), P/S (20%), PEG (20%)
        # ============================================================
        # REQUIRE value_score - must calculate from data
        value_score = None

        # Fetch value_inputs from stock_scores table to get percentile ranks
        try:
            cur.execute("""
                SELECT value_inputs
                FROM stock_scores
                WHERE symbol = %s
            """, (symbol,))

            value_data_row = cur.fetchone()
            if value_data_row and value_data_row[0]:
                value_inputs = value_data_row[0]

                # Handle both dict (from JSONB) and string (from JSON) types
                if isinstance(value_inputs, str):
                    value_inputs = json.loads(value_inputs)

                # Extract percentile ranks from value_inputs
                pe_percentile = value_inputs.get('pe_percentile_rank')
                pb_percentile = value_inputs.get('pb_percentile_rank')
                ps_percentile = value_inputs.get('ps_percentile_rank')
                peg_percentile = value_inputs.get('peg_percentile_rank')

                # Calculate value score from percentile ranks (weighted average)
                # Lower P/E, P/B, P/S, PEG = higher percentile, which is better for value
                value_components = []

                if pe_percentile is not None:
                    pe_contribution = (float(pe_percentile) / 100) * 35  # 35% weight
                    value_components.append(pe_contribution)

                if pb_percentile is not None:
                    pb_contribution = (float(pb_percentile) / 100) * 25  # 25% weight
                    value_components.append(pb_contribution)

                if ps_percentile is not None:
                    ps_contribution = (float(ps_percentile) / 100) * 20  # 20% weight
                    value_components.append(ps_contribution)

                if peg_percentile is not None:
                    peg_contribution = (float(peg_percentile) / 100) * 20  # 20% weight
                    value_components.append(peg_contribution)

                # Calculate final value score from available components
                if value_components:
                    value_score = sum(value_components)
                    value_score = max(0, min(100, value_score))

                    logger.debug(f"{symbol} Value Components: PE={pe_percentile}, "
                                f"PB={pb_percentile}, PS={ps_percentile}, PEG={peg_percentile}")
        except (psycopg2.Error, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"{symbol}: Could not calculate percentile-based value score: {e}")

        # Fallback: Use neutral value score if data missing
        if value_score is None:
            value_score = 50
            logger.warning(f"{symbol}: Using neutral default value_score of 50")

        # ============================================================
        # Quality Score - Percentile-Based Industry Standard (Fama-French, MSCI, AQR)
        # 4-component system using percentile ranking for market-relative scoring
        # ============================================================
        # REQUIRE quality_score - must calculate from data
        quality_score = None

        # Only calculate percentile-based quality score if we have quality_metrics data
        if quality_metrics is not None:
            # Component 1: Profitability (40 points) - ROE, ROA, Gross Margin
            profitability_score = 0

            if stock_roe is not None:
                roe_percentile = calculate_percentile_rank(stock_roe, quality_metrics.get('roe', []))
                profitability_score += (roe_percentile / 100) * 16  # 40% of 40 points

            if stock_roa is not None:
                roa_percentile = calculate_percentile_rank(stock_roa, quality_metrics.get('roa', []))
                profitability_score += (roa_percentile / 100) * 12  # 30% of 40 points

            if stock_gross_margin is not None:
                margin_percentile = calculate_percentile_rank(stock_gross_margin, quality_metrics.get('gross_margin', []))
                profitability_score += (margin_percentile / 100) * 12  # 30% of 40 points

            # Component 2: Financial Strength (30 points) - Debt/Equity (inverted), Current Ratio
            strength_score = 0

            if stock_debt_to_equity is not None:
                # Invert debt_to_equity - lower is better, so negate for percentile calculation
                debt_percentile = calculate_percentile_rank(-stock_debt_to_equity,
                                                            [-d for d in quality_metrics.get('debt_to_equity', [])])
                strength_score += (debt_percentile / 100) * 18  # 60% of 30 points

            if stock_current_ratio is not None:
                current_ratio_percentile = calculate_percentile_rank(stock_current_ratio,
                                                                     quality_metrics.get('current_ratio', []))
                strength_score += (current_ratio_percentile / 100) * 12  # 40% of 30 points

            # Component 3: Earnings Quality (20 points) - FCF/NI ratio
            earnings_quality_score = 0

            if stock_fcf_to_ni is not None:
                fcf_ni_percentile = calculate_percentile_rank(stock_fcf_to_ni, quality_metrics.get('fcf_to_ni', []))
                earnings_quality_score = (fcf_ni_percentile / 100) * 20

            # Component 4: Stability (10 points) - Volatility (inverted, lower is better)
            stability_score = 0

            if volatility_30d is not None:
                # Invert volatility - lower is better, so negate for percentile calculation
                volatility_percentile = calculate_percentile_rank(-volatility_30d,
                                                                  [-v for v in quality_metrics.get('volatility', [])])
                stability_score = (volatility_percentile / 100) * 10

            # Calculate final quality score
            quality_score = profitability_score + strength_score + earnings_quality_score + stability_score
            quality_score = max(0, min(100, quality_score))

            logger.debug(f"{symbol} Quality Components: Profitability={profitability_score:.2f}, "
                        f"Strength={strength_score:.2f}, Earnings Quality={earnings_quality_score:.2f}, "
                        f"Stability={stability_score:.2f}")
        else:
            # Fallback: Use neutral quality score if metrics not available
            quality_score = 50
            logger.warning(f"{symbol}: No quality metrics available, using neutral default quality_score of 50")

        # ============================================================
        # Growth Score - Percentile-Based TTM Metrics (Industry Standard)
        # 5-component system using percentile ranking for market-relative growth scoring
        # ============================================================
        # REQUIRE growth_score - must calculate from data
        growth_score = None

        # Only calculate percentile-based growth score if we have growth_metrics data
        if growth_metrics is not None:
            # Component 1: Revenue Growth (25 points) - TTM revenue growth percentile
            revenue_growth_score = 0
            if stock_revenue_growth is not None:
                rev_percentile = calculate_percentile_rank(stock_revenue_growth, growth_metrics.get('revenue_growth', []))
                revenue_growth_score = (rev_percentile / 100) * 25

            # Component 2: Earnings Growth (30 points) - TTM earnings growth percentile
            earnings_growth_score = 0
            if stock_earnings_growth is not None:
                earn_percentile = calculate_percentile_rank(stock_earnings_growth, growth_metrics.get('earnings_growth', []))
                earnings_growth_score = (earn_percentile / 100) * 30

            # Component 3: Earnings Acceleration (20 points) - Quarterly vs annual growth comparison
            earnings_accel_score = 0
            if stock_earnings_q_growth is not None and stock_earnings_growth is not None:
                # Positive when Q growth > annual growth (accelerating)
                acceleration = stock_earnings_q_growth - stock_earnings_growth
                accel_percentile = calculate_percentile_rank(acceleration,
                                                            [q - a for q, a in zip(growth_metrics.get('earnings_q_growth', []),
                                                                                  growth_metrics.get('earnings_growth', []))
                                                            if q is not None and a is not None])
                earnings_accel_score = (accel_percentile / 100) * 20

            # Component 4: Margin Expansion (15 points) - Gross + Operating margin percentiles
            margin_expansion_score = 0
            if stock_gross_margin_growth is not None:
                gross_margin_percentile = calculate_percentile_rank(stock_gross_margin_growth,
                                                                    growth_metrics.get('gross_margin', []))
                margin_expansion_score += (gross_margin_percentile / 100) * 7.5  # 50% of 15 points

            if stock_operating_margin_growth is not None:
                op_margin_percentile = calculate_percentile_rank(stock_operating_margin_growth,
                                                                growth_metrics.get('operating_margin', []))
                margin_expansion_score += (op_margin_percentile / 100) * 7.5  # 50% of 15 points

            # Component 5: Sustainable Growth (10 points) - ROE × (1 - payout_ratio)
            sustainable_growth_score = 0
            if stock_sustainable_growth is not None:
                sustainable_percentile = calculate_percentile_rank(stock_sustainable_growth,
                                                                   growth_metrics.get('sustainable_growth', []))
                sustainable_growth_score = (sustainable_percentile / 100) * 10

            # Calculate final growth score
            growth_score = (revenue_growth_score + earnings_growth_score + earnings_accel_score +
                          margin_expansion_score + sustainable_growth_score)
            growth_score = max(0, min(100, growth_score))

            logger.debug(f"{symbol} Growth Components: Revenue={revenue_growth_score:.2f}, "
                        f"Earnings={earnings_growth_score:.2f}, Acceleration={earnings_accel_score:.2f}, "
                        f"Margin Expansion={margin_expansion_score:.2f}, Sustainable={sustainable_growth_score:.2f}")
        else:
            # Fallback: Use neutral growth score if metrics not available
            growth_score = 50
            logger.warning(f"{symbol}: No growth metrics available, using neutral default growth_score of 50")

        # Positioning Score (Real institutional and insider data + Accumulation/Distribution)
        # 5-component system: Institutional(25%), Insider(20%), Short(20%), Acc/Dist(25%), Count(10%)
        # NO FALLBACK VALUES - if data is missing, positioning_score will be None
        positioning_score = None

        # Only calculate if we have at least some positioning data
        if any([institutional_ownership is not None,
                insider_ownership is not None,
                short_percent_of_float is not None,
                institution_count is not None,
                acc_dist_rating is not None]):

            inst_score = 0
            insider_score = 0
            short_score = 0
            acc_dist_score = 0
            count_score = 0

            # Institutional ownership component (0-25 points) - 25%
            # Optimal range: 40-70% (strong institutional support but not too crowded)
            if institutional_ownership is not None:
                if 40 <= institutional_ownership <= 70:
                    inst_score = 25  # Optimal institutional ownership
                elif 30 <= institutional_ownership < 40:
                    inst_score = 22  # Good institutional ownership
                elif 70 < institutional_ownership <= 80:
                    inst_score = 20  # High but acceptable
                elif 20 <= institutional_ownership < 30:
                    inst_score = 16  # Moderate institutional ownership
                elif 80 < institutional_ownership <= 90:
                    inst_score = 14  # Very high (crowded trade risk)
                elif institutional_ownership < 20:
                    inst_score = 10  # Low institutional interest
                else:  # > 90%
                    inst_score = 7   # Extremely crowded

            # Insider ownership component (0-20 points) - 20%
            # Higher is better (skin in the game)
            if insider_ownership is not None:
                if insider_ownership >= 15:
                    insider_score = 20  # Very strong insider ownership
                elif insider_ownership >= 10:
                    insider_score = 18  # Strong insider ownership
                elif insider_ownership >= 5:
                    insider_score = 14  # Good insider ownership
                elif insider_ownership >= 2:
                    insider_score = 10  # Moderate insider ownership
                elif insider_ownership >= 1:
                    insider_score = 6   # Low insider ownership
                else:
                    insider_score = 2   # Very low/no insider ownership

            # Short interest component (0-20 points) - 20%
            # Lower is better (less bearish pressure)
            if short_percent_of_float is not None:
                if short_percent_of_float < 2:
                    short_score = 20  # Very low short interest
                elif short_percent_of_float < 5:
                    short_score = 18  # Low short interest
                elif short_percent_of_float < 10:
                    short_score = 14  # Moderate short interest
                elif short_percent_of_float < 15:
                    short_score = 10  # High short interest
                elif short_percent_of_float < 20:
                    short_score = 5   # Very high short interest
                else:
                    short_score = 0   # Extremely high short interest

            # Accumulation/Distribution Rating component (0-25 points) - 25%
            # IBD-style institutional buying/selling patterns
            # 0-100 scale where 80-100=Heavy Accumulation, 0-20=Heavy Distribution
            if acc_dist_rating is not None:
                # Scale 0-100 rating to 0-25 points (25% of positioning score)
                acc_dist_score = (acc_dist_rating / 100) * 25

            # Institution count component (0-10 points) - 10%
            # More institutions = broader confidence
            if institution_count is not None:
                if institution_count >= 500:
                    count_score = 10  # Very broad institutional support
                elif institution_count >= 300:
                    count_score = 9   # Broad institutional support
                elif institution_count >= 200:
                    count_score = 7   # Good institutional support
                elif institution_count >= 100:
                    count_score = 5   # Moderate institutional support
                elif institution_count >= 50:
                    count_score = 3   # Limited institutional support
                else:
                    count_score = 0   # Very limited institutional support

            positioning_score = inst_score + insider_score + short_score + acc_dist_score + count_score
            positioning_score = max(0, min(100, positioning_score))

        # Sentiment Score (Analyst ratings + Market sentiment)
        # Start with neutral 50, adjust based on available data
        sentiment_score = 50

        # Analyst sentiment component (0-50 points)
        if analyst_score is not None:
            # Scale from 1-5 to 0-50: (score-1)/4 * 50
            analyst_component = ((analyst_score - 1) / 4) * 50
            sentiment_score = analyst_component
        else:
            sentiment_score = 50  # Neutral if no analyst data

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

        # Composite Score (5-factor weighted average - Sentiment EXCLUDED)
        # Weights: Momentum (22.11%), Trend (15.79%), Growth (20.00%), Value (15.79%),
        #          Quality (15.79%), Positioning (10.53%)
        # Sentiment (5%) redistributed proportionally to all other factors
        # If positioning_score is None, redistribute its 10.53% weight proportionally to other factors
        if positioning_score is not None:
            composite_score = (
                momentum_score * 0.2211 +                # Short-term momentum (21% + 5%*21/95)
                trend_score * 0.1579 +                   # Trend alignment (15% + 5%*15/95)
                growth_score * 0.2000 +                  # Growth drivers (19% + 5%*19/95)
                value_score * 0.1579 +                   # Valuation (15% + 5%*15/95)
                quality_score * 0.1579 +                 # Quality/Risk (15% + 5%*15/95)
                positioning_score * 0.1053               # Institutional positioning (10% + 5%*10/95)
            )
        else:
            # Redistribute positioning's 10.53% weight proportionally across other factors
            # New weights: Momentum (24.71%), Trend (17.65%), Growth (22.36%), Value (17.65%),
            #              Quality (17.65%)
            composite_score = (
                momentum_score * 0.2471 +                # Short-term momentum
                trend_score * 0.1765 +                   # Trend alignment
                growth_score * 0.2236 +                  # Growth drivers
                value_score * 0.1765 +                   # Valuation
                quality_score * 0.1765                   # Quality/Risk
            )

        cur.close()

        # Clamp all scores to 0-100 and ensure DECIMAL(5,2) compatibility (max 999.99)
        def clamp_score(score):
            return max(0, min(100, float(score)))

        return {
            'symbol': symbol,
            'composite_score': float(round(clamp_score(composite_score), 2)),
            'momentum_score': float(round(clamp_score(momentum_score), 2)),
            'trend_score': float(round(clamp_score(trend_score), 2)),
            'value_score': float(round(clamp_score(value_score), 2)),
            'quality_score': float(round(clamp_score(quality_score), 2)),
            'growth_score': float(round(clamp_score(growth_score), 2)),
            'positioning_score': float(round(clamp_score(positioning_score), 2)),
            'sentiment_score': float(round(clamp_score(sentiment_score), 2)),
            'risk_score': float(round(clamp_score(risk_score), 2)) if risk_score is not None else None,
            'risk_inputs': risk_inputs,
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
            'pe_ratio': float(round(pe_ratio, 2)) if pe_ratio else None,
            # Momentum components (6-component system)
            'momentum_intraweek': float(round(intraweek_confirmation, 2)),
            'momentum_short_term': float(round(short_term_momentum, 2)),
            'momentum_medium_term': float(round(medium_term_momentum, 2)),
            'momentum_long_term': float(round(longer_term_momentum, 2)),
            'momentum_consistency': float(round(consistency_score, 2)),
            'roc_10d': float(round(roc_10d, 2)) if roc_10d is not None else None,
            'roc_20d': float(round(roc_20d, 2)) if roc_20d is not None else None,
            'roc_60d': float(round(roc_60d, 2)) if roc_60d is not None else None,
            'roc_120d': float(round(roc_120d, 2)) if roc_120d is not None else None,
            'roc_252d': float(round(roc_252d, 2)) if roc_252d is not None else None,
            'mom': float(round(mom_10d, 2)) if mom_10d is not None else None,
            'mansfield_rs': float(round(mansfield_rs, 2)) if mansfield_rs is not None else None,
            # Positioning component: Accumulation/Distribution Rating
            'acc_dist_rating': float(round(acc_dist_rating, 2)) if acc_dist_rating is not None else None
        }

    except Exception as e:
        import traceback
        logger.error(f"❌ Error calculating scores for {symbol}: {e}")
        logger.error(traceback.format_exc())
        conn.rollback()  # Rollback aborted transaction
        return None

def save_stock_score(conn, score_data):
    """Save stock score to database."""
    try:
        cur = conn.cursor()

        # Convert risk_inputs dict to JSON string for JSONB column
        if score_data.get('risk_inputs') is not None:
            score_data['risk_inputs'] = json.dumps(score_data['risk_inputs'])

        # Upsert query
        upsert_sql = """
        INSERT INTO stock_scores (
            symbol, composite_score, momentum_score, trend_score, value_score, quality_score, growth_score,
            positioning_score, sentiment_score, risk_score, risk_inputs,
            rsi, macd, sma_20, sma_50, volume_avg_30d, current_price,
            price_change_1d, price_change_5d, price_change_30d, volatility_30d,
            market_cap, pe_ratio,
            momentum_intraweek, momentum_short_term, momentum_medium_term, momentum_long_term,
            momentum_consistency,
            roc_10d, roc_20d, roc_60d, roc_120d, roc_252d, mom, mansfield_rs,
            acc_dist_rating,
            score_date, last_updated
        ) VALUES (
            %(symbol)s, %(composite_score)s, %(momentum_score)s, %(trend_score)s, %(value_score)s, %(quality_score)s, %(growth_score)s,
            %(positioning_score)s, %(sentiment_score)s, %(risk_score)s, %(risk_inputs)s,
            %(rsi)s, %(macd)s, %(sma_20)s, %(sma_50)s, %(volume_avg_30d)s, %(current_price)s,
            %(price_change_1d)s, %(price_change_5d)s, %(price_change_30d)s, %(volatility_30d)s,
            %(market_cap)s, %(pe_ratio)s,
            %(momentum_intraweek)s, %(momentum_short_term)s, %(momentum_medium_term)s, %(momentum_long_term)s,
            %(momentum_consistency)s,
            %(roc_10d)s, %(roc_20d)s, %(roc_60d)s, %(roc_120d)s, %(roc_252d)s, %(mom)s, %(mansfield_rs)s,
            %(acc_dist_rating)s,
            CURRENT_DATE, CURRENT_TIMESTAMP
        ) ON CONFLICT (symbol) DO UPDATE SET
            composite_score = EXCLUDED.composite_score,
            momentum_score = EXCLUDED.momentum_score,
            trend_score = EXCLUDED.trend_score,
            value_score = EXCLUDED.value_score,
            quality_score = EXCLUDED.quality_score,
            growth_score = EXCLUDED.growth_score,
            positioning_score = EXCLUDED.positioning_score,
            sentiment_score = EXCLUDED.sentiment_score,
            risk_score = EXCLUDED.risk_score,
            risk_inputs = EXCLUDED.risk_inputs,
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
            momentum_intraweek = EXCLUDED.momentum_intraweek,
            momentum_short_term = EXCLUDED.momentum_short_term,
            momentum_medium_term = EXCLUDED.momentum_medium_term,
            momentum_long_term = EXCLUDED.momentum_long_term,
            momentum_consistency = EXCLUDED.momentum_consistency,
            roc_10d = EXCLUDED.roc_10d,
            roc_20d = EXCLUDED.roc_20d,
            roc_60d = EXCLUDED.roc_60d,
            roc_120d = EXCLUDED.roc_120d,
            roc_252d = EXCLUDED.roc_252d,
            mom = EXCLUDED.mom,
            mansfield_rs = EXCLUDED.mansfield_rs,
            acc_dist_rating = EXCLUDED.acc_dist_rating,
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
        # Enable autocommit for better transaction handling
        conn.autocommit = True

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

        # Fetch all quality metrics for percentile-based quality scoring
        logger.info("📊 Fetching quality metrics for percentile-based scoring...")
        quality_metrics = fetch_all_quality_metrics(conn)
        if quality_metrics is None:
            logger.error("❌ CRITICAL: Failed to fetch quality metrics - stocks without quality data will FAIL to score")
            return False

        # Fetch all growth metrics for percentile-based growth scoring
        logger.info("📊 Fetching growth metrics for percentile-based scoring...")
        growth_metrics = fetch_all_growth_metrics(conn)
        if growth_metrics is None:
            logger.error("❌ CRITICAL: Failed to fetch growth metrics - stocks without growth data will FAIL to score")
            return False

        # Process each symbol
        successful = 0
        failed = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})")

                # Create a fresh cursor for each stock to avoid transaction abort issues
                score_data = get_stock_data_from_database(conn, symbol, quality_metrics, growth_metrics)
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