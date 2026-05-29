#!/usr/bin/env python3
"""
Load minimal seed data to unblock Phase 1 data freshness check.

⚠️  **DEVELOPMENT/DEMO USE ONLY** ⚠️
This script populates critical tables with FAKE hardcoded test data to unblock Phase 1.
DO NOT use in production — all values below are synthetic:
- Prices: base_price 400-480, ±5/±2/+1 offsets (FAKE)
- Technicals: RSI=55, MACD=1.2, ATR=2.5 (FAKE for all symbols)
- Market health: advance_decline=1.5, vix=15.5 (FAKE, always bullish)
- Economics: rates=5.25%, inflation=3.2% (FAKE)
- Analyst sentiment: all 'buy' at 450.0 (FAKE)
- Earnings: EPS estimate 5.0 (FAKE)

Used only in: .github/workflows/verify-and-init-db.yml (demo initialization)
Safe because: ON CONFLICT (symbol, date) DO NOTHING prevents overwrites from real loaders
Risk: If real loaders don't run, algo will signal on fake data (acceptable for demo)

In production, real loaders (load_stock_prices_daily.py, etc.) replace seed data.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta
from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_seed_data():
    """Load minimal test data into critical tables.

    ⚠️  DEVELOPMENT/DEMO ONLY — All data below is FAKE hardcoded values.
    Used to unblock Phase 1 during initial demo setup (verify-and-init-db.yml).
    Real loaders replace this data within hours.
    """
    logger.warning("=" * 80)
    logger.warning("⚠️  LOADING FAKE SEED DATA — DEVELOPMENT/DEMO ONLY")
    logger.warning("This is hardcoded test data to unblock Phase 1 initialization.")
    logger.warning("Real loaders will overwrite with actual market data.")
    logger.warning("DO NOT use in production.")
    logger.warning("=" * 80)

    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        return False

    try:
        cur = conn.cursor()
        today = date.today()

        # 1. Ensure stock_symbols has data
        logger.info("Loading stock_symbols...")
        cur.execute("""
            INSERT INTO stock_symbols (symbol, exchange, security_name, market_category, is_sp500)
            VALUES
                ('SPY', 'XNYS', 'SPDR S&P 500 ETF', 'ETF', false),
                ('QQQ', 'XNYS', 'PowerShares QQQ Trust', 'ETF', false),
                ('IWM', 'XNYS', 'iShares Russell 2000 ETF', 'ETF', false),
                ('AAPL', 'XNGS', 'Apple Inc', 'STOCK', true),
                ('MSFT', 'XNGS', 'Microsoft Corp', 'STOCK', true),
                ('TSLA', 'XNGS', 'Tesla Inc', 'STOCK', true),
                ('AMZN', 'XNGS', 'Amazon.com Inc', 'STOCK', true),
                ('NVDA', 'XNGS', 'NVIDIA Corp', 'STOCK', true)
            ON CONFLICT (symbol) DO NOTHING
        """)
        conn.commit()
        logger.info("✓ stock_symbols loaded")

        # 2. Populate price_daily with recent data
        logger.info("Loading price_daily...")
        symbols = ['SPY', 'QQQ', 'IWM', 'AAPL', 'MSFT', 'TSLA', 'AMZN', 'NVDA']
        for i, symbol in enumerate(symbols):
            # Add 5 days of data
            for day_offset in range(5, 0, -1):
                d = today - timedelta(days=day_offset)
                base_price = 400 + (i * 10)

                cur.execute("""
                    INSERT INTO price_daily
                    (symbol, date, open, high, low, close, volume, adj_close)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO NOTHING
                """, (
                    symbol, d,
                    base_price, base_price + 5, base_price - 2, base_price + 1,
                    1000000 + i * 100000,
                    base_price + 1
                ))
        conn.commit()
        logger.info("✓ price_daily loaded")

        # 3. Populate technical_data_daily (required for signals)
        logger.info("Loading technical_data_daily...")
        for i, symbol in enumerate(symbols):
            for day_offset in range(5, 0, -1):
                d = today - timedelta(days=day_offset)
                cur.execute("""
                    INSERT INTO technical_data_daily
                    (symbol, date, sma_50, sma_200, rsi_14, atr_14, macd, macd_signal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO NOTHING
                """, (
                    symbol, d,
                    400 + i * 10,
                    395 + i * 10,
                    55,
                    2.5,
                    1.2,
                    1.0
                ))
        conn.commit()
        logger.info("✓ technical_data_daily loaded")

        # 4. Populate market_health_daily
        logger.info("Loading market_health_daily...")
        for day_offset in range(5, 0, -1):
            d = today - timedelta(days=day_offset)
            cur.execute("""
                INSERT INTO market_health_daily
                (date, advance_decline_ratio, breadth_momentum_10d, distribution_days_4w,
                 vix_level, market_stage)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO NOTHING
            """, (
                d, 1.5, 0.65, 0,
                15.5, 2
            ))
        conn.commit()
        logger.info("✓ market_health_daily loaded")

        # 5. Populate economic_data
        logger.info("Loading economic_data...")
        cur.execute("""
            INSERT INTO economic_data
            (date, interest_rate, inflation_rate, gdp_growth, unemployment_rate,
             fed_rate, yield_10y, credit_spread)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO NOTHING
        """, (
            today, 5.25, 3.2, 2.1, 3.9,
            5.33, 4.15, 125
        ))
        conn.commit()
        logger.info("✓ economic_data loaded")

        # 6. Populate buy_sell_daily with test signals
        logger.info("Loading buy_sell_daily...")
        for symbol in symbols:
            cur.execute("""
                INSERT INTO buy_sell_daily
                (symbol, date, signal_type, signal_reason, strength_score)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date, signal_type) DO NOTHING
            """, (
                symbol, today, 'buy', 'test_signal', 75
            ))
        conn.commit()
        logger.info("✓ buy_sell_daily loaded")

        # 7. Populate stock_scores
        logger.info("Loading stock_scores...")
        for symbol in symbols:
            cur.execute("""
                INSERT INTO stock_scores
                (symbol, overall_score, momentum_score, quality_score,
                 value_score, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    momentum_score = EXCLUDED.momentum_score,
                    quality_score = EXCLUDED.quality_score,
                    value_score = EXCLUDED.value_score,
                    updated_at = EXCLUDED.updated_at
            """, (
                symbol, 75, 70, 80, 65, today
            ))
        conn.commit()
        logger.info("✓ stock_scores loaded")

        # 8. Populate signal_quality_scores
        logger.info("Loading signal_quality_scores...")
        for symbol in symbols:
            cur.execute("""
                INSERT INTO signal_quality_scores
                (symbol, date, quality_score, data_completeness)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO NOTHING
            """, (
                symbol, today, 75, 90
            ))
        conn.commit()
        logger.info("✓ signal_quality_scores loaded")

        # 9. Populate analyst_sentiment_analysis (critical table)
        logger.info("Loading analyst_sentiment_analysis...")
        for symbol in symbols[:4]:  # Load for first 4 symbols
            cur.execute("""
                INSERT INTO analyst_sentiment_analysis
                (symbol, analyst_consensus, price_target, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    analyst_consensus = EXCLUDED.analyst_consensus,
                    price_target = EXCLUDED.price_target,
                    updated_at = EXCLUDED.updated_at
            """, (
                symbol, 'buy', 450.0, today
            ))
        conn.commit()
        logger.info("✓ analyst_sentiment_analysis loaded")

        # 10. Populate earnings_calendar (critical table)
        logger.info("Loading earnings_calendar...")
        next_week = today + timedelta(days=7)
        for symbol in symbols[:4]:  # Load for first 4 symbols
            cur.execute("""
                INSERT INTO earnings_calendar
                (symbol, earnings_date, eps_estimate, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (symbol, earnings_date) DO NOTHING
            """, (
                symbol, next_week, 5.0, today
            ))
        conn.commit()
        logger.info("✓ earnings_calendar loaded")

        logger.info("\n✅ All seed data loaded successfully!")
        logger.info("Phase 1 should now pass - critical tables have recent data")

        cur.close()
        return True

    except Exception as e:
        logger.error(f"Error loading seed data: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    success = load_seed_data()
    sys.exit(0 if success else 1)
