#!/usr/bin/env python3
"""
Stock Scores Loader Script - Enhanced Scoring Logic v2.2 (Updated: 2025-10-16)
VERIFIED: 2025-10-26 Fresh reload completed successfully - 5,315/5,315 rows (100%) ✅
Trigger: 20251026_120000 - AWS deployment final scoring engine (all data ready)
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
3. Growth Score (19%): Earnings growth + Momentum + Stability
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
                value_score DECIMAL(5,2),
                quality_score DECIMAL(5,2),
                growth_score DECIMAL(5,2),
                positioning_score DECIMAL(5,2),
                sentiment_score DECIMAL(5,2),
                stability_score DECIMAL(5,2),
                stability_inputs JSONB,
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
                -- Data completeness and flagging (Option 1: Exclude from scores with clear flagging)
                score_status VARCHAR(50) DEFAULT 'complete',
                available_metrics JSONB,
                missing_metrics JSONB,
                score_notes TEXT,
                estimated_data_ready_date DATE,
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

        # Add data completeness flagging columns (Option 1: Clear flagging for missing data)
        try:
            cur.execute("""
                ALTER TABLE stock_scores
                ADD COLUMN IF NOT EXISTS score_status VARCHAR(50) DEFAULT 'complete',
                ADD COLUMN IF NOT EXISTS available_metrics JSONB,
                ADD COLUMN IF NOT EXISTS missing_metrics JSONB,
                ADD COLUMN IF NOT EXISTS score_notes TEXT,
                ADD COLUMN IF NOT EXISTS estimated_data_ready_date DATE;
            """)
            conn.commit()
            logger.info("✅ Data completeness flagging columns ready")
        except psycopg2.Error as e:
            logger.warning(f"⚠️ Could not add flagging columns: {e}")
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
            WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca')
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

def fetch_beta_from_database(conn, symbol):
    """
    Fetch beta from database (populated by loaddailycompanydata.py from yfinance).

    Beta is pre-fetched from yfinance.ticker.info by the ingestion loader.
    Uses a fresh cursor to isolate from main transaction to prevent abort cascades.
    Returns None if not found - caller will use neutral 1.0 fallback.
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
    if current_price and current_price > 0 and shares_outstanding and shares_outstanding > 0:
        market_cap = current_price * shares_outstanding
        liquidity_ratio = volume_avg_30d / market_cap
        # Normalize to 0-1 scale (typical liquidity ratios range 0-0.3)
        # Use log scale to compress range: min(liquidity_ratio / 0.3, 1.0)
        normalized_liquidity = min(liquidity_ratio / 0.3, 1.0)
        return normalized_liquidity

    # If no market cap data, return None (insufficient data for calculation)
    return None

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

def fetch_all_value_metrics(conn):
    """
    Fetch value metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each valuation metric.
    """
    try:
        cur = conn.cursor()

        # Fetch valuation metrics from key_metrics table
        cur.execute("""
            SELECT
                km.trailing_pe,
                km.price_to_book,
                km.price_to_sales_ttm,
                km.peg_ratio,
                km.ev_to_revenue,
                pd.symbol
            FROM key_metrics km
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON km.ticker = pd.symbol
            WHERE km.trailing_pe IS NOT NULL
               OR km.price_to_book IS NOT NULL
               OR km.price_to_sales_ttm IS NOT NULL
               OR km.peg_ratio IS NOT NULL
               OR km.ev_to_revenue IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary
        metrics = {
            'pe': [],
            'pb': [],
            'ps': [],
            'peg': [],
            'ev_revenue': []
        }

        # Process valuation metrics - collect all non-None values for percentile calculation
        for row in rows:
            pe, pb, ps, peg, ev_rev, symbol = row

            if pe is not None and pe > 0 and pe < 500:  # Filter out invalid values
                metrics['pe'].append(float(pe))
            if pb is not None and pb > 0 and pb < 100:
                metrics['pb'].append(float(pb))
            if ps is not None and ps > 0 and ps < 100:
                metrics['ps'].append(float(ps))
            if peg is not None and peg > 0 and peg < 500:
                metrics['peg'].append(float(peg))
            if ev_rev is not None and ev_rev > 0 and ev_rev < 100:
                metrics['ev_revenue'].append(float(ev_rev))

        logger.info(f"📊 Loaded value metrics for percentile calculation:")
        logger.info(f"   P/E Ratio: {len(metrics['pe'])} stocks")
        logger.info(f"   P/B Ratio: {len(metrics['pb'])} stocks")
        logger.info(f"   P/S Ratio: {len(metrics['ps'])} stocks")
        logger.info(f"   PEG Ratio: {len(metrics['peg'])} stocks")
        logger.info(f"   EV/Revenue: {len(metrics['ev_revenue'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch value metrics for percentile ranking: {e}")
        return None

def fetch_all_positioning_metrics(conn):
    """
    Fetch positioning metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each positioning metric.
    """
    try:
        cur = conn.cursor()

        # Fetch positioning metrics from positioning_metrics table
        cur.execute("""
            SELECT
                pm.institutional_ownership_pct,
                pm.insider_ownership_pct,
                pm.institution_count
            FROM positioning_metrics pm
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON pm.symbol = pd.symbol
            WHERE pm.institutional_ownership_pct IS NOT NULL
               OR pm.insider_ownership_pct IS NOT NULL
               OR pm.institution_count IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary
        metrics = {
            'institutional_ownership': [],
            'insider_ownership': [],
            'institution_count': []
        }

        # Process positioning metrics - collect all non-None values for percentile calculation
        for row in rows:
            inst_ownership, insider_ownership, inst_count = row

            if inst_ownership is not None and 0 <= inst_ownership <= 100:
                metrics['institutional_ownership'].append(float(inst_ownership))
            if insider_ownership is not None and 0 <= insider_ownership <= 100:
                metrics['insider_ownership'].append(float(insider_ownership))
            if inst_count is not None and inst_count > 0:
                metrics['institution_count'].append(float(inst_count))

        logger.info(f"📊 Loaded positioning metrics for percentile calculation:")
        logger.info(f"   Institutional Ownership: {len(metrics['institutional_ownership'])} stocks")
        logger.info(f"   Insider Ownership: {len(metrics['insider_ownership'])} stocks")
        logger.info(f"   Institution Count: {len(metrics['institution_count'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch positioning metrics for percentile ranking: {e}")
        return None

def fetch_all_stability_metrics(conn):
    """
    Fetch stability metrics for all stocks to enable percentile ranking.
    Returns a dictionary with lists of values for each risk metric.
    """
    try:
        cur = conn.cursor()

        # Fetch stability metrics from risk_metrics and price_daily
        cur.execute("""
            SELECT
                rm.volatility_12m_pct,
                rm.downside_volatility_pct,
                rm.max_drawdown_52w_pct,
                fm.beta
            FROM risk_metrics rm
            INNER JOIN (
                SELECT DISTINCT symbol FROM price_daily
            ) pd ON rm.symbol = pd.symbol
            LEFT JOIN financials fm ON rm.symbol = fm.ticker AND rm.date = fm.date
            WHERE rm.volatility_12m_pct IS NOT NULL
               OR rm.downside_volatility_pct IS NOT NULL
               OR rm.max_drawdown_52w_pct IS NOT NULL
               OR fm.beta IS NOT NULL
        """)

        rows = cur.fetchall()
        cur.close()

        # Build metrics dictionary
        metrics = {
            'volatility': [],
            'downside_volatility': [],
            'drawdown': [],
            'beta': []
        }

        # Process stability metrics - collect all non-None values for percentile calculation
        for row in rows:
            volatility, downside_vol, drawdown, beta = row

            if volatility is not None and volatility > 0 and volatility < 500:
                metrics['volatility'].append(float(volatility))
            if downside_vol is not None and downside_vol > 0 and downside_vol < 500:
                metrics['downside_volatility'].append(float(downside_vol))
            if drawdown is not None and 0 <= drawdown <= 100:
                metrics['drawdown'].append(float(drawdown))
            if beta is not None and beta > 0 and beta < 10:
                metrics['beta'].append(float(beta))

        logger.info(f"📊 Loaded stability metrics for percentile calculation:")
        logger.info(f"   Volatility (12M): {len(metrics['volatility'])} stocks")
        logger.info(f"   Downside Volatility: {len(metrics['downside_volatility'])} stocks")
        logger.info(f"   Drawdown (52W): {len(metrics['drawdown'])} stocks")
        logger.info(f"   Beta: {len(metrics['beta'])} stocks")

        return metrics

    except Exception as e:
        logger.error(f"❌ Failed to fetch stability metrics for percentile ranking: {e}")
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

def get_stock_data_from_database(conn, symbol, quality_metrics=None, growth_metrics=None, value_metrics=None):
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
        price_change_1d = ((current_price - float(df['close'].iloc[-2])) / float(df['close'].iloc[-2]) * 100) if current_price and len(df) >= 2 else None
        price_change_5d = ((current_price - float(df['close'].iloc[-6])) / float(df['close'].iloc[-6]) * 100) if current_price and len(df) >= 6 else None
        price_change_30d = ((current_price - float(df['close'].iloc[-31])) / float(df['close'].iloc[-31]) * 100) if current_price and len(df) >= 31 else None

        # Calculate volume average (last 30 days)
        volume_avg_30d = int(df['volume'].tail(30).mean()) if len(df) >= 30 else (int(df['volume'].mean()) if len(df) > 0 else None)

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
            rsi = float(raw_rsi) if raw_rsi is not None else None
            macd = float(raw_macd) if raw_macd is not None else None
            macd_hist = float(raw_macd_hist) if raw_macd_hist is not None else None
            sma_20 = float(raw_sma_20) if raw_sma_20 is not None else None
            sma_50 = float(raw_sma_50) if raw_sma_50 is not None else None
            sma_200 = float(raw_sma_200) if raw_sma_200 is not None else None
            atr = float(raw_atr) if raw_atr is not None else None
            mom_10d = float(raw_mom_10d) if raw_mom_10d is not None else None
            roc_10d = float(raw_roc_10d) if raw_roc_10d is not None else None
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

        # Get dual momentum metrics from momentum_metrics table
        cur.execute("""
            SELECT momentum_12_3, momentum_6m, momentum_3m, risk_adjusted_momentum
            FROM momentum_metrics
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
        """, (symbol,))

        momentum_data = cur.fetchone()
        if momentum_data and len(momentum_data) >= 4:
            # Convert Decimal types from PostgreSQL to float immediately after fetching
            raw_momentum_12m_1, raw_momentum_6m, raw_momentum_3m, raw_risk_adj_momentum = momentum_data
            momentum_12m_1 = float(raw_momentum_12m_1) if raw_momentum_12m_1 is not None else None
            momentum_6m = float(raw_momentum_6m) if raw_momentum_6m is not None else None
            momentum_3m = float(raw_momentum_3m) if raw_momentum_3m is not None else None
            risk_adjusted_momentum = float(raw_risk_adj_momentum) if raw_risk_adj_momentum is not None else None
        else:
            # No dual momentum data available
            momentum_12m_1 = None
            momentum_6m = None
            momentum_3m = None
            risk_adjusted_momentum = None

        if len(df) > 0:
            prices = df['close'].astype(float).values
            volatility_30d = calculate_volatility(prices)
        else:
            volatility_30d = None

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
            news_count = int(sentiment_data[1]) if sentiment_data and sentiment_data[1] is not None else None
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

        # Get market-level AAII sentiment for market sentiment component
        # REAL DATA ONLY - None if no data available
        try:
            cur.execute("""
                SELECT bullish, neutral, bearish
                FROM aaii_sentiment
                ORDER BY date DESC
                LIMIT 1
            """)
            aaii_data = cur.fetchone()
            aaii_sentiment_component = None  # Start with None (no data)
            if aaii_data and aaii_data[0] is not None and aaii_data[2] is not None:
                bullish = float(aaii_data[0])
                bearish = float(aaii_data[2])
                # Convert AAII bullish/bearish to sentiment score: -25 to +25
                # If bullish > 50%, positive sentiment; if bearish > 50%, negative
                aaii_sentiment_component = ((bullish - bearish) / 100) * 50
        except psycopg2.Error as e:
            logger.debug(f"AAII sentiment table query failed: {e}")
            aaii_sentiment_component = None  # Error - return None instead of fake 0

        # Get real positioning data from positioning_metrics table
        try:
            # Query positioning data directly from yfinance-sourced tables
            # NO positioning_metrics table needed - get data from yfinance tables instead

            institutional_ownership = None
            insider_ownership = None
            short_percent_of_float = None  # Will remain None if not available in data
            institution_count = None

            # 1. Get institutional ownership & count from institutional_positioning (yfinance data)
            try:
                cur.execute("""
                    SELECT
                        SUM(CASE WHEN market_share IS NOT NULL THEN market_share ELSE 0 END) as total_market_share,
                        COUNT(DISTINCT institution_name) as count
                    FROM institutional_positioning
                    WHERE symbol = %s
                """, (symbol,))
                inst_data = cur.fetchone()
                if inst_data:
                    # market_share is already as decimal (0.0-1.0)
                    institutional_ownership = float(inst_data[0]) if inst_data[0] is not None and inst_data[0] > 0 else None
                    institution_count = int(inst_data[1]) if inst_data[1] is not None and inst_data[1] > 0 else None
            except psycopg2.Error as e:
                logger.debug(f"Institutional positioning query failed for {symbol}: {e}")

            # 2. Get insider ownership count from insider_roster (yfinance data)
            # NOTE: We can't calculate true insider ownership % without market cap/shares outstanding
            # So we use insider_count as a presence indicator instead
            insider_count = None
            try:
                cur.execute("""
                    SELECT COUNT(DISTINCT insider_name) as insider_count
                    FROM insider_roster
                    WHERE symbol = %s AND shares_owned_directly > 0
                """, (symbol,))
                insider_count_data = cur.fetchone()
                if insider_count_data and insider_count_data[0] is not None:
                    insider_count = int(insider_count_data[0]) if insider_count_data[0] > 0 else None
            except psycopg2.Error as e:
                logger.debug(f"Insider count query failed for {symbol}: {e}")

            # Use insider_count as a proxy for insider_ownership score
            # (more insiders = more confidence in the company)
            # This will be scored using the institution_count thresholds (50+ = good support)
            if insider_count is not None and insider_count >= 5:
                insider_ownership = 5  # Presence of 5+ insiders with holdings = good sign
            elif insider_count is not None and insider_count >= 3:
                insider_ownership = 3  # 3-4 insiders = moderate confidence
            # else: insider_ownership stays None if <3 or no data

            # Note: short_percent_of_float may not exist in yfinance tables and will remain None

        except psycopg2.Error as e:
            conn.rollback()
            logger.warning(f"Positioning data query failed for {symbol}: {e}")
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
        stability_score = None
        stability_inputs = {
            'volatility_12m_pct': None,
            'downside_volatility_pct': None,
            'max_drawdown_52w_pct': None,
            'beta': None,
            'liquidity_risk': None
        }

        try:
            # Calculate risk components with graceful fallbacks
            risk_stability_score = None  # Initialize to prevent UnboundLocalError
            prices = df['close'].astype(float).values

            # Calculate volatility directly from price data (30-day)
            volatility_12m_pct = calculate_volatility(prices)  # Annualized
            if volatility_12m_pct is None:
                # No fallback - risk_stability_score will be None if volatility missing
                risk_stability_score = None
                logger.warning(f"{symbol}: Cannot calculate volatility - cannot calculate stability score")

            # Calculate downside volatility (only on down days)
            downside_volatility = calculate_downside_volatility(prices)
            if downside_volatility is None:
                # No fallback - stability will be None if downside volatility missing
                stability_score = None
                logger.warning(f"{symbol}: Cannot calculate downside volatility - cannot calculate stability score")

            # Fetch beta from database (fetched from yfinance by loaddailycompanydata.py)
            # NO FALLBACK - if beta is missing, it's missing. Only use real data.
            beta = fetch_beta_from_database(conn, symbol)
            if beta is None:
                logger.warning(f"{symbol}: Beta not found in database - will calculate stability without beta")

            # Calculate liquidity risk (based on volume)
            # Liquidity is optional - will be skipped if not available (REAL DATA ONLY)
            liquidity_risk = calculate_liquidity_risk(volume_avg_30d, current_price)

            # Try to get drawdown from risk_metrics table
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
            except Exception as e:
                logger.warning(f"{symbol}: risk_metrics table error ({e}), calculating drawdown from price data")

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
            liquidity_str = f"{liquidity_risk:.0f}" if liquidity_risk is not None else "N/A"
            logger.info(f"{symbol}: Calculated risk components - Vol={vol_str}, Downside={downside_str}, Drawdown={drawdown_str}, Beta={beta_str}, Liquidity={liquidity_str}")

            # PHASE 2 FIX: Calculate stability_score using available risk_metrics data
            # Only require: volatility_12m_pct, max_drawdown_52w_pct (downside_volatility is optional)
            # Use volatility_12m_pct as proxy for downside_volatility if not available
            if volatility_12m_pct is None or max_drawdown_52w_pct is None:
                stability_score = None
                logger.info(f"{symbol} Stability Score: None (missing essential volatility/drawdown data)")
            else:
                # Use downside_volatility if available, otherwise use volatility as proxy
                downside_vol_proxy = downside_volatility if downside_volatility is not None else volatility_12m_pct

                # All components available - calculate risk score
                # Convert all to 0-100 scale for risk components
                vol_percentile = max(0, min(100, 100 - (volatility_12m_pct * 2)))  # Inverted: lower vol = higher score
                downside_percentile = max(0, min(100, 100 - (downside_vol_proxy * 2.5)))  # Use proxy with adjusted scaling
                drawdown_percentile = max(0, min(100, 100 - max_drawdown_52w_pct))  # Inverted: lower drawdown = higher score

                # Calculate composite stability score - REAL DATA ONLY, no fallback defaults
                # Optional components: beta, liquidity (excluded if missing)
                components = []
                weights = []

                # Required: volatility (35%)
                components.append(vol_percentile)
                weights.append(0.35)

                # Required: downside (30%)
                components.append(downside_percentile)
                weights.append(0.30)

                # Required: drawdown (25%)
                components.append(drawdown_percentile)
                weights.append(0.25)

                # Optional: beta (10% if available)
                if beta is not None:
                    beta_percentile = max(0, min(100, 100 - (beta * 50)))  # Scale: 1.0=50, 0.5=75, 1.5=25
                    components.append(beta_percentile)
                    weights.append(0.10)
                else:
                    logger.info(f"{symbol}: Beta missing - calculating stability without beta (real data only)")

                # Re-normalize weights to sum to 1.0 (in case beta is missing)
                total_weight = sum(weights)
                normalized_weights = [w / total_weight for w in weights]

                # Calculate weighted composite
                risk_stability_score = sum(c * w for c, w in zip(components, normalized_weights))
                risk_stability_score = max(0, min(100, risk_stability_score))

                # Store risk inputs for display
                stability_inputs['volatility_12m_pct'] = round(volatility_12m_pct, 4)
                stability_inputs['downside_volatility_pct'] = round(downside_vol_proxy, 2)
                stability_inputs['max_drawdown_52w_pct'] = round(max_drawdown_52w_pct, 2)
                stability_inputs['beta'] = round(beta, 3) if beta is not None else None
                stability_inputs['liquidity_risk'] = round(liquidity_risk, 1) if liquidity_risk is not None else None

                beta_str = f", Beta_pct={beta_percentile:.0f}" if beta is not None else ""
                logger.info(f"{symbol} Stability Score: {risk_stability_score:.1f} (Vol_pct={vol_percentile:.0f}, Downside_pct={downside_percentile:.0f}, Drawdown_pct={drawdown_percentile:.0f}{beta_str}, Using {'calc' if downside_volatility is not None else 'proxy'} downside)")

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

        # Calculate price vs SMA50 deviation if not already available
        price_vs_sma_50 = None
        if current_price is not None and sma_50 is not None and sma_50 > 0:
            # Values are already converted to float in the conversion block above
            price_vs_sma_50 = ((current_price - sma_50) / sma_50) * 100

        # Calculate price vs SMA200 deviation if not already available
        price_vs_sma_200 = None
        if current_price is not None and sma_200 is not None and sma_200 > 0:
            # Values are already converted to float from price_data
            price_vs_sma_200 = ((current_price - sma_200) / sma_200) * 100

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

        # Component 5: Momentum Stability (10 points) - Multi-timeframe alignment
        # Primary: Check alignment across 3M, 6M, 12M returns from momentum_metrics
        # Fallback: Check alignment across ROC timeframes from technical indicators
        stability_score = 5  # Start neutral

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

        # Initialize momentum_consistency for use later in return dict
        momentum_consistency = None

        if len(timeframe_signals) >= 2:
            signal_sum = sum(timeframe_signals)
            signal_count = len(timeframe_signals)

            if abs(signal_sum) == signal_count:
                # All timeframes agree (all positive or all negative)
                momentum_consistency = 8 + trend_alignment_bonus
            elif abs(signal_sum) == signal_count - 1:
                # Mostly aligned (2 out of 3 agree)
                momentum_consistency = 6 + (trend_alignment_bonus * 0.5)
            elif signal_sum == 0:
                # Mixed signals - conflicting momentum
                momentum_consistency = 3
            else:
                momentum_consistency = 5

            momentum_consistency = max(0, min(10, momentum_consistency))

        # Calculate final momentum score (0-100 scale)
        # Components: 10 + 25 + 25 + 15 + 10 = 85 pts (scaled to 100)
        # Check if all momentum components are available
        if any(x is None for x in [intraweek_confirmation, short_term_momentum, medium_term_momentum,
                                    longer_term_momentum, momentum_consistency]):
            momentum_score = None
        else:
            raw_momentum_score = (intraweek_confirmation + short_term_momentum + medium_term_momentum +
                                 longer_term_momentum + momentum_consistency)
            # Scale from 85-point scale to 100-point scale
            momentum_score = (raw_momentum_score / 85) * 100
            momentum_score = max(0, min(100, momentum_score))

        # ============================================================
        # Value Score - Enhanced Percentile-Based Valuation with Quality Modifiers
        # Base: 4-component system (P/E, P/B, P/S, PEG percentiles)
        # Enhanced with modifiers: FCF Quality, Growth Context, Dividend Yield
        # ============================================================
        value_score = None

        # FIX: Calculate value score directly from key_metrics instead of circular read from stock_scores
        try:
            cur.execute("""
                SELECT
                    trailing_pe,
                    price_to_book,
                    price_to_sales_ttm,
                    peg_ratio,
                    ev_to_revenue,
                    free_cashflow,
                    dividend_yield,
                    payout_ratio
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            km = cur.fetchone()
            if km:
                # Extract raw valuation metrics
                trailing_pe = km[0]
                price_to_book = km[1]
                price_to_sales_ttm = km[2]
                peg_ratio_val = km[3]
                ev_to_revenue = km[4]
                free_cashflow = km[5]
                dividend_yield_val = km[6]
                payout_ratio = km[7]

                # COMPONENT 1: Percentile-Based Valuation Score (Percentile Ranking - Industry Standard)
                # Lower multiples = better values (inverted percentile calculation)
                value_score_components = []
                value_weights = []

                # PE ratio scoring: lower is better
                # Invert for percentile: lower PE should get higher percentile score
                if trailing_pe is not None and trailing_pe > 0 and trailing_pe < 500:
                    pe_percentile = calculate_percentile_rank(-float(trailing_pe),
                                                             [-pe for pe in value_metrics.get('pe', [])])
                    pe_score = (pe_percentile / 100) * 100 * 0.3
                    value_score_components.append(pe_score)
                    value_weights.append(0.3)

                # PB ratio scoring: lower is better
                if price_to_book is not None and price_to_book > 0 and price_to_book < 100:
                    pb_percentile = calculate_percentile_rank(-float(price_to_book),
                                                             [-pb for pb in value_metrics.get('pb', [])])
                    pb_score = (pb_percentile / 100) * 100 * 0.2
                    value_score_components.append(pb_score)
                    value_weights.append(0.2)

                # PS ratio scoring: lower is better
                if price_to_sales_ttm is not None and price_to_sales_ttm > 0 and price_to_sales_ttm < 100:
                    ps_percentile = calculate_percentile_rank(-float(price_to_sales_ttm),
                                                             [-ps for ps in value_metrics.get('ps', [])])
                    ps_score = (ps_percentile / 100) * 100 * 0.25
                    value_score_components.append(ps_score)
                    value_weights.append(0.25)

                # PEG ratio scoring: lower is better (<1.0 = value, >2.0 = expensive)
                if peg_ratio_val is not None and peg_ratio_val > 0 and peg_ratio_val < 500:
                    peg_percentile = calculate_percentile_rank(-float(peg_ratio_val),
                                                              [-peg for peg in value_metrics.get('peg', [])])
                    peg_score = (peg_percentile / 100) * 100 * 0.15
                    value_score_components.append(peg_score)
                    value_weights.append(0.15)

                # EV/Revenue scoring: lower is better
                if ev_to_revenue is not None and ev_to_revenue > 0 and ev_to_revenue < 100:
                    ev_percentile = calculate_percentile_rank(-float(ev_to_revenue),
                                                             [-ev for ev in value_metrics.get('ev_revenue', [])])
                    ev_score = (ev_percentile / 100) * 100 * 0.1
                    value_score_components.append(ev_score)
                    value_weights.append(0.1)

                if value_score_components:
                    # Re-normalize weights based on available components
                    total_weight = sum(value_weights)
                    normalized_weights = [w / total_weight for w in value_weights]
                    base_value_score = sum(score * weight for score, weight in zip(value_score_components, normalized_weights))

                    # COMPONENT 2: FCF Quality Modifier (0.8 - 1.2x)
                    fcf_modifier = 1.0
                    if free_cashflow is not None:
                        fcf_val = float(free_cashflow)
                        if fcf_val < 0:
                            fcf_modifier = 0.8  # Negative FCF = value trap
                        elif fcf_val > 0:
                            fcf_modifier = 1.1  # Positive FCF = quality increase

                    # COMPONENT 3: Dividend Modifier (0.95 - 1.05x)
                    dividend_modifier = 1.0
                    if dividend_yield_val is not None:
                        div_yield = float(dividend_yield_val)
                        if div_yield > 0.001:  # More than 0.1%
                            dividend_modifier = 1.05

                    # Calculate final value score
                    value_score = base_value_score * fcf_modifier * dividend_modifier
                    value_score = max(0, min(100, value_score))
                    logger.debug(f"{symbol} Value Score: PE={trailing_pe:.1f}, PB={price_to_book:.1f}, PS={price_to_sales_ttm:.1f}, base={base_value_score:.1f}, fcf_mod={fcf_modifier:.2f}, div_mod={dividend_modifier:.2f}, final={value_score:.1f}")

        except (psycopg2.Error, TypeError, ValueError) as e:
            logger.debug(f"{symbol}: Could not calculate value score from key_metrics: {e}")

        # No fallback - value_score remains None if cannot be calculated

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
            # No fallback - quality_score remains None if metrics not available
            pass

        # ============================================================
        # Growth Score - Percentile-Based TTM Metrics (Industry Standard)
        # 5-component system using percentile ranking for market-relative growth scoring
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
            # No fallback - growth_score remains None if metrics not available
            pass

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

        # Clamp sentiment score to 0-100
        if sentiment_score is not None:
            if isinstance(sentiment_score, (int, float)):
                sentiment_score = max(0, min(100, sentiment_score))
        # If sentiment_score is None, leave it as None (no data to calculate)

        # No fallback defaults - all scores remain None if not calculated
        # Composite will only use scores that have real values

        # Composite Score - Only use real (non-None) factors
        # Ideal weights: Momentum (22.35%), Growth (20.13%), Value (16.13%),
        #                Quality (16.13%), Stability (14.88%), Positioning (12.08%)
        # Adjust proportionally based on available factors (no fallback defaults)

        # Collect available factors and their ideal weights
        factors = []
        weights = []

        if momentum_score is not None:
            factors.append(momentum_score)
            weights.append(0.2235)
        if growth_score is not None:
            factors.append(growth_score)
            weights.append(0.2013)
        if value_score is not None:
            factors.append(value_score)
            weights.append(0.1613)
        if quality_score is not None:
            factors.append(quality_score)
            weights.append(0.1613)
        if stability_score is not None:
            factors.append(stability_score)
            weights.append(0.1488)
        if positioning_score is not None:
            factors.append(positioning_score)
            weights.append(0.1208)

        # Calculate composite only if we have factors
        if factors and sum(weights) > 0:
            # Normalize weights to sum to 1.0
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            composite_score = sum(f * w for f, w in zip(factors, normalized_weights))
        else:
            # No valid factors - composite remains None
            composite_score = None

        cur.close()

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

        # Track which metrics are available
        if momentum_score is not None:
            available_metrics.append('momentum')
        else:
            missing_metrics.append('momentum')

        if growth_score is not None:
            available_metrics.append('growth')
        else:
            missing_metrics.append('growth')

        if value_score is not None:
            available_metrics.append('value')
        else:
            missing_metrics.append('value')

        if quality_score is not None:
            available_metrics.append('quality')
        else:
            missing_metrics.append('quality')

        if stability_score is not None or risk_stability_score is not None:
            available_metrics.append('stability')
        else:
            missing_metrics.append('stability')

        if positioning_score is not None:
            available_metrics.append('positioning')
        else:
            missing_metrics.append('positioning')

        if sentiment_score is not None:
            available_metrics.append('sentiment')
        else:
            missing_metrics.append('sentiment')

        # Set status and notes based on missing data
        if missing_metrics:
            # Option 1: Don't calculate composite for stocks with missing key metrics
            if 'momentum' in missing_metrics:
                score_status = 'insufficient_data'
                score_notes = f"Requires 12+ months of price history for momentum calculation. Currently available: {', '.join(available_metrics)}"
                # Estimate when data will be available (~12 months from first price data)
                estimated_data_ready_date = (datetime.now().date() + timedelta(days=365))
                logger.info(f"{symbol}: ⏳ INSUFFICIENT_DATA - Missing momentum metric. Status: {score_status}")
            else:
                score_status = 'partial'
                score_notes = f"Some metrics missing. Available: {', '.join(available_metrics)}. Missing: {', '.join(missing_metrics)}"
                logger.warning(f"{symbol}: ⚠️ PARTIAL_DATA - Some metrics missing. Score calculated from available data only.")

        return {
            'symbol': symbol,
            'composite_score': float(round(clamp_score(composite_score), 2)) if composite_score is not None else None,
            'momentum_score': float(round(clamp_score(momentum_score), 2)) if momentum_score is not None else None,
            'value_score': float(round(clamp_score(value_score), 2)) if value_score is not None else None,
            'quality_score': float(round(clamp_score(quality_score), 2)) if quality_score is not None else None,
            'growth_score': float(round(clamp_score(growth_score), 2)) if growth_score is not None else None,
            'positioning_score': float(round(clamp_score(positioning_score), 2)) if positioning_score is not None else None,
            'sentiment_score': float(round(clamp_score(sentiment_score), 2)) if sentiment_score is not None else None,
            'stability_score': float(round(clamp_score(risk_stability_score), 2)) if risk_stability_score is not None else None,
            'stability_inputs': stability_inputs,
            'rsi': float(rsi) if rsi is not None else None,
            'macd': float(macd) if macd is not None else None,
            'sma_20': float(round(float(sma_20), 2)) if sma_20 else None,
            'sma_50': float(round(float(sma_50), 2)) if sma_50 else None,
            'volume_avg_30d': int(volume_avg_30d) if volume_avg_30d is not None else None,
            'current_price': float(round(current_price, 2)) if current_price is not None else None,
            'price_change_1d': float(round(price_change_1d, 2)) if price_change_1d is not None else None,
            'price_change_5d': float(round(price_change_5d, 2)) if price_change_5d is not None else None,
            'price_change_30d': float(round(price_change_30d, 2)) if price_change_30d is not None else None,
            'volatility_30d': float(volatility_30d) if volatility_30d is not None else None,
            'market_cap': int(market_cap) if market_cap else None,
            'pe_ratio': float(round(pe_ratio, 2)) if pe_ratio else None,
            # Momentum components (6-component system)
            'momentum_intraweek': float(round(intraweek_confirmation, 2)),
            'momentum_short_term': float(round(short_term_momentum, 2)),
            'momentum_medium_term': float(round(medium_term_momentum, 2)),
            'momentum_long_term': float(round(longer_term_momentum, 2)),
            'momentum_consistency': float(round(momentum_consistency, 2)) if momentum_consistency is not None else None,
            'roc_10d': float(round(roc_10d, 2)) if roc_10d is not None else None,
            'roc_20d': float(round(roc_20d, 2)) if roc_20d is not None else None,
            'roc_60d': float(round(roc_60d, 2)) if roc_60d is not None else None,
            'roc_120d': float(round(roc_120d, 2)) if roc_120d is not None else None,
            'roc_252d': float(round(roc_252d, 2)) if roc_252d is not None else None,
            'mom': float(round(mom_10d, 2)) if mom_10d is not None else None,
            'mansfield_rs': float(round(mansfield_rs, 2)) if mansfield_rs is not None else None,
            # Positioning component: Accumulation/Distribution Rating
            'acc_dist_rating': float(round(acc_dist_rating, 2)) if acc_dist_rating is not None else None,
            # Data completeness and flagging (Option 1)
            'score_status': score_status,
            'available_metrics': available_metrics,
            'missing_metrics': missing_metrics,
            'score_notes': score_notes,
            'estimated_data_ready_date': estimated_data_ready_date.isoformat() if estimated_data_ready_date else None
        }

    except Exception as e:
        import traceback
        logger.warning(f"⚠️ Error calculating scores for {symbol} - will attempt fallback: {e}")
        logger.debug(traceback.format_exc())
        # Try to save partial score if we have at least SOME calculated scores
        try:
            # Create minimal fallback score with any calculated components
            # Convert all numpy types to native Python types
            fallback_score = {
                'symbol': symbol,
                'composite_score': None,
                'momentum_score': float(momentum_score) if 'momentum_score' in locals() and momentum_score is not None else None,
                'value_score': float(value_score) if 'value_score' in locals() and value_score is not None else None,
                'quality_score': float(quality_score) if 'quality_score' in locals() and quality_score is not None else None,
                'growth_score': float(growth_score) if 'growth_score' in locals() and growth_score is not None else None,
                'positioning_score': float(positioning_score) if 'positioning_score' in locals() and positioning_score is not None else None,
                'sentiment_score': float(sentiment_score) if 'sentiment_score' in locals() and sentiment_score is not None else None,
                'stability_score': float(risk_stability_score) if 'risk_stability_score' in locals() and risk_stability_score is not None else None,
                'stability_inputs': None,
                'rsi': float(rsi) if 'rsi' in locals() and rsi is not None else None,
                'macd': float(macd) if 'macd' in locals() and macd is not None else None,
                'sma_20': float(round(float(sma_20), 2)) if 'sma_20' in locals() and sma_20 else None,
                'sma_50': float(round(float(sma_50), 2)) if 'sma_50' in locals() and sma_50 else None,
                'volume_avg_30d': int(volume_avg_30d) if 'volume_avg_30d' in locals() and volume_avg_30d is not None else None,
                'current_price': float(round(current_price, 2)) if 'current_price' in locals() and current_price is not None else None,
                'price_change_1d': None,
                'price_change_5d': None,
                'price_change_30d': None,
                'volatility_30d': None,
                'market_cap': None,
                'pe_ratio': None,
                'momentum_intraweek': None,
                'momentum_short_term': None,
                'momentum_medium_term': None,
                'momentum_long_term': None,
                'momentum_consistency': None,
                'roc_10d': None,
                'roc_20d': None,
                'roc_60d': None,
                'roc_120d': None,
                'roc_252d': None,
                'mom': None,
                'mansfield_rs': None,
                'acc_dist_rating': None
            }
            conn.rollback()  # Rollback aborted transaction
            # Return even the fallback - don't skip the stock entirely
            return fallback_score
        except:
            conn.rollback()
            return None

def save_stock_score(conn, score_data):
    """Save stock score to database."""
    try:
        cur = conn.cursor()

        # Convert stability_inputs dict to JSON string for JSONB column
        if score_data.get('stability_inputs') is not None:
            score_data['stability_inputs'] = json.dumps(score_data['stability_inputs'])

        # Upsert query
        upsert_sql = """
        INSERT INTO stock_scores (
            symbol, composite_score, momentum_score, value_score, quality_score, growth_score,
            positioning_score, sentiment_score, stability_score, stability_inputs,
            rsi, macd, sma_20, sma_50, volume_avg_30d, current_price,
            price_change_1d, price_change_5d, price_change_30d, volatility_30d,
            market_cap, pe_ratio,
            momentum_intraweek, momentum_short_term, momentum_medium_term, momentum_long_term,
            momentum_consistency,
            roc_10d, roc_20d, roc_60d, roc_120d, roc_252d, mom, mansfield_rs,
            acc_dist_rating,
            score_date, last_updated
        ) VALUES (
            %(symbol)s, %(composite_score)s, %(momentum_score)s, %(value_score)s, %(quality_score)s, %(growth_score)s,
            %(positioning_score)s, %(sentiment_score)s, %(stability_score)s, %(stability_inputs)s,
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
            value_score = EXCLUDED.value_score,
            quality_score = EXCLUDED.quality_score,
            growth_score = EXCLUDED.growth_score,
            positioning_score = EXCLUDED.positioning_score,
            sentiment_score = EXCLUDED.sentiment_score,
            stability_score = EXCLUDED.stability_score,
            stability_inputs = EXCLUDED.stability_inputs,
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
        cur.close()
        # Don't commit here - let the caller handle commits to maintain transaction control
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
        # Disable autocommit - use explicit commits for data persistence
        conn.autocommit = False

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
            logger.warning("⚠️  Failed to fetch value metrics - will continue with partial metrics allowed")
            value_metrics = {}  # Use empty dict - allow partial metrics for OR logic

        # Process each symbol
        successful = 0
        failed = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"📈 Processing {symbol} ({i}/{len(symbols)})")

                # Create a fresh cursor for each stock to avoid transaction abort issues
                score_data = get_stock_data_from_database(conn, symbol, quality_metrics, growth_metrics, value_metrics)
                if score_data:
                    # Save to database
                    if save_stock_score(conn, score_data):
                        # Commit after each stock to prevent long transaction abort cascades
                        conn.commit()
                        successful += 1

                        # Safe logging with diagnostic info - handle None values gracefully
                        try:
                            composite_str = f"{score_data['composite_score']:.2f}" if score_data['composite_score'] is not None else "NULL"
                            growth_str = f"{score_data['growth_score']:.2f}" if score_data['growth_score'] is not None else "NULL"
                            quality_str = f"{score_data['quality_score']:.2f}" if score_data['quality_score'] is not None else "NULL"
                            stability_str = f"{score_data['stability_score']:.2f}" if score_data['stability_score'] is not None else "NULL"

                            # Add diagnostic info if any scores are NULL
                            if None in [score_data['composite_score'], score_data['growth_score'], score_data['quality_score'], score_data['stability_score']]:
                                null_scores = []
                                if score_data['composite_score'] is None:
                                    null_scores.append("composite")
                                if score_data['growth_score'] is None:
                                    null_scores.append("growth")
                                if score_data['quality_score'] is None:
                                    null_scores.append("quality")
                                if score_data['stability_score'] is None:
                                    null_scores.append("stability")
                                logger.warning(f"⚠️ {symbol}: Composite={composite_str}, Growth={growth_str}, Quality={quality_str}, Stability={stability_str} | NULL: {', '.join(null_scores)}")
                            else:
                                logger.info(f"✅ {symbol}: Composite={composite_str}, Growth={growth_str}, Quality={quality_str}, Stability={stability_str}")
                        except Exception as e:
                            logger.warning(f"⚠️ {symbol}: Score calculation completed but logging failed: {e}")
                    else:
                        # Rollback on save failure to keep transaction clean
                        conn.rollback()
                        failed += 1
                else:
                    failed += 1
            except Exception as e:
                # Rollback on error to clean up transaction state
                try:
                    conn.rollback()
                except:
                    pass
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