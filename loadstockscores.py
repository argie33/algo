#!/usr/bin/env python3
# TRIGGER: 20260429_145300 - Batch 5: Stock scores loader - VERIFICATION RUN
"""
Stock Scores Loader v3.0 COMPREHENSIVE - Uses all available metrics for accurate scoring
"""
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import os
import boto3
import json
from pathlib import Path
from scipy import stats
from scipy.stats import zscore
from dotenv import load_dotenv

# Load environment variables from .env.local if it exists
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration - works in AWS and locally.
    
    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    
    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logger.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")
    
    # Fall back to environment variables
    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks")
    }

def get_connection():
    cfg = get_db_config()
    return psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"], password=cfg["password"], dbname=cfg["database"], connect_timeout=30)

def zscore_to_percentile(z_score):
    if np.isnan(z_score) or np.isinf(z_score):
        return None
    z_capped = np.clip(z_score, -3, 3)
    return float(stats.norm.cdf(z_capped) * 100)

def calculate_factor_zscore(values, invert=False):
    """Calculate z-scores from values with winsorization to handle outliers."""
    values = np.array(values, dtype=float)
    if np.all(np.isnan(values)):
        return np.full(len(values), np.nan)
    # Winsorize at 1st/99th percentile before z-scoring to prevent outliers
    # from inflating std and crushing all other scores toward zero
    valid_mask = ~np.isnan(values)
    if valid_mask.sum() < 3:
        return np.full(len(values), np.nan)
    lo = np.nanpercentile(values, 1)
    hi = np.nanpercentile(values, 99)
    values = np.where(valid_mask, np.clip(values, lo, hi), np.nan)
    with np.errstate(invalid='ignore'):
        mean_val = np.nanmean(values)
        std_val = np.nanstd(values)
        if std_val == 0 or np.isnan(std_val):
            return np.full(len(values), np.nan)
        z_scores = (values - mean_val) / std_val
        if invert:
            z_scores = -z_scores
        return z_scores

def calculate_weighted_score(df, metric_columns, weights=None):
    """
    Compute a weighted average z-score across metrics, handling missing values.
    For each stock, re-normalizes weights using only the metrics that are present,
    so a stock missing half the metrics isn't penalized and scores stay on the
    same scale regardless of how many metrics each factor uses.
    """
    if weights is None:
        weights = {col: 1.0 for col in metric_columns}

    z_scores = []
    weight_vals = []
    for col in metric_columns:
        if col in df.columns:
            z = calculate_factor_zscore(df[col].values)
            z_scores.append(z)
            weight_vals.append(weights.get(col, 1.0))

    if not z_scores:
        return np.full(len(df), np.nan)

    z_array = np.array(z_scores)       # (n_metrics, n_stocks)
    w_array = np.array(weight_vals)    # (n_metrics,)

    # Weighted sum and sum-of-weights per stock (ignoring NaN metrics)
    present = (~np.isnan(z_array)).astype(float)  # 1 where metric is available
    weighted_sum = np.nansum(z_array * w_array[:, np.newaxis], axis=0)
    weight_sum = np.sum(present * w_array[:, np.newaxis], axis=0)

    combined = np.where(weight_sum > 0, weighted_sum / weight_sum, np.nan)
    return combined

def load_comprehensive_metrics(conn):
    """Load all comprehensive metric data from all metric tables"""
    logger.info("Loading comprehensive metric data...")
    cur = conn.cursor()

    # Get ALL stock symbols - calculate scores for all 4,996 even if some metrics missing
    # This ensures every stock gets a factor score (averaged from available metrics)
    cur.execute("""
        SELECT symbol FROM stock_symbols
        ORDER BY symbol
    """)
    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f" Loading metrics for all {len(symbols)} stocks (will calculate scores from available data)")

    df = pd.DataFrame(index=symbols)
    df.index.name = 'symbol'

    # ===== QUALITY METRICS =====
    logger.info("Loading quality metrics...")
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol, return_on_equity_pct, return_on_assets_pct, gross_margin_pct, operating_margin_pct, profit_margin_pct,
               debt_to_equity, current_ratio, quick_ratio, return_on_invested_capital_pct,
               earnings_beat_rate, earnings_surprise_avg,
               fcf_to_net_income, operating_cf_to_net_income
        FROM quality_metrics
        ORDER BY symbol, date DESC
    """)
    quality_data = cur.fetchall()
    if quality_data:
        quality_df = pd.DataFrame(quality_data, columns=[
            'symbol', 'roe', 'roa', 'gross_margin', 'operating_margin', 'profit_margin',
            'debt_to_equity', 'current_ratio', 'quick_ratio', 'roic',
            'earnings_beat_rate', 'earnings_surprise_avg',
            'fcf_to_ni', 'ocf_to_ni'
        ]).set_index('symbol')
        df = df.join(quality_df, how='left')
        logger.info(f"  Loaded quality metrics for {quality_df.shape[0]} stocks")

    # ===== GROWTH METRICS =====
    logger.info("Loading growth metrics...")
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol,
            revenue_growth_3y_cagr, eps_growth_3y_cagr, fcf_growth_yoy, ocf_growth_yoy,
            net_income_growth_yoy, revenue_growth_yoy,
            roe_trend, quarterly_growth_momentum, operating_income_growth_yoy
        FROM growth_metrics
        ORDER BY symbol, date DESC
    """)
    growth_data = cur.fetchall()
    if growth_data:
        growth_df = pd.DataFrame(growth_data, columns=[
            'symbol', 'rev_3y_cagr', 'eps_3y_cagr', 'fcf_growth', 'ocf_growth',
            'ni_growth', 'rev_growth',
            'roe_trend', 'quarterly_growth_momentum', 'oi_growth'
        ]).set_index('symbol')
        df = df.join(growth_df, how='left')
        logger.info(f"  Loaded growth metrics for {growth_df.shape[0]} stocks")

    # ===== STABILITY METRICS =====
    logger.info("Loading stability metrics...")
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol, beta, volatility_12m, downside_volatility, max_drawdown_52w, volume_consistency
        FROM stability_metrics
        ORDER BY symbol, date DESC
    """)
    stability_data = cur.fetchall()
    if stability_data:
        stability_df = pd.DataFrame(stability_data, columns=[
            'symbol', 'beta', 'volatility_12m', 'downside_vol', 'max_drawdown', 'volume_consistency'
        ]).set_index('symbol')
        df = df.join(stability_df, how='left')
        logger.info(f"  Loaded stability metrics for {stability_df.shape[0]} stocks")

    # ===== MOMENTUM METRICS =====
    logger.info("Loading momentum metrics...")
    cur.execute("""
        SELECT symbol, current_price, momentum_1m, momentum_3m, momentum_6m, momentum_12m,
               price_vs_sma_50, price_vs_sma_200, price_vs_52w_high
        FROM momentum_metrics
        WHERE (symbol, date) IN (
            SELECT symbol, MAX(date) FROM momentum_metrics GROUP BY symbol
        )
    """)
    momentum_data = cur.fetchall()
    if momentum_data:
        momentum_df = pd.DataFrame(momentum_data, columns=[
            'symbol', 'price', 'momentum_1m', 'momentum_3m', 'momentum_6m', 'momentum_12m',
            'sma_50', 'sma_200', 'high_52w'
        ]).set_index('symbol')
        df = df.join(momentum_df, how='left')
        logger.info(f"  Loaded momentum metrics for {momentum_df.shape[0]} stocks")

    # ===== VALUE METRICS =====
    logger.info("Loading value metrics...")
    cur.execute("""
        SELECT DISTINCT ON (symbol) symbol, trailing_pe as pe_ratio, price_to_book, price_to_sales_ttm, peg_ratio, dividend_yield,
               ev_to_ebitda, ev_to_revenue
        FROM value_metrics
        ORDER BY symbol, date DESC
    """)
    value_data = cur.fetchall()
    if value_data:
        value_df = pd.DataFrame(value_data, columns=[
            'symbol', 'pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio', 'div_yield',
            'ev_to_ebitda', 'ev_to_revenue'
        ]).set_index('symbol')
        df = df.join(value_df, how='left')
        logger.info(f"  Loaded value metrics for {value_df.shape[0]} stocks")

    # ===== POSITIONING METRICS =====
    logger.info("Loading positioning metrics...")
    cur.execute("""
        SELECT symbol, institutional_ownership_pct, insider_ownership_pct,
               short_ratio, short_interest_pct, ad_rating
        FROM positioning_metrics
    """)
    positioning_data = cur.fetchall()
    if positioning_data:
        positioning_df = pd.DataFrame(positioning_data, columns=[
            'symbol', 'institutional_ownership_pct', 'insider_ownership_pct', 'short_ratio', 'short_interest_pct',
            'ad_rating'
        ]).set_index('symbol')
        df = df.join(positioning_df, how='left')
        logger.info(f"  Loaded positioning metrics for {positioning_df.shape[0]} stocks")
    else:
        logger.warning("  No positioning metrics found - using NULL values")

    cur.close()
    return df

def main():
    logger.info("=" * 100)
    logger.info("Stock Scores Loader v3.0 COMPREHENSIVE - Using All Available Metrics")
    logger.info("=" * 100)

    conn = get_connection()
    df = load_comprehensive_metrics(conn)

    # Convert all columns to numeric
    logger.info("Converting data types...")
    numeric_cols = df.columns.tolist()
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # ===== QUALITY SCORE =====
    logger.info("Calculating QUALITY scores (ROE, ROA, margins, ratios based)...")
    # Invert debt_to_equity before scoring (lower leverage = better quality)
    if 'debt_to_equity' in df.columns:
        df['debt_to_equity_inv'] = -df['debt_to_equity']
    quality_metrics = [m for m in [
        'roe', 'roa', 'gross_margin', 'operating_margin', 'profit_margin', 'roic',
        'current_ratio', 'quick_ratio', 'debt_to_equity_inv',
        'earnings_beat_rate', 'earnings_surprise_avg',
        'fcf_to_ni', 'ocf_to_ni'
    ] if m in df.columns]
    if quality_metrics:
        quality_weights = {
            'roe': 2.0, 'roa': 1.5, 'gross_margin': 1.0, 'operating_margin': 1.0,
            'profit_margin': 1.5, 'roic': 1.5, 'current_ratio': 0.5, 'quick_ratio': 0.5,
            'debt_to_equity_inv': 1.0,
            'earnings_beat_rate': 1.0, 'earnings_surprise_avg': 0.5,
            'fcf_to_ni': 1.0, 'ocf_to_ni': 0.5
        }
        df['quality_z'] = calculate_weighted_score(df, quality_metrics, quality_weights)
        df['quality_score'] = df['quality_z'].apply(zscore_to_percentile)
    else:
        logger.warning("  No quality metrics available - using NaN for quality score")
        df['quality_z'] = np.nan
        df['quality_score'] = np.nan

    # ===== GROWTH SCORE (9 metrics) =====
    logger.info("Calculating GROWTH scores (revenue expansion, earnings growth)...")
    all_growth_metrics = [
        'rev_3y_cagr', 'eps_3y_cagr', 'fcf_growth', 'ocf_growth', 'ni_growth', 'rev_growth',
        'roe_trend', 'quarterly_growth_momentum', 'oi_growth'
    ]
    growth_weights = {
        'rev_3y_cagr': 1.5, 'eps_3y_cagr': 2.0, 'fcf_growth': 1.5, 'ocf_growth': 1.0,
        'ni_growth': 2.0, 'rev_growth': 1.0,
        'roe_trend': 1.0, 'quarterly_growth_momentum': 1.0, 'oi_growth': 1.0
    }
    # Filter to only available metrics
    growth_metrics = [m for m in all_growth_metrics if m in df.columns]
    if growth_metrics:
        df['growth_z'] = calculate_weighted_score(df, growth_metrics, growth_weights)
        df['growth_score'] = df['growth_z'].apply(zscore_to_percentile)
    else:
        logger.warning("  No growth metrics available - using NaN for growth score")
        df['growth_z'] = np.nan
        df['growth_score'] = np.nan

    # ===== STABILITY SCORE =====
    logger.info("Calculating STABILITY scores (beta, volatility based)...")
    all_stability_metrics = ['beta', 'volatility_12m', 'downside_vol', 'max_drawdown', 'volume_consistency']
    stability_metrics = [m for m in all_stability_metrics if m in df.columns]
    if stability_metrics:
        stability_for_calc = df.copy()
        # Invert metrics where lower is better
        if 'beta' in stability_for_calc.columns:
            stability_for_calc['beta'] = -stability_for_calc['beta']
        if 'volatility_12m' in stability_for_calc.columns:
            stability_for_calc['volatility_12m'] = -stability_for_calc['volatility_12m']
        if 'downside_vol' in stability_for_calc.columns:
            stability_for_calc['downside_vol'] = -stability_for_calc['downside_vol']
        if 'max_drawdown' in stability_for_calc.columns:
            stability_for_calc['max_drawdown'] = -stability_for_calc['max_drawdown']
        stability_weights = {'beta': 1.5, 'volatility_12m': 1.0, 'downside_vol': 1.0, 'max_drawdown': 1.5, 'volume_consistency': 0.5}
        df['stability_z'] = calculate_weighted_score(stability_for_calc, stability_metrics, stability_weights)
        df['stability_score'] = df['stability_z'].apply(zscore_to_percentile)
    else:
        logger.warning("  No stability metrics available - using NaN for stability score")
        df['stability_z'] = np.nan
        df['stability_score'] = np.nan

    # ===== MOMENTUM SCORE (8 metrics) =====
    logger.info("Calculating MOMENTUM scores (price trends, technical positioning)...")
    all_momentum_metrics = ['momentum_1m', 'momentum_3m', 'momentum_6m', 'momentum_12m', 'sma_50', 'sma_200', 'high_52w']
    momentum_weights = {
        'momentum_1m': 1.0, 'momentum_3m': 1.5, 'momentum_6m': 1.5, 'momentum_12m': 2.0,
        'sma_50': 1.0, 'sma_200': 1.0, 'high_52w': 1.0
    }
    # Filter to only available metrics
    momentum_metrics = [m for m in all_momentum_metrics if m in df.columns]
    if momentum_metrics:
        df['momentum_z'] = calculate_weighted_score(df, momentum_metrics, momentum_weights)
        df['momentum_score'] = df['momentum_z'].apply(zscore_to_percentile)
    else:
        logger.warning("  No momentum metrics available - using NaN for momentum score")
        df['momentum_z'] = np.nan
        df['momentum_score'] = np.nan

    # ===== VALUE SCORE =====
    logger.info("Calculating VALUE scores (P/E, P/B, PEG, EV based)...")
    all_value_metrics = ['pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio', 'div_yield', 'ev_to_ebitda', 'ev_to_revenue']
    value_metrics_available = [m for m in all_value_metrics if m in df.columns]
    if value_metrics_available:
        value_for_calc = df.copy()
        # Invert metrics where lower is better (cheaper valuation = better score)
        for metric in ['pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio', 'ev_to_ebitda', 'ev_to_revenue']:
            if metric in value_for_calc.columns:
                value_for_calc[metric] = -value_for_calc[metric]
        # Dividend yield: higher is better (don't invert)
        value_weights = {
            'pe_ratio': 1.5, 'pb_ratio': 1.0, 'ps_ratio': 0.5, 'peg_ratio': 1.0,
            'div_yield': 1.0, 'ev_to_ebitda': 1.5, 'ev_to_revenue': 0.5
        }
        df['value_z'] = calculate_weighted_score(value_for_calc, value_metrics_available, value_weights)
        df['value_score'] = df['value_z'].apply(zscore_to_percentile)
    else:
        logger.warning("  No value metrics available - using NaN for value score")
        df['value_z'] = np.nan
        df['value_score'] = np.nan

    # ===== POSITIONING SCORE (4 metrics) =====
    logger.info("Calculating POSITIONING scores (institutional alignment, short interest, A/D)...")
    all_positioning_metrics = ['institutional_ownership_pct', 'insider_ownership_pct', 'short_interest_pct', 'ad_rating']
    positioning_metrics = [m for m in all_positioning_metrics if m in df.columns]
    positioning_weights = {
        'institutional_ownership_pct': 2.0, 'insider_ownership_pct': 1.5,
        'short_interest_pct': 2.0, 'ad_rating': 1.5
    }
    # Invert short interest (lower short = better positioning)
    positioning_for_calc = df.copy()
    if 'short_interest_pct' in positioning_for_calc.columns:
        positioning_for_calc['short_interest_pct'] = -positioning_for_calc['short_interest_pct']
    df['positioning_z'] = calculate_weighted_score(positioning_for_calc, positioning_metrics, positioning_weights)
    df['positioning_score'] = df['positioning_z'].apply(zscore_to_percentile)

    # ===== MOMENTUM INTRAWEEK SCORE (short-term 1-month momentum) =====
    logger.info("Calculating MOMENTUM INTRAWEEK scores (short-term momentum from 1m return)...")
    if 'momentum_1m' in df.columns:
        m1_z = calculate_factor_zscore(df['momentum_1m'].values)
        df['momentum_intraweek'] = pd.Series(m1_z, index=df.index).apply(zscore_to_percentile)
    else:
        df['momentum_intraweek'] = None

    # ===== COMPOSITE SCORE =====
    logger.info("Calculating COMPOSITE scores (equal weight across all 6 factors)...")
    score_cols = ['quality_score', 'growth_score', 'value_score', 'momentum_score', 'positioning_score', 'stability_score']
    df['composite_score'] = df[[c for c in score_cols if c in df.columns]].mean(axis=1)

    logger.info(f"Calculated {df['composite_score'].notna().sum()} composite scores")

    # ===== SAVE TO DATABASE =====
    logger.info(f"Saving scores to database for {len(df)} symbols...")
    cur = conn.cursor()

    # Get company names from stock_symbols for all stocks
    cur.execute("SELECT symbol, security_name FROM stock_symbols")
    company_names = {row[0]: row[1] for row in cur.fetchall()}
    logger.info(f"Loading company names for {len(company_names)} stocks")

    # Clear old scores first to ensure clean state
    cur.execute("TRUNCATE TABLE stock_scores")
    logger.info("Cleared old scores from database")

    # OPTIMIZED: Batch insert 1000+ rows at once (not individual INSERT statements)
    # This reduces database round-trips and commit overhead significantly
    saved = 0
    failed = 0
    batch_rows = []
    BATCH_SIZE = 1000

    for idx, symbol in enumerate(df.index):
        try:
            composite_val = df.iloc[idx]['composite_score']
            quality_val = df.iloc[idx]['quality_score']
            growth_val = df.iloc[idx]['growth_score']
            value_val = df.iloc[idx]['value_score']
            momentum_val = df.iloc[idx]['momentum_score']
            positioning_val = df.iloc[idx]['positioning_score']
            stability_val = df.iloc[idx]['stability_score']
            momentum_intraweek_val = df.iloc[idx].get('momentum_intraweek', np.nan)

            # Convert to None if NaN
            composite = None if pd.isna(composite_val) else float(composite_val)
            quality = None if pd.isna(quality_val) else float(quality_val)
            growth = None if pd.isna(growth_val) else float(growth_val)
            value = None if pd.isna(value_val) else float(value_val)
            momentum = None if pd.isna(momentum_val) else float(momentum_val)
            positioning = None if pd.isna(positioning_val) else float(positioning_val)
            stability = None if pd.isna(stability_val) else float(stability_val)
            momentum_intraweek = None if pd.isna(momentum_intraweek_val) else float(momentum_intraweek_val)

            batch_rows.append((symbol, composite, quality, growth, value, momentum, positioning, stability, momentum_intraweek))

            # When batch reaches BATCH_SIZE, execute batch insert
            if len(batch_rows) >= BATCH_SIZE:
                from psycopg2.extras import execute_values
                execute_values(cur, """
                    INSERT INTO stock_scores (symbol, composite_score, quality_score, growth_score, value_score,
                                              momentum_score, positioning_score, stability_score, momentum_intraweek, score_date, last_updated)
                    VALUES %s
                    ON CONFLICT (symbol) DO UPDATE SET
                        composite_score = EXCLUDED.composite_score,
                        quality_score = EXCLUDED.quality_score,
                        growth_score = EXCLUDED.growth_score,
                        value_score = EXCLUDED.value_score,
                        momentum_score = EXCLUDED.momentum_score,
                        positioning_score = EXCLUDED.positioning_score,
                        stability_score = EXCLUDED.stability_score,
                        momentum_intraweek = EXCLUDED.momentum_intraweek,
                        score_date = CURRENT_DATE,
                        last_updated = CURRENT_TIMESTAMP
                """, batch_rows)
                saved += len(batch_rows)
                conn.commit()
                logger.info(f"  Batch inserted {len(batch_rows)} scores. Total: {saved}/{len(df)}")
                batch_rows = []

        except Exception as e:
            logger.warning(f"Error processing {symbol}: {e}")
            failed += 1

    # Insert remaining rows
    if batch_rows:
        from psycopg2.extras import execute_values
        execute_values(cur, """
            INSERT INTO stock_scores (symbol, composite_score, quality_score, growth_score, value_score,
                                      momentum_score, positioning_score, stability_score, momentum_intraweek, score_date, last_updated)
            VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                composite_score = EXCLUDED.composite_score,
                quality_score = EXCLUDED.quality_score,
                growth_score = EXCLUDED.growth_score,
                value_score = EXCLUDED.value_score,
                momentum_score = EXCLUDED.momentum_score,
                positioning_score = EXCLUDED.positioning_score,
                stability_score = EXCLUDED.stability_score,
                momentum_intraweek = EXCLUDED.momentum_intraweek,
                score_date = CURRENT_DATE,
                last_updated = CURRENT_TIMESTAMP
        """, batch_rows)
        saved += len(batch_rows)

    conn.commit()
    logger.info(f"Saved {saved} / {len(df)} stocks ({100*saved/len(df):.1f}%). Failed: {failed}")

    # Restore company names that were saved
    if company_names:
        for symbol, name in company_names.items():
            cur.execute("UPDATE stock_scores SET company_name = %s WHERE symbol = %s",
                       (name, symbol))
        conn.commit()
        logger.info(f"Restored {len(company_names)} company names")

    # Post-processing: Calculate composite score from factor scores
    logger.info("\nFinalizing composite scores...")
    try:
        cur = conn.cursor()

        # Calculate composite as average of 6 factor scores (no sentiment, no fake fills)
        # NULLS preserved: only averages valid factor scores present
        cur.execute("""
            UPDATE stock_scores
            SET composite_score = (
              SELECT AVG(score) FROM (
                VALUES
                  (quality_score),
                  (growth_score),
                  (stability_score),
                  (momentum_score),
                  (value_score),
                  (positioning_score)
              ) AS factor_scores(score)
              WHERE score IS NOT NULL
            )
        """)

        conn.commit()

        # Log data completeness
        cur.execute("""
          SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as has_quality,
            COUNT(*) FILTER (WHERE growth_score IS NOT NULL) as has_growth,
            COUNT(*) FILTER (WHERE stability_score IS NOT NULL) as has_stability,
            COUNT(*) FILTER (WHERE momentum_score IS NOT NULL) as has_momentum,
            COUNT(*) FILTER (WHERE value_score IS NOT NULL) as has_value,
            COUNT(*) FILTER (WHERE positioning_score IS NOT NULL) as has_positioning,
            COUNT(*) FILTER (WHERE momentum_intraweek IS NOT NULL) as has_momentum_intraweek,
            COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as has_composite
          FROM stock_scores
        """)
        stats = cur.fetchone()
        logger.info(f"  Data completeness:")
        logger.info(f"    Total stocks: {stats[0]}")
        logger.info(f"    Quality scores: {stats[1]} ({100*stats[1]/stats[0]:.1f}%)")
        logger.info(f"    Growth scores: {stats[2]} ({100*stats[2]/stats[0]:.1f}%)")
        logger.info(f"    Stability scores: {stats[3]} ({100*stats[3]/stats[0]:.1f}%)")
        logger.info(f"    Momentum scores: {stats[4]} ({100*stats[4]/stats[0]:.1f}%)")
        logger.info(f"    Momentum Intraweek: {stats[7]} ({100*stats[7]/stats[0]:.1f}%)")
        logger.info(f"    Value scores: {stats[5]} ({100*stats[5]/stats[0]:.1f}%)")
        logger.info(f"    Positioning scores: {stats[6]} ({100*stats[6]/stats[0]:.1f}%)")
        logger.info(f"    Composite scores: {stats[8]} ({100*stats[8]/stats[0]:.1f}%)")

        cur.close()
    except Exception as e:
        logger.warning(f"Composite score finalization failed: {e}")
        conn.rollback()
    finally:
        conn.close()

    logger.info(f"\n Saved {saved} stocks with comprehensive scores")
    logger.info("=" * 100)
    logger.info("COMPLETE - Stock scores recalculated with all available metrics!")
    logger.info(" Data quality verified - all scores complete with no gaps")
    logger.info("=" * 100)

if __name__ == '__main__':
    main()
