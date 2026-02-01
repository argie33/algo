#!/usr/bin/env python3
"""
Stock Scores Loader v2.0 FIXED - Direct save without ON CONFLICT issues
"""
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from scipy import stats
from scipy.stats import zscore
from sklearn.ensemble import RandomForestRegressor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_HOST = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'
DB_PORT = 5432
DB_USER = 'stocks'
DB_PASSWORD = 'bed0elAn'
DB_NAME = 'stocks'

def get_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, connect_timeout=30)

def zscore_to_percentile(z_score):
    if np.isnan(z_score) or np.isinf(z_score):
        return None
    z_capped = np.clip(z_score, -3, 3)
    return float(stats.norm.cdf(z_capped) * 100)

def calculate_factor_zscore(values, invert=False):
    if np.all(np.isnan(values)):
        return np.full(len(values), np.nan)
    with np.errstate(invalid='ignore'):
        mean_val = np.nanmean(values)
        std_val = np.nanstd(values)
        if std_val == 0 or np.isnan(std_val):
            return np.full(len(values), np.nan)
        z_scores = (values - mean_val) / std_val
        if invert:
            z_scores = -z_scores
        return z_scores

def load_all_stock_data(conn):
    logger.info("Loading all stock data...")
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT s.symbol FROM stock_symbols s
        WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
        AND (s.etf = 'N' OR s.etf IS NULL)
        AND s.symbol NOT ILIKE '%$%'
    """)
    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f"Found {len(symbols)} stocks")

    df = pd.DataFrame(index=symbols)
    df.index.name = 'symbol'

    # Load all metrics - simplified for speed
    cur.execute("SELECT ticker, return_on_equity_pct, revenue_growth_pct, earnings_growth_pct FROM key_metrics")
    metrics_df = pd.DataFrame(cur.fetchall(), columns=['symbol', 'roe', 'revenue_growth', 'eps_growth']).set_index('symbol')
    df = df.join(metrics_df, how='left')

    cur.execute("SELECT symbol, volatility_12m, beta FROM stability_metrics ORDER BY date DESC LIMIT 5002")
    stab_df = pd.DataFrame(cur.fetchall(), columns=['symbol', 'volatility', 'beta']).drop_duplicates(subset=['symbol']).set_index('symbol')
    df = df.join(stab_df, how='left')

    cur.execute("SELECT symbol, institutional_ownership_pct, insider_ownership_pct, short_interest_pct FROM positioning_metrics")
    pos_df = pd.DataFrame(cur.fetchall(), columns=['symbol', 'inst_own', 'insider_own', 'short_int']).set_index('symbol')
    df = df.join(pos_df, how='left')

    cur.execute("SELECT symbol, ad_rating FROM stock_scores WHERE ad_rating IS NOT NULL")
    ad_df = pd.DataFrame(cur.fetchall(), columns=['symbol', 'ad_rating']).set_index('symbol')
    df = df.join(ad_df, how='left')

    cur.close()
    return df

def main():
    logger.info("=" * 80)
    logger.info("Stock Scores Loader v2.0 FIXED - Z-Score Based Scoring")
    logger.info("=" * 80)

    conn = get_connection()
    df = load_all_stock_data(conn)

    # Convert all factor columns to numeric (handle mixed types)
    logger.info("Converting columns to numeric types...")
    df['roe'] = pd.to_numeric(df['roe'], errors='coerce')
    df['revenue_growth'] = pd.to_numeric(df['revenue_growth'], errors='coerce')
    df['eps_growth'] = pd.to_numeric(df['eps_growth'], errors='coerce')
    df['volatility'] = pd.to_numeric(df['volatility'], errors='coerce')
    df['inst_own'] = pd.to_numeric(df['inst_own'], errors='coerce')

    # Calculate Z-scores for each factor
    logger.info("Calculating Z-scores...")
    df['quality_z'] = calculate_factor_zscore(df['roe'].values)
    df['growth_z'] = calculate_factor_zscore(df['revenue_growth'].values)
    df['value_z'] = calculate_factor_zscore(1.0 / (df['roe'].fillna(1).values + 0.1))
    df['momentum_z'] = calculate_factor_zscore(df['eps_growth'].values)
    df['stability_z'] = calculate_factor_zscore(df['volatility'].values, invert=True)
    df['positioning_z'] = calculate_factor_zscore(df['inst_own'].values)

    # Convert to percentiles
    for col in ['quality_z', 'growth_z', 'value_z', 'momentum_z', 'positioning_z', 'stability_z']:
        df[col.replace('_z', '_score')] = df[col].apply(zscore_to_percentile)

    # Calculate composite
    score_cols = ['quality_score', 'growth_score', 'value_score', 'momentum_score', 'positioning_score', 'stability_score']
    df['composite_score'] = df[[c for c in score_cols if c in df.columns]].mean(axis=1)

    logger.info(f"Calculated {df['composite_score'].notna().sum()} composite scores")

    # SAVE with INSERT...ON CONFLICT to avoid deadlocks
    logger.info("Saving to database...")
    cur = conn.cursor()

    saved = 0
    for idx, symbol in enumerate(df.index):
        try:
            # Get row data by position to avoid Series issues
            composite_val = df.iloc[idx]['composite_score']
            quality_val = df.iloc[idx]['quality_score']
            growth_val = df.iloc[idx]['growth_score']
            value_val = df.iloc[idx]['value_score']
            momentum_val = df.iloc[idx]['momentum_score']
            positioning_val = df.iloc[idx]['positioning_score']
            stability_val = df.iloc[idx]['stability_score']
            ad_rating_val = df.iloc[idx]['ad_rating'] if 'ad_rating' in df.columns else None

            # Convert to None if NaN, otherwise to float
            composite = None if pd.isna(composite_val) else float(composite_val)
            quality = None if pd.isna(quality_val) else float(quality_val)
            growth = None if pd.isna(growth_val) else float(growth_val)
            value = None if pd.isna(value_val) else float(value_val)
            momentum = None if pd.isna(momentum_val) else float(momentum_val)
            positioning = None if pd.isna(positioning_val) else float(positioning_val)
            stability = None if pd.isna(stability_val) else float(stability_val)
            ad_rating = None if pd.isna(ad_rating_val) else float(ad_rating_val)

            # INSERT with ON CONFLICT UPDATE (no deadlock issue)
            cur.execute("""
                INSERT INTO stock_scores (symbol, composite_score, quality_score, growth_score, value_score,
                                          momentum_score, positioning_score, stability_score, ad_rating, score_date, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, CURRENT_TIMESTAMP)
                ON CONFLICT (symbol) DO UPDATE SET
                    composite_score = EXCLUDED.composite_score,
                    quality_score = EXCLUDED.quality_score,
                    growth_score = EXCLUDED.growth_score,
                    value_score = EXCLUDED.value_score,
                    momentum_score = EXCLUDED.momentum_score,
                    positioning_score = EXCLUDED.positioning_score,
                    stability_score = EXCLUDED.stability_score,
                    ad_rating = EXCLUDED.ad_rating,
                    score_date = CURRENT_DATE,
                    last_updated = CURRENT_TIMESTAMP
            """, (symbol, composite, quality, growth, value, momentum, positioning, stability, ad_rating))

            saved += 1
            if saved % 500 == 0:
                conn.commit()
                logger.info(f"  Saved {saved} scores...")
        except Exception as e:
            logger.warning(f"Error for {symbol}: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"\n✅ Saved {saved} stocks with composite scores")
    logger.info("=" * 80)
    logger.info("COMPLETE!")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
