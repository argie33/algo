#!/usr/bin/env python3
"""
Stock Scores Loader - Multi-Factor Stock Scoring System

DEPLOYMENT MODES:
  • AWS Production: Uses DB_SECRET_ARN (Lambda/ECS)
    └─ Fetches DB credentials from AWS Secrets Manager
    └─ Calculates comprehensive stock scores
    └─ Writes to PostgreSQL RDS database

  • Local Development: Uses DB_HOST/DB_USER/DB_PASSWORD env vars
    └─ Falls back if DB_SECRET_ARN not set
    └─ Same calculation logic for testing

VERSION INFO:
VERIFIED: 2025-10-26 Fresh reload completed successfully - 5,315/5,315 rows (100%) ✅
Trigger: 20251225_150000 - AWS deployment final scoring engine (rebuild needed)
Calculates and stores improved stock scores using multi-factor analysis.
Deploy stock scores calculation to populate comprehensive quality metrics.
TRIGGER: 20251225 - Rebuild Docker image and deploy stock scores on AWS
Trigger: 20251220-FINAL - Update stale technical_data_daily after infrastructure deployment
CRITICAL FIX: Wrapped sentiment, analyst_recommendations, and institutional_positioning
queries in try-except blocks to handle missing tables gracefully with rollback.
Trigger: Force rebuild to test AWS deployment with correct environment variables.

Data Sources:
- price_daily: Price data, volume, volatility, multi-timeframe momentum
- technical_data_daily: RSI, MACD, moving averages with alignment analysis
- earnings: PE ratios, EPS growth, earnings consistency
- earnings_history: Growth trends and earnings surprise patterns

Scoring Methodology (0-100 scale) - 7 Factor Model:
1. Momentum Score (22%): Technical confirmation (RSI + MACD + SMA50) + 3m/6m/12m-1 price momentum percentiles
2. Growth Score (20%): Earnings growth rate + Revenue acceleration + Profit margin trends
3. Value Score (16%): PE/PB/PS/PEG percentile rankings + EV/Revenue ratio
4. Quality Score (16%): ROE + ROA + Debt ratios + FCF/NI ratio + Earnings beat consistency
5. Stability Score (15%): Volatility + Downside deviation + Max drawdown + Beta percentiles
6. Positioning Score (12%): Institutional ownership + Insider ownership + Short interest + Accumulation/Distribution + Institution count
7. Sentiment Score (5%): Analyst ratings + News sentiment + AAII sentiment indicators

Version History:
- v2.0: Enhanced multi-factor scoring with improved technical + fundamental analysis
- v1.13: Add fallback to stock_prices if stock_symbols is empty
- v1.12: Use stock_symbols table like other loaders
- v1.11: Clean slate - drop and recreate table with correct schema
- v1.10: Robust migration with step-by-step table creation
"""

import os
import sys
import json
import decimal
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import boto3

# Database configuration
DB_SECRET_ARN = os.getenv('DB_SECRET_ARN')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE CONNECTION FUNCTION
# ============================================================================
def get_db_credentials_from_aws():
    """Fetch DB credentials from AWS Secrets Manager"""
    try:
        secret_str = boto3.client("secretsmanager", region_name="us-east-1") \
                         .get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        logger.error(f"❌ Failed to get credentials from AWS Secrets Manager: {e}")
        return None

def get_db_connection():
    """Create PostgreSQL database connection"""
    try:
        # Try AWS Secrets Manager first if DB_SECRET_ARN is set
        if DB_SECRET_ARN:
            creds = get_db_credentials_from_aws()
            if creds:
                conn = psycopg2.connect(
                    host=creds["host"],
                    port=creds["port"],
                    user=creds["user"],
                    password=creds["password"],
                    database=creds["dbname"]
                )
                logger.info(f"✅ Connected to database: {creds['dbname']} (AWS)")
                return conn

        # Try local socket connection first (peer authentication)
        try:
            conn = psycopg2.connect(
                dbname=DB_NAME,
                user="stocks"
            )
            logger.info(f"✅ Connected to database: {DB_NAME} (socket)")
            return conn
        except:
            pass

        # Fall back to environment variables
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        logger.info(f"✅ Connected to database: {DB_NAME}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None

# ============================================================================
# TECHNICAL INDICATOR FUNCTIONS
# ============================================================================
def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index (RSI)"""
    try:
        if prices is None or len(prices) < period + 1:
            return None

        prices = np.array(prices, dtype=float)
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)
    except Exception as e:
        logger.debug(f"RSI calculation error: {e}")
        return None

def calculate_macd(prices, fast=12, slow=26):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    try:
        if prices is None or len(prices) < slow:
            return None

        prices = np.array(prices, dtype=float)
        ema_fast = prices[-fast:].mean()  # Simplified EMA
        ema_slow = prices[-slow:].mean()  # Simplified EMA
        macd = ema_fast - ema_slow
        return float(macd) if macd else None
    except Exception as e:
        logger.debug(f"MACD calculation error: {e}")
        return None

def calculate_sma(prices, period=20):
    """Calculate Simple Moving Average (SMA)"""
    try:
        if prices is None or len(prices) < period:
            return None
        prices = np.array(prices, dtype=float)
        sma = np.mean(prices[-period:])
        return float(sma) if sma else None
    except Exception as e:
        logger.debug(f"SMA calculation error: {e}")
        return None

def calculate_roc(prices, period=12):
    """Calculate Rate of Change (ROC)"""
    try:
        if prices is None or len(prices) < period + 1:
            return None
        prices = np.array(prices, dtype=float)
        roc = ((prices[-1] - prices[-period-1]) / prices[-period-1]) * 100
        return float(roc) if roc else None
    except Exception as e:
        logger.debug(f"ROC calculation error: {e}")
        return None

def calculate_volatility(prices, period=20):
    """Calculate volatility (standard deviation) of price returns"""
    try:
        if prices is None or len(prices) < period:
            return None
        prices = np.array(prices, dtype=float)
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns[-period:]) * np.sqrt(252) * 100  # Annualized
        return float(volatility) if volatility else None
    except Exception as e:
        logger.debug(f"Volatility calculation error: {e}")
        return None

def calculate_momentum_score(rsi, macd):
    """Calculate momentum score from RSI and MACD"""
    try:
        if rsi is None or macd is None:
            return None
        # Simple momentum combination (0-100 scale)
        score = (rsi + 50) / 2 if macd > 0 else (rsi) / 2
        return float(max(0, min(100, score)))
    except Exception as e:
        logger.debug(f"Momentum score calculation error: {e}")
        return None

def calculate_composite_score(scores):
    """Calculate weighted composite score from factor scores"""
    try:
        if not scores or all(v is None for v in scores.values()):
            return None
        # Weight factors
        weights = {
            'momentum': 0.22,
            'growth': 0.20,
            'value': 0.16,
            'quality': 0.16,
            'stability': 0.15,
            'positioning': 0.12,
            'sentiment': 0.05
        }
        composite = sum(scores.get(k, 0) * v for k, v in weights.items() if scores.get(k) is not None)
        return float(max(0, min(100, composite)))
    except Exception as e:
        logger.debug(f"Composite score calculation error: {e}")
        return None

def clear_old_stock_scores(conn):
    """Clear old stock scores before loading new ones to avoid stale data."""
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM stock_scores;")
        conn.commit()
        logger.info("🗑️  Cleared all old stock_scores data - fresh load starting")
        cur.close()
        return True
    except Exception as e:
        logger.error(f"❌ Failed to clear stock_scores: {e}")
        conn.rollback()
        return False

def create_stock_scores_table(conn):
    """Create stock_scores table if it doesn't exist."""
    try:
        cur = conn.cursor()

        # Create table with COMPREHENSIVE schema - ALL individual indicator values
        logger.info("Creating stock_scores table with ALL indicator values...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_scores (
                symbol VARCHAR(50) PRIMARY KEY,
                company_name VARCHAR(255),
                composite_score DECIMAL(5,2),
                momentum_score DECIMAL(5,2),
                value_score DECIMAL(5,2),
                quality_score DECIMAL(5,2),
                growth_score DECIMAL(5,2),
                positioning_score DECIMAL(5,2),
                sentiment_score DECIMAL(5,2),
                stability_score DECIMAL(5,2),

                -- Momentum Components
                rsi DECIMAL(5,2),
                macd DECIMAL(5,2),
                sma50 DECIMAL(5,2),
                momentum_3m DECIMAL(10,2),
                momentum_6m DECIMAL(10,2),
                momentum_12m DECIMAL(10,2),
                price_vs_sma_50 DECIMAL(10,2),
                price_vs_sma_200 DECIMAL(10,2),
                price_vs_52w_high DECIMAL(10,2),

                -- Value Components
                pe_ratio DECIMAL(10,2),
                forward_pe DECIMAL(10,2),
                pb_ratio DECIMAL(10,2),
                ps_ratio DECIMAL(10,2),
                peg_ratio DECIMAL(10,2),
                ev_revenue DECIMAL(10,2),

                -- Quality Components
                roe DECIMAL(5,2),
                roa DECIMAL(5,2),
                debt_ratio DECIMAL(5,2),
                fcf_ni_ratio DECIMAL(5,2),
                earnings_surprise DECIMAL(5,2),

                -- Growth Components
                earnings_growth DECIMAL(5,2),
                revenue_growth DECIMAL(5,2),
                margin_trend DECIMAL(5,2),

                -- Stability Components
                volatility DECIMAL(10,2),
                downside_volatility DECIMAL(10,2),
                max_drawdown DECIMAL(10,2),
                beta DECIMAL(5,2),

                -- Positioning Components
                institutional_ownership DECIMAL(5,2),
                insider_ownership DECIMAL(5,2),
                short_interest DECIMAL(5,2),
                accumulation_distribution DECIMAL(5,2),
                institution_count DECIMAL(5,2),

                -- Sentiment Components
                analyst_rating DECIMAL(5,2),
                news_sentiment DECIMAL(5,2),
                aaii_sentiment DECIMAL(5,2),

                score_date DATE DEFAULT CURRENT_DATE,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        logger.info("✅ stock_scores table ready")


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
    Returns ALL symbols for comprehensive coverage - processes stocks with limited or no price history.
    This ensures all 5,312 stocks get scored, not just those with 20+ days of price data."""
    try:
        cur = conn.cursor()
        logger.info("🔍 Executing stock symbols query...")

        # Get ALL symbols to score (removed 20-day minimum price history requirement)
        # Process all stocks including those with limited or no price history
        # User requirement: "we need all the inputs i see many with null" and "we should be calculating them...we'll get values for them all now"
        limit_clause = f"LIMIT {limit}" if limit else ""
        cur.execute(f"""
            SELECT DISTINCT s.symbol
            FROM stock_symbols s
            LEFT JOIN price_daily p ON s.symbol = p.symbol
            LEFT JOIN key_metrics km ON s.symbol = km.ticker
            WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca')
              AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
            GROUP BY s.symbol
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

# RSI, MACD, Volatility calculations moved to scoring_engine.py
# They are now imported at the top of this file

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

def fetch_beta_from_database(conn, symbol):
    """
    Fetch beta from database (populated by loaddailycompanydata.py from yfinance).

    Beta is pre-fetched from yfinance.ticker.info by the ingestion loader.
    Uses a fresh cursor to isolate from main transaction to prevent abort cascades.
    Returns None if not found - NO FALLBACK (real data only).
    """
    try:
        # Use a fresh cursor for this operation to avoid transaction abort propagation
        cur = conn.cursor()

        # Try PRIMARY SOURCE: risk_metrics (where loaddailycompanydata populates beta)
        try:
            cur.execute("""
                SELECT beta FROM risk_metrics
                WHERE symbol = %s AND beta IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """, (symbol,))
            result = cur.fetchone()
            if result:
                cur.close()
                return result[0]
        except Exception as e:
            # Ignore individual table errors - they don't abort main transaction due to try-except
            logger.debug(f"Beta not in risk_metrics for {symbol}: {e}")
            pass

        # Try key_metrics as backup
        try:
            cur.execute("""
                SELECT beta FROM key_metrics
                WHERE symbol = %s AND beta IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """, (symbol,))
            result = cur.fetchone()
            if result:
                cur.close()
                return result[0]
        except Exception as e:
            logger.debug(f"Beta not in key_metrics for {symbol}: {e}")
            pass

        # Try quality_metrics as fallback
        try:
            cur.execute("""
                SELECT beta FROM quality_metrics
                WHERE symbol = %s AND beta IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """, (symbol,))
            result = cur.fetchone()
            if result:
                cur.close()
                return result[0]
        except Exception as e:
            logger.debug(f"Beta not in quality_metrics for {symbol}: {e}")
            pass

        # Try financial_ratios as last resort
        try:
            cur.execute("""
                SELECT beta FROM financial_ratios
                WHERE symbol = %s AND beta IS NOT NULL
                LIMIT 1
            """, (symbol,))
            result = cur.fetchone()
            if result:
                cur.close()
                return result[0]
        except Exception as e:
            logger.debug(f"Beta not in financial_ratios for {symbol}: {e}")
            pass

        cur.close()
        return None  # Return None - caller will use neutral 1.0 fallback
    except Exception as e:
        logger.debug(f"Could not fetch beta from database for {symbol}: {e}")
        return None

def calculate_liquidity_risk(volume_avg_30d, current_price, shares_outstanding=None):
    """
    Calculate Liquidity Risk based on daily volume relative to market cap.

    Liquidity Risk = Average Daily Volume / Market Cap (as %)
    Higher = Better liquidity (lower risk)
    Lower = Worse liquidity (higher risk)

    Returns None if insufficient data. Returns normalized score (0-1) if data available.
    """
    if not volume_avg_30d or volume_avg_30d <= 0:
        return None  # No real volume data available

    # If we have market cap data, calculate normalized liquidity
    if current_price is not None and current_price > 0 and shares_outstanding is not None and shares_outstanding > 0:
        market_cap = current_price * shares_outstanding
        liquidity_ratio = volume_avg_30d / market_cap
        # Normalize to 0-1 scale (typical liquidity ratios range 0-0.3)
        # Use log scale to compress range: min(liquidity_ratio / 0.3, 1.0)
        normalized_liquidity = min(liquidity_ratio / 0.3, 1.0)
        return normalized_liquidity

    # If no market cap data, return None (insufficient data for calculation)
    return None

def calculate_volume_consistency_score(prices, volumes):
    """
    Calculate Volume Consistency Score: measures how consistent trading volume is.

    Higher score = more consistent volume (better liquidity)
    Lower score = volatile volume (worse liquidity)
    Returns 0-100 score or None if insufficient data.
    """
    if volumes is None or len(volumes) < 20:
        return None

    volumes = np.array(volumes)
    volumes = volumes[volumes > 0]  # Filter out zero volumes

    if len(volumes) < 20:
        return None

    # Calculate coefficient of variation (standard deviation / mean)
    mean_vol = np.mean(volumes)
    if mean_vol == 0:
        return None

    cv = np.std(volumes) / mean_vol
    # Convert CV to 0-100 score: lower CV = higher score
    # CV typically ranges 0.5-2.0 for liquid stocks
    score = max(0, 100 - (cv * 50))  # Inverted so high consistency = high score
    return min(100, score)

def calculate_turnover_velocity_score(volume_avg_30d, market_cap):
    """
    Calculate Turnover Velocity Score: measures how quickly shares turn over.

    Higher score = shares turn over more frequently (better liquidity)
    Lower score = lower turnover (worse liquidity)
    Returns 0-100 score or None if insufficient data.

    DATA INTEGRITY: Returns None if data is insufficient (no fallback to 0.0)
    """
    # Return None if either data is missing or invalid
    if volume_avg_30d is None or market_cap is None:
        return None

    # Return None if either is zero/negative (insufficient real data)
    if volume_avg_30d <= 0 or market_cap <= 0:
        return None

    # Annualized turnover: (daily volume * 252 trading days) / market cap
    annualized_turnover = (volume_avg_30d * 252) / market_cap

    # Score: typical range is 0-5, scale to 0-100
    # 5+ = excellent (100), <0.1 = very poor (0)
    if annualized_turnover >= 5:
        return 100.0
    elif annualized_turnover <= 0.1:
        return 0.0
    else:
        # Linear scale between 0.1 and 5
        return (annualized_turnover - 0.1) / (5 - 0.1) * 100

def calculate_volatility_volume_ratio_score(prices, volumes):
    """
    Calculate Volatility/Volume Ratio Score: measures price stability relative to volume.

    Higher score = price stable despite volume (good liquidity)
    Lower score = price volatile relative to volume (poor liquidity)
    Returns 0-100 score or None if insufficient data.
    """
    if prices is None or len(prices) < 20 or volumes is None or len(volumes) < 20:
        return None

    prices = np.array(prices)
    volumes = np.array(volumes)
    volumes = volumes[volumes > 0]

    if len(prices) < 20 or len(volumes) < 20:
        return None

    # Calculate daily returns volatility
    returns = np.diff(prices) / prices[:-1]
    returns_vol = np.std(returns)

    # Calculate normalized volume (standard deviation)
    mean_vol = np.mean(volumes)
    if mean_vol == 0:
        return None
    vol_normalized = np.std(volumes) / mean_vol

    # Ratio: lower is better (stable prices, high consistent volume)
    # Invert so high ratio = low score, low ratio = high score
    if vol_normalized == 0:
        ratio = 0
    else:
        ratio = returns_vol / vol_normalized if vol_normalized > 0 else 0

    # Convert to 0-100 scale
    # Typical good range: ratio < 0.05, poor range: ratio > 0.2
    if ratio <= 0.05:
        return 100.0
    elif ratio >= 0.2:
        return 0.0
    else:
        return 100 - ((ratio - 0.05) / (0.2 - 0.05) * 100)

def calculate_daily_spread_score(prices):
    """
    Calculate Daily Spread Score: measures bid-ask spread using historical price data over wide window.

    Uses all available historical data (not just recent) to capture typical spread behavior.
    Higher score = tighter spreads (better liquidity)
    Lower score = wider spreads (worse liquidity)
    Returns 0-100 score or None if insufficient data.
    """
    if prices is None or len(prices) < 20:
        return None

    # Use ALL available price history (wide window) not just recent data
    # This captures typical bid-ask behavior over full dataset
    prices = np.array(prices)

    # Calculate average absolute price change as spread proxy (wider window = more representative)
    price_changes = np.abs(np.diff(prices)) / prices[:-1]
    avg_spread = np.mean(price_changes)

    # Convert to percentage and score
    spread_pct = avg_spread * 100

    # Score: <0.1% = excellent (100), >2% = poor (0) - full 0-100 scale
    # REAL DATA INTEGRITY: No fallback values, use full range
    if spread_pct <= 0.1:
        return 100.0
    elif spread_pct >= 2.0:
        return 0.0  # Wide spreads = poor liquidity (return 0, not fallback 20)
    else:
        # Linear scale between 0.1 and 2.0
        return 100 - ((spread_pct - 0.1) / (2.0 - 0.1) * 100)

def calculate_downside_volatility_score(prices):
    """
    Calculate Downside Volatility Score: measures volatility of negative returns (downside risk).

    Downside volatility (downside deviation) = sqrt(sum of (min(return, 0))^2 / n)
    Only penalizes volatility on the downside - ignores upside volatility.
    Lower downside volatility = better (less downside risk).
    Returns 0-100 score or None if insufficient data.
    """
    if prices is None or len(prices) < 20:
        return None

    prices = np.array(prices, dtype=float)

    # Calculate daily returns
    if len(prices) < 2:
        return None

    returns = np.diff(prices) / prices[:-1]

    # Calculate downside deviation: sqrt(mean(min(return, 0)^2))
    # Only consider negative returns for downside volatility
    downside_returns = np.minimum(returns, 0)
    downside_variance = np.mean(downside_returns ** 2)

    if downside_variance <= 0:
        return 100.0  # No downside volatility detected

    downside_volatility = np.sqrt(downside_variance)

    # Convert to percentage
    downside_vol_pct = downside_volatility * 100

    # Score: <0.5% = excellent (100), >3% = poor (0)
    # Lower downside volatility = higher score (better)
    if downside_vol_pct <= 0.5:
        return 100.0
    elif downside_vol_pct >= 3.0:
        return 0.0
    else:
        # Linear scale between 0.5 and 3.0
        return 100 - ((downside_vol_pct - 0.5) / (3.0 - 0.5) * 100)

def calculate_z_score_normalized(value, all_values):
    """
    Calculate z-score normalized rank of a value within a list of values.
    Returns a score from 0-100 representing z-score normalized position.
    Mean = 50 (0 std devs), ±1σ = 34-66, ±3σ = 5-95
    Returns None if data is insufficient.

    REQUIRES: Both value and all_values with sufficient data
    """
    if value is None or all_values is None or len(all_values) == 0:
        return None  # FAIL: No data available

    # Remove None values, NaN, and Infinity, convert to float
    valid_values = []
    for v in all_values:
        if v is not None:
            try:
                # Handle numpy arrays/Series by extracting scalar value
                if hasattr(v, '__len__') and not isinstance(v, (str, bytes)):
                    # It's array-like, extract first element
                    v_scalar = v.flat[0] if hasattr(v, 'flat') else v[0]
                else:
                    v_scalar = v
                v_float = float(v_scalar)
                # Skip NaN and Infinity values
                if not (np.isnan(v_float) or np.isinf(v_float)):
                    valid_values.append(v_float)
            except (ValueError, TypeError, IndexError):
                # Skip non-numeric values
                continue

    if len(valid_values) < 2:
        return None  # FAIL: Need at least 2 values for std dev calculation

    try:
        # Handle numpy arrays/Series for value as well
        if hasattr(value, '__len__') and not isinstance(value, (str, bytes)):
            value_scalar = value.flat[0] if hasattr(value, 'flat') else value[0]
        else:
            value_scalar = value
        value_float = float(value_scalar)
        # Skip if value itself is NaN or Infinity
        if np.isnan(value_float) or np.isinf(value_float):
            return None  # FAIL: Value is NaN or Infinity
    except (ValueError, TypeError, IndexError):
        return None  # FAIL: Cannot convert value to float

    # Calculate mean and standard deviation
    mean = np.mean(valid_values)
    std_dev = np.std(valid_values)

    # Handle zero std dev (all values identical)
    if std_dev == 0:
        return None  # Return None when data has no variation (cannot calculate meaningful score)

    # Calculate z-score: (value - mean) / std_dev
    z_score = (value_float - mean) / std_dev

    # Convert z-score to 0-100 scale: center at 50, scale by 15 (±3σ = 5-95)
    # This caps extreme outliers naturally while still rewarding them
    normalized_score = 50 + (z_score * 15)

    # Clamp to 0-100 range to prevent extreme scores
    normalized_score = max(0, min(100, normalized_score))

    # CRITICAL: Convert to native Python float to avoid NumPy type issues
    # NumPy scalars cause "ambiguous truth value" errors in boolean context
    return float(round(float(normalized_score), 2))

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
                km.operating_margin_pct,
                km.profit_margin_pct,
                km.debt_to_equity,
                km.current_ratio,
                km.quick_ratio,
                km.free_cashflow,
                km.net_income,
                km.ebitda,
                km.total_debt,
                km.total_cash,
                km.operating_cashflow,
                km.payout_ratio,
                pd.symbol
            FROM key_metrics km
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON km.ticker = pd.symbol
            WHERE km.return_on_equity_pct IS NOT NULL
               OR km.return_on_assets_pct IS NOT NULL
               OR km.gross_margin_pct IS NOT NULL
               OR km.operating_margin_pct IS NOT NULL
               OR km.profit_margin_pct IS NOT NULL
               OR km.debt_to_equity IS NOT NULL
               OR km.current_ratio IS NOT NULL
               OR km.payout_ratio IS NOT NULL
        """)

        rows = cur.fetchall()

        # Fetch volatility data for all stocks (CRITICAL FIX: Added LIMIT to prevent millions of rows being fetched)
        # Instead of fetching ALL 120 days x 5000+ symbols = millions of rows, use aggregation
        cur.execute("""
            SELECT symbol,
                   stddev_pop(CAST(close AS FLOAT)) as volatility,
                   COUNT(*) as data_points
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY symbol
            HAVING COUNT(*) >= 20
        """)

        volatility_rows = cur.fetchall()
        price_rows = []  # Not needed anymore, using aggregated data
        cur.close()

        # Build metrics dictionary
        metrics = {
            'roe': [],
            'roa': [],
            'gross_margin': [],
            'operating_margin': [],
            'profit_margin': [],
            'debt_to_equity': [],
            'current_ratio': [],
            'quick_ratio': [],
            'fcf_to_ni': [],
            'operating_cf_to_ni': [],
            'roic': [],
            'volatility': [],
            'payout_ratio': []
        }

        # Process key metrics
        for row in rows:
            roe, roa, gross_margin, op_margin, profit_margin, debt_to_equity, current_ratio, quick_ratio, fcf, net_income, ebitda, total_debt, total_cash, ocf, payout, symbol = row

            if roe is not None:
                metrics['roe'].append(float(roe))
            if roa is not None:
                metrics['roa'].append(float(roa))
            if gross_margin is not None:
                metrics['gross_margin'].append(float(gross_margin))
            if op_margin is not None:
                metrics['operating_margin'].append(float(op_margin))
            if profit_margin is not None:
                metrics['profit_margin'].append(float(profit_margin))
            if debt_to_equity is not None:
                metrics['debt_to_equity'].append(float(debt_to_equity))
            if current_ratio is not None:
                metrics['current_ratio'].append(float(current_ratio))
            if quick_ratio is not None:
                metrics['quick_ratio'].append(float(quick_ratio))
            if payout is not None and payout >= 0 and payout <= 2.0:  # Reasonable bounds (0-200%)
                metrics['payout_ratio'].append(float(payout))

            # Calculate FCF/NI ratio
            if fcf is not None and net_income is not None and net_income != 0:
                fcf_to_ni = (float(fcf) / float(net_income)) * 100
                metrics['fcf_to_ni'].append(fcf_to_ni)

            # Calculate Operating CF/NI ratio
            if ocf is not None and net_income is not None and net_income != 0:
                ocf_to_ni = (float(ocf) / float(net_income)) * 100
                metrics['operating_cf_to_ni'].append(ocf_to_ni)

            # Calculate ROIC = EBIT(DA) / Invested Capital
            # ROIC = EBITDA / (Total Debt + Equity - Cash)
            # Simplified: Uses EBITDA as proxy for NOPAT (before tax)
            if ebitda is not None and total_debt is not None and total_cash is not None:
                try:
                    ebitda_val = float(ebitda)
                    debt_val = float(total_debt)
                    cash_val = float(total_cash)

                    # Invested Capital = Debt + Equity - Cash
                    # Since we don't have equity directly, use: IC = Debt + (Market Cap relationship)
                    # Simpler approach: IC = Debt - Cash + (implied from EBITDA and returns)
                    # Most direct: Use EBITDA / (Total Debt + Total Equity - Cash)
                    # For our purposes: ROIC ~ EBITDA / Capital Employed

                    invested_capital = debt_val + cash_val  # Conservative estimate
                    if invested_capital > 0:
                        roic_pct = (ebitda_val / invested_capital) * 100
                        # Clamp ROIC to reasonable range (-100% to +200%)
                        roic_pct = max(-100, min(200, roic_pct))
                        metrics['roic'].append(roic_pct)
                except (ValueError, TypeError):
                    pass

        # Process volatility data (now using aggregated stddev from query, much faster)
        for row in volatility_rows:
            symbol, volatility, data_points = row
            if volatility is not None:
                # Convert stddev to percentage volatility for consistency
                metrics['volatility'].append(float(volatility))

        # Fetch EPS growth stability and earnings surprise from quality_metrics table
        # These are pre-calculated by loadfactormetrics.py and needed for quality component scores
        try:
            qm_cur = conn.cursor()  # Create new cursor since main cursor was closed
            qm_cur.execute("""
                SELECT eps_growth_stability, earnings_surprise_avg
                FROM quality_metrics
                WHERE eps_growth_stability IS NOT NULL OR earnings_surprise_avg IS NOT NULL
            """)

            qm_rows = qm_cur.fetchall()
            metrics['eps_growth_stability'] = []
            metrics['earnings_surprise_avg'] = []

            for eps_stab, earn_surp in qm_rows:
                if eps_stab is not None:
                    metrics['eps_growth_stability'].append(float(eps_stab))
                if earn_surp is not None:
                    metrics['earnings_surprise_avg'].append(float(earn_surp))

            qm_cur.close()
        except Exception as e:
            logger.warning(f"Could not fetch eps_growth_stability/earnings_surprise_avg from quality_metrics: {e}")
            metrics['eps_growth_stability'] = []
            metrics['earnings_surprise_avg'] = []

        logger.info(f"📊 Loaded quality metrics for percentile calculation:")
        logger.info(f"   ROE: {len(metrics['roe'])} stocks")
        logger.info(f"   ROA: {len(metrics['roa'])} stocks")
        logger.info(f"   Gross Margin: {len(metrics['gross_margin'])} stocks")
        logger.info(f"   Debt/Equity: {len(metrics['debt_to_equity'])} stocks")
        logger.info(f"   Current Ratio: {len(metrics['current_ratio'])} stocks")
        logger.info(f"   FCF/NI: {len(metrics['fcf_to_ni'])} stocks")
        logger.info(f"   ROIC: {len(metrics['roic'])} stocks")
        logger.info(f"   Volatility: {len(metrics['volatility'])} stocks")
        logger.info(f"   EPS Growth Stability: {len(metrics.get('eps_growth_stability', []))} stocks")
        logger.info(f"   Earnings Surprise: {len(metrics.get('earnings_surprise_avg', []))} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch quality metrics for percentile ranking: {e}")
        return None

def fetch_all_growth_metrics(conn):
    """
    Fetch growth metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each metric.
    Uses LEFT JOIN to include ALL stocks in price_daily, even if key_metrics data is sparse.
    """
    try:
        cur = conn.cursor()

        # Fetch growth metrics from key_metrics table - use LEFT JOIN to get all stocks
        # Even if a stock has sparse key_metrics data, it should still be included for percentile calculation
        cur.execute("""
            SELECT
                km.revenue_growth_pct,
                km.earnings_growth_pct,
                km.earnings_q_growth_pct,
                km.gross_margin_pct,
                km.operating_margin_pct,
                km.return_on_equity_pct,
                km.payout_ratio,
                gm.fcf_growth_yoy,
                gm.ocf_growth_yoy,
                pd.symbol
            FROM (
                SELECT DISTINCT symbol FROM price_daily
            ) pd
            LEFT JOIN key_metrics km ON km.ticker = pd.symbol
            LEFT JOIN growth_metrics gm ON gm.symbol = pd.symbol
            WHERE km.revenue_growth_pct IS NOT NULL
               OR km.earnings_growth_pct IS NOT NULL
               OR km.gross_margin_pct IS NOT NULL
               OR km.operating_margin_pct IS NOT NULL
               OR gm.fcf_growth_yoy IS NOT NULL
               OR gm.ocf_growth_yoy IS NOT NULL
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
            'sustainable_growth': [],  # ROE × (1 - payout_ratio)
            'fcf_growth': [],  # Free Cash Flow growth YoY
            'ocf_growth': []  # Operating Cash Flow growth YoY
        }

        # Process growth metrics
        for row in rows:
            rev_growth, earn_growth, earn_q_growth, gross_margin, op_margin, roe, payout, fcf_growth, ocf_growth, symbol = row

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
            if fcf_growth is not None:
                metrics['fcf_growth'].append(float(fcf_growth))
            if ocf_growth is not None:
                metrics['ocf_growth'].append(float(ocf_growth))

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
        logger.info(f"   FCF Growth: {len(metrics['fcf_growth'])} stocks")
        logger.info(f"   OCF Growth: {len(metrics['ocf_growth'])} stocks")
        logger.info(f"   Sustainable Growth: {len(metrics['sustainable_growth'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch growth metrics for percentile ranking: {e}")
        return None

def fetch_all_value_metrics(conn):
    """
    Fetch value metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each valuation metric.
    CRITICAL: Must include ALL valuation metrics used in Value Score calculation:
    - PE, PB, PS (traditional valuation)
    - EV/EBITDA, EV/Revenue (enterprise value - critical for unprofitable companies)
    - PEG (growth-adjusted)
    """
    try:
        cur = conn.cursor()

        # Fetch ALL valuation metrics from key_metrics table
        # CRITICAL: Include ev_to_ebitda for unprofitable companies (key for flexible weighting)
        # CRITICAL: Include dividend_yield for dividend/income component
        # CRITICAL: Include free_cashflow and market_cap for FCF Yield calculation
        # NO INNER JOIN LIMITATION - include ALL stocks with metrics regardless of price_daily status
        cur.execute("""
            SELECT
                km.trailing_pe,
                km.forward_pe,
                km.price_to_book,
                km.price_to_sales_ttm,
                km.peg_ratio,
                km.ev_to_revenue,
                km.ev_to_ebitda,
                km.dividend_yield,
                km.free_cashflow,
                km.ticker as symbol
            FROM key_metrics km
            WHERE km.trailing_pe IS NOT NULL
               OR km.forward_pe IS NOT NULL
               OR km.price_to_book IS NOT NULL
               OR km.price_to_sales_ttm IS NOT NULL
               OR km.peg_ratio IS NOT NULL
               OR km.ev_to_revenue IS NOT NULL
               OR km.ev_to_ebitda IS NOT NULL
               OR km.dividend_yield IS NOT NULL
               OR km.free_cashflow IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary - CRITICAL FIX: Added ev_ebitda, forward_pe
        metrics = {
            'pe': [],
            'forward_pe': [],
            'pb': [],
            'ps': [],
            'peg': [],
            'ev_revenue': [],
            'ev_ebitda': [],  # CRITICAL: Was missing - needed for unprofitable stocks
            'dividend_yield': []  # CRITICAL: Needed for dividend yield component
            # NOTE: fcf_yield removed - can't calculate without market_cap (price * shares)
            # FCF Yield will be calculated per-stock but won't have percentile ranking
        }

        # Process valuation metrics - collect all non-None values for percentile calculation
        # CRITICAL: Include zero and negative values - they're valid data points for ranking
        # P/E can be negative (unprofitable), dividend yield can be 0 (no payout), etc.
        for row in rows:
            pe, forward_pe, pb, ps, peg, ev_rev, ev_ebit, div_yield, fcf, symbol = row

            # P/E Ratio: Allow negative (unprofitable), just apply reasonable bounds on absolute value
            if pe is not None and abs(pe) < 5000:  # CRITICAL: Include negatives for unprofitable companies
                metrics['pe'].append(float(pe))
            # Forward P/E Ratio: Allow positive only (forward estimates)
            if forward_pe is not None and forward_pe > 0 and forward_pe < 5000:
                metrics['forward_pe'].append(float(forward_pe))
            # P/B Ratio: Allow negative (negative equity companies)
            if pb is not None and pb != 0 and abs(pb) < 5000:  # CRITICAL: Include negatives
                metrics['pb'].append(float(pb))
            # P/S Ratio: Allow negative (negative sales companies)
            if ps is not None and ps != 0 and abs(ps) < 5000:  # CRITICAL: Include negatives
                metrics['ps'].append(float(ps))
            # PEG Ratio: Allow zero and positive
            if peg is not None and peg >= 0 and peg < 5000:  # CRITICAL: Include 0 growth stocks
                metrics['peg'].append(float(peg))
            # EV/Revenue: Allow negative (negative EV or revenue)
            if ev_rev is not None and ev_rev != 0 and abs(ev_rev) < 5000:  # CRITICAL: Include negatives
                metrics['ev_revenue'].append(float(ev_rev))
            # CRITICAL: EV/EBITDA - allow both positive and negative values for proper ranking
            # Unprofitable companies may have negative EBITDA (include them for complete picture)
            if ev_ebit is not None and abs(ev_ebit) < 5000:  # CRITICAL: Include negatives for unprofitable companies
                metrics['ev_ebitda'].append(float(ev_ebit))
            # CRITICAL: Dividend Yield - key metric for income-focused value investing
            # Include 0 dividend (companies that don't pay dividends are valid for ranking)
            if div_yield is not None and div_yield >= 0 and div_yield < 100:  # CRITICAL: Include 0 dividend stocks
                metrics['dividend_yield'].append(float(div_yield))
        # CRITICAL: FCF Yield - Calculate from free_cashflow / (price * shares)
        # Join key_metrics with latest price_daily to get current price
        cur = conn.cursor()
        cur.execute("""
            SELECT
                CAST((km.free_cashflow / (pd.close * km.implied_shares_outstanding)) * 100 AS DECIMAL(10,4)) as fcf_yield
            FROM key_metrics km
            JOIN LATERAL (
                SELECT close
                FROM price_daily
                WHERE symbol = km.ticker
                ORDER BY date DESC
                LIMIT 1
            ) pd ON true
            WHERE km.free_cashflow IS NOT NULL
              AND km.implied_shares_outstanding IS NOT NULL
              AND km.implied_shares_outstanding > 0
              AND pd.close > 0
        """)

        fcf_yields = []
        for row in cur.fetchall():
            fcf_yield_val = row[0]
            if fcf_yield_val is not None:
                try:
                    fcf_val = float(fcf_yield_val)
                    if abs(fcf_val) < 500:  # Reasonable bounds
                        fcf_yields.append(fcf_val)
                except (ValueError, TypeError):
                    pass

        metrics['fcf_yield'] = fcf_yields
        cur.close()

        logger.info(f"📊 Loaded value metrics for percentile calculation (FLEXIBLE WEIGHTING):")
        logger.info(f"   P/E Ratio: {len(metrics['pe'])} stocks")
        logger.info(f"   Forward P/E: {len(metrics['forward_pe'])} stocks")
        logger.info(f"   P/B Ratio: {len(metrics['pb'])} stocks")
        logger.info(f"   P/S Ratio: {len(metrics['ps'])} stocks")
        logger.info(f"   PEG Ratio: {len(metrics['peg'])} stocks")
        logger.info(f"   EV/Revenue: {len(metrics['ev_revenue'])} stocks")
        logger.info(f"   EV/EBITDA: {len(metrics['ev_ebitda'])} stocks")
        logger.info(f"   Dividend Yield: {len(metrics['dividend_yield'])} stocks")
        logger.info(f"   FCF Yield: {len(metrics['fcf_yield'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch value metrics for percentile ranking: {e}")
        return None

def fetch_all_positioning_metrics(conn):
    """
    Fetch positioning metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each positioning metric.
    Uses actual column names from positioning_metrics table.
    """
    try:
        cur = conn.cursor()

        # Fetch positioning metrics from positioning_metrics table using correct column names
        cur.execute("""
            SELECT
                pm.institutional_ownership_pct,
                pm.insider_ownership_pct,
                pm.institutional_holders_count,
                pm.short_interest_pct
            FROM positioning_metrics pm
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON pm.symbol = pd.symbol
            WHERE pm.institutional_ownership_pct IS NOT NULL
               OR pm.insider_ownership_pct IS NOT NULL
               OR pm.institutional_holders_count IS NOT NULL
               OR pm.short_interest_pct IS NOT NULL
        """)

        rows = cur.fetchall()

        # Build metrics dictionary
        metrics = {
            'institutional_ownership': [],
            'insider_ownership': [],
            'institution_count': [],
            'short_percent_of_float': []
        }

        # Process positioning metrics - collect all non-None values for percentile calculation
        for row in rows:
            inst_ownership, insider_ownership, inst_count, short_pct = row

            if inst_ownership is not None and 0 <= inst_ownership <= 100:
                metrics['institutional_ownership'].append(float(inst_ownership))
            if insider_ownership is not None and 0 <= insider_ownership <= 100:
                metrics['insider_ownership'].append(float(insider_ownership))
            if inst_count is not None and inst_count > 0:
                metrics['institution_count'].append(float(inst_count))
            if short_pct is not None and short_pct >= 0:
                # short_interest_pct stored as percentage value (0-100)
                short_pct_value = float(short_pct) * 100 if short_pct <= 1 else float(short_pct)
                if 0 <= short_pct_value <= 100:
                    metrics['short_percent_of_float'].append(short_pct_value)

        cur.close()

        logger.info(f"📊 Loaded positioning metrics for percentile calculation:")
        logger.info(f"   Institutional Ownership: {len(metrics['institutional_ownership'])} stocks")
        logger.info(f"   Insider Ownership: {len(metrics['insider_ownership'])} stocks")
        logger.info(f"   Institution Count: {len(metrics['institution_count'])} stocks")
        logger.info(f"   Short Interest: {len(metrics['short_percent_of_float'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch positioning metrics for percentile ranking: {e}")
        return None

def fetch_all_stability_metrics(conn):
    """
    Fetch stability metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each risk metric.

    CRITICAL: Uses robust percentile-based filtering (5-95%) instead of hard bounds
    to ensure sufficient sample size and representative data distribution.
    """
    try:
        cur = conn.cursor()

        # Fetch stability metrics - get LATEST data per symbol (table has multiple dates)
        cur.execute("""
            SELECT
                sm.volatility_12m,
                sm.max_drawdown_52w,
                sm.beta
            FROM stability_metrics sm
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON sm.symbol = pd.symbol
            INNER JOIN (
                SELECT symbol, MAX(date) as latest_date
                FROM stability_metrics
                GROUP BY symbol
            ) latest ON sm.symbol = latest.symbol AND sm.date = latest.latest_date
            WHERE sm.volatility_12m IS NOT NULL
               OR sm.max_drawdown_52w IS NOT NULL
               OR sm.beta IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build raw metrics dictionary (no filtering yet)
        volatility_raw = []
        drawdown_raw = []
        beta_raw = []

        for row in rows:
            volatility, drawdown, beta = row

            if volatility is not None and volatility > 0:
                volatility_raw.append(float(volatility))
            if drawdown is not None and 0 <= drawdown <= 100:
                drawdown_raw.append(float(drawdown))
            if beta is not None and beta > 0:
                beta_raw.append(float(beta))

        # Use percentile-based filtering (5-95%) to remove extreme outliers
        # while preserving representative distribution for z-score normalization
        import statistics

        def apply_percentile_filter(values, p_low=1, p_high=99):
            """
            Remove values below p_low and above p_high percentiles.
            WIDENED FROM 5-95 to 1-99 to preserve more legitimate data variation.
            This minimizes artificial compression while still removing extreme statistical outliers.
            """
            if len(values) < 100:
                return values  # Not enough data for percentile filtering

            sorted_vals = sorted(values)
            low_idx = max(0, int(len(values) * (p_low / 100)))
            high_idx = min(len(values), int(len(values) * (p_high / 100)))

            p_low_val = sorted_vals[low_idx]
            p_high_val = sorted_vals[high_idx]

            return [v for v in values if p_low_val <= v <= p_high_val]

        # Apply percentile-based filtering to each metric (1-99% range to preserve data)
        volatility_filtered = apply_percentile_filter(volatility_raw, p_low=1, p_high=99)
        drawdown_filtered = apply_percentile_filter(drawdown_raw, p_low=1, p_high=99)
        beta_filtered = apply_percentile_filter(beta_raw, p_low=1, p_high=99)

        metrics = {
            'volatility': volatility_filtered,
            'drawdown': drawdown_filtered,
            'beta': beta_filtered
        }

        logger.info(f"📊 Loaded stability metrics for percentile calculation (5-95% filtering):")
        logger.info(f"   Volatility (12M): {len(volatility_filtered)}/{len(volatility_raw)} stocks")
        logger.info(f"   Drawdown (52W): {len(drawdown_filtered)}/{len(drawdown_raw)} stocks")
        logger.info(f"   Beta: {len(beta_filtered)}/{len(beta_raw)} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch stability metrics for percentile ranking: {e}")
        return None


def get_stock_data_from_database(conn, symbol, quality_metrics=None, growth_metrics=None, value_metrics=None, positioning_metrics=None, stability_metrics=None):
    """Get stock data from database tables and calculate all scores."""
    try:
        cur = conn.cursor()

        # Convert Decimal to native Python types helper
        def to_float(val):
            """Convert Decimal or any numeric type to float, or return None"""
            if val is None:
                return None
            from decimal import Decimal
            if isinstance(val, Decimal):
                return float(val)
            return float(val) if val is not None else None

        # Get company name from company_profile table
        company_name = None
        try:
            cur.execute("""
                SELECT short_name
                FROM company_profile
                WHERE ticker = %s
                LIMIT 1
            """, (symbol,))
            cp_data = cur.fetchone()
            if cp_data and cp_data[0]:
                company_name = cp_data[0]
        except Exception as e:
            logger.debug(f"Could not fetch company name for {symbol}: {e}")

        # Initialize all momentum-related variables to prevent NameError in JSONB columns
        momentum_intraweek = None
        momentum_3m = None
        momentum_6m = None
        momentum_12_3 = None  # 12-month minus 3-month momentum
        momentum_3m_score = None
        momentum_6m_score = None
        momentum_12_3_score = None
        price_vs_sma_50 = None
        stock_revenue_growth = None
        stock_earnings_growth = None
        acceleration = None
        stock_gross_margin_growth = None
        institutional_ownership_pct = None
        insider_ownership_pct = None
        short_percent_of_float = None
        institution_count = None
        stock_roe = None
        stock_roa = None
        stock_gross_margin = None
        stock_operating_margin = None
        stock_profit_margin = None
        stock_fcf_to_ni = None
        stock_operating_cf_to_ni = None
        stock_debt_to_equity = None
        stock_current_ratio = None
        stock_quick_ratio = None
        beat_rate = None
        earnings_surprise_avg = None  # Will be fetched from quality_metrics table
        eps_growth_std = None
        payout_ratio = None

        # Initialize all value metric variables to prevent NameError in value score calculations
        trailing_pe = None
        forward_pe = None
        price_to_book = None
        price_to_sales_ttm = None
        peg_ratio = None
        peg_ratio_val = None
        ev_to_revenue = None
        ev_to_ebitda = None
        free_cashflow = None
        dividend_yield = None
        dividend_yield_val = None

        # Get price data from price_daily table (last 200 days to ensure 65+ trading days)
        # Note: 200 calendar days accounts for weekends/holidays to guarantee ~130+ trading days
        cur.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM price_daily
            WHERE symbol = %s
            AND date >= CURRENT_DATE - INTERVAL '200 days'
            ORDER BY date DESC
            LIMIT 200
        """, (symbol,))

        price_data = cur.fetchall()
        if not price_data:
            logger.warning(f"⚠️ No price data for {symbol}, calculating scores with NULL inputs")
            # Don't return None - calculate what we can with empty price data
        elif len(price_data) < 20:
            logger.debug(f"⚠️ Limited price data for {symbol}: {len(price_data)} records (need 20+ for full accuracy)")
            # Continue - we'll calculate what we can with partial data

        # Convert to pandas DataFrame for easier calculations
        if price_data:
            df = pd.DataFrame(price_data, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close'])
            df = df.sort_values('date')  # Sort chronologically for calculations
            # Convert all numeric columns to float to avoid Decimal type issues
            for col in ['open', 'high', 'low', 'close', 'volume', 'adj_close']:
                df[col] = df[col].astype(float)
            current_price = float(df['close'].iloc[-1])
        else:
            df = pd.DataFrame()  # Empty dataframe
            current_price = None

        # Calculate price changes (only if we have current price)
        price_change_1d = ((current_price - float(df['close'].iloc[-2])) / float(df['close'].iloc[-2]) * 100) if (current_price is not None) and len(df) >= 2 else None
        price_change_5d = ((current_price - float(df['close'].iloc[-6])) / float(df['close'].iloc[-6]) * 100) if (current_price is not None) and len(df) >= 6 else None
        price_change_30d = ((current_price - float(df['close'].iloc[-31])) / float(df['close'].iloc[-31]) * 100) if (current_price is not None) and len(df) >= 31 else None

        # Calculate volume average (last 30 days)
        volume_avg_30d = int(df['volume'].tail(30).mean()) if len(df) >= 30 else (int(df['volume'].mean()) if len(df) > 0 else None)

        # Calculate 52-week high/low (252 trading days)
        high_52w = df['high'].tail(252).max() if len(df) >= 252 else (df['high'].max() if len(df) > 0 else None)
        low_52w = df['low'].tail(252).min() if len(df) >= 252 else (df['low'].min() if len(df) > 0 else None)

        # Calculate 52-week range % (higher % = less stable, wild swings)
        range_52w_pct = None
        if high_52w is not None and low_52w is not None and bool(float(low_52w) > 0):
            range_52w_pct = ((high_52w - low_52w) / low_52w) * 100

        # Get latest technical data including momentum indicators
        cur.execute("""
            SELECT rsi, macd, macd_hist, sma_20, sma_50, sma_200, atr, mom, roc
            FROM technical_data_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))

        tech_data = cur.fetchone()
        if tech_data and len(tech_data) >= 9:
            # Convert Decimal types from PostgreSQL to float immediately after fetching
            raw_rsi, raw_macd, raw_macd_hist, raw_sma_20, raw_sma_50, raw_sma_200, raw_atr, raw_mom_10d, raw_roc_10d = tech_data
            rsi = to_float(raw_rsi)
            macd = to_float(raw_macd)
            macd_hist = to_float(raw_macd_hist)
            sma_20 = to_float(raw_sma_20)
            sma_50 = to_float(raw_sma_50)
            sma_200 = to_float(raw_sma_200)
            atr = to_float(raw_atr)
            mom_10d = to_float(raw_mom_10d)
            roc_10d = to_float(raw_roc_10d)
            roc_20d = None
            roc_60d = None
            roc_120d = None
            roc_252d = None
            mansfield_rs = None
        else:
            # Calculate basic technical indicators from price data
            prices = df['close'].astype(float).values
            rsi = calculate_rsi(prices)
            macd = calculate_macd(prices)
            macd_hist = None
            sma_20 = df['close'].tail(20).mean() if len(df) >= 20 else None
            sma_50 = df['close'].tail(50).mean() if len(df) >= 50 else None
            sma_200 = df['close'].tail(200).mean() if len(df) >= 200 else None
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

        # Get dual momentum metrics from momentum_metrics table (optional - handle gracefully if table doesn't exist)
        momentum_12_3 = None
        momentum_6m = None
        momentum_3m = None
        risk_adjusted_momentum = None

        # Initialize all momentum variables to None BEFORE any code path can reference them
        momentum_12m = None
        momentum_6m = None
        momentum_3m = None
        momentum_12_3 = None
        risk_adjusted_momentum = None

        try:
            cur.execute("""
                SELECT momentum_12m, momentum_6m, momentum_3m
                FROM momentum_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))

            momentum_data = cur.fetchone()
            if momentum_data and len(momentum_data) >= 3:
                # Convert Decimal types from PostgreSQL to float immediately after fetching
                raw_momentum_12m, raw_momentum_6m, raw_momentum_3m = momentum_data
                momentum_12m = to_float(raw_momentum_12m)
                momentum_6m = to_float(raw_momentum_6m)
                momentum_3m = to_float(raw_momentum_3m)
                # Calculate 12-month minus 3-month (longer-term momentum excluding medium-term)
                if momentum_12m is not None and momentum_3m is not None:
                    momentum_12_3 = momentum_12m - momentum_3m
                else:
                    momentum_12_3 = None
        except Exception:
            # If momentum_metrics table doesn't exist or query fails, skip momentum data
            # Variables already initialized to None above
            pass

        if len(df) > 0:
            prices = df['close'].astype(float).values
            volatility_30d = calculate_volatility(prices)
        else:
            volatility_30d = None

        # Get A/D (Accumulation/Distribution) Rating from positioning_metrics table
        # This is calculated in loadfactormetrics.py using price history
        acc_dist_rating = None
        try:
            cur.execute(
                "SELECT ad_rating FROM positioning_metrics WHERE symbol = %s",
                (symbol,)
            )
            db_result = cur.fetchone()
            acc_dist_rating = db_result[0] if db_result and db_result[0] is not None else None
        except (psycopg2.Error, TypeError):
            acc_dist_rating = None

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
            eps_values = [to_float(row[0]) for row in earnings_data if row[0] is not None]
            if eps_values and len(eps_values) >= 4:
                trailing_eps = sum(eps_values[:4])  # Last 4 quarters
                if trailing_eps > 0 and current_price is not None:
                    pe_ratio = current_price / trailing_eps

        # Fetch shares outstanding from key_metrics table to calculate market cap
        market_cap = None
        shares_outstanding = None
        try:
            cur.execute("""
                SELECT implied_shares_outstanding FROM key_metrics WHERE ticker = %s
            """, (symbol,))
            shares_data = cur.fetchone()
            if shares_data and shares_data[0] is not None:
                shares_outstanding = to_float(shares_data[0])
                # Calculate market cap if both current price and shares outstanding available
                if current_price is not None and current_price > 0:
                    market_cap = current_price * shares_outstanding
        except psycopg2.Error as e:
            conn.rollback()
            logger.debug(f"{symbol}: Could not fetch shares outstanding: {str(e)[:50]}")
            shares_outstanding = None
            market_cap = None

        # VALIDATION FIX: Check if calculated market_cap is unreasonably high
        # Issue: implied_shares_outstanding from yfinance may be based on stale prices
        # Solution: validate against volume-based estimate and use that if market_cap is inflated
        if market_cap is not None and volume_avg_30d is not None and volume_avg_30d > 0 and current_price is not None and current_price > 0:
            # Estimate market cap from average daily trading volume as reality check
            # Assumption: typical daily volume is ~10% of market cap annual turnover
            # So shares_outstanding = volume / 0.1 (10% daily turnover)
            estimated_shares = volume_avg_30d * 10
            estimated_market_cap = current_price * estimated_shares

            # If calculated market_cap is >5x the estimated value, use estimate instead
            # This handles cases where shares_outstanding is inflated from stale yfinance data
            if market_cap > estimated_market_cap * 5:
                logger.info(f"{symbol}: Market cap {market_cap:,.0f} appears inflated (est: {estimated_market_cap:,.0f}), using volume-based estimate")
                market_cap = estimated_market_cap

        # If market_cap still None, calculate from volume estimate
        if market_cap is None and volume_avg_30d is not None and volume_avg_30d > 0 and current_price is not None and current_price > 0:
            # Estimate market cap from average daily trading volume
            # Assumption: typical daily volume is 5-10% of shares outstanding
            # So shares_outstanding ≈ volume / average_daily_turnover_rate (0.1 = 10%)
            # Using 10% as realistic estimate: shares = volume * 10
            estimated_shares = volume_avg_30d * 10  # Realistic estimate (10% daily turnover)
            market_cap = current_price * estimated_shares
            logger.debug(f"{symbol}: Estimated market cap from volume (no shares data): ${market_cap:,.0f}")

        # Get sentiment data for Sentiment Score - NO SILENT FAILURES
        sentiment_score_raw = None
        news_count = None
        try:
            cur.execute("""
                SELECT sentiment_score, news_count
                FROM sentiment
                WHERE symbol = %s
                AND date_recorded >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY date_recorded DESC
                LIMIT 1
            """, (symbol,))
            sentiment_data = cur.fetchone()
            if sentiment_data:
                sentiment_score_raw = to_float(sentiment_data[0])
                news_count = to_float(sentiment_data[1])
        except psycopg2.Error as e:
            conn.rollback()
            logger.debug(f"{symbol}: Sentiment data not available ({str(e)[:50]})")
            sentiment_score_raw = None
            news_count = None

        # Get analyst recommendations from analyst_sentiment_analysis table - NO SILENT FAILURES
        analyst_score = None
        analyst_record_count = 0
        try:
            cur.execute("""
                SELECT bullish_count, bearish_count, neutral_count, total_analysts
                FROM analyst_sentiment_analysis
                WHERE symbol = %s
                ORDER BY date_recorded DESC
                LIMIT 1
            """, (symbol,))
            analyst_rec = cur.fetchone()
            if analyst_rec:
                # Calculate sentiment score from bullish/bearish/neutral counts
                bullish = int(analyst_rec[0]) if analyst_rec[0] is not None else 0
                bearish = int(analyst_rec[1]) if analyst_rec[1] is not None else 0
                neutral = int(analyst_rec[2]) if analyst_rec[2] is not None else 0
                total = int(analyst_rec[3]) if analyst_rec[3] is not None else 0

                # Sentiment score: (bullish - bearish) / total, scaled to 0-100
                # Net sentiment: +1 = all bullish, -1 = all bearish, 0 = mixed/neutral
                if total > 0:
                    analyst_score = float(((bullish - bearish) / total) * 50 + 50)  # Scale to 0-100
                    analyst_record_count = total
                else:
                    analyst_score = None
                    analyst_record_count = 0
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"❌ ANALYST RECOMMENDATIONS QUERY FAILED for {symbol}: {str(e)[:100]}")
            analyst_score = None
            analyst_record_count = 0

        # Get market-level AAII sentiment for market sentiment component
        # REAL DATA ONLY - None if no data available - NO SILENT FAILURES
        aaii_sentiment_component = None
        try:
            cur.execute("""
                SELECT bullish, neutral, bearish
                FROM aaii_sentiment
                ORDER BY date DESC
                LIMIT 1
            """)
            aaii_data = cur.fetchone()
            if aaii_data and aaii_data[0] is not None and aaii_data[2] is not None:
                bullish = to_float(aaii_data[0])
                bearish = to_float(aaii_data[2])
                # Convert AAII bullish/bearish to sentiment score: -25 to +25
                # If bullish > 50%, positive sentiment; if bearish > 50%, negative
                aaii_sentiment_component = ((bullish - bearish) / 100) * 50
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"❌ AAII SENTIMENT QUERY FAILED: {str(e)[:100]}")  # ✅ VISIBLE ERROR
            aaii_sentiment_component = None

        # Get real positioning data - use actual institutional_positioning table
        # CRITICAL FIX: Data stored as decimals (0-1) but scoring expects percentages (0-100)
        # Multiply by 100 to convert for proper threshold comparison - NO SILENT FAILURES
        institutional_ownership = None
        insider_ownership = None
        short_percent_of_float = None
        institution_count = None

        # ============================================================
        # CRITICAL FIX #2: Ensure positioning metrics use consistent 0-100 scale
        # Data sources:
        # - institutional_positioning.market_share: stored as percentage (0-100)
        # - key_metrics.held_percent_insiders: stored as decimal (0-1), needs *100
        # - key_metrics.short_percent_of_float: stored as decimal (0-1), needs *100
        # - positioning_metrics table: used for percentile lists, ensure consistent scale
        # ============================================================

        # 1. Get institutional + insider ownership from positioning_metrics table (REAL DATA SOURCE) - NO SILENT FAILURES
        try:
            cur.execute("""
                SELECT
                    institutional_ownership_pct,
                    insider_ownership_pct,
                    institutional_holders_count
                FROM positioning_metrics
                WHERE symbol = %s
                LIMIT 1
            """, (symbol,))
            pos_data = cur.fetchone()
            if pos_data:
                # positioning_metrics stores values as NUMERIC percentages (0-100 scale) - CONVERT DECIMAL TYPES
                institutional_ownership = to_float(pos_data[0])
                insider_ownership = to_float(pos_data[1])
                institution_count = int(pos_data[2]) if pos_data[2] is not None else None

                # REAL DATA ONLY - if values are None, they stay None (no fake defaults)
                if institutional_ownership is not None and (institutional_ownership < 0 or institutional_ownership > 100):
                    logger.warning(f"{symbol}: institutional_ownership {institutional_ownership} outside 0-100 range, skipping")
                    institutional_ownership = None
                if insider_ownership is not None and (insider_ownership < 0 or insider_ownership > 100):
                    logger.warning(f"{symbol}: insider_ownership {insider_ownership} outside 0-100 range, skipping")
                    insider_ownership = None
            else:
                # No positioning_metrics data available - return None (REAL DATA ONLY)
                institutional_ownership = None
                insider_ownership = None
                institution_count = None
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"❌ POSITIONING_METRICS QUERY FAILED for {symbol}: {str(e)[:100]}")  # ✅ VISIBLE ERROR
            institutional_ownership = None
            insider_ownership = None
            institution_count = None

        # 3. Get short interest from key_metrics table (stored as decimal 0-1, convert to percentage) - NO SILENT FAILURES
        try:
            cur.execute("""
                SELECT short_percent_of_float FROM key_metrics WHERE ticker = %s
            """, (symbol,))
            short_data = cur.fetchone()
            if short_data and short_data[0] is not None:
                # key_metrics.short_percent_of_float is stored as DECIMAL (0-1), MULTIPLY BY 100 to normalize to 0-100 scale
                raw_value = to_float(short_data[0])
                # Detect and normalize scale if needed
                if raw_value > 1:  # Already in percentage form (0-100)
                    short_percent_of_float = raw_value
                    logger.debug(f"{symbol}: short interest already in 0-100 scale: {raw_value}")
                else:  # 0-1 form, convert to percentage
                    short_percent_of_float = raw_value * 100
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"❌ SHORT INTEREST QUERY FAILED for {symbol}: {str(e)[:100]}")  # ✅ VISIBLE ERROR
            short_percent_of_float = None

        # ============================================================
        # Risk Score Calculation - Best-in-Class Framework
        # Pure Risk Minimization Model (Option A - Defensive Focus)
        # Formula: 30% volatility + 25% downside_vol + 25% drawdown + 15% beta + 5% liquidity
        # LOWER volatility/drawdown/beta = HIGHER score (safer stocks)
        # REQUIRES ALL DATA or None - NO NEUTRAL DEFAULTS
        # ============================================================
        stability_score = None
        stability_inputs = {
            'volatility_12m_pct': None,
            'downside_volatility_pct': None,
            'max_drawdown_52w_pct': None,
            'beta': None,
            'volume_consistency': None,
            'turnover_velocity': None,
            'volatility_volume_ratio': None,
            'daily_spread': None
        }

        try:
            # Calculate risk components with graceful fallbacks
            risk_stability_score = None  # Initialize to prevent UnboundLocalError

            # Check if we have price data before accessing df
            if len(df) == 0:
                logger.warning(f"{symbol}: No price data available for risk/liquidity calculations")
                prices = None
                volatility_12m_pct = None
                downside_volatility = None
            else:
                prices = df['close'].astype(float).values

                # Calculate volatility directly from price data (30-day)
                volatility_12m_pct = calculate_volatility(prices)  # Annualized
                if volatility_12m_pct is None:
                    logger.warning(f"{symbol}: Cannot calculate volatility - will calculate stability without it")

                # Calculate downside volatility (only on down days)
                downside_volatility = calculate_downside_volatility(prices)
                if downside_volatility is None:
                    logger.warning(f"{symbol}: Cannot calculate downside volatility - will calculate stability without it")

            # Fetch Beta from stability_metrics table for this specific stock
            # Use percentile-filtered list from stability_metrics for comparative scoring
            # NOTE: Get the most recent row WITH beta, not just the most recent row (which may have NULL beta)
            beta = None
            try:
                cur.execute("""
                    SELECT beta FROM stability_metrics
                    WHERE symbol = %s AND beta IS NOT NULL
                    ORDER BY date DESC LIMIT 1
                """, (symbol,))
                beta_row = cur.fetchone()
                if beta_row and beta_row[0] is not None:
                    beta = float(beta_row[0])
            except Exception as e:
                logger.debug(f"{symbol}: Could not fetch beta from stability_metrics: {e}")
                beta = None

            # No fallback calculation - beta must come from database or remain None
            # Never calculate synthetic beta from price data as a fallback

            if not stability_metrics or not stability_metrics.get('beta'):
                logger.debug(f"{symbol}: Beta distribution not available - will calculate stability without beta")

            # Calculate 4 market liquidity metrics (REAL DATA ONLY - NO FALLBACKS)
            # All metrics return 0-100 scores or None if data insufficient
            # Note: market_cap already calculated above from current_price + shares_outstanding
            volumes = (df['volume'].astype(float).values if 'volume' in df.columns else None) if len(df) > 0 else None

            # 1. Volume Consistency Score (lower volatility = higher score)
            volume_consistency_score = calculate_volume_consistency_score(prices, volumes)

            # 2. Turnover Velocity Score (annualized share turnover)
            turnover_velocity_score = calculate_turnover_velocity_score(volume_avg_30d, market_cap)

            # 3. Volatility/Volume Ratio Score (price stability relative to volume)
            volatility_volume_ratio_score = calculate_volatility_volume_ratio_score(prices, volumes)

            # 4. Daily Spread Score (tight spreads = higher score)
            daily_spread_score = calculate_daily_spread_score(prices)

            # 5. Downside Volatility Score (downside deviation of returns)
            downside_volatility_score = calculate_downside_volatility_score(prices)

            # Store 5 market liquidity metrics IMMEDIATELY (before stability calculation)
            # These are data inputs and should be stored regardless of stability score calculation success
            stability_inputs['volume_consistency'] = round(volume_consistency_score, 1) if volume_consistency_score is not None else None
            stability_inputs['turnover_velocity'] = round(turnover_velocity_score, 1) if turnover_velocity_score is not None else None
            stability_inputs['volatility_volume_ratio'] = round(volatility_volume_ratio_score, 1) if volatility_volume_ratio_score is not None else None
            stability_inputs['daily_spread'] = round(daily_spread_score, 1) if daily_spread_score is not None else None
            stability_inputs['downside_volatility'] = round(downside_volatility_score, 1) if downside_volatility_score is not None else None

            # Calculate drawdown from price data (no external stability_metrics table used)
            # Price data is the source of truth for historical drawdown calculation
            try:
                # Find high in last 252 trading days (~1 year)
                prices_array = df['close'].astype(float).values
                if len(prices_array) >= 20:
                    max_price = prices_array.max()
                    current_price_val = prices_array[-1]
                    if max_price > 0:
                        max_drawdown_52w_pct = ((max_price - current_price_val) / max_price) * 100
                    else:
                        max_drawdown_52w_pct = None  # Insufficient data - no fallback
                else:
                    max_drawdown_52w_pct = None  # Insufficient data - no fallback
            except Exception as e:
                logging.debug(f"Failed to calculate drawdown for {symbol}: {e}")
                max_drawdown_52w_pct = None

            vol_str = f"{volatility_12m_pct:.1f}%" if volatility_12m_pct is not None else "N/A"
            downside_str = f"{downside_volatility:.1f}%" if downside_volatility is not None else "N/A"
            drawdown_str = f"{max_drawdown_52w_pct:.1f}%" if max_drawdown_52w_pct is not None else "N/A"
            beta_str = f"{beta:.2f}" if beta is not None else "N/A"
            logger.info(f"{symbol}: Calculated risk components - Vol={vol_str}, Downside={downside_str}, Drawdown={drawdown_str}, Beta={beta_str}")

            # ALWAYS POPULATE STABILITY INPUTS REGARDLESS OF SCORE CALCULATION
            # These are raw metrics that should be stored for API display even if score can't be calculated
            stability_inputs['volatility_12m_pct'] = round(volatility_12m_pct, 4) if volatility_12m_pct is not None else None
            stability_inputs['downside_volatility_pct'] = round(downside_volatility, 4) if downside_volatility is not None else None
            stability_inputs['volatility_risk_component'] = round(downside_volatility_score, 2) if downside_volatility_score is not None else None
            stability_inputs['max_drawdown_52w_pct'] = round(max_drawdown_52w_pct, 2) if max_drawdown_52w_pct is not None else None
            stability_inputs['beta'] = round(beta, 3) if beta is not None else None
            stability_inputs['range_52w_pct'] = round(range_52w_pct, 2) if range_52w_pct is not None else None

            # PHASE 3 FIX: Calculate stability_score with ONLY max_drawdown available if needed
            # MIN REQUIREMENT: At least max_drawdown_52w_pct from database OR calculated from price data
            # volatility_12m_pct can be None - will use only available components
            if max_drawdown_52w_pct is None:
                stability_score = None
                logger.info(f"{symbol} Stability Score: None (missing essential drawdown data)")
            else:
                # All components available - calculate risk score
                # Convert all to 0-100 scale using DYNAMIC percentile ranking (CRITICAL FIX #1)
                # NOTE: downside_volatility not available in risk_metrics table, so only using volatility, drawdown, beta

                # Volatility: lower is better (inverted percentile - lower volatility = higher score)
                vol_percentile = None
                if stability_metrics is not None and volatility_12m_pct is not None:
                    volatility_list = stability_metrics.get('volatility')
                    if volatility_list and len(volatility_list) > 0:
                        vol_percentile = calculate_z_score_normalized(volatility_12m_pct, volatility_list)
                        # Invert: lower volatility should score higher
                        vol_percentile = 100 - vol_percentile if vol_percentile is not None else None
                    else:
                        logger.debug(f"{symbol}: Volatility distribution list empty or missing")

                # Drawdown: lower is better (inverted percentile)
                drawdown_percentile = None
                if stability_metrics is not None and max_drawdown_52w_pct is not None:
                    drawdown_list = stability_metrics.get('drawdown')
                    if drawdown_list and len(drawdown_list) > 0:
                        drawdown_percentile = calculate_z_score_normalized(max_drawdown_52w_pct, drawdown_list)
                        # Invert: lower drawdown should score higher
                        drawdown_percentile = 100 - drawdown_percentile if drawdown_percentile is not None else None
                    else:
                        logger.debug(f"{symbol}: Drawdown distribution list empty or missing")

                # 52-Week Range: lower range = more stable (convert to 0-100 score directly)
                # Range < 20% = 100 (very stable), Range > 200% = 0 (very volatile)
                range_52w_score = None
                if range_52w_pct is not None:
                    # Linear mapping: 0% range = 100, 300% range = 0
                    # Formula: max(0, min(100, 100 - (range_52w_pct / 3)))
                    range_52w_score = max(0, min(100, 100 - (range_52w_pct / 3)))
                    logger.debug(f"{symbol}: 52-week range = {range_52w_pct:.1f}%, stability score = {range_52w_score:.1f}")

                # Calculate composite stability score - REAL DATA ONLY, no fallback defaults
                # Enhanced Multi-Timeframe Model: Price Action (50%) + Liquidity (35%) + Long-Term Range (15%)
                # SHORT-TERM: Volatility + drawdown + beta (price action)
                # LONG-TERM: 52-week range (captures annual stability bounds)
                # MARKET-CONDITION: Liquidity metrics
                components = []
                weights = []

                # PRICE ACTION METRICS (50% total) - short-term stability:
                # Required: volatility (25% - directly measures daily price movement stability)
                if vol_percentile is not None:
                    components.append(vol_percentile)
                    weights.append(0.25)

                # Volatility Risk Component: downside volatility (10% - downside deviation of returns)
                # Measures risk of losses relative to upside - key for risk-averse investors
                downside_volatility_percentile = None
                if downside_volatility_score is not None and downside_volatility_score > 0:
                    # Convert downside volatility score (0-100) to percentile
                    downside_volatility_percentile = 100 - downside_volatility_score  # Invert: higher downside vol = lower score
                    if downside_volatility_percentile is not None:
                        components.append(downside_volatility_percentile)
                        weights.append(0.10)

                # Required: drawdown (20% - directly measures maximum drop from peak)
                if drawdown_percentile is not None:
                    components.append(drawdown_percentile)
                    weights.append(0.20)

                # Optional: beta (5% if available - measures market correlation)
                if beta is not None and stability_metrics and stability_metrics.get('beta'):
                    # Use DYNAMIC percentile ranking for beta (lower is better - less volatile than market)
                    beta_percentile = calculate_z_score_normalized(beta, stability_metrics['beta'])
                    # Invert: lower beta (more stable) should score higher
                    beta_percentile = 100 - beta_percentile if beta_percentile is not None else None
                    if beta_percentile is not None:
                        components.append(beta_percentile)
                        weights.append(0.05)
                else:
                    logger.info(f"{symbol}: Beta missing - calculating stability without beta")

                # LONG-TERM STABILITY (15% total) - annual price range:
                # 52-week range measures whether stock stays in consistent band or has wild swings
                if range_52w_score is not None:
                    components.append(range_52w_score)
                    weights.append(0.15)

                # LIQUIDITY METRICS (35% total - illiquid stocks = less stable price action):
                # These measure trading volume consistency and cost (spreads) - key indicator of price stability
                if volume_consistency_score is not None:
                    components.append(volume_consistency_score)
                    weights.append(0.12)
                if daily_spread_score is not None:
                    components.append(daily_spread_score)
                    weights.append(0.12)
                if turnover_velocity_score is not None:
                    components.append(turnover_velocity_score)
                    weights.append(0.11)

                # Check if we have at least one component
                if len(components) == 0:
                    risk_stability_score = None
                    logger.warning(f"{symbol}: ⚠️ NO STABILITY COMPONENTS FOUND - vol_percentile={vol_percentile}, drawdown_percentile={drawdown_percentile}, range_52w={range_52w_score}, vol_consistency={volume_consistency_score}, beta={beta}")
                else:
                    # Re-normalize weights to sum to 1.0 (in case some components are missing)
                    total_weight = sum(weights)
                    if total_weight > 0:
                        normalized_weights = [w / total_weight for w in weights]

                        # Calculate weighted composite (multi-timeframe: 50% price action + 35% liquidity + 15% annual range)
                        risk_stability_score = sum(c * w for c, w in zip(components, normalized_weights))
                        risk_stability_score = max(0, min(100, risk_stability_score))
                    else:
                        risk_stability_score = None
                        logger.warning(f"{symbol}: Total weight is zero - stability calculation impossible")

                    # NOTE: stability_inputs already populated above (BEFORE score calculation)
                    # Multi-timeframe model - short-term volatility, long-term range, market liquidity

                    # Log with proper null handling
                    vol_str = f"{vol_percentile:.0f}" if vol_percentile is not None else "N/A"
                    drawdown_str = f"{drawdown_percentile:.0f}" if drawdown_percentile is not None else "N/A"
                    range_str = f", Range_52W={range_52w_pct:.1f}%" if range_52w_pct is not None else ""
                    beta_str = f", Beta_pct={100 - calculate_z_score_normalized(beta, stability_metrics['beta']):.0f}" if (beta is not None and stability_metrics and stability_metrics.get('beta') and calculate_z_score_normalized(beta, stability_metrics['beta']) is not None) else ""
                    logger.info(f"{symbol} Stability Score: {risk_stability_score:.1f} (Vol_pct={vol_str}, Drawdown_pct={drawdown_str}{range_str}{beta_str}, multi-timeframe: 50% price action + 35% liquidity + 15% annual range)")

                    # Assign to stability_score for final output
                    stability_score = risk_stability_score

        except Exception as e:
            import traceback
            logger.error(f"{symbol}: Risk calculation failed: {e}")
            logger.error(traceback.format_exc())
            # FIX: Handle transaction errors gracefully
            try:
                conn.rollback()  # Roll back failed transaction
                logger.info(f"{symbol}: Transaction rolled back, continuing")
            except Exception as rollback_error:
                logger.warning(f"{symbol}: Rollback failed ({rollback_error}), attempting reconnect")
                try:
                    # Try to reconnect if transaction is in bad state
                    conn.close()
                    conn = get_db_connection()
                    if conn:
                        logger.info(f"{symbol}: Reconnected to database")
                except Exception as reconnect_error:
                    logger.error(f"{symbol}: Could not reconnect ({reconnect_error})")
            # No fallback - stability_score remains None if calculation fails

        # Get quality metrics from key_metrics table for percentile-based quality score
        stock_roe = None
        stock_roa = None
        stock_gross_margin = None
        stock_debt_to_equity = None
        stock_current_ratio = None
        stock_fcf_to_ni = None
        # REFACTORED: Now fetch pre-calculated inputs from quality_metrics table (populated by loadfactormetrics.py)
        stock_roic = None
        stock_operating_margin = None
        stock_profit_margin = None
        stock_operating_cf_to_ni = None
        stock_quick_ratio = None
        stock_payout_ratio = None
        stock_eps_growth_stability = None
        stock_roe_stability_index = None

        try:
            # Fetch quality inputs from key_metrics table (yfinance data - best coverage)
            cur.execute("""
                SELECT
                    return_on_equity_pct,
                    return_on_assets_pct,
                    gross_margin_pct,
                    debt_to_equity,
                    current_ratio,
                    operating_margin_pct,
                    profit_margin_pct,
                    quick_ratio,
                    payout_ratio
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            qm_data = cur.fetchone()
            if qm_data:
                roe, roa, gross_margin, debt_to_equity, current_ratio, op_margin, profit_margin, quick_ratio, payout_ratio = qm_data
                stock_roe = float(roe) if roe is not None else None
                stock_roa = float(roa) if roa is not None else None
                stock_gross_margin = float(gross_margin) if gross_margin is not None else None
                stock_debt_to_equity = float(debt_to_equity) if debt_to_equity is not None else None
                stock_current_ratio = float(current_ratio) if current_ratio is not None else None
                stock_operating_margin = float(op_margin) if op_margin is not None else None
                stock_profit_margin = float(profit_margin) if profit_margin is not None else None
                stock_quick_ratio = float(quick_ratio) if quick_ratio is not None else None
                stock_payout_ratio = float(payout_ratio) if payout_ratio is not None else None

                # Note: These columns don't exist in key_metrics (would need statement loader data):
                # - return_on_invested_capital_pct
                # - fcf_to_net_income, operating_cf_to_net_income (need CF statement data)
                # - eps_growth_stability (need historical EPS data)
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Key metrics table query failed for {symbol}: {e}")

        # Fetch missing quality components from quality_metrics table (populated by loadfactormetrics.py)
        try:
            cur.execute("""
                SELECT
                    fcf_to_net_income,
                    eps_growth_stability,
                    earnings_surprise_avg,
                    operating_cf_to_net_income,
                    roe_stability_index
                FROM quality_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))

            qm_row = cur.fetchone()
            if qm_row:
                fcf_ni, eps_stab, earn_surp, ocf_ni, roe_stab = qm_row
                stock_fcf_to_ni = float(fcf_ni) if fcf_ni is not None else None
                stock_eps_growth_stability = float(eps_stab) if eps_stab is not None else None
                stock_roe_stability_index = float(roe_stab) if roe_stab is not None else None
                # earnings_surprise_score will be calculated from this below
                # stock_operating_cf_to_ni = float(ocf_ni) if ocf_ni is not None else None
        except psycopg2.Error as e:
            conn.rollback()
            logger.debug(f"Quality metrics table query failed for {symbol}: {e}")

        # Get growth metrics from key_metrics table for percentile-based growth score
        stock_revenue_growth = None
        stock_earnings_growth = None
        stock_earnings_q_growth = None
        stock_gross_margin_growth = None
        stock_operating_margin_growth = None
        stock_net_margin_growth = None
        stock_sustainable_growth = None
        stock_quarterly_growth_momentum = None
        stock_operating_income_growth_yoy = None
        stock_net_income_growth_yoy = None
        stock_fcf_growth_yoy = None
        stock_ocf_growth_yoy = None
        stock_asset_growth_yoy = None

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
                stock_payout_ratio = float(payout) if payout is not None else None

                # Calculate sustainable growth rate: ROE × (1 - payout_ratio)
                if roe_for_growth is not None and payout is not None:
                    payout_ratio = min(float(payout), 1.0)  # Cap at 1.0
                    stock_sustainable_growth = float(roe_for_growth) * (1 - payout_ratio)
        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Growth metrics query failed for {symbol}: {e}")

        # Fetch growth metrics from growth_metrics table (includes YoY growth rates and margin trends)
        try:
            cur.execute("""
                SELECT quarterly_growth_momentum, operating_margin_trend, net_margin_trend,
                       operating_income_growth_yoy, net_income_growth_yoy, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy
                FROM growth_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
            """, (symbol,))

            qgm_data = cur.fetchone()
            if qgm_data:
                qgm_value, op_margin_trend, net_margin_trend, oi_growth_yoy, ni_growth_yoy, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy = qgm_data
                stock_quarterly_growth_momentum = float(qgm_value) if qgm_value is not None else None
                stock_operating_margin_growth = float(op_margin_trend) if op_margin_trend is not None else None
                stock_net_margin_growth = float(net_margin_trend) if net_margin_trend is not None else None
                stock_operating_income_growth_yoy = float(oi_growth_yoy) if oi_growth_yoy is not None else None
                stock_net_income_growth_yoy = float(ni_growth_yoy) if ni_growth_yoy is not None else None
                stock_fcf_growth_yoy = float(fcf_growth_yoy) if fcf_growth_yoy is not None else None
                stock_ocf_growth_yoy = float(ocf_growth_yoy) if ocf_growth_yoy is not None else None
                stock_asset_growth_yoy = float(asset_growth_yoy) if asset_growth_yoy is not None else None
        except psycopg2.Error as e:
            conn.rollback()
            logger.debug(f"Growth metrics query failed for {symbol}: {e}")

        # Calculate individual scores (0-100 scale)

        # ============================================================
        # Momentum Score - 6-Component Industry-Standard System
        # Based on academic momentum research (Jegadeesh & Titman, AQR, Dimensional)
        # ============================================================

        # Convert all technical indicators from Decimal to float to avoid type mismatches
        # PostgreSQL returns numeric values as Decimal objects that don't work with Python floats
        try:
            if 'rsi' in locals() and rsi is not None:
                rsi = float(rsi)
            if 'macd' in locals() and macd is not None:
                macd = float(macd)
            if 'macd_hist' in locals() and macd_hist is not None:
                macd_hist = float(macd_hist)
            if 'current_price' in locals() and current_price is not None:
                current_price = float(current_price)
            if 'sma_50' in locals() and sma_50 is not None:
                sma_50 = float(sma_50)
            if 'momentum_3m' in locals() and momentum_3m is not None:
                momentum_3m = float(momentum_3m)
            if 'momentum_6m' in locals() and momentum_6m is not None:
                momentum_6m = float(momentum_6m)
            if 'momentum_12m' in locals() and momentum_12m is not None:
                momentum_12m = float(momentum_12m)
        except (ValueError, TypeError) as e:
            logger.warning(f"{symbol}: Type conversion warning in momentum score - {e}")

        # Component 1: Intraweek Trend Confirmation (10 points) - Technical Indicators
        # Confirms current momentum through RSI, MACD, and price vs SMA50
        # NO DEFAULTS - only real data. Return None if any component missing.
        intraweek_confirmation = None

        # RSI sub-component (0-4 points) - overbought/oversold detection
        # REAL DATA ONLY - None if RSI missing
        rsi_score = None
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
        # REAL DATA ONLY - None if MACD/histogram missing
        macd_score = None
        if macd is not None and macd_hist is not None:
            if macd > 0:
                macd_score = 1.5 + min(abs(macd) * 0.5, 1.5)  # 1.5-3 for positive
            else:
                macd_score = max(0, 1.5 + macd * 0.5)  # 0-1.5 for negative

            # Bonus for MACD histogram (momentum acceleration)
            if macd_hist is not None and macd_hist > 0:
                macd_score = min(3, macd_score + 0.25)

        # Calculate price vs SMA50 deviation if not already available
        price_vs_sma_50 = None
        if current_price is not None and sma_50 is not None and bool(float(sma_50) > 0):
            # Values are already converted to float in the conversion block above
            price_vs_sma_50 = ((current_price - sma_50) / sma_50) * 100

        # Calculate price vs SMA200 deviation if not already available
        price_vs_sma_200 = None
        if current_price is not None and sma_200 is not None and bool(float(sma_200) > 0):
            # Values are already converted to float from price_data
            price_vs_sma_200 = ((current_price - sma_200) / sma_200) * 100

        # Calculate price vs 52-week high
        price_vs_52w_high = None
        if current_price is not None and high_52w is not None and bool(float(high_52w) > 0):
            price_vs_52w_high = ((current_price - high_52w) / high_52w) * 100

        # Price vs SMA50 sub-component (0-3 points) - trend confirmation
        # REAL DATA ONLY - None if price_vs_sma_50 missing
        sma50_score = None
        if price_vs_sma_50 is not None:
            if price_vs_sma_50 > 5:
                sma50_score = 2.5 + min(price_vs_sma_50 * 0.2, 0.5)  # 2.5-3 for strong above
            elif price_vs_sma_50 > 0:
                sma50_score = 1.5 + (price_vs_sma_50 * 0.2)  # 1.5-2.5 for above
            elif price_vs_sma_50 > -5:
                sma50_score = 0.5 + (price_vs_sma_50 + 5) * 0.2  # 0.5-1.5 for slightly below
            else:
                sma50_score = max(0, 0.5 + (price_vs_sma_50 + 5) * 0.1)  # 0-0.5 for well below

        # Only combine if ALL three sub-components have real data
        if rsi_score is not None and macd_score is not None and sma50_score is not None:
            intraweek_confirmation = rsi_score + macd_score + sma50_score
            momentum_intraweek = intraweek_confirmation  # Store for API response
        else:
            intraweek_confirmation = None
            momentum_intraweek = None
            if rsi_score is None:
                logger.debug(f"{symbol}: RSI missing - intraweek_confirmation = None")
            if macd_score is None:
                logger.debug(f"{symbol}: MACD missing - intraweek_confirmation = None")
            if sma50_score is None:
                logger.debug(f"{symbol}: SMA50 missing - intraweek_confirmation = None")

        # Component 2-4: Momentum Returns using Percentile Normalization (like other scores)
        # Three timeframes weighted equally (1/3 each of total momentum score)
        # REAL DATA ONLY - no neutral defaults
        momentum_components = []
        momentum_weights = []

        # Initialize momentum component scores (will be set if data available)
        # Start as None - only set if real data exists
        momentum_3m_score = None
        momentum_6m_score = None
        momentum_12_3_score = None

        # Get all momentum values for percentile calculation
        # Load all momentum metrics from database for percentile ranking
        # ONE WAY ONLY: Latest date, all symbols, all 3 components or NULL
        momentum_metrics = []
        try:
            # Get the most recent date with momentum data (deterministic, not fallback)
            cur.execute("""
                SELECT DISTINCT date FROM momentum_metrics
                WHERE momentum_3m IS NOT NULL OR momentum_6m IS NOT NULL OR momentum_12m IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """)
            latest_date_row = cur.fetchone()

            if latest_date_row:
                latest_date = latest_date_row[0]
                # Fetch ALL momentum metrics for that date (5,025 symbols)
                # This builds the full percentile pool from the same date
                cur.execute("""
                    SELECT momentum_3m, momentum_6m, momentum_12m
                    FROM momentum_metrics
                    WHERE date = %s
                    AND (momentum_3m IS NOT NULL OR momentum_6m IS NOT NULL OR momentum_12m IS NOT NULL)
                """, (latest_date,))

                for row in cur.fetchall():
                    momentum_metrics.append({
                        'momentum_3m': row[0],
                        'momentum_6m': row[1],
                        'momentum_12m': row[2]
                    })

                logger.debug(f"Loaded {len(momentum_metrics)} momentum metrics from {latest_date} (single date, deterministic)")
            else:
                logger.warning("No momentum data available in momentum_metrics table")
                momentum_metrics = []
        except Exception as e:
            logger.warning(f"⚠️ {symbol}: Error fetching momentum metrics for percentile calculation: {e}")
            logger.debug(f"Exception details: {type(e).__name__}")
            momentum_metrics = []

        # CRITICAL FIX: Safely extract momentum values from metrics, handling NumPy types
        # NumPy arrays/scalars can't be evaluated in boolean context (is not None)
        all_3m = []
        all_6m = []
        all_12_3 = []
        for m in momentum_metrics:
            try:
                val_3m = m.get('momentum_3m')
                # Try-except wrapping even the None check in case NumPy array is passed
                try:
                    is_not_none = val_3m is not None
                except (ValueError, TypeError):
                    is_not_none = False
                if is_not_none:
                    all_3m.append(float(val_3m))
            except (ValueError, TypeError):
                pass
            try:
                val_6m = m.get('momentum_6m')
                try:
                    is_not_none = val_6m is not None
                except (ValueError, TypeError):
                    is_not_none = False
                if is_not_none:
                    all_6m.append(float(val_6m))
            except (ValueError, TypeError):
                pass
            try:
                val_12m = m.get('momentum_12m')
                try:
                    is_not_none = val_12m is not None
                except (ValueError, TypeError):
                    is_not_none = False
                if is_not_none:
                    all_12_3.append(float(val_12m))
            except (ValueError, TypeError):
                pass

        logger.debug(f"{symbol}: Momentum pools - 3m={len(all_3m)}, 6m={len(all_6m)}, 12_3={len(all_12_3)}")

        # 3-month momentum (medium-term)
        if momentum_3m is not None and len(all_3m) > 0:
            momentum_3m_percentile = calculate_z_score_normalized(float(momentum_3m), all_3m)
            if momentum_3m_percentile is not None:
                momentum_3m_score = (momentum_3m_percentile / 100) * 100
                momentum_components.append(momentum_3m_score)
                momentum_weights.append(0.20)  # 20% for medium-term
            else:
                logger.debug(f"{symbol}: momentum_3m percentile calculation returned None (value={momentum_3m}, pool_size={len(all_3m)})")

        # 6-month momentum (longer medium-term)
        if momentum_6m is not None and len(all_6m) > 0:
            momentum_6m_percentile = calculate_z_score_normalized(float(momentum_6m), all_6m)
            if momentum_6m_percentile is not None:
                momentum_6m_score = (momentum_6m_percentile / 100) * 100
                momentum_components.append(momentum_6m_score)
                momentum_weights.append(0.20)  # 20% for longer medium-term
            else:
                logger.debug(f"{symbol}: momentum_6m percentile calculation returned None (value={momentum_6m}, pool_size={len(all_6m)})")

        # 12-month minus 3-month momentum (long-term trend momentum)
        if momentum_12_3 is not None and len(all_12_3) > 0:
            momentum_12_3_percentile = calculate_z_score_normalized(float(momentum_12_3), all_12_3)
            if momentum_12_3_percentile is not None:
                momentum_12_3_score = (momentum_12_3_percentile / 100) * 100
                momentum_components.append(momentum_12_3_score)
                momentum_weights.append(0.15)  # 15% for long-term trend
            else:
                logger.debug(f"{symbol}: momentum_12_3 percentile calculation returned None (value={momentum_12_3}, pool_size={len(all_12_3)})")

        # RSI (Relative Strength Index) - momentum oscillator
        all_rsi = []
        try:
            cur.execute("""
                SELECT rsi FROM technical_data_daily
                WHERE rsi IS NOT NULL
                AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY date DESC
                LIMIT 5000
            """)
            for row in cur.fetchall():
                if row[0] is not None:
                    all_rsi.append(float(row[0]))
        except Exception as e:
            logger.debug(f"{symbol}: Could not fetch RSI distribution: {e}")

        if rsi is not None and len(all_rsi) > 100:
            rsi_percentile = calculate_z_score_normalized(float(rsi), all_rsi)
            if rsi_percentile is not None:
                rsi_score = (rsi_percentile / 100) * 100
                momentum_components.append(rsi_score)
                momentum_weights.append(0.10)  # 10% for RSI momentum indicator
                logger.debug(f"{symbol}: Added RSI to momentum (percentile={rsi_percentile:.1f}, score={rsi_score:.1f})")

        # MACD (Moving Average Convergence Divergence) - momentum indicator
        all_macd = []
        try:
            cur.execute("""
                SELECT macd FROM technical_data_daily
                WHERE macd IS NOT NULL
                AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY date DESC
                LIMIT 5000
            """)
            for row in cur.fetchall():
                if row[0] is not None:
                    all_macd.append(float(row[0]))
        except Exception as e:
            logger.debug(f"{symbol}: Could not fetch MACD distribution: {e}")

        if macd is not None and len(all_macd) > 100:
            macd_percentile = calculate_z_score_normalized(float(macd), all_macd)
            if macd_percentile is not None:
                macd_score = (macd_percentile / 100) * 100
                momentum_components.append(macd_score)
                momentum_weights.append(0.10)  # 10% for MACD momentum indicator
                logger.debug(f"{symbol}: Added MACD to momentum (percentile={macd_percentile:.1f}, score={macd_score:.1f})")

        # ADDITIONAL MOMENTUM COMPONENTS: Price position relative to moving averages
        # These provide trend confirmation and reversal signals
        # NOTE: Accumulation/Distribution (A/D) is NOT part of momentum_score but is stored/displayed separately

        # Price vs SMA50 (technical trend confirmation)
        all_price_vs_sma50 = []
        try:
            if price_data and len(price_data) >= 50:
                # Calculate price_vs_sma_50 for all stocks to build distribution
                cur.execute("""
                    SELECT
                        (pd.close - tc.sma_50) / tc.sma_50 * 100 as price_deviation
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily tc ON pd.symbol = tc.symbol AND pd.date = tc.date
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '200 days'
                    AND tc.sma_50 IS NOT NULL
                    AND pd.close IS NOT NULL
                    ORDER BY pd.date DESC
                    LIMIT 5000
                """)
                for row in cur.fetchall():
                    if row[0] is not None:
                        all_price_vs_sma50.append(float(row[0]))
        except Exception as e:
            logger.debug(f"{symbol}: Could not fetch price_vs_sma50 distribution: {e}")

        if price_vs_sma_50 is not None and len(all_price_vs_sma50) > 100:
            price_vs_sma50_percentile = calculate_z_score_normalized(float(price_vs_sma_50), all_price_vs_sma50)
            if price_vs_sma50_percentile is not None:
                price_vs_sma50_score = (price_vs_sma50_percentile / 100) * 100
                momentum_components.append(price_vs_sma50_score)
                momentum_weights.append(0.16)  # 16% weight for trend confirmation
                logger.debug(f"{symbol}: Added price_vs_sma50 to momentum (percentile={price_vs_sma50_percentile:.1f}, score={price_vs_sma50_score:.1f})")

        # Price vs SMA200 (longer-term trend)
        all_price_vs_sma200 = []
        try:
            if price_data and len(price_data) >= 200:
                cur.execute("""
                    SELECT
                        (pd.close - tc.sma_200) / tc.sma_200 * 100 as price_deviation
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily tc ON pd.symbol = tc.symbol AND pd.date = tc.date
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '200 days'
                    AND tc.sma_200 IS NOT NULL
                    AND pd.close IS NOT NULL
                    ORDER BY pd.date DESC
                    LIMIT 5000
                """)
                for row in cur.fetchall():
                    if row[0] is not None:
                        all_price_vs_sma200.append(float(row[0]))
        except Exception as e:
            logger.debug(f"{symbol}: Could not fetch price_vs_sma200 distribution: {e}")

        if price_vs_sma_200 is not None and len(all_price_vs_sma200) > 100:
            price_vs_sma200_percentile = calculate_z_score_normalized(float(price_vs_sma_200), all_price_vs_sma200)
            if price_vs_sma200_percentile is not None:
                price_vs_sma200_score = (price_vs_sma200_percentile / 100) * 100
                momentum_components.append(price_vs_sma200_score)
                momentum_weights.append(0.17)  # 17% weight for long-term trend
                logger.debug(f"{symbol}: Added price_vs_sma200 to momentum (percentile={price_vs_sma200_percentile:.1f}, score={price_vs_sma200_score:.1f})")

        # Price vs 52W High (recovery potential)
        all_price_vs_52w = []
        try:
            if price_data and len(price_data) >= 252:
                cur.execute("""
                    SELECT
                        (pd.close - MAX(pd.high) OVER (PARTITION BY pd.symbol ORDER BY pd.date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW)) / MAX(pd.high) OVER (PARTITION BY pd.symbol ORDER BY pd.date ROWS BETWEEN 252 PRECEDING AND CURRENT ROW) * 100 as price_deviation
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '300 days'
                    ORDER BY pd.date DESC
                    LIMIT 5000
                """)
                for row in cur.fetchall():
                    if row[0] is not None:
                        all_price_vs_52w.append(float(row[0]))
        except Exception as e:
            logger.debug(f"{symbol}: Could not fetch price_vs_52w distribution: {e}")

        if price_vs_52w_high is not None and len(all_price_vs_52w) > 100:
            price_vs_52w_percentile = calculate_z_score_normalized(float(price_vs_52w_high), all_price_vs_52w)
            if price_vs_52w_percentile is not None:
                price_vs_52w_score = (price_vs_52w_percentile / 100) * 100
                momentum_components.append(price_vs_52w_score)
                momentum_weights.append(0.17)  # 17% weight for recovery potential
                logger.debug(f"{symbol}: Added price_vs_52w_high to momentum (percentile={price_vs_52w_percentile:.1f}, score={price_vs_52w_score:.1f})")

        # Calculate momentum score using percentile normalization (consistent with other scores)
        # FLEXIBLE: Require at least 2/6 components with dynamic weight normalization
        if len(momentum_components) >= 2:  # At least 2 components required
            # Calculate weighted average with remaining components
            total_weight = sum(momentum_weights)
            if total_weight > 0:
                normalized_weights = [w / total_weight for w in momentum_weights]
                momentum_score = sum(score * weight for score, weight in zip(momentum_components, normalized_weights))
                momentum_score = max(0, min(100, momentum_score))
                logger.debug(f"{symbol}: Momentum score calculated from {len(momentum_components)}/6 components: {momentum_score:.2f}")
            else:
                momentum_score = None
                logger.debug(f"{symbol}: Momentum weights sum to zero - momentum_score = NULL")
        else:
            # Missing too many components (fewer than 2) - no score
            momentum_score = None
            logger.debug(f"{symbol}: Missing momentum components - only {len(momentum_components)}/6 available - momentum_score = NULL")

        # ============================================================
        # Value Score - Comprehensive Percentile-Based Valuation with NESTED NORMALIZATION
        # CRITICAL: Requires at least ONE valuation metric (PE, PB, PS, EV/EBITDA, etc)
        # Uses NESTED NORMALIZATION (like Quality score) to achieve proper 0-100 range
        # Groups: Valuation Multiples (45%), Enterprise Value (35%), Growth-Adjusted (15%), Dividend (5%)
        # ============================================================
        value_score = None
        fcf_yield = None  # Initialize FCF Yield

        # Calculate value score directly from key_metrics with professional standards
        try:
            cur.execute("""
                SELECT
                    trailing_pe,
                    forward_pe,
                    price_to_book,
                    price_to_sales_ttm,
                    peg_ratio,
                    ev_to_revenue,
                    ev_to_ebitda,
                    free_cashflow,
                    dividend_yield,
                    earnings_growth_pct,
                    dividend_rate,
                    last_annual_dividend_amt,
                    eps_trailing,
                    net_income
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            km = cur.fetchone()
            if km:
                # Extract raw valuation metrics
                trailing_pe = km[0]
                forward_pe = km[1]
                price_to_book = km[2]
                price_to_sales_ttm = km[3]
                peg_ratio_val = km[4]
                ev_to_revenue = km[5]
                ev_to_ebitda = km[6]
                free_cashflow = km[7]
                dividend_yield_val = km[8]
                earnings_growth_pct = km[9]
                dividend_rate = km[10]
                last_annual_dividend_amt = km[11]
                eps_trailing = km[12]
                net_income = km[13]

                # CHECK IF COMPANY IS UNPROFITABLE
                # For VALUE scoring, unprofitable companies should rank at bottom, not be excluded
                is_unprofitable = (eps_trailing is not None and eps_trailing < 0) or \
                                 (net_income is not None and net_income < 0)

                # For unprofitable companies with NULL P/E metrics, we know WHY they're NULL
                # (no earnings) - this is a REAL value signal (bad value), not missing data

                # CALCULATE PEG RATIO if missing (3X better coverage by calculating ourselves)
                # PEG = PE / Earnings Growth Rate
                if peg_ratio_val is None and earnings_growth_pct is not None:
                    try:
                        growth_pct = float(earnings_growth_pct)
                        if growth_pct > 0:
                            # Use forward PE if available, otherwise trailing PE
                            pe_for_peg = forward_pe if forward_pe is not None and forward_pe > 0 else trailing_pe
                            if pe_for_peg is not None:
                                pe_val = float(pe_for_peg)
                                if pe_val > 0:
                                    peg_ratio_val = pe_val / growth_pct
                                    logger.debug(f"{symbol}: Calculated PEG={peg_ratio_val:.2f} from PE={pe_val:.2f} / Growth={growth_pct:.2f}%")
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        pass

                # CALCULATE DIVIDEND YIELD if missing
                # Dividend Yield = (Annual Dividend / Current Price) * 100
                if dividend_yield_val is None and current_price is not None:
                    try:
                        price_val = float(current_price)
                        if price_val > 0:
                            annual_div = dividend_rate if dividend_rate is not None else last_annual_dividend_amt
                            if annual_div is not None:
                                div_val = float(annual_div)
                                if div_val > 0:
                                    dividend_yield_val = (div_val / price_val) * 100
                                    logger.debug(f"{symbol}: Calculated dividend_yield={dividend_yield_val:.2f}% from div={div_val:.2f} / price={price_val:.2f}")
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        pass

                # Calculate FCF Yield from free_cashflow and market_cap (market_cap calculated earlier in code)
                fcf_yield = None
                if free_cashflow is not None and market_cap is not None and market_cap > 0:
                    fcf_yield = (free_cashflow / market_cap) * 100  # As percentage

                # INDUSTRY STANDARD: Check if we have AT LEAST ONE valuation metric (flexible weighting)
                # Supports both profitable companies (with PE) and unprofitable (with EV/EBITDA, P/B, P/S)
                # This is the professional quantitative finance approach (Fama-French, MSCI, AQR)
                # CRITICAL: EV/EBITDA, P/B can be NEGATIVE for unprofitable/negative equity companies - allow both signs!
                has_any_metric = (
                    (trailing_pe is not None and trailing_pe > 0 and trailing_pe < 5000) or
                    (price_to_book is not None and price_to_book != 0 and abs(price_to_book) < 5000) or
                    (price_to_sales_ttm is not None and price_to_sales_ttm > 0 and price_to_sales_ttm < 5000) or
                    (peg_ratio_val is not None and peg_ratio_val > 0 and peg_ratio_val < 5000) or
                    (ev_to_revenue is not None and ev_to_revenue > 0 and ev_to_revenue < 5000) or
                    (ev_to_ebitda is not None and abs(ev_to_ebitda) > 0 and abs(ev_to_ebitda) < 5000)
                )

                if not has_any_metric:
                    value_score = None
                    logger.debug(f"{symbol}: No valuation metrics available (PE={trailing_pe}, PB={price_to_book}, PS={price_to_sales_ttm}, EV/EBITDA={ev_to_ebitda}) - value_score = NULL")
                else:
                    # NESTED NORMALIZATION APPROACH (Like Quality Score for consistency)
                    # Step 1: Normalize each category internally, Step 2: Aggregate categories

                    # ========================
                    # CATEGORY 1: VALUATION MULTIPLES (45% weight)
                    # ========================
                    valuation_components = []
                    valuation_weights = []

                    # PE Ratio (20 pts max) - Primary valuation metric (Trailing P/E)
                    # CRITICAL: Unprofitable companies get low score, not excluded
                    # NULL P/E for unprofitable = bad value signal, not missing data
                    if value_metrics is not None and value_metrics.get('pe'):
                        if trailing_pe is not None and trailing_pe > 0:
                            # Has P/E ratio - normal scoring
                            pe_percentile = calculate_z_score_normalized(-float(trailing_pe),
                                                                         [-pe for pe in value_metrics.get('pe', []) if pe is not None])
                            if pe_percentile is not None:
                                valuation_components.append(pe_percentile)
                                valuation_weights.append(20)
                        elif is_unprofitable:
                            # Unprofitable (NULL P/E but has negative earnings)
                            # Give bottom 5th percentile - worse than expensive stocks
                            valuation_components.append(5.0)
                            valuation_weights.append(20)
                            logger.debug(f"{symbol}: Unprofitable - P/E penalty score=5.0")

                    # Forward PE Ratio (20 pts max) - Forward-looking valuation
                    # CRITICAL: Unprofitable companies get low score, not excluded
                    if value_metrics is not None and value_metrics.get('forward_pe'):
                        if forward_pe is not None and forward_pe > 0 and forward_pe < 5000:
                            # Has forward P/E - normal scoring
                            forward_pe_percentile = calculate_z_score_normalized(-float(forward_pe),
                                                                               [-fpe for fpe in value_metrics.get('forward_pe', []) if fpe is not None])
                            if forward_pe_percentile is not None:
                                valuation_components.append(forward_pe_percentile)
                                valuation_weights.append(20)
                        elif is_unprofitable and trailing_pe is None:
                            # Unprofitable with no forward guidance either
                            # Give bottom 5th percentile
                            valuation_components.append(5.0)
                            valuation_weights.append(20)
                            logger.debug(f"{symbol}: Unprofitable - Forward P/E penalty score=5.0")

                    # PB Ratio (25 pts max) - Book value measure
                    # CRITICAL FIX: Skip missing metrics entirely instead of defaulting to 0
                    if value_metrics is not None and value_metrics.get('pb') and price_to_book is not None and price_to_book != 0 and abs(price_to_book) < 5000:
                        pb_percentile = calculate_z_score_normalized(-float(price_to_book),
                                                                     [-pb for pb in value_metrics.get('pb', []) if pb is not None])
                        if pb_percentile is not None:
                            valuation_components.append(pb_percentile)
                            valuation_weights.append(25)

                    # PS Ratio (25 pts max) - Revenue-based measure
                    # Allow negative values (for negative sales companies)
                    if value_metrics is not None and value_metrics.get('ps') and price_to_sales_ttm is not None and price_to_sales_ttm != 0 and abs(price_to_sales_ttm) < 5000:
                        ps_percentile = calculate_z_score_normalized(-float(price_to_sales_ttm),
                                                                     [-ps for ps in value_metrics.get('ps', []) if ps is not None])
                        if ps_percentile is not None:
                            valuation_components.append(ps_percentile)
                            valuation_weights.append(25)

                    # ===========================
                    # CATEGORY 2: ENTERPRISE VALUE METRICS (35% weight)
                    # ===========================
                    ev_components = []
                    ev_weights = []

                    # EV/EBITDA
                    # CRITICAL FIX: Skip missing metrics entirely instead of defaulting to 0
                    if value_metrics is not None and value_metrics.get('ev_ebitda') and ev_to_ebitda is not None and abs(ev_to_ebitda) > 0 and abs(ev_to_ebitda) < 5000:
                        ev_ebitda_percentile = calculate_z_score_normalized(-float(ev_to_ebitda),
                                                                            [-ev for ev in value_metrics.get('ev_ebitda', []) if ev is not None])
                        if ev_ebitda_percentile is not None:
                            ev_components.append(ev_ebitda_percentile)
                            ev_weights.append(50)

                    # EV/Revenue
                    # Allow negative values (for negative EV or revenue companies)
                    if value_metrics is not None and value_metrics.get('ev_revenue') and ev_to_revenue is not None and ev_to_revenue != 0 and abs(ev_to_revenue) < 5000:
                        ev_rev_percentile = calculate_z_score_normalized(-float(ev_to_revenue),
                                                                         [-ev for ev in value_metrics.get('ev_revenue', []) if ev is not None])
                        if ev_rev_percentile is not None:
                            ev_components.append(ev_rev_percentile)
                            ev_weights.append(50)

                    # ==========================
                    # CATEGORY 3: GROWTH-ADJUSTED (15% weight)
                    # ==========================
                    growth_components = []
                    growth_weights = []

                    # PEG Ratio
                    # CRITICAL: Unprofitable companies get low score, not excluded
                    # NULL PEG for unprofitable = bad value signal, not missing data
                    if value_metrics is not None and value_metrics.get('peg'):
                        if peg_ratio_val is not None and peg_ratio_val > 0 and peg_ratio_val < 500:
                            # Has PEG ratio - normal scoring
                            peg_percentile = calculate_z_score_normalized(-float(peg_ratio_val),
                                                                      [-peg for peg in value_metrics.get('peg', []) if peg is not None])
                            if peg_percentile is not None:
                                growth_components.append(peg_percentile)
                                growth_weights.append(100)
                        elif is_unprofitable:
                            # Unprofitable (NULL PEG - no earnings growth to measure)
                            # Give bottom 5th percentile - worse than high PEG stocks
                            growth_components.append(5.0)
                            growth_weights.append(100)
                            logger.debug(f"{symbol}: Unprofitable - PEG penalty score=5.0")

                    # =====================
                    # CATEGORY 4: DIVIDEND (5% weight)
                    # =====================
                    dividend_components = []
                    dividend_weights = []

                    # Dividend Yield
                    if dividend_yield_val is not None and dividend_yield_val > 0:
                        try:
                            div_yield = float(dividend_yield_val)
                            if div_yield > 0.001:
                                if value_metrics is not None and value_metrics.get('dividend_yield'):
                                    div_percentile = calculate_z_score_normalized(div_yield,
                                                                              value_metrics.get('dividend_yield', []))
                                    if div_percentile is not None:
                                        dividend_components.append(div_percentile)
                                        dividend_weights.append(100)
                        except (ValueError, TypeError):
                            pass

                    # =====================
                    # CATEGORY 5: FCF YIELD (10% weight)
                    # =====================
                    fcf_components = []
                    fcf_weights = []

                    # FCF Yield - Free Cash Flow yield (VALUE metric - inverse of P/FCF)
                    # Higher FCF yield = cheaper relative to cash generation = better value
                    if fcf_yield is not None:
                        try:
                            fcf_val = float(fcf_yield)
                            if abs(fcf_val) > 0.001:
                                if value_metrics is not None and value_metrics.get('fcf_yield'):
                                    # Higher FCF yield = better value (don't invert)
                                    fcf_percentile = calculate_z_score_normalized(fcf_val,
                                                                                  value_metrics.get('fcf_yield', []))
                                    if fcf_percentile is not None:
                                        fcf_components.append(fcf_percentile)
                                        fcf_weights.append(100)
                        except (ValueError, TypeError):
                            pass

                    # CRITICAL FIX: COMBINE ALL COMPONENTS AT FACTOR LEVEL (NOT NESTED NORMALIZATION)
                    # Do NOT normalize categories separately - combine all raw components with proper weights
                    # then apply single z-score normalization at the factor level
                    value_components = []
                    value_weights = []

                    # Add all valuation components with 45% category weight
                    for comp, weight in zip(valuation_components, valuation_weights):
                        value_components.append(comp)
                        value_weights.append(weight * 0.45)  # Category weight

                    # Add all EV components with 30% category weight
                    for comp, weight in zip(ev_components, ev_weights):
                        value_components.append(comp)
                        value_weights.append(weight * 0.30)

                    # Add all growth components with 10% category weight
                    for comp, weight in zip(growth_components, growth_weights):
                        value_components.append(comp)
                        value_weights.append(weight * 0.10)

                    # Add all dividend components with 5% category weight
                    for comp, weight in zip(dividend_components, dividend_weights):
                        value_components.append(comp)
                        value_weights.append(weight * 0.05)

                    # Add all FCF yield components with 10% category weight
                    for comp, weight in zip(fcf_components, fcf_weights):
                        value_components.append(comp)
                        value_weights.append(weight * 0.10)

                    # Calculate value_score with SINGLE z-score normalization (NO NESTED NORMALIZATION)
                    # FIX #5: Apply weights AFTER aggregation, not before
                    value_score = None
                    if len(value_components) > 0:
                        # Step 1: Aggregate raw components (these are already percentile-normalized individual inputs)
                        total_weight = sum(value_weights)
                        normalized_weights = [w / total_weight for w in value_weights]
                        aggregated_value = sum(c * w for c, w in zip(value_components, normalized_weights))

                        # Step 2: Normalize aggregated value using z-score against all stocks (SINGLE level)
                        # Note: Use aggregated components list for z-score normalization across all stocks
                        if value_metrics and 'aggregated_value' in value_metrics and len(value_metrics['aggregated_value']) > 1:
                            value_score = calculate_z_score_normalized(aggregated_value, value_metrics['aggregated_value'])
                        else:
                            # Fallback: use aggregated value directly (already 0-100 from input percentiles)
                            # Cap at 95 to avoid artificial 100 ceiling (reserves 100 for truly exceptional cases)
                            # This prevents high-percentile stocks from all clustering at 100
                            value_score = max(0, min(95, aggregated_value))
                        logger.debug(f"{symbol} Value Score: {value_score:.2f} (SINGLE LEVEL NORMALIZATION - {len(value_components)} components)")
                    else:
                        value_score = None
                        logger.debug(f"{symbol}: No valid value metrics available - value_score = NULL")

        except Exception as e:
            logger.warning(f"⚠️ {symbol}: EXCEPTION calculating value score from key_metrics: {type(e).__name__}: {e}")

        # Professional standard: No fallback - value_score remains None if professional criteria not met

        # ============================================================
        # Quality Score - Percentile-Based Industry Standard (Fama-French, MSCI, AQR)
        # 4-component system using percentile ranking for market-relative scoring
        # ============================================================
        # REQUIRE quality_score - must calculate from data
        quality_score = None

        # Diagnostic: log if quality metrics are unavailable
        if quality_metrics is None or len(quality_metrics) == 0:
            logger.debug(f"{symbol}: quality_metrics is empty or None - quality_score will be NULL")
        elif stock_roe is None and stock_roa is None and stock_gross_margin is None:
            logger.debug(f"{symbol}: No quality inputs available (ROE/ROA/Gross Margin all NULL)")

        # Only calculate percentile-based quality score if we have quality_metrics data
        if quality_metrics is not None:
            # CRITICAL FIX #3: Dynamic weight normalization for Quality score sub-components
            # Track which sub-components are present for each major component
            # to normalize by actual available weight rather than theoretical max

            # Component 1: Profitability (38 points max) - ROIC, ROE, OpMargin, ROA, OpCF/NI, Profit Margin, Gross Margin
            # REVISED OPTION B: Emphasize ROIC (best capital efficiency metric), add missing metrics
            profitability_score = 0
            profitability_weight_used = 0  # Track actual weight used
            profitability_weight_max = 0   # Track maximum possible for normalization

            # ROIC: 14 pts (36.8%) - PRIMARY capital efficiency metric, increased from 8
            if stock_roic is not None:
                roic_percentile = calculate_z_score_normalized(stock_roic, quality_metrics.get('roic', []))
                profitability_score += (roic_percentile / 100) * 14
                profitability_weight_used += 14
            profitability_weight_max += 14

            # ROE: 10 pts (26.3%) - decreased from 15 to prioritize ROIC
            if stock_roe is not None:
                roe_percentile = calculate_z_score_normalized(stock_roe, quality_metrics.get('roe', []))
                profitability_score += (roe_percentile / 100) * 10
                profitability_weight_used += 10
            profitability_weight_max += 10

            # Operating Margin: 6 pts (15.8%) - NEW: operational execution quality
            if stock_operating_margin is not None:
                opm_percentile = calculate_z_score_normalized(stock_operating_margin, quality_metrics.get('operating_margin', []))
                if opm_percentile is not None:
                    profitability_score += (opm_percentile / 100) * 6
                    profitability_weight_used += 6
            profitability_weight_max += 6

            # ROA: 5 pts (13.2%) - decreased from 12 (overlaps with ROIC & ROE)
            if stock_roa is not None:
                roa_percentile = calculate_z_score_normalized(stock_roa, quality_metrics.get('roa', []))
                if roa_percentile is not None:
                    profitability_score += (roa_percentile / 100) * 5
                    profitability_weight_used += 5
            profitability_weight_max += 5

            # Operating CF/NI: 2 pts (5.3%) - NEW: light weighting, proxy for earnings quality
            if stock_operating_cf_to_ni is not None:
                ocf_percentile = calculate_z_score_normalized(stock_operating_cf_to_ni, quality_metrics.get('operating_cf_to_ni', []))
                if ocf_percentile is not None:
                    profitability_score += (ocf_percentile / 100) * 2
                    profitability_weight_used += 2
            profitability_weight_max += 2

            # Profit Margin: 0.5 pts (1.3%) - NEW: minimal weighting (overlaps with other metrics)
            if stock_profit_margin is not None:
                pm_percentile = calculate_z_score_normalized(stock_profit_margin, quality_metrics.get('profit_margin', []))
                if pm_percentile is not None:
                    profitability_score += (pm_percentile / 100) * 0.5
                    profitability_weight_used += 0.5
            profitability_weight_max += 0.5

            # Gross Margin: 0.5 pts (1.3%) - decreased from 11 (model-dependent, not universal)
            if stock_gross_margin is not None:
                gm_percentile = calculate_z_score_normalized(stock_gross_margin, quality_metrics.get('gross_margin', []))
                if gm_percentile is not None:
                    profitability_score += (gm_percentile / 100) * 0.5
                    profitability_weight_used += 0.5
            profitability_weight_max += 0.5

            # Normalize profitability to 0-100 scale based on available metrics
            if profitability_weight_used > 0:
                profitability_score = (profitability_score / profitability_weight_used) * 100
            else:
                profitability_score = None

            # Component 2: Financial Strength (28 points max) - Debt/Equity, Current Ratio, Quick Ratio, Payout Ratio
            strength_score = 0
            strength_weight_used = 0
            strength_weight_max = 0

            # Debt-to-Equity: 14 pts (50%) - inverted, lower is better
            # SECTOR-AWARE: Compare against same sector peers, not all stocks
            # Insurance/Financial companies have different leverage norms than tech/manufacturing
            if stock_debt_to_equity is not None:
                try:
                    # Get stock's sector from company_profile
                    cur.execute("SELECT sector FROM company_profile WHERE ticker = %s", (symbol,))
                    sector_row = cur.fetchone()
                    stock_sector = sector_row[0] if sector_row else None

                    # Get debt ratios for same sector only
                    if stock_sector:
                        cur.execute("""
                            SELECT qm.debt_to_equity
                            FROM quality_metrics qm
                            JOIN company_profile cp ON qm.ticker = cp.ticker
                            WHERE cp.sector = %s AND qm.debt_to_equity IS NOT NULL
                        """, (stock_sector,))
                        sector_debt_ratios = [row[0] for row in cur.fetchall()]

                        if sector_debt_ratios:
                            # Compare against sector peers
                            debt_percentile = calculate_z_score_normalized(-stock_debt_to_equity,
                                                                        [-d for d in sector_debt_ratios])
                        else:
                            # Fallback to all stocks if sector has no data
                            debt_percentile = calculate_z_score_normalized(-stock_debt_to_equity,
                                                                        [-d for d in quality_metrics.get('debt_to_equity', [])])
                    else:
                        # No sector data, use all stocks
                        debt_percentile = calculate_z_score_normalized(-stock_debt_to_equity,
                                                                    [-d for d in quality_metrics.get('debt_to_equity', [])])

                    if debt_percentile is not None:
                        strength_score += (debt_percentile / 100) * 14
                        strength_weight_used += 14
                except (psycopg2.Error, TypeError, ValueError) as e:
                    logger.debug(f"{symbol}: Could not apply sector-aware debt ranking: {e}, falling back to global ranking")
                    # Fallback to original logic
                    debt_percentile = calculate_z_score_normalized(-stock_debt_to_equity,
                                                                [-d for d in quality_metrics.get('debt_to_equity', [])])
                    if debt_percentile is not None:
                        strength_score += (debt_percentile / 100) * 14
                        strength_weight_used += 14
            strength_weight_max += 14

            # Current Ratio: 7 pts (25%) - higher is better
            if stock_current_ratio is not None:
                current_ratio_percentile = calculate_z_score_normalized(stock_current_ratio,
                                                                     quality_metrics.get('current_ratio', []))
                if current_ratio_percentile is not None:
                    strength_score += (current_ratio_percentile / 100) * 7
                    strength_weight_used += 7
            strength_weight_max += 7

            # Quick Ratio: 4 pts (14.3%) - higher is better, stricter liquidity test than current ratio
            if stock_quick_ratio is not None:
                quick_ratio_percentile = calculate_z_score_normalized(stock_quick_ratio,
                                                                   quality_metrics.get('quick_ratio', []))
                if quick_ratio_percentile is not None:
                    strength_score += (quick_ratio_percentile / 100) * 4
                    strength_weight_used += 4
            strength_weight_max += 4

            # Payout Ratio: 3 pts (10.7%) - moderate is better (30-60%), inverted scoring
            # For payout ratio, moderate values are best - very low and very high are both risky
            if stock_payout_ratio is not None:
                # Ideal payout ratio is around 0.4-0.5, so use distance from 0.45 (inverted)
                payout_percentile = calculate_z_score_normalized(-abs(stock_payout_ratio - 0.45),
                                                              [-abs(p - 0.45) if p is not None else 0
                                                               for p in quality_metrics.get('payout_ratio', [])])
                if payout_percentile is not None:
                    strength_score += (payout_percentile / 100) * 3
                    strength_weight_used += 3
            strength_weight_max += 3

            # Normalize strength to 0-100 scale based on available metrics
            if strength_weight_used > 0:
                strength_score = (strength_score / strength_weight_used) * 100
            else:
                strength_score = None

            # Component 3: Earnings Quality (19 points) - FCF/NI ratio
            earnings_quality_score = None

            if stock_fcf_to_ni is not None:
                fcf_ni_percentile = calculate_z_score_normalized(stock_fcf_to_ni, quality_metrics.get('fcf_to_ni', []))
                earnings_quality_score = (fcf_ni_percentile / 100) * 100  # Already 0-100 scale, one metric

            # Component 4: EPS Growth Stability (10 points) - Standard deviation of EPS growth (lower std = more consistent, better)
            # EPS Growth Stability measures how consistent earnings growth has been (lower std deviation = more predictable)
            eps_stability_score = None

            if stock_eps_growth_stability is not None:
                # Invert EPS growth std - lower is better, so negate for percentile calculation
                # Lower std means more consistent/stable growth, which is a quality signal
                eps_std_percentile = calculate_z_score_normalized(-stock_eps_growth_stability,
                                                               [-s for s in quality_metrics.get('eps_growth_stability', []) if s is not None])
                if eps_std_percentile is not None:
                    eps_stability_score = eps_std_percentile  # Already 0-100 scale from percentile rank

            # Component 5: ROE Stability Index (10 points) - NEW: ROE trend and consistency
            # Measures how stable and positive ROE has been over 4 years
            # Formula: (% of years with positive ROE) × (1 - ROE volatility) × 100
            roe_stability_score = None

            if stock_roe_stability_index is not None:
                # roe_stability_index is already 0-100 scale from database
                roe_stability_score = stock_roe_stability_index
                logger.debug(f"{symbol}: ROE Stability = {roe_stability_score:.2f}")

            # Component 6: Earnings Surprise Consistency (5 points) - Pre-calculated from quality_metrics
            earnings_surprise_score = None

            # Fetch pre-calculated earnings_surprise_avg from quality_metrics (more comprehensive historical data)
            # This is populated by loadfactormetrics.py and includes all historical earnings surprises
            # Falls back to calculating from recent earnings_history if quality_metrics data not available

            try:
                # Try to use earnings_surprise_avg from quality_metrics first (calculated by loadfactormetrics.py)
                # This metric includes historical earnings surprise data for better consistency

                # Note: earnings_surprise_avg is already fetched in qm_row above at line 2112
                # but we need to explicitly handle it for percentile calculation

                # Query recent earnings surprises from earnings_history (last 4 quarters) as fallback
                surprise_sql = """
                    SELECT eps_actual, eps_estimate FROM earnings_history
                    WHERE ticker = %s AND quarter >= CURRENT_DATE - INTERVAL '12 months'
                    ORDER BY quarter DESC LIMIT 4
                """
                cur.execute(surprise_sql, (symbol,))
                surprise_rows = cur.fetchall()

                # Calculate beat rate from quarters with valid guidance estimates only
                quarters_with_guidance = []
                if surprise_rows:
                    for actual, estimate in surprise_rows:
                        if actual is not None and estimate is not None and estimate > 0:
                            quarters_with_guidance.append((actual, estimate))

                # CONGLOMERATE FIX: Skip earnings surprise for companies without sufficient guidance
                # Conglomerates (like BRK.B) often don't provide guidance, resulting in <2 quarters with estimates
                # This caused unfair penalty. Instead, set to None and let weight normalization handle it.
                if quarters_with_guidance and len(quarters_with_guidance) >= 2:
                    # Calculate beat rate (% of quarters where actual > estimate)
                    beats = 0
                    for actual, estimate in quarters_with_guidance:
                        if float(actual) > float(estimate):
                            beats += 1

                    beat_rate = beats / len(quarters_with_guidance)

                    # Score based on beat rate using linear interpolation (0-100)
                    # This eliminates fake "neutral 50" midpoint value
                    # 0% beat rate = 0, 100% beat rate = 100
                    earnings_surprise_score = beat_rate * 100
                    earnings_surprise_score = round(earnings_surprise_score, 2)
                else:
                    # Insufficient guidance data - likely a conglomerate that doesn't provide guidance
                    # Skip this metric rather than penalize
                    earnings_surprise_score = None
                    logger.debug(f"{symbol}: Insufficient guidance data ({len(quarters_with_guidance)} quarters with estimates), skipping earnings surprise")
            except (psycopg2.Error, TypeError, ValueError) as e:
                logger.debug(f"{symbol}: Could not calculate earnings surprise score: {e}")
                earnings_surprise_score = None

            # Calculate final quality score with dynamic weight normalization
            # Build arrays of present components and their weights for normalization
            quality_components = []
            quality_weights = []
            quality_weight_names = []

            if profitability_score is not None:
                quality_components.append(profitability_score)
                quality_weights.append(40)
                quality_weight_names.append("Profitability")

            if strength_score is not None:
                quality_components.append(strength_score)
                quality_weights.append(25)
                quality_weight_names.append("Strength")

            if earnings_quality_score is not None:
                quality_components.append(earnings_quality_score)
                quality_weights.append(20)
                quality_weight_names.append("EarningsQuality")

            if eps_stability_score is not None:
                quality_components.append(eps_stability_score)
                quality_weights.append(10)
                quality_weight_names.append("EPSStability")

            if roe_stability_score is not None:
                quality_components.append(roe_stability_score)
                quality_weights.append(10)
                quality_weight_names.append("ROEStability")

            if earnings_surprise_score is not None:
                quality_components.append(earnings_surprise_score)
                quality_weights.append(5)
                quality_weight_names.append("EarningsSurprise")

            # Data Quality Gate - Use whatever components are available
            # Re-normalize weights based on actual data present
            # This ensures all stocks get a score based on real metrics
            if len(quality_components) >= 1:  # Require at least 1 real component
                total_quality_weight = sum(quality_weights)
                normalized_quality_weights = [w / total_quality_weight for w in quality_weights]

                # Calculate: sum of (component * normalized_weight)
                # Components are already 0-100, so this gives weighted average 0-100
                quality_score = sum(c * w for c, w in zip(quality_components, normalized_quality_weights))
                quality_score = max(0, min(100, quality_score))

                logger.info(f"{symbol} Quality: {len(quality_components)}/5 components available - Score={quality_score:.2f}")
            else:
                # No quality data at all - return NULL
                quality_score = None
                logger.warning(f"{symbol}: NO QUALITY DATA - score is NULL")
        else:
            # No fallback - quality_score remains None if metrics not available
            pass

        # ============================================================
        # Growth Score - Percentile-Based TTM Metrics (Industry Standard)
        # 7-component system using percentile ranking for market-relative growth scoring
        # Reweighted to emphasize earnings quality and cash flow growth
        # ============================================================
        # REQUIRE growth_score - must calculate from data
        growth_score = None

        # Diagnostic: log if growth metrics are unavailable
        if growth_metrics is None or len(growth_metrics) == 0:
            logger.debug(f"{symbol}: growth_metrics is empty or None - growth_score will be NULL")
        elif stock_revenue_growth is None and stock_earnings_growth is None:
            logger.debug(f"{symbol}: No growth inputs available (Revenue/Earnings growth both NULL)")

        # Only calculate percentile-based growth score if we have growth_metrics data
        if growth_metrics is not None:
            # Component 1: Revenue Growth - TTM revenue growth percentile (converted to 0-100)
            revenue_growth_score = 0
            if stock_revenue_growth is not None:
                rev_percentile = calculate_z_score_normalized(stock_revenue_growth, growth_metrics.get('revenue_growth', []))
                revenue_growth_score = rev_percentile  # Keep as 0-100, not scaled to 20 points

            # Component 2: Earnings Growth - TTM earnings growth percentile (converted to 0-100)
            earnings_growth_score = 0
            if stock_earnings_growth is not None:
                earn_percentile = calculate_z_score_normalized(stock_earnings_growth, growth_metrics.get('earnings_growth', []))
                earnings_growth_score = earn_percentile  # Keep as 0-100, not scaled to 35 points

            # Component 3: Earnings Acceleration - Quarterly vs annual growth comparison (converted to 0-100)
            earnings_accel_score = 0
            if stock_earnings_q_growth is not None and stock_earnings_growth is not None:
                # Positive when Q growth > annual growth (accelerating)
                acceleration = stock_earnings_q_growth - stock_earnings_growth
                accel_percentile = calculate_z_score_normalized(acceleration,
                                                            [q - a for q, a in zip(growth_metrics.get('earnings_q_growth', []),
                                                                                  growth_metrics.get('earnings_growth', []))
                                                            if q is not None and a is not None])
                earnings_accel_score = accel_percentile  # Keep as 0-100, not scaled to 15 points

            # Component 4: Margin Expansion - Gross + Operating margin percentiles (converted to 0-100)
            margin_expansion_score = 0
            if stock_gross_margin_growth is not None:
                gross_margin_percentile = calculate_z_score_normalized(stock_gross_margin_growth,
                                                                    growth_metrics.get('gross_margin', []))
                margin_expansion_score += gross_margin_percentile  # Keep as 0-100, weight handles allocation

            if stock_operating_margin_growth is not None:
                op_margin_percentile = calculate_z_score_normalized(stock_operating_margin_growth,
                                                                growth_metrics.get('operating_margin', []))
                margin_expansion_score += op_margin_percentile  # Keep as 0-100, weight handles allocation

            # If both margins available, take average to keep scale 0-100
            if stock_gross_margin_growth is not None and stock_operating_margin_growth is not None:
                margin_expansion_score = margin_expansion_score / 2

            # Component 5: Sustainable Growth - ROE × (1 - payout_ratio) (converted to 0-100)
            sustainable_growth_score = 0
            if stock_sustainable_growth is not None:
                sustainable_percentile = calculate_z_score_normalized(stock_sustainable_growth,
                                                                   growth_metrics.get('sustainable_growth', []))
                sustainable_growth_score = sustainable_percentile  # Keep as 0-100, not scaled to 10 points

            # Component 6: Free Cash Flow Growth - YoY FCF growth percentile (converted to 0-100)
            fcf_growth_score = 0
            if stock_fcf_growth_yoy is not None:
                fcf_percentile = calculate_z_score_normalized(stock_fcf_growth_yoy, growth_metrics.get('fcf_growth', []))
                fcf_growth_score = fcf_percentile  # Keep as 0-100, not scaled to 8 points

            # Component 7: Operating Cash Flow Growth - YoY OCF growth percentile (converted to 0-100)
            ocf_growth_score = 0
            if stock_ocf_growth_yoy is not None:
                ocf_percentile = calculate_z_score_normalized(stock_ocf_growth_yoy, growth_metrics.get('ocf_growth', []))
                ocf_growth_score = ocf_percentile  # Keep as 0-100, not scaled to 7 points

            # Calculate final growth score with dynamic normalization
            # Total weight = 115 points, normalize to 0-100 scale
            growth_components = []
            growth_weights = []
            growth_weight_names = []

            if revenue_growth_score > 0:
                growth_components.append(revenue_growth_score)
                growth_weights.append(20)
                growth_weight_names.append("Revenue")
            if earnings_growth_score > 0:
                growth_components.append(earnings_growth_score)
                growth_weights.append(35)
                growth_weight_names.append("Earnings")
            if earnings_accel_score > 0:
                growth_components.append(earnings_accel_score)
                growth_weights.append(15)
                growth_weight_names.append("Acceleration")
            if margin_expansion_score > 0:
                growth_components.append(margin_expansion_score)
                growth_weights.append(20)
                growth_weight_names.append("Margins")
            if sustainable_growth_score > 0:
                growth_components.append(sustainable_growth_score)
                growth_weights.append(10)
                growth_weight_names.append("Sustainable")
            if fcf_growth_score > 0:
                growth_components.append(fcf_growth_score)
                growth_weights.append(8)
                growth_weight_names.append("FCFGrowth")
            if ocf_growth_score > 0:
                growth_components.append(ocf_growth_score)
                growth_weights.append(7)
                growth_weight_names.append("OCFGrowth")

            if len(growth_components) > 0:
                total_growth_weight = sum(growth_weights)
                normalized_growth_weights = [w / total_growth_weight for w in growth_weights]
                growth_score = sum(c * w for c, w in zip(growth_components, normalized_growth_weights))
                growth_score = max(0, min(100, growth_score))

                logger.debug(f"{symbol} Growth Components: {', '.join([f'{n}={c:.1f}' for n, c in zip(growth_weight_names, growth_components)])} -> Final={growth_score:.2f} (NORMALIZED)")
            else:
                growth_score = None
        else:
            # No fallback - growth_score remains None if metrics not available
            growth_score = None

        # Positioning Score with NESTED NORMALIZATION for consistency
        # Categories: Ownership (50%), Short Interest (15%), Accumulation/Distribution (25%), Institution Count (10%)
        # NO FALLBACK VALUES - if data is missing, positioning_score will be None
        positioning_score = None

        # Only calculate if we have at least some positioning data
        # Safely check for positioning data - avoid NumPy scalar ambiguity in any()
        try:
            has_positioning_data = any([institutional_ownership is not None,
                    insider_ownership is not None,
                    short_percent_of_float is not None,
                    institution_count is not None,
                    acc_dist_rating is not None])
        except (ValueError, TypeError):
            # NumPy scalar comparison failed, use fallback approach
            has_positioning_data = False
            try:
                if institutional_ownership is not None:
                    has_positioning_data = True
            except (ValueError, TypeError):
                pass
            if not has_positioning_data:
                try:
                    if insider_ownership is not None:
                        has_positioning_data = True
                except (ValueError, TypeError):
                    pass
            if not has_positioning_data:
                try:
                    if short_percent_of_float is not None:
                        has_positioning_data = True
                except (ValueError, TypeError):
                    pass
            if not has_positioning_data:
                try:
                    if institution_count is not None:
                        has_positioning_data = True
                except (ValueError, TypeError):
                    pass
            if not has_positioning_data:
                try:
                    if acc_dist_rating is not None:
                        has_positioning_data = True
                except (ValueError, TypeError):
                    pass

        if has_positioning_data:
            # NESTED NORMALIZATION APPROACH (Like Quality and Value Scores)
            # Step 1: Normalize each category internally, Step 2: Aggregate categories

            # ========================
            # CATEGORY 1: OWNERSHIP (50% weight)
            # ========================
            ownership_components = []
            ownership_weights = []

            # Institutional Ownership (50 pts)
            if institutional_ownership is not None:
                try:
                    if positioning_metrics and isinstance(positioning_metrics, dict) and positioning_metrics.get('institutional_ownership'):
                        inst_list = positioning_metrics['institutional_ownership']
                        if inst_list and len(inst_list) > 0:
                            inst_percentile = sum(1 for x in inst_list if x <= institutional_ownership) / len(inst_list) * 100
                            ownership_components.append(inst_percentile)
                            ownership_weights.append(50)
                except (TypeError, ZeroDivisionError, KeyError) as e:
                    logger.debug(f"⚠️ Error calculating institutional ownership percentile: {e}")

            # Insider Ownership (50 pts)
            if insider_ownership is not None:
                try:
                    if positioning_metrics and isinstance(positioning_metrics, dict) and positioning_metrics.get('insider_ownership'):
                        insider_list = positioning_metrics['insider_ownership']
                        if insider_list and len(insider_list) > 0:
                            insider_percentile = sum(1 for x in insider_list if x <= insider_ownership) / len(insider_list) * 100
                            ownership_components.append(insider_percentile)
                            ownership_weights.append(50)
                except (TypeError, ZeroDivisionError, KeyError) as e:
                    logger.debug(f"⚠️ Error calculating insider ownership percentile: {e}")

            # Normalize ownership to 0-100
            ownership_score = None
            if len(ownership_components) > 0:
                total_own_weight = sum(ownership_weights)
                normalized_own_weights = [w / total_own_weight for w in ownership_weights]
                ownership_score = sum(c * w for c, w in zip(ownership_components, normalized_own_weights))

            # ========================
            # CATEGORY 2: SHORT INTEREST (15% weight)
            # ========================
            short_components = []
            short_weights = []

            # Short Interest (inverted - lower is better)
            if short_percent_of_float is not None:
                try:
                    if positioning_metrics and isinstance(positioning_metrics, dict) and positioning_metrics.get('short_percent_of_float'):
                        short_list = positioning_metrics['short_percent_of_float']
                        if short_list and len(short_list) > 0:
                            short_percentile = sum(1 for x in short_list if x <= short_percent_of_float) / len(short_list) * 100
                            short_score = 100 - short_percentile  # Invert: lower short = higher score
                            short_components.append(short_score)
                            short_weights.append(100)
                except (TypeError, ZeroDivisionError, KeyError) as e:
                    logger.debug(f"⚠️ Error calculating short interest percentile: {e}")

            # Normalize short interest to 0-100
            short_score = None
            if len(short_components) > 0:
                total_short_weight = sum(short_weights)
                normalized_short_weights = [w / total_short_weight for w in short_weights]
                short_score = sum(c * w for c, w in zip(short_components, normalized_short_weights))

            # ========================
            # CATEGORY 3: ACCUMULATION/DISTRIBUTION (25% weight)
            # ========================
            acc_dist_score = None
            if acc_dist_rating is not None:
                # Already 0-100 scale, no percentile needed
                acc_dist_score = float(acc_dist_rating)

            # ========================
            # CATEGORY 4: INSTITUTION COUNT (10% weight)
            # ========================
            count_components = []
            count_weights = []

            if institution_count is not None:
                try:
                    if positioning_metrics and isinstance(positioning_metrics, dict) and positioning_metrics.get('institution_count'):
                        count_list = positioning_metrics['institution_count']
                        if count_list and len(count_list) > 0:
                            count_percentile = sum(1 for x in count_list if x <= institution_count) / len(count_list) * 100
                            count_components.append(count_percentile)
                            count_weights.append(100)
                except (TypeError, ZeroDivisionError, KeyError) as e:
                    logger.debug(f"⚠️ Error calculating institution count percentile: {e}")

            # Normalize count to 0-100
            count_score = None
            if len(count_components) > 0:
                total_count_weight = sum(count_weights)
                normalized_count_weights = [w / total_count_weight for w in count_weights]
                count_score = sum(c * w for c, w in zip(count_components, normalized_count_weights))

            # AGGREGATE CATEGORIES WITH SINGLE-LEVEL NORMALIZATION (Consistent with Quality Score)
            # All components are already 0-100 percentiles, combine with proper weights
            if ownership_score is not None or short_score is not None or acc_dist_score is not None or count_score is not None:
                positioning_components = []
                positioning_weights = []

                if ownership_score is not None:
                    positioning_components.append(ownership_score)
                    positioning_weights.append(0.50)  # 50% relative weight
                if short_score is not None:
                    positioning_components.append(short_score)
                    positioning_weights.append(0.15)  # 15% relative weight
                if acc_dist_score is not None:
                    positioning_components.append(acc_dist_score)
                    positioning_weights.append(0.25)  # 25% relative weight
                if count_score is not None:
                    positioning_components.append(count_score)
                    positioning_weights.append(0.10)  # 10% relative weight

                # Final aggregation with weighted average (SINGLE LEVEL - no nested normalization)
                if len(positioning_components) > 0:
                    total_weight = sum(positioning_weights)
                    normalized_weights = [w / total_weight for w in positioning_weights]
                    positioning_score = sum(score * weight for score, weight in zip(positioning_components, normalized_weights))
                    positioning_score = max(0, min(100, positioning_score))

                    logger.debug(f"{symbol} Positioning Score: {positioning_score:.2f} (SINGLE LEVEL NORMALIZATION - {len(positioning_components)} categories)")
                else:
                    positioning_score = None
                    logger.debug(f"{symbol}: No valid positioning categories available - positioning_score = NULL")
            else:
                positioning_score = None
                logger.debug(f"{symbol}: All positioning categories are None - positioning_score = NULL")

        # Sentiment Score (Analyst ratings + News sentiment + Market sentiment) - ONLY REAL DATA
        # Start with None - only use if we have real data
        sentiment_score = None

        # Analyst sentiment component (0-50 points)
        if analyst_score is not None:
            # Scale from 1-5 to 0-50: (score-1)/4 * 50
            analyst_component = ((analyst_score - 1) / 4) * 50
            sentiment_score = analyst_component
        # No else clause - remain None if no analyst data (no fallback to 50)

        # News sentiment component (add up to ±25 points)
        if sentiment_score is not None and sentiment_score_raw is not None:
            # Assuming sentiment_score_raw is 0-1 scale, convert to -25 to +25
            news_component = (sentiment_score_raw - 0.5) * 50
            sentiment_score += news_component

        # Bonus for high news coverage (indicates interest)
        if sentiment_score is not None:
            if news_count is not None and news_count > 10:
                sentiment_score += min(10, news_count * 0.5)
            elif news_count is not None and news_count > 5:
                sentiment_score += 5

        # Market-level AAII sentiment component (up to ±25 points)
        # This provides market context for the sentiment score
        # ONLY add AAII if we have real analyst/news data AND real AAII data (REAL DATA ONLY)
        if aaii_sentiment_component is not None and sentiment_score is not None:
            # Add AAII component to existing sentiment (only with real data)
            sentiment_score += aaii_sentiment_component * 0.5  # Weight at 50% to avoid over-influence
        # If no analyst/news data, sentiment_score remains None - no fallback defaults

        # Clamp sentiment score to 0-100 (safely handle NumPy types)
        try:
            if sentiment_score is not None:
                if isinstance(sentiment_score, (int, float)):
                    sentiment_score = max(0, min(100, sentiment_score))
        except (ValueError, TypeError):
            pass  # NumPy type comparison failed, leave as is
        # If sentiment_score is None, leave it as None (no data to calculate)

        # No fallback defaults - all scores remain None if not calculated
        # Composite Score - FIXED WEIGHTS APPROACH
        # CRITICAL: NO FAKE DATA & NO WEIGHT INFLATION
        # Missing factors are treated as 0 (fair penalty without changing other weights)
        # Weights ALWAYS stay the same regardless of missing data
        # This prevents hidden bias where missing data inflates other weights

        # FIXED weights - NORMALIZED to sum to 1.0 for fair 0-100 scoring
        # Original base weights (12%, 18%, 18%, 25%, 16%, 11%)
        # SENTIMENT EXCLUDED: 99.9% of stocks missing sentiment data
        # These 6 factors represent 95% of total weight; evenly distributed among them
        # FIX: Weights properly normalized to exactly 1.0 (previous rounding error was 104.17%)
        weights = {
            'momentum': 0.1200,      # 12.00%
            'growth': 0.1800,        # 18.00%
            'value': 0.1800,         # 18.00%
            'quality': 0.2500,       # 25.00% PRIMARY
            'stability': 0.1600,     # 16.00%
            'positioning': 0.1100,   # 11.00%
            # 'sentiment': EXCLUDED - 99.9% missing data
            # TOTAL: 1.0000 (100.00%) - enables fair 0-100 scoring with neutral=50
        }

        # Build factors with ONLY real data (no 0 padding)
        # CRITICAL: Even "is not None" checks fail with NumPy arrays, so wrap the entire conversion
        def safe_convert_score(score):
            try:
                # NumPy scalars from percentile calculations need conversion
                if score is not None:
                    return float(score)
                return None
            except (ValueError, TypeError):
                # If the "is not None" check itself fails (NumPy array ambiguity), return None
                return None

        all_factors = {
            'momentum': safe_convert_score(momentum_score),
            'growth': safe_convert_score(growth_score),
            'value': safe_convert_score(value_score),
            'quality': safe_convert_score(quality_score),
            'stability': safe_convert_score(stability_score),
            'positioning': safe_convert_score(positioning_score),
            'sentiment': safe_convert_score(sentiment_score),
        }

        # Count real factors - safely handle NumPy types
        def safe_is_not_none(val):
            try:
                return val is not None
            except (ValueError, TypeError):
                return False

        real_factor_count = sum(1 for score in all_factors.values() if safe_is_not_none(score))

        # Calculate composite score with FLEXIBLE WEIGHTING
        # Industry standard: Calculate from whatever factors ARE available (minimum 4 of 6)
        # Supports Fama-French, MSCI, AQR quantitative finance practices

        # Track real factor count and collect available factors (excluding sentiment)
        real_factor_count_no_sentiment = sum(1 for score in [momentum_score, growth_score, value_score,
                                                              quality_score, stability_score, positioning_score]
                                            if safe_is_not_none(score))

        # Build composite from available factors
        factor_values_for_composite = {}
        factor_weights_for_composite = {}

        # Safely check each score (handle NumPy type comparisons)
        try:
            if momentum_score is not None:
                factor_values_for_composite['momentum'] = momentum_score
                factor_weights_for_composite['momentum'] = weights['momentum']
        except (ValueError, TypeError):
            pass  # NumPy type comparison failed, skip this factor

        try:
            if growth_score is not None:
                factor_values_for_composite['growth'] = growth_score
                factor_weights_for_composite['growth'] = weights['growth']
        except (ValueError, TypeError):
            pass

        try:
            if value_score is not None:
                factor_values_for_composite['value'] = value_score
                factor_weights_for_composite['value'] = weights['value']
        except (ValueError, TypeError):
            pass

        try:
            if quality_score is not None:
                factor_values_for_composite['quality'] = quality_score
                factor_weights_for_composite['quality'] = weights['quality']
        except (ValueError, TypeError):
            pass

        try:
            if stability_score is not None:
                factor_values_for_composite['stability'] = stability_score
                factor_weights_for_composite['stability'] = weights['stability']
        except (ValueError, TypeError):
            pass

        try:
            if positioning_score is not None:
                factor_values_for_composite['positioning'] = positioning_score
                factor_weights_for_composite['positioning'] = weights['positioning']
        except (ValueError, TypeError):
            pass

        # REAL DATA ONLY: Calculate composite ONLY when ALL 6 of 6 factors are present
        # Strict data integrity: no partial composites to ensure all composites are directly comparable
        composite_score = None
        factors_present_count = len(factor_values_for_composite)

        if factors_present_count == 6:
            # All 6 factors present - calculate composite score
            # Use standard weights (no re-normalization needed since all factors are present)
            try:
                weighted_sum = 0
                for k in factor_values_for_composite.keys():
                    factor_val = factor_values_for_composite[k]
                    factor_wt = factor_weights_for_composite[k]
                    weighted_sum += factor_val * factor_wt

                composite_score = weighted_sum

                # Clamp to 0-100
                composite_score = max(0, min(100, composite_score))

            except Exception as e:
                logger.error(f"{symbol}: Error calculating composite score: {e}, factors_present_count={factors_present_count}")
                composite_score = None
        else:
            # Fewer than 6 factors - no composite score (insufficient real data)
            pass

        # Don't close cursor here - it's reused in save_stock_score for INSERT operation
        # The cursor will be closed in save_stock_score after the database INSERT completes

        # Clamp scores to 0-100 (only if not None)
        def clamp_score(score):
            if score is None:
                return None
            return max(0, min(100, float(score)))

        # Option 1 + API Flagging: Track missing metrics for data completeness flagging
        # Identify available metrics and flag missing ones
        available_metrics = []
        missing_metrics = []
        score_status = 'complete'
        score_notes = None
        estimated_data_ready_date = None

        # Track which metrics are available (safely handle NumPy types)
        try:
            if momentum_score is not None:
                available_metrics.append('momentum')
            else:
                missing_metrics.append('momentum')
        except (ValueError, TypeError):
            missing_metrics.append('momentum')

        try:
            if growth_score is not None:
                available_metrics.append('growth')
            else:
                missing_metrics.append('growth')
        except (ValueError, TypeError):
            missing_metrics.append('growth')

        try:
            if value_score is not None:
                available_metrics.append('value')
            else:
                missing_metrics.append('value')
        except (ValueError, TypeError):
            missing_metrics.append('value')

        try:
            if quality_score is not None:
                available_metrics.append('quality')
            else:
                missing_metrics.append('quality')
        except (ValueError, TypeError):
            missing_metrics.append('quality')

        try:
            if stability_score is not None or risk_stability_score is not None:
                available_metrics.append('stability')
            else:
                missing_metrics.append('stability')
        except (ValueError, TypeError):
            missing_metrics.append('stability')

        try:
            if positioning_score is not None:
                available_metrics.append('positioning')
            else:
                missing_metrics.append('positioning')
        except (ValueError, TypeError):
            missing_metrics.append('positioning')

        try:
            if sentiment_score is not None:
                available_metrics.append('sentiment')
            else:
                missing_metrics.append('sentiment')
        except (ValueError, TypeError):
            missing_metrics.append('sentiment')

        # Set status and notes based on missing data and composite_score availability
        if composite_score is None and real_factor_count < 4:
            score_status = 'insufficient_data'
            score_notes = f"Composite score requires 4+ real factors. Available: {real_factor_count} ({', '.join(available_metrics)}). Missing: {', '.join(missing_metrics)}"
            estimated_data_ready_date = (datetime.now().date() + timedelta(days=365))
            logger.info(f"{symbol}: ⏳ INSUFFICIENT_DATA - Only {real_factor_count} real factors, need 4+ for composite")
        elif missing_metrics:
            score_status = 'partial'
            score_notes = f"Composite score calculated from {real_factor_count} real factors. Available: {', '.join(available_metrics)}. Missing: {', '.join(missing_metrics)}"
            logger.warning(f"{symbol}: ⚠️ PARTIAL_DATA - {real_factor_count} real factors (weights re-normalized)")

        return {
            'symbol': symbol,
            'company_name': company_name,
            'composite_score': float(round(clamp_score(composite_score), 2)) if composite_score is not None else None,
            'momentum_score': float(round(clamp_score(momentum_score), 2)) if momentum_score is not None else None,
            'value_score': float(round(clamp_score(value_score), 2)) if value_score is not None else None,
            'quality_score': float(round(clamp_score(quality_score), 2)) if quality_score is not None else None,
            'growth_score': float(round(clamp_score(growth_score), 2)) if growth_score is not None else None,
            'positioning_score': float(round(clamp_score(positioning_score), 2)) if positioning_score is not None else None,
            'sentiment_score': float(round(clamp_score(sentiment_score), 2)) if sentiment_score is not None else None,
            'stability_score': float(round(clamp_score(risk_stability_score), 2)) if risk_stability_score is not None else None,
            'stability_inputs': stability_inputs,
            'beta': float(round(beta, 3)) if beta is not None else None,
            'rsi': float(rsi) if rsi is not None else None,
            'macd': float(macd) if macd is not None else None,
            'sma_20': float(round(float(sma_20), 2)) if sma_20 is not None else None,
            'sma_50': float(round(float(sma_50), 2)) if sma_50 is not None else None,
            'volume_avg_30d': int(volume_avg_30d) if volume_avg_30d is not None else None,
            'current_price': float(round(current_price, 2)) if current_price is not None else None,
            'price_change_1d': float(round(price_change_1d, 2)) if price_change_1d is not None else None,
            'price_change_5d': float(round(price_change_5d, 2)) if price_change_5d is not None else None,
            'price_change_30d': float(round(price_change_30d, 2)) if price_change_30d is not None else None,
            'volatility_30d': float(volatility_30d) if volatility_30d is not None else None,
            'market_cap': int(market_cap) if market_cap is not None else None,
            'pe_ratio': float(round(pe_ratio, 2)) if pe_ratio is not None else None,
            'forward_pe': float(round(forward_pe, 2)) if forward_pe is not None else None,
            # Momentum components (technical confirmation + 3m/6m/12-3m percentiles)
            'momentum_intraweek': float(round(momentum_intraweek, 2)) if momentum_intraweek is not None else None,
            'momentum_short_term': float(round(momentum_3m_score, 2)) if momentum_3m_score is not None else None,
            'momentum_medium_term': float(round(momentum_6m_score, 2)) if momentum_6m_score is not None else None,
            'momentum_long_term': float(round(momentum_12_3_score, 2)) if momentum_12_3_score is not None else None,
            'momentum_consistency': None,
            'price_vs_sma_50': float(round(price_vs_sma_50, 2)) if price_vs_sma_50 is not None else None,
            'price_vs_sma_200': float(round(price_vs_sma_200, 2)) if price_vs_sma_200 is not None else None,
            'price_vs_52w_high': float(round(price_vs_52w_high, 2)) if price_vs_52w_high is not None else None,
            'roc_10d': float(round(roc_10d, 2)) if roc_10d is not None else None,
            'roc_20d': float(round(roc_20d, 2)) if roc_20d is not None else None,
            'roc_60d': float(round(roc_60d, 2)) if roc_60d is not None else None,
            'roc_120d': float(round(roc_120d, 2)) if roc_120d is not None else None,
            'roc_252d': float(round(roc_252d, 2)) if roc_252d is not None else None,
            'mom': float(round(mom_10d, 2)) if mom_10d is not None else None,
            'mansfield_rs': float(round(mansfield_rs, 2)) if mansfield_rs is not None else None,
            # Positioning component: Accumulation/Distribution Rating
            'accumulation_distribution': float(round(acc_dist_rating, 2)) if acc_dist_rating is not None else None,
            'short_interest': float(round(short_percent_of_float, 2)) if short_percent_of_float is not None else None,
            # JSONB Input Columns - Store all component details for frontend display
            'momentum_inputs': json.dumps({
                'momentum_3m': float(round(momentum_3m, 2)) if momentum_3m is not None else None,
                'momentum_6m': float(round(momentum_6m, 2)) if momentum_6m is not None else None,
                'momentum_12m': float(round(momentum_12m, 2)) if momentum_12m is not None else None,
                'momentum_12_3': float(round(momentum_12_3, 2)) if momentum_12_3 is not None else None,
                'price_vs_sma_50': float(round(price_vs_sma_50, 2)) if price_vs_sma_50 is not None else None,
                'price_vs_sma_200': float(round(price_vs_sma_200, 2)) if price_vs_sma_200 is not None else None,
                'price_vs_52w_high': float(round(price_vs_52w_high, 2)) if price_vs_52w_high is not None else None,
            }),
            'growth_inputs': json.dumps({
                'revenue_growth_3y_cagr': float(round(stock_revenue_growth * 100, 2)) if stock_revenue_growth is not None else None,
                'eps_growth_3y_cagr': float(round(stock_earnings_growth * 100, 2)) if stock_earnings_growth is not None else None,
                'operating_income_growth_yoy': float(round(stock_operating_income_growth_yoy, 2)) if stock_operating_income_growth_yoy is not None else None,
                'net_income_growth_yoy': float(round(stock_net_income_growth_yoy, 2)) if stock_net_income_growth_yoy is not None else None,
                'roe_trend': float(round(stock_roe, 4)) if stock_roe is not None else None,
                'sustainable_growth_rate': float(round(stock_sustainable_growth * 100, 2)) if stock_sustainable_growth is not None else None,
                'fcf_growth_yoy': float(round(stock_fcf_growth_yoy, 2)) if stock_fcf_growth_yoy is not None else None,
                'ocf_growth_yoy': float(round(stock_ocf_growth_yoy, 2)) if stock_ocf_growth_yoy is not None else None,
                'gross_margin_trend': float(round(stock_gross_margin_growth * 100, 2)) if stock_gross_margin_growth is not None else None,
                'operating_margin_trend': float(round(stock_operating_margin_growth * 100, 2)) if stock_operating_margin_growth is not None else None,
                'net_margin_trend': float(round(stock_net_margin_growth * 100, 2)) if stock_net_margin_growth is not None else None,
                'quarterly_growth_momentum': float(round(stock_quarterly_growth_momentum, 2)) if stock_quarterly_growth_momentum is not None else None,
                'asset_growth_yoy': float(round(stock_asset_growth_yoy, 2)) if stock_asset_growth_yoy is not None else None,
            }),
            'positioning_inputs': json.dumps({
                'institutional_ownership_pct': float(round(institutional_ownership_pct * 100, 2)) if institutional_ownership_pct is not None else None,
                'insider_ownership_pct': float(round(insider_ownership_pct * 100, 2)) if insider_ownership_pct is not None else None,
                'short_percent_of_float': float(round(short_percent_of_float, 2)) if short_percent_of_float is not None else None,
                'institution_count': int(institution_count) if institution_count is not None else None,
            }),
            'quality_inputs': json.dumps({
                'return_on_equity_pct': float(round(stock_roe, 2)) if stock_roe is not None else None,
                'return_on_assets_pct': float(round(stock_roa, 2)) if stock_roa is not None else None,
                'gross_margin_pct': float(round(stock_gross_margin * 100, 2)) if stock_gross_margin is not None else None,
                'return_on_invested_capital_pct': float(round(stock_roic * 100, 2)) if stock_roic is not None else None,
                'operating_margin_pct': float(round(stock_operating_margin * 100, 2)) if stock_operating_margin is not None else None,
                'profit_margin_pct': float(round(stock_profit_margin * 100, 2)) if stock_profit_margin is not None else None,
                'fcf_to_net_income': float(round(stock_fcf_to_ni, 4)) if stock_fcf_to_ni is not None else None,
                'operating_cf_to_net_income': float(round(stock_operating_cf_to_ni, 4)) if stock_operating_cf_to_ni is not None else None,
                'debt_to_equity': float(round(stock_debt_to_equity, 4)) if stock_debt_to_equity is not None else None,
                'current_ratio': float(round(stock_current_ratio, 4)) if stock_current_ratio is not None else None,
                'quick_ratio': float(round(stock_quick_ratio, 4)) if stock_quick_ratio is not None else None,
                'earnings_surprise_avg': float(round(earnings_surprise_avg, 2)) if earnings_surprise_avg is not None else None,
                'eps_growth_stability': float(round(eps_growth_std, 4)) if eps_growth_std is not None else None,
                'payout_ratio': float(round(payout_ratio * 100, 2)) if payout_ratio is not None else None,
            }),
            'value_inputs': json.dumps({
                'stock_pe': float(round(trailing_pe, 2)) if trailing_pe is not None else None,
                'stock_forward_pe': float(round(forward_pe, 2)) if forward_pe is not None else None,
                'stock_pb': float(round(price_to_book, 2)) if price_to_book is not None else None,
                'stock_ps': float(round(price_to_sales_ttm, 2)) if price_to_sales_ttm is not None else None,
                'stock_ev_ebitda': float(round(ev_to_ebitda, 2)) if ev_to_ebitda is not None else None,
                'stock_ev_revenue': float(round(ev_to_revenue, 2)) if ev_to_revenue is not None else None,
                'peg_ratio': float(round(peg_ratio_val, 2)) if peg_ratio_val is not None else None,
                'stock_dividend_yield': float(round(dividend_yield_val * 100, 2)) if dividend_yield_val is not None else None,
                'stock_fcf_yield': float(round(fcf_yield, 2)) if fcf_yield is not None else None,
            }),
            # Data completeness and flagging (Option 1)
            'score_status': locals().get('score_status'),
            'available_metrics': locals().get('available_metrics'),
            'missing_metrics': locals().get('missing_metrics'),
            'score_notes': locals().get('score_notes'),
            'estimated_data_ready_date': locals().get('estimated_data_ready_date').isoformat() if locals().get('estimated_data_ready_date') else None,
            # Factor count for transparency - shows how many of 6 factors were real (non-zero, sentiment excluded)
            'real_factor_count': real_factor_count_no_sentiment if 'real_factor_count_no_sentiment' in locals() else None
        }

    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Error calculating scores for {symbol} - checking data completeness: {e}")
        logger.warning(f"FULL TRACEBACK:\n{traceback.format_exc()}")

        # INDUSTRY STANDARD DATA QUALITY: Save if we have 5+ out of 6 factors
        # This follows professional practice: comprehensive scores require most (not all) factors
        # Allows for occasional missing metrics while preventing sparse/incomplete coverage
        try:
            # Check if 6 factor scores are available
            # Use try-except to safely handle NumPy scalars/arrays which can't be compared directly
            try:
                has_momentum = 'momentum_score' in locals() and momentum_score is not None
            except (ValueError, TypeError):
                has_momentum = False
            try:
                has_value = 'value_score' in locals() and value_score is not None
            except (ValueError, TypeError):
                has_value = False
            try:
                has_quality = 'quality_score' in locals() and quality_score is not None
            except (ValueError, TypeError):
                has_quality = False
            try:
                has_growth = 'growth_score' in locals() and growth_score is not None
            except (ValueError, TypeError):
                has_growth = False
            try:
                has_positioning = 'positioning_score' in locals() and positioning_score is not None
            except (ValueError, TypeError):
                has_positioning = False
            try:
                has_stability = 'risk_stability_score' in locals() and risk_stability_score is not None
            except (ValueError, TypeError):
                has_stability = False

            factor_count = sum([has_momentum, has_value, has_quality, has_growth, has_positioning, has_stability])
            sufficient_factors = factor_count >= 1  # Need at least 1 out of 6 factors to maximize coverage (score ALL stocks)

            if sufficient_factors:
                # 1+ factors available - save this score (maximize coverage approach)
                logger.info(f"📊 {symbol}: {factor_count}/6 factors available (minimum threshold: 1) - saving score")

                # Collect calculated input JSON strings from try block if available, otherwise None
                # These are already-calculated JSON strings from earlier sections, not fallback data
                momentum_inputs_data = momentum_inputs if 'momentum_inputs' in locals() else None
                growth_inputs_data = growth_inputs if 'growth_inputs' in locals() else None
                quality_inputs_data = quality_inputs if 'quality_inputs' in locals() else None
                positioning_inputs_data = positioning_inputs if 'positioning_inputs' in locals() else None
                value_inputs_data = value_inputs if 'value_inputs' in locals() else None
                stability_inputs_data = stability_inputs if 'stability_inputs' in locals() else None

                calculated_score = {
                    'symbol': symbol,
                    'company_name': company_name if 'company_name' in locals() else None,
                    'composite_score': float(round(composite_score, 2)) if composite_score is not None else None,
                    'momentum_score': float(momentum_score) if momentum_score is not None else None,
                    'value_score': float(value_score) if value_score is not None else None,
                    'quality_score': float(quality_score) if quality_score is not None else None,
                    'growth_score': float(growth_score) if growth_score is not None else None,
                    'positioning_score': float(positioning_score) if positioning_score is not None else None,
                    'sentiment_score': float(sentiment_score) if 'sentiment_score' in locals() and sentiment_score is not None else None,
                    'stability_score': float(risk_stability_score) if risk_stability_score is not None else None,
                    'beta': float(round(beta, 3)) if 'beta' in locals() and beta is not None else None
                }
                conn.rollback()
                return calculated_score
            else:
                # Insufficient factor coverage - DO NOT SAVE
                # Require at least 1 factor to score (maximize coverage approach)
                missing = []
                if not has_momentum: missing.append('momentum')
                if not has_value: missing.append('value')
                if not has_quality: missing.append('quality')
                if not has_growth: missing.append('growth')
                if not has_positioning: missing.append('positioning')
                if not has_stability: missing.append('stability')

                logger.error(f"❌ {symbol}: INSUFFICIENT_DATA - Only {factor_count}/6 factors available (need 1+). Missing: {', '.join(missing)} - SKIPPING")
                conn.rollback()
                return None
        except Exception as error:
            logger.error(f"❌ {symbol}: Error during score calculation: {error}")
            conn.rollback()
            return None

def save_stock_score(conn, score_data):
    """Save stock score to database."""
    try:
        cur = conn.cursor()

        # Ensure all required keys exist in score_data with None as default
        # This handles cases where indicator data wasn't collected
        required_keys = [
            'symbol', 'company_name', 'composite_score', 'momentum_score', 'value_score', 'quality_score',
            'growth_score', 'positioning_score', 'sentiment_score', 'stability_score',
            'rsi', 'macd', 'sma50', 'momentum_3m', 'momentum_6m', 'momentum_12m',
            'pe_ratio', 'forward_pe', 'pb_ratio', 'ps_ratio', 'peg_ratio', 'ev_revenue',
            'roe', 'roa', 'debt_ratio', 'fcf_ni_ratio', 'earnings_surprise',
            'earnings_growth', 'revenue_growth', 'margin_trend',
            'volatility', 'downside_volatility', 'max_drawdown', 'beta',
            'institutional_ownership', 'insider_ownership', 'short_interest', 'accumulation_distribution', 'institution_count',
            'analyst_rating', 'news_sentiment', 'aaii_sentiment'
        ]
        for key in required_keys:
            if key not in score_data:
                score_data[key] = None

        # Upsert query - with all 43 columns from comprehensive schema
        upsert_sql = """
        INSERT INTO stock_scores (
            symbol, company_name, composite_score, momentum_score, value_score, quality_score,
            growth_score, positioning_score, sentiment_score, stability_score,
            rsi, macd, sma50, momentum_3m, momentum_6m, momentum_12m,
            price_vs_sma_50, price_vs_sma_200, price_vs_52w_high,
            pe_ratio, forward_pe, pb_ratio, ps_ratio, peg_ratio, ev_revenue,
            roe, roa, debt_ratio, fcf_ni_ratio, earnings_surprise,
            earnings_growth, revenue_growth, margin_trend,
            volatility, downside_volatility, max_drawdown, beta,
            institutional_ownership, insider_ownership, short_interest, accumulation_distribution, institution_count,
            analyst_rating, news_sentiment, aaii_sentiment,
            score_date, last_updated
        ) VALUES (
            %(symbol)s, %(company_name)s, %(composite_score)s, %(momentum_score)s, %(value_score)s, %(quality_score)s,
            %(growth_score)s, %(positioning_score)s, %(sentiment_score)s, %(stability_score)s,
            %(rsi)s, %(macd)s, %(sma50)s, %(momentum_3m)s, %(momentum_6m)s, %(momentum_12m)s,
            %(price_vs_sma_50)s, %(price_vs_sma_200)s, %(price_vs_52w_high)s,
            %(pe_ratio)s, %(forward_pe)s, %(pb_ratio)s, %(ps_ratio)s, %(peg_ratio)s, %(ev_revenue)s,
            %(roe)s, %(roa)s, %(debt_ratio)s, %(fcf_ni_ratio)s, %(earnings_surprise)s,
            %(earnings_growth)s, %(revenue_growth)s, %(margin_trend)s,
            %(volatility)s, %(downside_volatility)s, %(max_drawdown)s, %(beta)s,
            %(institutional_ownership)s, %(insider_ownership)s, %(short_interest)s, %(accumulation_distribution)s, %(institution_count)s,
            %(analyst_rating)s, %(news_sentiment)s, %(aaii_sentiment)s,
            CURRENT_DATE, CURRENT_TIMESTAMP
        ) ON CONFLICT (symbol) DO UPDATE SET
            company_name = EXCLUDED.company_name,
            composite_score = EXCLUDED.composite_score,
            momentum_score = EXCLUDED.momentum_score,
            value_score = EXCLUDED.value_score,
            quality_score = EXCLUDED.quality_score,
            growth_score = EXCLUDED.growth_score,
            positioning_score = EXCLUDED.positioning_score,
            sentiment_score = EXCLUDED.sentiment_score,
            stability_score = EXCLUDED.stability_score,
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            sma50 = EXCLUDED.sma50,
            momentum_3m = EXCLUDED.momentum_3m,
            momentum_6m = EXCLUDED.momentum_6m,
            momentum_12m = EXCLUDED.momentum_12m,
            price_vs_sma_50 = EXCLUDED.price_vs_sma_50,
            price_vs_sma_200 = EXCLUDED.price_vs_sma_200,
            price_vs_52w_high = EXCLUDED.price_vs_52w_high,
            pe_ratio = EXCLUDED.pe_ratio,
            forward_pe = EXCLUDED.forward_pe,
            pb_ratio = EXCLUDED.pb_ratio,
            ps_ratio = EXCLUDED.ps_ratio,
            peg_ratio = EXCLUDED.peg_ratio,
            ev_revenue = EXCLUDED.ev_revenue,
            roe = EXCLUDED.roe,
            roa = EXCLUDED.roa,
            debt_ratio = EXCLUDED.debt_ratio,
            fcf_ni_ratio = EXCLUDED.fcf_ni_ratio,
            earnings_surprise = EXCLUDED.earnings_surprise,
            earnings_growth = EXCLUDED.earnings_growth,
            revenue_growth = EXCLUDED.revenue_growth,
            margin_trend = EXCLUDED.margin_trend,
            volatility = EXCLUDED.volatility,
            downside_volatility = EXCLUDED.downside_volatility,
            max_drawdown = EXCLUDED.max_drawdown,
            beta = EXCLUDED.beta,
            institutional_ownership = EXCLUDED.institutional_ownership,
            insider_ownership = EXCLUDED.insider_ownership,
            short_interest = EXCLUDED.short_interest,
            accumulation_distribution = EXCLUDED.accumulation_distribution,
            institution_count = EXCLUDED.institution_count,
            analyst_rating = EXCLUDED.analyst_rating,
            news_sentiment = EXCLUDED.news_sentiment,
            aaii_sentiment = EXCLUDED.aaii_sentiment,
            score_date = CURRENT_DATE,
            last_updated = CURRENT_TIMESTAMP
        """

        cur.execute(upsert_sql, score_data)
        cur.close()
        # Don't commit here - let the caller handle commits to maintain transaction control
        return True

    except psycopg2.Error as e:
        logger.error(f"❌ Failed to save score for {score_data['symbol']}: {e}")
        # In autocommit mode, no need to rollback - error is already isolated
        return False

def sync_ad_scores_to_positioning_metrics(conn):
    """Sync A/D scores from stock_scores.accumulation_distribution to positioning_metrics.ad_rating."""
    try:
        cur = conn.cursor()
        sync_sql = """
        UPDATE positioning_metrics pm
        SET ad_rating = ss.accumulation_distribution
        FROM stock_scores ss
        WHERE pm.symbol = ss.symbol
        AND ss.accumulation_distribution IS NOT NULL
        """
        cur.execute(sync_sql)
        cur.close()
        affected = cur.rowcount if hasattr(cur, 'rowcount') else 0
        logger.info(f"✅ Synced A/D scores to positioning_metrics")
        return True
    except Exception as e:
        logger.error(f"❌ Error syncing A/D scores: {e}")
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
        # Enable autocommit to avoid "transaction is aborted" errors when one stock fails
        # Each operation commits immediately, preventing cascade failures
        conn.autocommit = True

        # Create stock_scores table
        if not create_stock_scores_table(conn):
            return False

        # Clear old stock_scores data before loading new ones
        if not clear_old_stock_scores(conn):
            logger.warning("⚠️  Warning: failed to clear old data but continuing...")

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
            logger.warning("⚠️  Failed to fetch quality metrics - will continue with partial metrics allowed")
            quality_metrics = {}  # Use empty dict - allow partial metrics for OR logic

        # Fetch all growth metrics for percentile-based growth scoring
        logger.info("📊 Fetching growth metrics for percentile-based scoring...")
        growth_metrics = fetch_all_growth_metrics(conn)
        if growth_metrics is None:
            logger.warning("⚠️  Failed to fetch growth metrics - will continue with partial metrics allowed")
            growth_metrics = {}  # Use empty dict - allow partial metrics for OR logic

        # Fetch all value metrics for percentile-based value scoring
        logger.info("📊 Fetching value metrics for percentile-based scoring...")
        value_metrics = fetch_all_value_metrics(conn)
        if value_metrics is None:
            logger.warning("⚠️  Failed to fetch value metrics - retrying with direct query...")
            # Retry with direct query to ensure metrics are always populated
            try:
                cur = conn.cursor()
                cur.execute("SELECT trailing_pe, forward_pe, price_to_book, price_to_sales_ttm, peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield FROM key_metrics WHERE trailing_pe IS NOT NULL OR forward_pe IS NOT NULL OR price_to_book IS NOT NULL OR price_to_sales_ttm IS NOT NULL OR peg_ratio IS NOT NULL OR ev_to_revenue IS NOT NULL OR ev_to_ebitda IS NOT NULL")
                rows = cur.fetchall()
                cur.close()

                value_metrics = {'pe': [], 'forward_pe': [], 'pb': [], 'ps': [], 'peg': [], 'ev_revenue': [], 'ev_ebitda': [], 'dividend_yield': [], 'payout_ratio': []}
                for row in rows:
                    pe, fpe, pb, ps, peg, ev_rev, ev_ebit, div_yield = row
                    if pe is not None and abs(pe) < 5000:
                        value_metrics['pe'].append(float(pe))
                    if fpe is not None and fpe > 0 and fpe < 5000:
                        value_metrics['forward_pe'].append(float(fpe))
                    if pb is not None and pb >= 0 and pb < 5000:
                        value_metrics['pb'].append(float(pb))
                    if ps is not None and ps >= 0 and ps < 5000:
                        value_metrics['ps'].append(float(ps))
                    if peg is not None and peg >= 0 and peg < 5000:
                        value_metrics['peg'].append(float(peg))
                    if ev_rev is not None and ev_rev >= 0 and ev_rev < 5000:
                        value_metrics['ev_revenue'].append(float(ev_rev))
                    if ev_ebit is not None and abs(ev_ebit) < 5000:
                        value_metrics['ev_ebitda'].append(float(ev_ebit))
                    if div_yield is not None and div_yield >= 0 and div_yield < 100:
                        value_metrics['dividend_yield'].append(float(div_yield))
                logger.info(f"✅ Recovered {sum(len(v) for v in value_metrics.values())} metrics from direct query")
            except Exception as e:
                logger.warning(f"❌ Direct query also failed ({e}) - initializing empty metrics")
                value_metrics = {
                    'pe': [],
                    'pb': [],
                    'ps': [],
                    'peg': [],
                    'ev_revenue': [],
                    'ev_ebitda': [],
                    'dividend_yield': [],
                    'payout_ratio': []
                }

        # Fetch all positioning metrics for percentile-based positioning scoring
        logger.info("📊 Fetching positioning metrics for percentile-based scoring...")
        positioning_metrics = fetch_all_positioning_metrics(conn)
        if positioning_metrics is None:
            logger.error("❌ Failed to fetch positioning metrics - CRITICAL DATA REQUIRED")
            positioning_metrics = None  # No fallback - return None if data unavailable

        # Fetch all stability metrics for percentile-based stability scoring
        logger.info("📊 Fetching stability metrics for percentile-based scoring...")
        stability_metrics = fetch_all_stability_metrics(conn)
        if stability_metrics is None:
            logger.error("❌ Failed to fetch stability metrics - CRITICAL DATA REQUIRED")
            stability_metrics = None  # No fallback - return None if data unavailable

        # Process each symbol
        successful = 0
        failed = 0
        import time

        for i, symbol in enumerate(symbols, 1):
            try:
                # Log every 10th stock to reduce I/O overhead
                if i % 10 == 1:
                    logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})")

                # Create a fresh cursor for each stock to avoid transaction abort issues
                score_data = get_stock_data_from_database(conn, symbol, quality_metrics, growth_metrics, value_metrics, positioning_metrics, stability_metrics)
                if score_data:
                    # Save to database
                    if save_stock_score(conn, score_data):
                        # Autocommit mode handles commits automatically
                        successful += 1

                        # Safe logging with diagnostic info - handle None values gracefully (every 10th stock or on NULL scores)
                        try:
                            composite_str = f"{score_data['composite_score']:.2f}" if score_data['composite_score'] is not None else "NULL"
                            momentum_str = f"{score_data['momentum_score']:.2f}" if score_data['momentum_score'] is not None else "NULL"
                            growth_str = f"{score_data['growth_score']:.2f}" if score_data['growth_score'] is not None else "NULL"
                            quality_str = f"{score_data['quality_score']:.2f}" if score_data['quality_score'] is not None else "NULL"
                            positioning_str = f"{score_data['positioning_score']:.2f}" if score_data['positioning_score'] is not None else "NULL"
                            stability_str = f"{score_data['stability_score']:.2f}" if score_data['stability_score'] is not None else "NULL"

                            # Add diagnostic info if any scores are NULL
                            if None in [score_data['composite_score'], score_data['momentum_score'], score_data['growth_score'], score_data['quality_score'], score_data['positioning_score'], score_data['stability_score']]:
                                null_scores = []
                                if score_data['composite_score'] is None:
                                    null_scores.append("composite")
                                if score_data['momentum_score'] is None:
                                    null_scores.append("momentum")
                                if score_data['growth_score'] is None:
                                    null_scores.append("growth")
                                if score_data['quality_score'] is None:
                                    null_scores.append("quality")
                                if score_data['positioning_score'] is None:
                                    null_scores.append("positioning")
                                if score_data['stability_score'] is None:
                                    null_scores.append("stability")
                                logger.warning(f"⚠️ {symbol}: Composite={composite_str}, Momentum={momentum_str}, Growth={growth_str}, Quality={quality_str}, Positioning={positioning_str}, Stability={stability_str} | NULL: {', '.join(null_scores)}")
                            elif i % 10 == 0:
                                logger.info(f"✅ {symbol}: Composite={composite_str}, Momentum={momentum_str}, Growth={growth_str}, Quality={quality_str}, Positioning={positioning_str}, Stability={stability_str}")
                        except Exception as e:
                            logger.warning(f"⚠️ {symbol}: Score calculation completed but logging failed: {e}")
                    else:
                        # Save failed - already logged in save_stock_score
                        failed += 1
                else:
                    failed += 1
            except Exception as e:
                # In autocommit mode, errors don't affect other stocks
                logger.error(f"❌ Error processing {symbol}: {e}")
                failed += 1

            # Reduced delay to improve speed (was 0.1s, now 0.01s)
            # Still prevents connection pool flooding on localhost
            time.sleep(0.01)

        logger.info(f"🎯 Completed! Successful: {successful}, Failed: {failed}")

        # Sync A/D scores to positioning_metrics for API and frontend display
        logger.info("📊 Syncing A/D scores to positioning_metrics...")
        if not sync_ad_scores_to_positioning_metrics(conn):
            logger.warning("⚠️  Failed to sync A/D scores but continuing")

        return True

    except Exception as e:
        logger.error(f"❌ Error in main process: {e}")
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)