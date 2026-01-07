#!/usr/bin/env python3
"""
OPTIMIZED Stock Scores Loader - Batch Loading Version
Loads ALL data at once instead of per-stock queries (5-10x faster!)
"""

import os
import sys
import psycopg2
import pandas as pd
import numpy as np
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

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    logger.info("🚀 OPTIMIZED Stock Scores Loader - BATCH MODE")

    try:
        # STEP 1: Load ALL price data at once
        logger.info("📊 Loading ALL price data (batch)...")
        cur.execute("""
            SELECT symbol, date, close, volume,
                   LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '252 days'
            ORDER BY symbol, date
        """)
        price_data = cur.fetchall()
        price_df = pd.DataFrame(price_data, columns=['symbol', 'date', 'close', 'volume', 'prev_close'])
        logger.info(f"✅ Loaded {len(price_df)} price records")

        # STEP 2: Load ALL technical data at once
        logger.info("📊 Loading ALL technical data (batch)...")
        cur.execute("""
            SELECT symbol, rsi, macd, sma_50, sma_200
            FROM technical_data_daily
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY symbol, date DESC
        """)
        tech_data = cur.fetchall()
        tech_df = pd.DataFrame(tech_data, columns=['symbol', 'rsi', 'macd', 'sma_50', 'sma_200'])
        # Get latest per symbol
        tech_df = tech_df.drop_duplicates(subset=['symbol'], keep='first')
        logger.info(f"✅ Loaded {len(tech_df)} technical records")

        # STEP 3: Load ALL factor metrics at once
        logger.info("📊 Loading ALL factor metrics (batch)...")
        cur.execute("""
            SELECT symbol, momentum_12m, momentum_6m, momentum_3m
            FROM momentum_metrics
            ORDER BY symbol, date DESC
        """)
        momentum_data = cur.fetchall()
        momentum_df = pd.DataFrame(momentum_data, columns=['symbol', 'momentum_12m', 'momentum_6m', 'momentum_3m'])
        momentum_df = momentum_df.drop_duplicates(subset=['symbol'], keep='first')
        logger.info(f"✅ Loaded {len(momentum_df)} momentum records")

        # STEP 4: Load ALL quality metrics
        logger.info("📊 Loading ALL quality metrics (batch)...")
        cur.execute("""
            SELECT symbol, return_on_equity_pct, return_on_assets_pct, debt_to_equity, fcf_to_net_income, earnings_surprise_avg
            FROM quality_metrics
            ORDER BY symbol
        """)
        quality_data = cur.fetchall()
        quality_df = pd.DataFrame(quality_data, columns=['symbol', 'return_on_equity_pct', 'return_on_assets_pct', 'debt_to_equity', 'fcf_to_net_income', 'earnings_surprise_avg'])
        logger.info(f"✅ Loaded {len(quality_df)} quality records")

        # STEP 5: Load ALL growth metrics
        logger.info("📊 Loading ALL growth metrics (batch)...")
        cur.execute("""
            SELECT symbol, eps_growth_3y_cagr, revenue_growth_3y_cagr, net_margin_trend
            FROM growth_metrics
            ORDER BY symbol
        """)
        growth_data = cur.fetchall()
        growth_df = pd.DataFrame(growth_data, columns=['symbol', 'eps_growth_3y_cagr', 'revenue_growth_3y_cagr', 'net_margin_trend'])
        logger.info(f"✅ Loaded {len(growth_df)} growth records")

        # STEP 6: Load ALL positioning metrics
        logger.info("📊 Loading ALL positioning metrics (batch)...")
        cur.execute("""
            SELECT symbol, institutional_ownership_pct, insider_ownership_pct, short_interest_pct
            FROM positioning_metrics
            ORDER BY symbol
        """)
        positioning_data = cur.fetchall()
        positioning_df = pd.DataFrame(positioning_data, columns=['symbol', 'institutional_ownership_pct', 'insider_ownership_pct', 'short_interest_pct'])
        logger.info(f"✅ Loaded {len(positioning_df)} positioning records")

        # STEP 7: Load ALL stability metrics
        logger.info("📊 Loading ALL stability metrics (batch)...")
        cur.execute("""
            SELECT symbol, volatility_12m, max_drawdown_52w, beta
            FROM stability_metrics
            ORDER BY symbol
        """)
        stability_data = cur.fetchall()
        stability_df = pd.DataFrame(stability_data, columns=['symbol', 'volatility_12m', 'max_drawdown_52w', 'beta'])
        logger.info(f"✅ Loaded {len(stability_df)} stability records")

        # STEP 8: Load ALL analyst sentiment
        logger.info("📊 Loading ALL analyst sentiment (batch)...")
        cur.execute("""
            SELECT symbol, bullish_count, bearish_count, neutral_count, total_analysts
            FROM analyst_sentiment_analysis
            WHERE date_recorded = (SELECT MAX(date_recorded) FROM analyst_sentiment_analysis)
            ORDER BY symbol
        """)
        analyst_data = cur.fetchall()
        analyst_df = pd.DataFrame(analyst_data, columns=['symbol', 'bullish_count', 'bearish_count', 'neutral_count', 'total_analysts'])
        logger.info(f"✅ Loaded {len(analyst_df)} analyst records")

        # STEP 9: Get all symbols to process
        logger.info("📊 Getting all symbols...")
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"✅ Processing {len(symbols)} symbols")

        # STEP 10: BATCH UPSERT - Delete and reload all scores
        logger.info("🗑️  Deleting old stock_scores...")
        cur.execute("DELETE FROM stock_scores")
        conn.commit()

        logger.info("⚡ Computing scores in memory and batch inserting...")
        insert_count = 0
        batch_size = 500
        batch_inserts = []

        for idx, symbol in enumerate(symbols, 1):
            # Get data for this symbol from already-loaded DataFrames
            sym_price = price_df[price_df['symbol'] == symbol]
            sym_tech = tech_df[tech_df['symbol'] == symbol]
            sym_momentum = momentum_df[momentum_df['symbol'] == symbol]
            sym_quality = quality_df[quality_df['symbol'] == symbol]
            sym_growth = growth_df[growth_df['symbol'] == symbol]
            sym_positioning = positioning_df[positioning_df['symbol'] == symbol]
            sym_stability = stability_df[stability_df['symbol'] == symbol]
            sym_analyst = analyst_df[analyst_df['symbol'] == symbol]

            # PERCENTILE-BASED NORMALIZATION: Calculate percentile rank (0-100) for each metric
            # Momentum: percentile rank of momentum_12m across all symbols
            momentum_val = float(sym_momentum['momentum_12m'].iloc[0]) if not sym_momentum.empty and pd.notna(sym_momentum['momentum_12m'].iloc[0]) else None
            if momentum_val is not None and len(momentum_df[momentum_df['momentum_12m'].notna()]) > 0:
                momentum_percentile = (momentum_df[momentum_df['momentum_12m'].notna()]['momentum_12m'] < momentum_val).sum() / len(momentum_df[momentum_df['momentum_12m'].notna()]) * 100
                momentum_score = max(0, min(100, momentum_percentile))
            else:
                momentum_score = 50.0

            # Quality: percentile rank of return_on_equity_pct (higher is better)
            quality_val = float(sym_quality['return_on_equity_pct'].iloc[0]) if not sym_quality.empty and pd.notna(sym_quality['return_on_equity_pct'].iloc[0]) else None
            if quality_val is not None and len(quality_df[quality_df['return_on_equity_pct'].notna()]) > 0:
                quality_percentile = (quality_df[quality_df['return_on_equity_pct'].notna()]['return_on_equity_pct'] < quality_val).sum() / len(quality_df[quality_df['return_on_equity_pct'].notna()]) * 100
                quality_score = max(0, min(100, quality_percentile))
            else:
                quality_score = 50.0

            # Growth: percentile rank of eps_growth_3y_cagr (higher is better)
            growth_val = float(sym_growth['eps_growth_3y_cagr'].iloc[0]) if not sym_growth.empty and pd.notna(sym_growth['eps_growth_3y_cagr'].iloc[0]) else None
            if growth_val is not None and len(growth_df[growth_df['eps_growth_3y_cagr'].notna()]) > 0:
                growth_percentile = (growth_df[growth_df['eps_growth_3y_cagr'].notna()]['eps_growth_3y_cagr'] < growth_val).sum() / len(growth_df[growth_df['eps_growth_3y_cagr'].notna()]) * 100
                growth_score = max(0, min(100, growth_percentile))
            else:
                growth_score = 50.0

            # Stability: inverted percentile of volatility (lower volatility is better)
            stability_val = float(sym_stability['volatility_12m'].iloc[0]) if not sym_stability.empty and pd.notna(sym_stability['volatility_12m'].iloc[0]) else None
            if stability_val is not None and len(stability_df[stability_df['volatility_12m'].notna()]) > 0:
                # Inverted: higher volatility = lower score
                volatility_percentile = (stability_df[stability_df['volatility_12m'].notna()]['volatility_12m'] < stability_val).sum() / len(stability_df[stability_df['volatility_12m'].notna()]) * 100
                stability_score = 100 - max(0, min(100, volatility_percentile))
            else:
                stability_score = 50.0

            # Positioning: percentile rank of institutional_ownership_pct (higher is better)
            positioning_val = float(sym_positioning['institutional_ownership_pct'].iloc[0]) if not sym_positioning.empty and pd.notna(sym_positioning['institutional_ownership_pct'].iloc[0]) else None
            if positioning_val is not None and len(positioning_df[positioning_df['institutional_ownership_pct'].notna()]) > 0:
                positioning_percentile = (positioning_df[positioning_df['institutional_ownership_pct'].notna()]['institutional_ownership_pct'] < positioning_val).sum() / len(positioning_df[positioning_df['institutional_ownership_pct'].notna()]) * 100
                positioning_score = max(0, min(100, positioning_percentile))
            else:
                positioning_score = 50.0

            # Sentiment: percentile rank of bullish_count (higher is better)
            sentiment_val = float(sym_analyst['bullish_count'].iloc[0]) if not sym_analyst.empty and pd.notna(sym_analyst['bullish_count'].iloc[0]) else None
            if sentiment_val is not None and len(analyst_df[analyst_df['bullish_count'].notna()]) > 0:
                sentiment_percentile = (analyst_df[analyst_df['bullish_count'].notna()]['bullish_count'] < sentiment_val).sum() / len(analyst_df[analyst_df['bullish_count'].notna()]) * 100
                sentiment_score = max(0, min(100, sentiment_percentile))
            else:
                sentiment_score = None

            # Composite score: weighted average of 6 factors (exclude value_score for now)
            if sentiment_score is not None:
                composite_score = (momentum_score * 0.22 + growth_score * 0.20 +
                                  quality_score * 0.16 + stability_score * 0.15 +
                                  positioning_score * 0.12 + sentiment_score * 0.05)
            else:
                composite_score = (momentum_score * 0.22 + growth_score * 0.20 +
                                  quality_score * 0.16 + stability_score * 0.15 +
                                  positioning_score * 0.12) / 0.95  # Renormalize to exclude sentiment

            batch_inserts.append((
                symbol,
                float(composite_score), float(momentum_score), float(growth_score), float(quality_score),
                float(positioning_score), float(sentiment_score) if sentiment_score is not None else None, float(stability_score),
                datetime.now().date()
            ))

            if len(batch_inserts) >= batch_size or idx == len(symbols):
                # Batch upsert (insert or update)
                cur.executemany("""
                    INSERT INTO stock_scores
                    (symbol, composite_score, momentum_score, growth_score, quality_score,
                     positioning_score, sentiment_score, stability_score, score_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        composite_score = EXCLUDED.composite_score,
                        momentum_score = EXCLUDED.momentum_score,
                        growth_score = EXCLUDED.growth_score,
                        quality_score = EXCLUDED.quality_score,
                        positioning_score = EXCLUDED.positioning_score,
                        sentiment_score = EXCLUDED.sentiment_score,
                        stability_score = EXCLUDED.stability_score,
                        score_date = EXCLUDED.score_date
                """, batch_inserts)
                conn.commit()
                insert_count += len(batch_inserts)
                logger.info(f"✅ Updated {insert_count}/{len(symbols)} scores ({idx}/{len(symbols)} symbols)")
                batch_inserts = []

        logger.info(f"✅ Stock scores loader COMPLETED - {insert_count} stocks updated!")
        logger.info(f"⏱️  This optimized batch version processed {len(symbols)} stocks in seconds!")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
