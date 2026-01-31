#!/usr/bin/env python3
"""
Stock Scores Loader v2.0 - Z-Score Based Multi-Factor Scoring System

METHODOLOGY:
1. Z-Score Normalization (scipy.stats.zscore)
   - For each metric, calculate z-score across ALL stocks
   - Z-scores naturally create -3 to +3 range (full 0-100 when converted)

2. Factor Scores (6 total):
   - Quality: Average z-scores of [ROE, ROA, profit margin, earnings stability]
   - Growth: Average z-scores of [revenue growth, EPS growth, FCF growth]
   - Value: Average z-scores of [1/PE, 1/PB, 1/PS, 1/EV_EBITDA] (inverted - lower is better)
   - Momentum: Average z-scores of [RSI, MACD, price momentum metrics]
   - Positioning: Average z-scores of [institutional ownership, insider ownership, short interest (inv), A/D rating, institution count]
   - Stability: Average z-scores of [-volatility, -drawdown, -beta] (inverted - lower is better)

3. Machine Learning Weight Discovery:
   - Train RandomForestRegressor using the 6 factor scores as inputs
   - Target = average of all factors (baseline)
   - Use feature_importances_ as weights for final composite score

4. Convert Z-Scores to 0-100:
   - Z-score distribution: scipy.stats.norm.cdf(z_score) * 100
   - This naturally spreads: bad=-3 sigma -> 0, average=0 -> 50, good=+3 sigma -> 100

VERSION: 2.0 - Complete rewrite using proven z-score methodology
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
from scipy import stats
from scipy.stats import zscore
from sklearn.ensemble import RandomForestRegressor
import boto3
import warnings
warnings.filterwarnings('ignore')

# Database configuration
DB_SECRET_ARN = os.getenv('DB_SECRET_ARN')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadstockscores_v2.py"

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def get_db_connection(script_name="loader"):
    """Connect to database using AWS Secrets Manager (priority) or environment variables.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    # Try AWS Secrets Manager first
    if DB_SECRET_ARN:
        try:
            sm = boto3.client("secretsmanager", region_name="us-east-1")
            secret = json.loads(sm.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
            conn = psycopg2.connect(
                host=secret["host"], port=int(secret.get("port", 5432)),
                user=secret["username"], password=secret["password"],
                database=secret["dbname"],
                connect_timeout=30,
                options='-c statement_timeout=600000'
            )
            logger.info("Using AWS Secrets Manager for database config")
            return conn
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fallback: Use environment variables
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_user = os.getenv('DB_USER', 'stocks')
    db_password = os.getenv('DB_PASSWORD', '')
    db_name = os.getenv('DB_NAME', 'stocks')

    try:
        conn = psycopg2.connect(
            host=db_host, port=int(db_port),
            user=db_user, password=db_password,
            database=db_name,
            connect_timeout=30,
            options='-c statement_timeout=600000'
        )
        logger.info("Using environment variables for database config")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise Exception("Could not connect to database - no valid credentials found")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def to_float(val):
    """Convert Decimal, NumPy types, or any numeric to float."""
    if val is None:
        return np.nan
    try:
        if isinstance(val, decimal.Decimal):
            return float(val)
        return float(val)
    except (ValueError, TypeError):
        return np.nan

def zscore_to_percentile(z_score):
    """
    Convert z-score to 0-100 percentile using CDF.

    Formula: scipy.stats.norm.cdf(z_score) * 100
    - Z=-3 -> ~0.13 (rounds to ~0)
    - Z=0  -> 50
    - Z=+3 -> ~99.87 (rounds to ~100)
    """
    if np.isnan(z_score) or np.isinf(z_score):
        return np.nan
    # Cap at +/- 3 sigma for reasonable bounds
    z_capped = np.clip(z_score, -3, 3)
    return stats.norm.cdf(z_capped) * 100

def calculate_factor_zscore(values, invert=False):
    """
    Calculate z-scores for a series of values.

    Args:
        values: numpy array of metric values
        invert: If True, negate z-scores (for metrics where lower is better)

    Returns:
        numpy array of z-scores (NaN for missing values)
    """
    # Handle all-NaN case
    if np.all(np.isnan(values)):
        return np.full(len(values), np.nan)

    # Calculate z-score, handling NaN values
    with np.errstate(invalid='ignore'):
        mean_val = np.nanmean(values)
        std_val = np.nanstd(values)

        if std_val == 0 or np.isnan(std_val):
            return np.full(len(values), np.nan)

        z_scores = (values - mean_val) / std_val

        if invert:
            z_scores = -z_scores

        return z_scores

# ============================================================================
# A/D RATING CALCULATION
# ============================================================================

def calculate_ad_rating_for_symbol(cursor, symbol):
    """
    Calculate IBD-style Accumulation/Distribution Rating (50-100 scale).

    Analyzes 20-60 trading days of volume data to determine institutional
    buying/selling patterns:
    - A: 90-100% accumulation volume = Strong Accumulation (90-100 score)
    - B: 70-89% accumulation volume = Moderate Accumulation (80-89 score)
    - C: 50-69% accumulation volume = Neutral (70-79 score)
    - D: 30-49% accumulation volume = Moderate Distribution (60-69 score)
    - E: 0-29% accumulation volume = Strong Distribution (50-59 score)
    """
    try:
        cursor.execute("""
            SELECT date, close, volume
            FROM price_daily
            WHERE symbol = %s
            AND close IS NOT NULL
            AND volume IS NOT NULL
            ORDER BY date DESC
            LIMIT 100
        """, (symbol,))

        rows = cursor.fetchall()

        # Need at least 20 days of data
        if len(rows) < 20:
            return np.nan

        # Reverse to chronological order
        rows = list(reversed(rows))

        # Calculate accumulation vs distribution volume
        accumulation_volume = 0
        distribution_volume = 0
        total_volume = 0

        for i in range(1, len(rows)):
            current_close = float(rows[i][1])
            current_volume = float(rows[i][2])
            previous_close = float(rows[i-1][1])

            total_volume += current_volume

            if current_close > previous_close:
                accumulation_volume += current_volume
            elif current_close < previous_close:
                distribution_volume += current_volume

        if total_volume == 0:
            return np.nan

        # Calculate accumulation percentage and convert to 50-100 scale
        accumulation_pct = (accumulation_volume / total_volume) * 100
        rating_score = 50 + (accumulation_pct / 2)

        return round(rating_score, 2)

    except Exception as e:
        logger.debug(f"A/D calculation failed for {symbol}: {e}")
        return np.nan

def calculate_ad_ratings_batch(conn, symbols):
    """Calculate A/D ratings for a batch of symbols."""
    logger.info(f"  Calculating A/D ratings for {len(symbols)} symbols...")

    cur = conn.cursor()
    ad_ratings = {}

    for i, symbol in enumerate(symbols):
        ad_ratings[symbol] = calculate_ad_rating_for_symbol(cur, symbol)

        if (i + 1) % 1000 == 0:
            logger.info(f"    Calculated A/D for {i+1}/{len(symbols)} symbols")

    cur.close()

    non_null = sum(1 for v in ad_ratings.values() if not np.isnan(v))
    logger.info(f"  A/D ratings calculated: {non_null}/{len(symbols)} stocks")

    return ad_ratings

# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_all_stock_data(conn):
    """
    Load all required metrics for all stocks into a single DataFrame.
    This is more efficient than querying per-stock.

    Returns:
        pd.DataFrame with all metrics indexed by symbol
    """
    logger.info("Loading all stock data for z-score calculation...")
    cur = conn.cursor()

    # Query 1: Get all eligible stock symbols
    cur.execute("""
        SELECT DISTINCT s.symbol
        FROM stock_symbols s
        WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
          AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
          AND (s.test_issue != 'Y' OR s.test_issue IS NULL)
          AND (s.financial_status != 'D' OR s.financial_status IS NULL)
          AND s.symbol NOT ILIKE '%$%'
          AND s.security_name NOT ILIKE '%SPAC%'
          AND s.security_name NOT ILIKE '%Special Purpose%'
          AND s.security_name NOT ILIKE '%Blank Check%'
          AND s.security_name NOT ILIKE '%Acquisition Company%'
          AND s.security_name NOT ILIKE '%ETN%'
          AND s.security_name NOT ILIKE '%Fund%'
          AND s.security_name NOT ILIKE '%Trust%'
    """)
    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f"Found {len(symbols)} eligible stock symbols")

    # Initialize DataFrame with symbols as index
    df = pd.DataFrame(index=symbols)
    df.index.name = 'symbol'

    # ========================================
    # QUALITY METRICS
    # ========================================
    logger.info("Loading quality metrics...")
    cur.execute("""
        SELECT
            km.ticker as symbol,
            km.return_on_equity_pct as roe,
            km.return_on_assets_pct as roa,
            km.profit_margin_pct as profit_margin,
            km.operating_margin_pct as operating_margin,
            km.gross_margin_pct as gross_margin,
            km.debt_to_equity,
            km.current_ratio,
            km.quick_ratio
        FROM key_metrics km
    """)
    quality_rows = cur.fetchall()
    quality_df = pd.DataFrame(quality_rows, columns=[
        'symbol', 'roe', 'roa', 'profit_margin', 'operating_margin',
        'gross_margin', 'debt_to_equity', 'current_ratio', 'quick_ratio'
    ]).set_index('symbol')

    # Add earnings stability from quality_metrics table
    cur.execute("""
        SELECT symbol, eps_growth_stability, fcf_to_net_income
        FROM quality_metrics
    """)
    eps_stability_rows = cur.fetchall()
    eps_stability_df = pd.DataFrame(eps_stability_rows, columns=[
        'symbol', 'eps_growth_stability', 'fcf_to_net_income'
    ]).set_index('symbol')
    quality_df = quality_df.join(eps_stability_df, how='outer')

    df = df.join(quality_df, how='left')
    logger.info(f"  Quality metrics loaded: {len(quality_df)} records")

    # ========================================
    # GROWTH METRICS
    # ========================================
    logger.info("Loading growth metrics...")
    cur.execute("""
        SELECT
            km.ticker as symbol,
            km.revenue_growth_pct as revenue_growth,
            km.earnings_growth_pct as eps_growth,
            km.earnings_q_growth_pct as eps_q_growth
        FROM key_metrics km
    """)
    growth_rows = cur.fetchall()
    growth_df = pd.DataFrame(growth_rows, columns=[
        'symbol', 'revenue_growth', 'eps_growth', 'eps_q_growth'
    ]).set_index('symbol')

    # Add FCF growth from growth_metrics table
    cur.execute("""
        SELECT symbol, fcf_growth_yoy, ocf_growth_yoy, eps_growth_3y_cagr
        FROM growth_metrics
    """)
    fcf_growth_rows = cur.fetchall()
    fcf_growth_df = pd.DataFrame(fcf_growth_rows, columns=[
        'symbol', 'fcf_growth_yoy', 'ocf_growth_yoy', 'eps_growth_3y_cagr'
    ]).set_index('symbol')
    growth_df = growth_df.join(fcf_growth_df, how='outer')

    df = df.join(growth_df, how='left', rsuffix='_growth')
    logger.info(f"  Growth metrics loaded: {len(growth_df)} records")

    # ========================================
    # VALUE METRICS
    # ========================================
    logger.info("Loading value metrics...")
    cur.execute("""
        SELECT
            km.ticker as symbol,
            km.trailing_pe as pe_ratio,
            km.forward_pe,
            km.price_to_book as pb_ratio,
            km.price_to_sales_ttm as ps_ratio,
            km.peg_ratio,
            km.ev_to_ebitda,
            km.ev_to_revenue,
            km.dividend_yield
        FROM key_metrics km
    """)
    value_rows = cur.fetchall()
    value_df = pd.DataFrame(value_rows, columns=[
        'symbol', 'pe_ratio', 'forward_pe', 'pb_ratio', 'ps_ratio',
        'peg_ratio', 'ev_to_ebitda', 'ev_to_revenue', 'dividend_yield'
    ]).set_index('symbol')

    df = df.join(value_df, how='left', rsuffix='_value')
    logger.info(f"  Value metrics loaded: {len(value_df)} records")

    # ========================================
    # MOMENTUM METRICS
    # ========================================
    logger.info("Loading momentum metrics...")

    # Technical indicators from technical_data_daily (latest per symbol)
    # Use subquery for better performance on large tables
    cur.execute("""
        SELECT t.symbol, t.rsi, t.macd, t.macd_hist, t.sma_50, t.sma_200
        FROM technical_data_daily t
        INNER JOIN (
            SELECT symbol, MAX(date) as max_date
            FROM technical_data_daily
            WHERE rsi IS NOT NULL
            GROUP BY symbol
        ) latest ON t.symbol = latest.symbol AND t.date = latest.max_date
    """)
    tech_rows = cur.fetchall()
    tech_df = pd.DataFrame(tech_rows, columns=[
        'symbol', 'rsi', 'macd', 'macd_hist', 'sma_50', 'sma_200'
    ]).set_index('symbol')

    # Momentum from momentum_metrics table (optimized query)
    cur.execute("""
        SELECT m.symbol, m.momentum_3m, m.momentum_6m, m.momentum_12m
        FROM momentum_metrics m
        INNER JOIN (
            SELECT symbol, MAX(date) as max_date
            FROM momentum_metrics
            WHERE momentum_3m IS NOT NULL OR momentum_6m IS NOT NULL
            GROUP BY symbol
        ) latest ON m.symbol = latest.symbol AND m.date = latest.max_date
    """)
    mom_rows = cur.fetchall()
    mom_df = pd.DataFrame(mom_rows, columns=[
        'symbol', 'momentum_3m', 'momentum_6m', 'momentum_12m'
    ]).set_index('symbol')
    tech_df = tech_df.join(mom_df, how='outer')

    # Get current prices for price vs SMA calculations (optimized)
    cur.execute("""
        SELECT p.symbol, p.close as current_price
        FROM price_daily p
        INNER JOIN (
            SELECT symbol, MAX(date) as max_date
            FROM price_daily
            GROUP BY symbol
        ) latest ON p.symbol = latest.symbol AND p.date = latest.max_date
    """)
    price_rows = cur.fetchall()
    price_df = pd.DataFrame(price_rows, columns=['symbol', 'current_price']).set_index('symbol')
    tech_df = tech_df.join(price_df, how='outer')

    df = df.join(tech_df, how='left', rsuffix='_mom')
    logger.info(f"  Momentum metrics loaded: {len(tech_df)} records")

    # ========================================
    # POSITIONING METRICS
    # ========================================
    logger.info("Loading positioning metrics...")
    cur.execute("""
        SELECT
            symbol,
            institutional_ownership_pct,
            insider_ownership_pct,
            short_interest_pct,
            institutional_holders_count
        FROM positioning_metrics
    """)
    pos_rows = cur.fetchall()
    pos_df = pd.DataFrame(pos_rows, columns=[
        'symbol', 'institutional_ownership', 'insider_ownership',
        'short_interest', 'institution_count'
    ]).set_index('symbol')

    df = df.join(pos_df, how='left', rsuffix='_pos')
    logger.info(f"  Positioning metrics loaded: {len(pos_df)} records")

    # ========================================
    # A/D RATING (Accumulation/Distribution)
    # ========================================
    logger.info("Loading A/D ratings from stock_scores.accumulation_distribution...")
    cur.execute("""
        SELECT symbol, accumulation_distribution as ad_rating
        FROM stock_scores
        WHERE accumulation_distribution IS NOT NULL
    """)
    ad_rows = cur.fetchall()
    if ad_rows:
        ad_df = pd.DataFrame(ad_rows, columns=['symbol', 'ad_rating']).set_index('symbol')
        df = df.join(ad_df, how='left', rsuffix='_ad')
        logger.info(f"  A/D ratings loaded: {len(ad_df)} records (1 of 5 Positioning inputs)")
    else:
        df['ad_rating'] = np.nan
        logger.info("  A/D ratings: Not available - using NaN (skipping expensive batch calculation)")
        logger.info("  Note: A/D Rating is 1 of 5 components in Positioning factor - other 4 components will be calculated")

    # ========================================
    # STABILITY METRICS
    # ========================================
    logger.info("Loading stability metrics...")
    cur.execute("""
        SELECT s.symbol, s.volatility_12m, s.max_drawdown_52w, s.beta
        FROM stability_metrics s
        INNER JOIN (
            SELECT symbol, MAX(date) as max_date
            FROM stability_metrics
            WHERE volatility_12m IS NOT NULL OR beta IS NOT NULL
            GROUP BY symbol
        ) latest ON s.symbol = latest.symbol AND s.date = latest.max_date
    """)
    stab_rows = cur.fetchall()
    stab_df = pd.DataFrame(stab_rows, columns=[
        'symbol', 'volatility_12m', 'max_drawdown_52w', 'beta'
    ]).set_index('symbol')

    df = df.join(stab_df, how='left', rsuffix='_stab')
    logger.info(f"  Stability metrics loaded: {len(stab_df)} records")

    # ========================================
    # COMPANY INFO
    # ========================================
    cur.execute("""
        SELECT ticker as symbol, short_name as company_name
        FROM company_profile
    """)
    company_rows = cur.fetchall()
    company_df = pd.DataFrame(company_rows, columns=['symbol', 'company_name']).set_index('symbol')
    df = df.join(company_df, how='left')

    cur.close()

    # Convert all columns to float (handle Decimal types)
    for col in df.columns:
        if col != 'company_name':
            df[col] = df[col].apply(to_float)

    logger.info(f"Total stocks loaded: {len(df)}")
    logger.info(f"Columns: {list(df.columns)}")

    return df

# ============================================================================
# Z-SCORE FACTOR CALCULATION
# ============================================================================

def calculate_quality_factor(df):
    """
    Calculate Quality factor score using z-score normalization.

    Components (4 metrics):
    - ROE (higher is better)
    - ROA (higher is better)
    - Profit Margin (higher is better)
    - Earnings Stability (lower std dev is better - INVERTED)

    Returns: Series of z-scores for Quality factor
    """
    logger.info("Calculating Quality factor z-scores...")

    # Calculate z-scores for each component
    z_roe = calculate_factor_zscore(df['roe'].values, invert=False)
    z_roa = calculate_factor_zscore(df['roa'].values, invert=False)
    z_profit_margin = calculate_factor_zscore(df['profit_margin'].values, invert=False)
    z_eps_stability = calculate_factor_zscore(df['eps_growth_stability'].values, invert=True)  # Lower is better

    # Stack z-scores and calculate mean (ignoring NaN)
    z_stack = np.column_stack([z_roe, z_roa, z_profit_margin, z_eps_stability])
    quality_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(quality_z))
    logger.info(f"  Quality factor calculated for {non_nan_count} stocks")

    return pd.Series(quality_z, index=df.index, name='quality_z')

def calculate_growth_factor(df):
    """
    Calculate Growth factor score using z-score normalization.

    Components (3 metrics):
    - Revenue Growth (higher is better)
    - EPS Growth (higher is better)
    - FCF Growth YoY (higher is better)

    Returns: Series of z-scores for Growth factor
    """
    logger.info("Calculating Growth factor z-scores...")

    z_revenue = calculate_factor_zscore(df['revenue_growth'].values, invert=False)
    z_eps = calculate_factor_zscore(df['eps_growth'].values, invert=False)
    z_fcf = calculate_factor_zscore(df['fcf_growth_yoy'].values, invert=False)

    z_stack = np.column_stack([z_revenue, z_eps, z_fcf])
    growth_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(growth_z))
    logger.info(f"  Growth factor calculated for {non_nan_count} stocks")

    return pd.Series(growth_z, index=df.index, name='growth_z')

def calculate_value_factor(df):
    """
    Calculate Value factor score using z-score normalization.

    Components (4 metrics) - ALL INVERTED (lower valuation = higher score):
    - 1/PE (inverted - lower PE is better value)
    - 1/PB (inverted - lower PB is better value)
    - 1/PS (inverted - lower PS is better value)
    - 1/EV_EBITDA (inverted - lower EV/EBITDA is better value)

    Returns: Series of z-scores for Value factor
    """
    logger.info("Calculating Value factor z-scores...")

    # Calculate inverted ratios (1/x) for value metrics
    # Higher 1/PE means lower PE which is better value
    pe_inv = np.where(df['pe_ratio'].values > 0, 1 / df['pe_ratio'].values, np.nan)
    pb_inv = np.where(df['pb_ratio'].values > 0, 1 / df['pb_ratio'].values, np.nan)
    ps_inv = np.where(df['ps_ratio'].values > 0, 1 / df['ps_ratio'].values, np.nan)
    ev_ebitda_inv = np.where(df['ev_to_ebitda'].values > 0, 1 / df['ev_to_ebitda'].values, np.nan)

    z_pe = calculate_factor_zscore(pe_inv, invert=False)  # Already inverted above
    z_pb = calculate_factor_zscore(pb_inv, invert=False)
    z_ps = calculate_factor_zscore(ps_inv, invert=False)
    z_ev_ebitda = calculate_factor_zscore(ev_ebitda_inv, invert=False)

    z_stack = np.column_stack([z_pe, z_pb, z_ps, z_ev_ebitda])
    value_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(value_z))
    logger.info(f"  Value factor calculated for {non_nan_count} stocks")

    return pd.Series(value_z, index=df.index, name='value_z')

def calculate_momentum_factor(df):
    """
    Calculate Momentum factor score using z-score normalization.

    Components (5 metrics):
    - RSI (higher indicates momentum, but neutral around 50)
    - MACD (higher is better momentum)
    - Momentum 3M (higher is better)
    - Momentum 6M (higher is better)
    - Momentum 12M (higher is better)

    Returns: Series of z-scores for Momentum factor
    """
    logger.info("Calculating Momentum factor z-scores...")

    z_rsi = calculate_factor_zscore(df['rsi'].values, invert=False)
    z_macd = calculate_factor_zscore(df['macd'].values, invert=False)
    z_mom_3m = calculate_factor_zscore(df['momentum_3m'].values, invert=False)
    z_mom_6m = calculate_factor_zscore(df['momentum_6m'].values, invert=False)
    z_mom_12m = calculate_factor_zscore(df['momentum_12m'].values, invert=False)

    z_stack = np.column_stack([z_rsi, z_macd, z_mom_3m, z_mom_6m, z_mom_12m])
    momentum_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(momentum_z))
    logger.info(f"  Momentum factor calculated for {non_nan_count} stocks")

    return pd.Series(momentum_z, index=df.index, name='momentum_z')

def calculate_positioning_factor(df):
    """
    Calculate Positioning factor score using z-score normalization.

    Components (5 metrics):
    - Institutional Ownership (higher is better - smart money)
    - Insider Ownership (higher is better - skin in the game)
    - Short Interest (INVERTED - lower short interest is better)
    - A/D Rating (higher is better - accumulation > distribution)
    - Institution Count (higher is better - more institutional interest)

    A/D Rating is 1 of 5 inputs in the Positioning factor.

    Returns: Series of z-scores for Positioning factor
    """
    logger.info("Calculating Positioning factor z-scores (A/D rating is 1 of 5 inputs)...")

    z_inst_own = calculate_factor_zscore(df['institutional_ownership'].values, invert=False)
    z_insider_own = calculate_factor_zscore(df['insider_ownership'].values, invert=False)
    z_short_int = calculate_factor_zscore(df['short_interest'].values, invert=True)  # Lower is better
    z_ad_rating = calculate_factor_zscore(df['ad_rating'].values, invert=False)  # A/D RATING - KEY INPUT
    z_inst_count = calculate_factor_zscore(df['institution_count'].values, invert=False)

    z_stack = np.column_stack([z_inst_own, z_insider_own, z_short_int, z_ad_rating, z_inst_count])
    positioning_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(positioning_z))
    ad_rating_count = np.sum(~np.isnan(df['ad_rating'].values))
    logger.info(f"  Positioning factor calculated for {non_nan_count} stocks")
    logger.info(f"  A/D Rating available for {ad_rating_count} stocks (integrated as 1 of 5 components)")

    return pd.Series(positioning_z, index=df.index, name='positioning_z')

def calculate_stability_factor(df):
    """
    Calculate Stability factor score using z-score normalization.

    Components (3 metrics) - ALL INVERTED (lower risk = higher score):
    - Volatility 12M (INVERTED - lower volatility is better)
    - Max Drawdown 52W (INVERTED - lower drawdown is better)
    - Beta (INVERTED - lower beta is more stable)

    Returns: Series of z-scores for Stability factor
    """
    logger.info("Calculating Stability factor z-scores...")

    z_volatility = calculate_factor_zscore(df['volatility_12m'].values, invert=True)  # Lower is better
    z_drawdown = calculate_factor_zscore(df['max_drawdown_52w'].values, invert=True)  # Lower is better
    z_beta = calculate_factor_zscore(df['beta'].values, invert=True)  # Lower is better

    z_stack = np.column_stack([z_volatility, z_drawdown, z_beta])
    stability_z = np.nanmean(z_stack, axis=1)

    non_nan_count = np.sum(~np.isnan(stability_z))
    logger.info(f"  Stability factor calculated for {non_nan_count} stocks")

    return pd.Series(stability_z, index=df.index, name='stability_z')

# ============================================================================
# MACHINE LEARNING WEIGHT DISCOVERY
# ============================================================================

def discover_factor_weights_ml(factor_df):
    """
    Use RandomForestRegressor to discover optimal factor weights.

    Approach:
    1. Use 6 factor z-scores as features (X)
    2. Target (y) = average of all 6 factors (baseline composite)
    3. Train RandomForest to learn relationships
    4. Extract feature_importances_ as weights

    This discovers data-driven weights that reflect the natural importance
    of each factor in explaining stock score variation.

    Args:
        factor_df: DataFrame with columns [quality_z, growth_z, value_z, momentum_z, positioning_z, stability_z]

    Returns:
        dict: Factor weights that sum to 1.0
    """
    logger.info("Discovering factor weights using RandomForest...")

    factor_cols = ['quality_z', 'growth_z', 'value_z', 'momentum_z', 'positioning_z', 'stability_z']

    # Get rows with at least 4 non-NaN factors for training
    valid_mask = factor_df[factor_cols].notna().sum(axis=1) >= 4
    train_df = factor_df[valid_mask].copy()

    if len(train_df) < 100:
        logger.warning(f"Insufficient data for ML weight discovery ({len(train_df)} samples). Using equal weights.")
        return {col: 1/6 for col in factor_cols}

    # Fill NaN with column mean for training (only for rows with >= 4 factors)
    X_train = train_df[factor_cols].fillna(train_df[factor_cols].mean())

    # Target = average of all factors (baseline score)
    y_train = X_train.mean(axis=1)

    # Train RandomForest
    rf = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        min_samples_split=20,
        random_state=42,
        n_jobs=-1
    )
    rf.fit(X_train, y_train)

    # Extract feature importances as weights
    importances = rf.feature_importances_
    weights = dict(zip(factor_cols, importances / importances.sum()))

    logger.info("ML-discovered factor weights:")
    for factor, weight in sorted(weights.items(), key=lambda x: -x[1]):
        logger.info(f"  {factor}: {weight:.4f} ({weight*100:.1f}%)")

    return weights

# ============================================================================
# COMPOSITE SCORE CALCULATION
# ============================================================================

def calculate_composite_scores(factor_df, weights):
    """
    Calculate composite scores using discovered weights.

    Formula:
    1. Convert each factor z-score to 0-100 using norm.cdf(z) * 100
    2. Weighted average of factor scores using ML-discovered weights

    Args:
        factor_df: DataFrame with factor z-scores
        weights: dict of factor weights from ML discovery

    Returns:
        DataFrame with factor scores (0-100) and composite score
    """
    logger.info("Calculating composite scores...")

    factor_cols = ['quality_z', 'growth_z', 'value_z', 'momentum_z', 'positioning_z', 'stability_z']
    score_cols = ['quality_score', 'growth_score', 'value_score', 'momentum_score', 'positioning_score', 'stability_score']

    result_df = factor_df.copy()

    # Convert z-scores to 0-100 percentile scores
    for z_col, score_col in zip(factor_cols, score_cols):
        result_df[score_col] = factor_df[z_col].apply(zscore_to_percentile)

    # Calculate weighted composite score
    # Only calculate for stocks with at least 4 valid factor scores
    def calc_composite(row):
        scores = []
        used_weights = []

        for z_col, score_col in zip(factor_cols, score_cols):
            score = row[score_col]
            if not np.isnan(score):
                scores.append(score)
                weight_key = z_col  # Use z_col name to get weight
                used_weights.append(weights.get(weight_key, 1/6))

        if len(scores) < 4:
            return np.nan

        # Re-normalize weights
        total_weight = sum(used_weights)
        normalized_weights = [w / total_weight for w in used_weights]

        composite = sum(s * w for s, w in zip(scores, normalized_weights))
        return np.clip(composite, 0, 100)

    result_df['composite_score'] = result_df.apply(calc_composite, axis=1)

    # Count non-NaN composite scores
    valid_composite = result_df['composite_score'].notna().sum()
    logger.info(f"Composite scores calculated for {valid_composite} stocks")

    return result_df

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def create_stock_scores_table(conn):
    """Create/update stock_scores table with z-score columns."""
    try:
        cur = conn.cursor()

        logger.info("Ensuring stock_scores table has z-score columns...")

        # Add new z-score and weight columns if they don't exist
        # Using DO $$ block for idempotent column additions
        cur.execute("""
            DO $$
            BEGIN
                -- Add factor z-score columns
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'quality_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN quality_z DECIMAL(6,3);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'growth_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN growth_z DECIMAL(6,3);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'value_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN value_z DECIMAL(6,3);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'momentum_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN momentum_z DECIMAL(6,3);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'positioning_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN positioning_z DECIMAL(6,3);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'stability_z') THEN
                    ALTER TABLE stock_scores ADD COLUMN stability_z DECIMAL(6,3);
                END IF;

                -- Add ML weight columns
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'quality_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN quality_weight DECIMAL(5,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'growth_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN growth_weight DECIMAL(5,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'value_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN value_weight DECIMAL(5,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'momentum_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN momentum_weight DECIMAL(5,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'positioning_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN positioning_weight DECIMAL(5,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'stability_weight') THEN
                    ALTER TABLE stock_scores ADD COLUMN stability_weight DECIMAL(5,4);
                END IF;

                -- Add A/D rating column
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'ad_rating') THEN
                    ALTER TABLE stock_scores ADD COLUMN ad_rating DECIMAL(5,2);
                END IF;

                -- Add volatility_12m if not exists
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'stock_scores' AND column_name = 'volatility_12m') THEN
                    ALTER TABLE stock_scores ADD COLUMN volatility_12m DECIMAL(5,2);
                END IF;
            END $$;
        """)
        conn.commit()

        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_scores_composite ON stock_scores(composite_score DESC);
            CREATE INDEX IF NOT EXISTS idx_stock_scores_date ON stock_scores(score_date);
        """)
        conn.commit()

        logger.info("Stock scores table ready with z-score columns")
        cur.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"Failed to update stock_scores table: {e}")
        return False

def safe_float(val, decimals=2, max_val=999.99):
    """Convert numpy/pandas types to Python float for SQL, handling NaN and overflow."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        # Convert to Python float explicitly (handles numpy.float64)
        f = float(round(float(val), decimals))
        # Clamp extreme values to fit database precision limits
        if f > max_val:
            return max_val
        if f < -max_val:
            return -max_val
        return f
    except (ValueError, TypeError):
        return None

def save_scores_to_database(conn, scores_df, weights):
    """Save scores to database."""
    logger.info("Saving scores to database...")

    cur = conn.cursor()
    saved_count = 0
    error_count = 0

    # Convert weights to Python floats
    py_weights = {k: float(v) for k, v in weights.items()}

    for symbol, row in scores_df.iterrows():
        try:
            cur.execute("""
                INSERT INTO stock_scores (
                    symbol, company_name,
                    composite_score, momentum_score, value_score, quality_score,
                    growth_score, positioning_score, stability_score,
                    quality_z, growth_z, value_z, momentum_z, positioning_z, stability_z,
                    quality_weight, growth_weight, value_weight, momentum_weight, positioning_weight, stability_weight,
                    rsi, macd, pe_ratio, pb_ratio, roe, revenue_growth,
                    institutional_ownership, ad_rating, volatility_12m, beta,
                    score_date, last_updated
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CURRENT_DATE, CURRENT_TIMESTAMP
                )
                ON CONFLICT (symbol) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    composite_score = EXCLUDED.composite_score,
                    momentum_score = EXCLUDED.momentum_score,
                    value_score = EXCLUDED.value_score,
                    quality_score = EXCLUDED.quality_score,
                    growth_score = EXCLUDED.growth_score,
                    positioning_score = EXCLUDED.positioning_score,
                    stability_score = EXCLUDED.stability_score,
                    quality_z = EXCLUDED.quality_z,
                    growth_z = EXCLUDED.growth_z,
                    value_z = EXCLUDED.value_z,
                    momentum_z = EXCLUDED.momentum_z,
                    positioning_z = EXCLUDED.positioning_z,
                    stability_z = EXCLUDED.stability_z,
                    quality_weight = EXCLUDED.quality_weight,
                    growth_weight = EXCLUDED.growth_weight,
                    value_weight = EXCLUDED.value_weight,
                    momentum_weight = EXCLUDED.momentum_weight,
                    positioning_weight = EXCLUDED.positioning_weight,
                    stability_weight = EXCLUDED.stability_weight,
                    rsi = EXCLUDED.rsi,
                    macd = EXCLUDED.macd,
                    pe_ratio = EXCLUDED.pe_ratio,
                    pb_ratio = EXCLUDED.pb_ratio,
                    roe = EXCLUDED.roe,
                    revenue_growth = EXCLUDED.revenue_growth,
                    institutional_ownership = EXCLUDED.institutional_ownership,
                    ad_rating = EXCLUDED.ad_rating,
                    volatility_12m = EXCLUDED.volatility_12m,
                    beta = EXCLUDED.beta,
                    score_date = CURRENT_DATE,
                    last_updated = CURRENT_TIMESTAMP
            """, (
                symbol,
                row.get('company_name'),
                safe_float(row.get('composite_score'), 2),
                safe_float(row.get('momentum_score'), 2),
                safe_float(row.get('value_score'), 2),
                safe_float(row.get('quality_score'), 2),
                safe_float(row.get('growth_score'), 2),
                safe_float(row.get('positioning_score'), 2),
                safe_float(row.get('stability_score'), 2),
                safe_float(row.get('quality_z'), 3),
                safe_float(row.get('growth_z'), 3),
                safe_float(row.get('value_z'), 3),
                safe_float(row.get('momentum_z'), 3),
                safe_float(row.get('positioning_z'), 3),
                safe_float(row.get('stability_z'), 3),
                py_weights.get('quality_z', 0.167),
                py_weights.get('growth_z', 0.167),
                py_weights.get('value_z', 0.167),
                py_weights.get('momentum_z', 0.167),
                py_weights.get('positioning_z', 0.167),
                py_weights.get('stability_z', 0.167),
                safe_float(row.get('rsi'), 2),
                safe_float(row.get('macd'), 4),
                safe_float(row.get('pe_ratio'), 2),
                safe_float(row.get('pb_ratio'), 2),
                safe_float(row.get('roe'), 2),
                safe_float(row.get('revenue_growth'), 2),
                safe_float(row.get('institutional_ownership'), 4) if not pd.isna(row.get('institutional_ownership')) else None,  # Keep as decimal
                safe_float(row.get('ad_rating'), 2),
                safe_float(row.get('volatility_12m'), 2),
                safe_float(row.get('beta'), 2),
            ))
            saved_count += 1

            if saved_count % 500 == 0:
                conn.commit()
                logger.info(f"  Saved {saved_count} scores...")

        except Exception as e:
            error_count += 1
            if error_count <= 5:
                logger.warning(f"Error saving {symbol}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()

    logger.info(f"Saved {saved_count} scores to database ({error_count} errors)")
    return saved_count

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Stock Scores Loader v2.0 - Z-Score Based Scoring System")
    logger.info("=" * 60)

    # Connect to database
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("Failed to connect to database")
        sys.exit(1)

    try:
        # Create table if needed
        if not create_stock_scores_table(conn):
            sys.exit(1)

        # Load all stock data
        df = load_all_stock_data(conn)

        # Calculate factor z-scores
        logger.info("")
        logger.info("=" * 40)
        logger.info("CALCULATING FACTOR Z-SCORES")
        logger.info("=" * 40)

        df['quality_z'] = calculate_quality_factor(df)
        df['growth_z'] = calculate_growth_factor(df)
        df['value_z'] = calculate_value_factor(df)
        df['momentum_z'] = calculate_momentum_factor(df)
        df['positioning_z'] = calculate_positioning_factor(df)  # Includes A/D rating
        df['stability_z'] = calculate_stability_factor(df)

        # Discover factor weights using ML
        logger.info("")
        logger.info("=" * 40)
        logger.info("ML WEIGHT DISCOVERY")
        logger.info("=" * 40)

        factor_cols = ['quality_z', 'growth_z', 'value_z', 'momentum_z', 'positioning_z', 'stability_z']
        weights = discover_factor_weights_ml(df[factor_cols])

        # Calculate composite scores
        logger.info("")
        logger.info("=" * 40)
        logger.info("CALCULATING COMPOSITE SCORES")
        logger.info("=" * 40)

        scores_df = calculate_composite_scores(df, weights)

        # Print score distribution summary
        logger.info("")
        logger.info("Score Distribution Summary:")
        for col in ['composite_score', 'quality_score', 'growth_score', 'value_score',
                    'momentum_score', 'positioning_score', 'stability_score']:
            if col in scores_df.columns:
                valid_scores = scores_df[col].dropna()
                if len(valid_scores) > 0:
                    logger.info(f"  {col}: min={valid_scores.min():.1f}, median={valid_scores.median():.1f}, "
                               f"max={valid_scores.max():.1f}, count={len(valid_scores)}")

        # Save to database
        logger.info("")
        logger.info("=" * 40)
        logger.info("SAVING TO DATABASE")
        logger.info("=" * 40)

        saved_count = save_scores_to_database(conn, scores_df, weights)

        # Final summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("EXECUTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total stocks processed: {len(df)}")
        logger.info(f"Composite scores calculated: {scores_df['composite_score'].notna().sum()}")
        logger.info(f"Scores saved to database: {saved_count}")

        # Print top 10 stocks by composite score
        logger.info("")
        logger.info("Top 10 Stocks by Composite Score:")
        top_stocks = scores_df.nlargest(10, 'composite_score')[
            ['company_name', 'composite_score', 'quality_score', 'growth_score',
             'value_score', 'momentum_score', 'positioning_score', 'stability_score']
        ]
        for symbol, row in top_stocks.iterrows():
            logger.info(f"  {symbol}: {row['composite_score']:.1f} (Q={row['quality_score']:.1f}, "
                       f"G={row['growth_score']:.1f}, V={row['value_score']:.1f}, "
                       f"M={row['momentum_score']:.1f}, P={row['positioning_score']:.1f}, S={row['stability_score']:.1f})")

        sys.exit(0)

    except Exception as e:
        import traceback
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
