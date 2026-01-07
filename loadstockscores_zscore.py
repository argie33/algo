#!/usr/bin/env python3
"""
INDUSTRY-STANDARD Stock Scores Loader - Z-Score Normalization
Following financial industry best practices:
- Z-score normalization on all metrics
- Outlier handling (±3 sigma capping)
- Percentile conversion via standard normal CDF
- Proper missing data handling
"""

import os
import sys
import psycopg2
import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database config
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'bed0elAn')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    """Create database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def zscore_normalize(value, distribution):
    """
    Convert a single value to z-score, cap at ±3 sigma, convert to 0-100 percentile scale.

    INDUSTRY STANDARD APPROACH:
    1. Calculate mean and std dev on valid data (distribution)
    2. Convert value: z = (value - mean) / std_dev
    3. Cap outliers: z = max(-3, min(3, z))
    4. Convert to percentile via standard normal CDF: percentile = Φ(z) * 100
    5. Result: 0-100 scale with proper handling of extreme values
    """
    if pd.isna(value):
        return None  # No data

    valid_values = distribution.dropna()

    if len(valid_values) == 0:
        return None  # No distribution data

    if len(valid_values) == 1:
        return 50.0  # Only one value in distribution, neutral score

    mean = valid_values.mean()
    std_dev = valid_values.std()

    if std_dev == 0:
        return 50.0  # All values are identical, neutral score

    # Calculate z-score for this value
    z_score = (value - mean) / std_dev

    # Cap at ±3 sigma (industry standard for outlier handling)
    z_score_capped = np.clip(z_score, -3, 3)

    # Convert to percentile using standard normal CDF
    # Φ(z) gives percentile in 0-1 range, multiply by 100 for 0-100 scale
    percentile = stats.norm.cdf(z_score_capped) * 100

    return percentile

def calculate_factor_score(factor_values, weights=None):
    """
    Calculate a composite factor score from multiple z-score normalized components.

    Handles:
    - Variable number of inputs (dynamic weighting)
    - Missing data (skipped, not default to 50)
    - Proper averaging of normalized scores
    """
    valid_indices = ~factor_values.isna()

    if not valid_indices.any():
        return None  # No data

    valid_scores = factor_values[valid_indices]

    if weights is None:
        # Equal weighting for available metrics
        return valid_scores.mean()
    else:
        # Weighted average for available metrics
        valid_weights = weights[valid_indices]
        if valid_weights.sum() == 0:
            return valid_scores.mean()
        return (valid_scores * valid_weights).sum() / valid_weights.sum()

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    logger.info("🚀 INDUSTRY-STANDARD Stock Scores Loader - Z-SCORE NORMALIZATION")

    try:
        # STEP 1: Load ALL metrics at once
        logger.info("📊 Loading ALL metrics (batch)...")

        # Momentum metrics
        cur.execute("SELECT symbol, momentum_12m, momentum_6m, momentum_3m FROM momentum_metrics ORDER BY symbol")
        momentum_data = cur.fetchall()
        momentum_df = pd.DataFrame(momentum_data, columns=['symbol', 'momentum_12m', 'momentum_6m', 'momentum_3m'])
        momentum_df = momentum_df.drop_duplicates(subset=['symbol'], keep='first')
        logger.info(f"✅ Loaded {len(momentum_df)} momentum records")

        # Quality metrics - EXPANDED to include margin metrics for revenue/earnings quality
        cur.execute("SELECT symbol, return_on_equity_pct, return_on_assets_pct, fcf_to_net_income, eps_growth_stability, gross_margin_pct, operating_margin_pct, profit_margin_pct FROM quality_metrics ORDER BY symbol")
        quality_data = cur.fetchall()
        quality_df = pd.DataFrame(quality_data, columns=['symbol', 'roe_pct', 'roa_pct', 'fcf_ni', 'eps_stability', 'gross_margin', 'operating_margin', 'profit_margin'])
        logger.info(f"✅ Loaded {len(quality_df)} quality records (EXPANDED: added margin metrics)")

        # Growth metrics
        cur.execute("SELECT symbol, sustainable_growth_rate, fcf_growth_yoy, ocf_growth_yoy FROM growth_metrics ORDER BY symbol")
        growth_data = cur.fetchall()
        growth_df = pd.DataFrame(growth_data, columns=['symbol', 'sustainable_growth', 'fcf_growth', 'ocf_growth'])
        logger.info(f"✅ Loaded {len(growth_df)} growth records")

        # Value metrics
        cur.execute("SELECT symbol, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm, peg_ratio FROM value_metrics ORDER BY symbol")
        value_data = cur.fetchall()
        value_df = pd.DataFrame(value_data, columns=['symbol', 'trailing_pe', 'forward_pe', 'pb_ratio', 'ps_ratio', 'peg_ratio'])
        logger.info(f"✅ Loaded {len(value_df)} value records")

        # Stability metrics
        cur.execute("SELECT symbol, volatility_12m, downside_volatility, max_drawdown_52w, beta FROM stability_metrics ORDER BY symbol")
        stability_data = cur.fetchall()
        stability_df = pd.DataFrame(stability_data, columns=['symbol', 'volatility', 'downside_vol', 'max_drawdown', 'beta'])
        logger.info(f"✅ Loaded {len(stability_df)} stability records")

        # Positioning metrics
        cur.execute("SELECT symbol, institutional_ownership_pct, insider_ownership_pct, short_interest_pct FROM positioning_metrics ORDER BY symbol")
        positioning_data = cur.fetchall()
        positioning_df = pd.DataFrame(positioning_data, columns=['symbol', 'inst_ownership', 'insider_ownership', 'short_interest'])
        logger.info(f"✅ Loaded {len(positioning_df)} positioning records")

        # Analyst sentiment
        cur.execute("SELECT symbol, bullish_count FROM analyst_sentiment_analysis WHERE date_recorded = (SELECT MAX(date_recorded) FROM analyst_sentiment_analysis) ORDER BY symbol")
        analyst_data = cur.fetchall()
        analyst_df = pd.DataFrame(analyst_data, columns=['symbol', 'bullish_count'])
        logger.info(f"✅ Loaded {len(analyst_df)} analyst records")

        # Get all symbols
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"📊 Processing {len(symbols)} symbols with z-score normalization")

        # STEP 2: Pre-calculate z-score statistics for all metrics
        logger.info("📈 Pre-calculating z-score statistics (mean/std for all metrics)...")

        # For inverse metrics (lower is better), we invert them first
        # Replace zeros with NaN to avoid division by zero
        value_df['pe_inverse'] = value_df['trailing_pe'].replace(0, np.nan).apply(lambda x: 1.0/x if pd.notna(x) else np.nan)
        stability_df['vol_inverse'] = stability_df['volatility'].replace(0, np.nan).apply(lambda x: 1.0/x if pd.notna(x) else np.nan)

        logger.info("✅ Z-score statistics ready")

        # STEP 3: Clear old scores
        cur.execute("DELETE FROM stock_scores")
        conn.commit()
        logger.info("🗑️  Cleared old stock_scores")

        # STEP 4: Calculate scores with z-score normalization
        logger.info("⚡ Computing z-score normalized scores...")
        insert_count = 0
        batch_size = 500
        batch_inserts = []

        for idx, symbol in enumerate(symbols, 1):
            # Get all metrics for this symbol
            momentum = momentum_df[momentum_df['symbol'] == symbol]
            quality = quality_df[quality_df['symbol'] == symbol]
            growth = growth_df[growth_df['symbol'] == symbol]
            value = value_df[value_df['symbol'] == symbol]
            stability = stability_df[stability_df['symbol'] == symbol]
            positioning = positioning_df[positioning_df['symbol'] == symbol]
            analyst = analyst_df[analyst_df['symbol'] == symbol]

            # MOMENTUM SCORE: Z-score normalize 3-month, 6-month, 12-month returns
            momentum_components = []
            if not momentum.empty:
                if pd.notna(momentum['momentum_3m'].iloc[0]):
                    m3_zscore = zscore_normalize(momentum['momentum_3m'].iloc[0], momentum_df['momentum_3m'])
                    if m3_zscore is not None:
                        momentum_components.append(m3_zscore)
                if pd.notna(momentum['momentum_6m'].iloc[0]):
                    m6_zscore = zscore_normalize(momentum['momentum_6m'].iloc[0], momentum_df['momentum_6m'])
                    if m6_zscore is not None:
                        momentum_components.append(m6_zscore)
                if pd.notna(momentum['momentum_12m'].iloc[0]):
                    m12_zscore = zscore_normalize(momentum['momentum_12m'].iloc[0], momentum_df['momentum_12m'])
                    if m12_zscore is not None:
                        momentum_components.append(m12_zscore)

            momentum_score = np.mean(momentum_components) if momentum_components else None

            # QUALITY SCORE: Z-score normalize 7 components (EXPANDED)
            # Original 4: ROE, ROA, FCF/NI, EPS stability
            # ADDED 3: Gross Margin (revenue profitability), Operating Margin (earnings quality), Profit Margin (net profitability)
            quality_components = []
            if not quality.empty:
                if pd.notna(quality['roe_pct'].iloc[0]):
                    roe_zscore = zscore_normalize(quality['roe_pct'].iloc[0], quality_df['roe_pct'])
                    if roe_zscore is not None:
                        quality_components.append(roe_zscore)
                if pd.notna(quality['roa_pct'].iloc[0]):
                    roa_zscore = zscore_normalize(quality['roa_pct'].iloc[0], quality_df['roa_pct'])
                    if roa_zscore is not None:
                        quality_components.append(roa_zscore)
                if pd.notna(quality['fcf_ni'].iloc[0]):
                    fcf_zscore = zscore_normalize(quality['fcf_ni'].iloc[0], quality_df['fcf_ni'])
                    if fcf_zscore is not None:
                        quality_components.append(fcf_zscore)
                if pd.notna(quality['eps_stability'].iloc[0]):
                    eps_zscore = zscore_normalize(quality['eps_stability'].iloc[0], quality_df['eps_stability'])
                    if eps_zscore is not None:
                        quality_components.append(eps_zscore)
                # NEW: Gross margin (revenue profitability)
                if pd.notna(quality['gross_margin'].iloc[0]):
                    gm_zscore = zscore_normalize(quality['gross_margin'].iloc[0], quality_df['gross_margin'])
                    if gm_zscore is not None:
                        quality_components.append(gm_zscore)
                # NEW: Operating margin (earnings quality)
                if pd.notna(quality['operating_margin'].iloc[0]):
                    om_zscore = zscore_normalize(quality['operating_margin'].iloc[0], quality_df['operating_margin'])
                    if om_zscore is not None:
                        quality_components.append(om_zscore)
                # NEW: Profit margin (net profitability)
                if pd.notna(quality['profit_margin'].iloc[0]):
                    pm_zscore = zscore_normalize(quality['profit_margin'].iloc[0], quality_df['profit_margin'])
                    if pm_zscore is not None:
                        quality_components.append(pm_zscore)

            quality_score = np.mean(quality_components) if quality_components else None

            # GROWTH SCORE: Z-score normalize sustainable growth, FCF growth, OCF growth
            growth_components = []
            if not growth.empty:
                if pd.notna(growth['sustainable_growth'].iloc[0]):
                    sg_zscore = zscore_normalize(growth['sustainable_growth'].iloc[0], growth_df['sustainable_growth'])
                    if sg_zscore is not None:
                        growth_components.append(sg_zscore)
                if pd.notna(growth['fcf_growth'].iloc[0]):
                    fcf_g_zscore = zscore_normalize(growth['fcf_growth'].iloc[0], growth_df['fcf_growth'])
                    if fcf_g_zscore is not None:
                        growth_components.append(fcf_g_zscore)
                if pd.notna(growth['ocf_growth'].iloc[0]):
                    ocf_g_zscore = zscore_normalize(growth['ocf_growth'].iloc[0], growth_df['ocf_growth'])
                    if ocf_g_zscore is not None:
                        growth_components.append(ocf_g_zscore)

            growth_score = np.mean(growth_components) if growth_components else None

            # VALUE SCORE: Z-score normalize inverse P/E, inverse vol P/B, P/S, PEG
            value_components = []
            if not value.empty:
                if pd.notna(value['pe_inverse'].iloc[0]):
                    pe_zscore = zscore_normalize(value['pe_inverse'].iloc[0], value_df['pe_inverse'])  # Inverted
                    if pe_zscore is not None:
                        value_components.append(pe_zscore)
                if pd.notna(value['pb_ratio'].iloc[0]):
                    pb_zscore = zscore_normalize(value['pb_ratio'].iloc[0], value_df['pb_ratio'])
                    if pb_zscore is not None:
                        value_components.append(pb_zscore)
                if pd.notna(value['ps_ratio'].iloc[0]):
                    ps_zscore = zscore_normalize(value['ps_ratio'].iloc[0], value_df['ps_ratio'])
                    if ps_zscore is not None:
                        value_components.append(ps_zscore)
                if pd.notna(value['peg_ratio'].iloc[0]):
                    peg_zscore = zscore_normalize(value['peg_ratio'].iloc[0], value_df['peg_ratio'])
                    if peg_zscore is not None:
                        value_components.append(peg_zscore)

            value_score = np.mean(value_components) if value_components else None

            # STABILITY SCORE: Z-score normalize volatility (inverse), downside vol (inverse), drawdown, beta
            stability_components = []
            if not stability.empty:
                if pd.notna(stability['vol_inverse'].iloc[0]):
                    vol_zscore = zscore_normalize(stability['vol_inverse'].iloc[0], stability_df['vol_inverse'])  # Inverted
                    if vol_zscore is not None:
                        stability_components.append(vol_zscore)
                if pd.notna(stability['downside_vol'].iloc[0]):
                    dv_zscore = zscore_normalize(stability['downside_vol'].iloc[0], stability_df['downside_vol'])
                    if dv_zscore is not None:
                        stability_components.append(dv_zscore)
                if pd.notna(stability['max_drawdown'].iloc[0]):
                    dd_zscore = zscore_normalize(stability['max_drawdown'].iloc[0], stability_df['max_drawdown'])
                    if dd_zscore is not None:
                        stability_components.append(dd_zscore)
                if pd.notna(stability['beta'].iloc[0]) and stability['beta'].iloc[0] > 0:
                    beta_zscore = zscore_normalize(stability['beta'].iloc[0], stability_df['beta'])
                    if beta_zscore is not None:
                        stability_components.append(beta_zscore)

            stability_score = np.mean(stability_components) if stability_components else None

            # POSITIONING SCORE: Z-score normalize institutional ownership, insider ownership, short interest (inverse)
            positioning_components = []
            if not positioning.empty:
                if pd.notna(positioning['inst_ownership'].iloc[0]):
                    io_zscore = zscore_normalize(positioning['inst_ownership'].iloc[0], positioning_df['inst_ownership'])
                    if io_zscore is not None:
                        positioning_components.append(io_zscore)
                if pd.notna(positioning['insider_ownership'].iloc[0]):
                    insider_zscore = zscore_normalize(positioning['insider_ownership'].iloc[0], positioning_df['insider_ownership'])
                    if insider_zscore is not None:
                        positioning_components.append(insider_zscore)
                if pd.notna(positioning['short_interest'].iloc[0]) and positioning['short_interest'].iloc[0] != 0:
                    # Short interest: lower is better (inverted) - skip if zero to avoid division error
                    si_inverse = 1.0 / positioning['short_interest'].iloc[0]
                    si_dist_inverse = 1.0 / positioning_df['short_interest'].replace(0, np.nan)
                    si_zscore = zscore_normalize(si_inverse, si_dist_inverse)
                    if si_zscore is not None:
                        positioning_components.append(si_zscore)

            positioning_score = np.mean(positioning_components) if positioning_components else None

            # SENTIMENT SCORE: Z-score normalize bullish count
            sentiment_score = None
            if not analyst.empty and pd.notna(analyst['bullish_count'].iloc[0]):
                sentiment_score = zscore_normalize(analyst['bullish_count'].iloc[0], analyst_df['bullish_count'])

            # COMPOSITE SCORE: Weighted average of 6 factors (Z-SCORE NORMALIZED)
            # Industry standard weights: Momentum 22%, Growth 20%, Quality 16%, Value 15%, Stability 15%, Positioning 12%
            factor_scores = []
            factor_weights = []

            # Only include factors that have valid scores
            if momentum_score is not None:
                factor_scores.append(momentum_score)
                factor_weights.append(0.22)
            if growth_score is not None:
                factor_scores.append(growth_score)
                factor_weights.append(0.20)
            if quality_score is not None:
                factor_scores.append(quality_score)
                factor_weights.append(0.16)
            if value_score is not None:
                factor_scores.append(value_score)
                factor_weights.append(0.15)
            if stability_score is not None:
                factor_scores.append(stability_score)
                factor_weights.append(0.15)
            if positioning_score is not None:
                factor_scores.append(positioning_score)
                factor_weights.append(0.12)

            if factor_scores:
                # Normalize weights to sum to 1
                factor_weights = np.array(factor_weights) / np.sum(factor_weights)
                factor_scores = np.array(factor_scores)
                composite_score = (factor_scores * factor_weights).sum()
                composite_score = max(0, min(100, composite_score))  # Clamp to 0-100
            else:
                composite_score = 50.0  # Default if no factors available

            batch_inserts.append((
                symbol,
                float(composite_score),
                float(momentum_score) if momentum_score is not None else None,
                float(growth_score) if growth_score is not None else None,
                float(quality_score) if quality_score is not None else None,
                float(value_score) if value_score is not None else None,
                float(positioning_score) if positioning_score is not None else None,
                float(sentiment_score) if sentiment_score is not None else None,
                float(stability_score) if stability_score is not None else None,
                datetime.now().date()
            ))

            if len(batch_inserts) >= batch_size or idx == len(symbols):
                # Batch upsert
                cur.executemany("""
                    INSERT INTO stock_scores
                    (symbol, composite_score, momentum_score, growth_score, quality_score,
                     value_score, positioning_score, sentiment_score, stability_score, score_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        composite_score = EXCLUDED.composite_score,
                        momentum_score = EXCLUDED.momentum_score,
                        growth_score = EXCLUDED.growth_score,
                        quality_score = EXCLUDED.quality_score,
                        value_score = EXCLUDED.value_score,
                        positioning_score = EXCLUDED.positioning_score,
                        sentiment_score = EXCLUDED.sentiment_score,
                        stability_score = EXCLUDED.stability_score,
                        score_date = EXCLUDED.score_date
                """, batch_inserts)
                conn.commit()
                insert_count += len(batch_inserts)
                logger.info(f"✅ Updated {insert_count}/{len(symbols)} scores with z-score normalization ({idx}/{len(symbols)} symbols)")
                batch_inserts = []

        logger.info(f"✅ Stock scores loader COMPLETED - {insert_count} stocks updated with INDUSTRY-STANDARD Z-SCORE NORMALIZATION!")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
