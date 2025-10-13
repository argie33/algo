#!/usr/bin/env python3
# Updated: 2025-10-13 - Buy/Sell Daily Signal Loader
# Updated: 2025-10-04 19:45 - Added transaction rollback for cascade failure prevention
# Updated: 2025-10-03 22:02 - Trigger deployment after null check fixes
# Updated: 2025-10-03 - Fixed SQL parameter formatting in swing metrics calculation
# Filter stocks only from stock_symbols (etf IS NULL OR etf != 'Y')
# Populate buy_sell_daily.sata_score, stage_number, mansfield_rs for all signals
# Fixed: Escaped % character in SQL comment to prevent psycopg2 parameter mixing error
import json
import logging
import os
import sys
from datetime import datetime

import boto3
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extensions
import requests
from psycopg2.extras import RealDictCursor

# Register numpy type adapters for psycopg2
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuyselldaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# ========================================
# Pine Script Breakout Trend Follower Configuration
# ========================================
USE_MA_FILTER = True  # Enable/disable MA filter (set to False to trade all breakouts)
MA_TYPE = 'SMA'  # 'SMA' or 'EMA' for trend filter
MA_LENGTH = 50  # MA period for filtering (default 50, Pine Script allows customization)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
if not FRED_API_KEY:
    logging.warning(
        "FRED_API_KEY environment variable is not set. Risk-free rate will be set to 0."
    )

# Check if we're in AWS (has DB_SECRET_ARN)
if os.environ.get("DB_SECRET_ARN"):
    # AWS mode - use Secrets Manager
    SECRET_ARN = os.environ["DB_SECRET_ARN"]
    sm_client = boto3.client("secretsmanager")
    secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
    creds = json.loads(secret_resp["SecretString"])

    DB_USER = creds["username"]
    DB_PASSWORD = creds["password"]
    DB_HOST = creds["host"]
    DB_PORT = int(creds.get("port", 5432))
    DB_NAME = creds["dbname"]
else:
    # Local mode - use environment variables
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_USER = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
    DB_NAME = os.environ.get("DB_NAME", "stocks")
    logging.info(f"Using local database: {DB_HOST}:{DB_PORT}/{DB_NAME}")


def get_db_connection():
    # Set statement timeout to 2 minutes (120000 ms) for complex queries
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options="-c statement_timeout=120000",
    )
    return conn


###############################################################################
# 1) DATABASE FUNCTIONS
###############################################################################
def get_symbols_from_db(limit=None):
    """Get symbols that have price and technical data (required for buy/sell signals)."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Optimized query: Use EXISTS subqueries instead of expensive JOINs + GROUP BY
        # This avoids materializing large join tables and expensive COUNT operations
        q = """
            SELECT s.symbol
            FROM stock_symbols s
            WHERE s.exchange IN ('NASDAQ', 'N', 'A', 'P')
              AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
              AND EXISTS (
                  SELECT 1 FROM price_daily p
                  WHERE p.symbol = s.symbol
                  LIMIT 1
              )
              AND EXISTS (
                  SELECT 1 FROM technical_data_daily t
                  WHERE t.symbol = s.symbol
                  LIMIT 1
              )
              AND (
                  SELECT COUNT(DISTINCT date)
                  FROM price_daily
                  WHERE symbol = s.symbol
              ) >= 60
            ORDER BY s.symbol
        """
        if limit:
            q += " LIMIT %s"
            cur.execute(q, (limit,))
        else:
            cur.execute(q)
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def create_buy_sell_table(cur):
    cur.execute("DROP TABLE IF EXISTS buy_sell_daily;")
    cur.execute(
        """
      CREATE TABLE buy_sell_daily (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(20)    NOT NULL,
        timeframe    VARCHAR(10)    NOT NULL,
        date         DATE           NOT NULL,
        open         REAL,
        high         REAL,
        low          REAL,
        close        REAL,
        volume       BIGINT,
        signal       VARCHAR(10),
        buylevel     REAL,
        stoplevel    REAL,
        selllevel    REAL,
        inposition   BOOLEAN,
        -- Swing Trading Metrics (O'Neill/Minervini)
        target_price REAL,
        current_price REAL,
        risk_reward_ratio NUMERIC(6,2),
        market_stage VARCHAR(30),
        pct_from_ema_21 NUMERIC(6,2),
        pct_from_sma_50 NUMERIC(6,2),
        pct_from_sma_200 NUMERIC(6,2),
        volume_ratio NUMERIC(6,2),
        volume_analysis VARCHAR(30),
        entry_quality_score INTEGER,
        profit_target_20pct REAL,
        profit_target_25pct REAL,
        current_gain_loss_pct NUMERIC(6,2),
        risk_pct NUMERIC(6,2),
        position_size_recommendation NUMERIC(18,2),
        passes_minervini_template BOOLEAN DEFAULT FALSE,
        rsi NUMERIC(6,2),
        adx NUMERIC(6,2),
        atr NUMERIC(10,4),
        daily_range_pct NUMERIC(6,2),
        volatility_profile VARCHAR(20),
        -- Stage Analysis Technical Attributes (SATA)
        sata_score INTEGER,              -- 0-10 SATA scoring
        stage_number INTEGER,            -- 1, 2, 3, or 4
        stage_confidence INTEGER,        -- 0-100 confidence in stage
        substage VARCHAR(50),            -- Stage 1 - Early/Mid/Late
        mansfield_rs NUMERIC(10,2),      -- Mansfield Relative Strength
        -- Pine Script Breakout Trend Follower Fields
        ma_filter_value REAL,            -- MA filter level (SMA/EMA)
        ma_filter_type VARCHAR(10),      -- 'SMA' or 'EMA'
        ma_filter_period INTEGER,        -- MA period (default 50)
        pivot_high_value REAL,           -- Last pivot high value
        pivot_low_value REAL,            -- Last pivot low value
        -- Base Pattern Detection Fields
        base_pivot_price REAL,           -- Resistance level to break
        base_support_price REAL,         -- Support level of base
        base_pattern VARCHAR(50),        -- VCP, Cup, Flat Base, etc.
        base_depth_pct NUMERIC(6,2),     -- Depth of base from high
        base_duration_days INTEGER,      -- Days in base
        base_tightness_score INTEGER,    -- 0-100, based on ATR contraction
        is_base_on_base BOOLEAN,         -- Building on prior base
        base_quality_score INTEGER,      -- Overall base quality 0-100
        UNIQUE(symbol, timeframe, date)
      );
    """
    )

    # Create base_levels tracking table
    cur.execute("DROP TABLE IF EXISTS base_levels CASCADE;")
    cur.execute("""
      CREATE TABLE base_levels (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        timeframe VARCHAR(10) NOT NULL,
        base_start_date DATE NOT NULL,
        base_end_date DATE,               -- NULL if still forming
        base_support REAL NOT NULL,       -- Low of base
        base_resistance REAL NOT NULL,    -- Pivot/high of base
        base_depth_pct NUMERIC(6,2),      -- (High - Low) / High * 100
        base_duration_weeks INTEGER,      -- Duration in weeks
        base_pattern VARCHAR(50),         -- VCP, Cup & Handle, Flat Base, etc.
        base_tightness NUMERIC(6,2),      -- ATR contraction ratio
        is_base_on_base BOOLEAN DEFAULT FALSE,
        prior_base_id INTEGER REFERENCES base_levels(id),
        breakout_date DATE,               -- When/if it broke out
        breakout_volume_ratio NUMERIC(6,2), -- Volume on breakout
        quality_score INTEGER,            -- 0-100 overall quality
        stage_at_base VARCHAR(30),        -- Stage when base formed
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, timeframe, base_start_date)
      );

      CREATE INDEX idx_base_levels_symbol ON base_levels(symbol);
      CREATE INDEX idx_base_levels_dates ON base_levels(base_start_date, base_end_date);
      CREATE INDEX idx_base_levels_quality ON base_levels(quality_score DESC);
    """
    )
    # Create stage function if not exists
    cur.execute("""
    CREATE OR REPLACE FUNCTION calculate_weinstein_stage(
        current_price NUMERIC,
        sma_50_current NUMERIC,
        sma_200_current NUMERIC,
        sma_50_prev NUMERIC,
        sma_200_prev NUMERIC,
        adx_value NUMERIC,
        volume_current BIGINT,
        volume_avg_50 BIGINT
    ) RETURNS TEXT AS $$
    DECLARE
        sma_50_slope NUMERIC;
        sma_200_slope NUMERIC;
        sma_200_flat_threshold NUMERIC := 0.05;  -- 200 SMA moving < 0.05% = flat/basing
        volume_ratio NUMERIC;
        stage TEXT;
    BEGIN
        -- Calculate slopes (rate of change)
        sma_50_slope := (sma_50_current - sma_50_prev) / NULLIF(sma_50_prev, 0) * 100;
        sma_200_slope := (sma_200_current - sma_200_prev) / NULLIF(sma_200_prev, 0) * 100;
        volume_ratio := volume_current::NUMERIC / NULLIF(volume_avg_50, 1);

        -- STAGE 2: ADVANCING (Uptrend with momentum)
        -- Strong bullish criteria - all must align
        IF (current_price > sma_50_current AND
            current_price > sma_200_current AND
            sma_50_current > sma_200_current AND
            sma_50_slope > 0.1 AND                    -- 50 SMA rising
            sma_200_slope > 0 AND                     -- 200 SMA rising
            COALESCE(adx_value, 0) > 25) THEN         -- Strong trend
            stage := 'Stage 2 - Advancing';

        -- STAGE 4: DECLINING (Downtrend with momentum)
        -- Strong bearish criteria - all must align
        ELSIF (current_price < sma_50_current AND
               current_price < sma_200_current AND
               sma_50_current < sma_200_current AND
               sma_50_slope < -0.1 AND                -- 50 SMA falling
               COALESCE(adx_value, 0) > 20) THEN      -- Trend strength
            stage := 'Stage 4 - Declining';

        -- STAGE 3: TOPPING (Distribution - losing momentum after uptrend)
        -- Price still above 200 but trend weakening
        ELSIF (current_price > sma_200_current AND
               (sma_50_slope < 0 OR ABS(sma_50_slope) < 0.1) AND  -- 50 SMA rolling over or flat
               COALESCE(adx_value, 0) < 25 AND                     -- Trend weakening
               sma_50_current > sma_200_current) THEN              -- Still in bullish structure
            stage := 'Stage 3 - Topping';

        -- STAGE 1: BASING (Consolidation/Accumulation)
        -- Key: 200 SMA flattening out, price consolidating
        -- This is where base patterns form (cup, flat base, VCP, etc.)
        ELSIF (ABS(sma_200_slope) < sma_200_flat_threshold AND      -- 200 SMA flat = base forming
               COALESCE(adx_value, 0) < 25 AND                       -- Low trend strength = consolidation
               current_price > sma_200_current * 0.85) THEN          -- Within 15% of 200 SMA
            stage := 'Stage 1 - Basing';

        -- STAGE 1: BASING (Recovery from Stage 4)
        -- Catching turn from downtrend to base
        ELSIF (current_price > sma_50_current AND                    -- Price recovering above 50 SMA
               sma_50_slope > -0.1 AND                               -- 50 SMA starting to flatten
               ABS(sma_200_slope) < sma_200_flat_threshold AND       -- 200 SMA flattening
               COALESCE(adx_value, 0) < 25) THEN                     -- Trend dying out
            stage := 'Stage 1 - Basing';

        -- DEFAULT: Treat ambiguous cases as Stage 1 (safer)
        -- Price consolidating, unclear trend direction
        ELSE
            stage := 'Stage 1 - Basing';
        END IF;

        RETURN stage;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    -- =========================================================================
    -- SATA Score Calculator: Stage Analysis Technical Attributes (0-10)
    -- Based on stageanalysis.com methodology
    -- =========================================================================
    CREATE OR REPLACE FUNCTION calculate_sata_score(
        current_price NUMERIC,
        sma_20 NUMERIC,
        sma_50 NUMERIC,
        sma_150 NUMERIC,
        sma_200 NUMERIC,
        sma_20_prev NUMERIC,
        sma_50_prev NUMERIC,
        high_52week NUMERIC,
        volume_current BIGINT,
        volume_avg_50 BIGINT,
        adx_value NUMERIC,
        mansfield_rs NUMERIC DEFAULT NULL  -- To be implemented
    ) RETURNS INTEGER AS $$
    DECLARE
        sata_score INTEGER := 0;
        sma_20_slope NUMERIC;
        sma_50_slope NUMERIC;
        pct_from_52w_high NUMERIC;
    BEGIN
        -- Calculate slopes for momentum
        sma_20_slope := ((sma_20 - sma_20_prev) / NULLIF(sma_20_prev, 0)) * 100;
        sma_50_slope := ((sma_50 - sma_50_prev) / NULLIF(sma_50_prev, 0)) * 100;
        pct_from_52w_high := ((current_price - high_52week) / NULLIF(high_52week, 0)) * 100;

        -- Component 1: Breakout/Breakdown (near 52-week high = breakout potential)
        -- Green if within 5% of 52-week high
        IF pct_from_52w_high >= -5 THEN
            sata_score := sata_score + 1;
        END IF;

        -- Components 2-5: Price vs Moving Averages (4 points total)
        -- Component 2: Price > 20 SMA (short-term trend)
        IF current_price > COALESCE(sma_20, 0) THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 3: Price > 50 SMA (intermediate trend)
        IF current_price > COALESCE(sma_50, 0) THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 4: Price > 150 SMA (long-term positioning)
        IF current_price > COALESCE(sma_150, 0) THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 5: Price > 200 SMA (major trend)
        IF current_price > COALESCE(sma_200, 0) THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 6: Mansfield Relative Strength
        -- Green if outperforming benchmark (RS > 0)
        IF COALESCE(mansfield_rs, 0) > 0 THEN
            sata_score := sata_score + 1;
        END IF;

        -- Components 7-8: Momentum (2 points)
        -- Component 7: 20 SMA slope (short-term momentum)
        IF sma_20_slope > 0.1 THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 8: 50 SMA slope (intermediate momentum)
        IF sma_50_slope > 0.1 THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 9: Volume (above average = accumulation)
        IF volume_current > COALESCE(volume_avg_50, 1) THEN
            sata_score := sata_score + 1;
        END IF;

        -- Component 10: Overhead Resistance (within 15% of 52w high = low resistance)
        IF pct_from_52w_high >= -15 THEN
            sata_score := sata_score + 1;
        END IF;

        RETURN sata_score;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;

    -- =========================================================================
    -- Enhanced Stage Calculator with SATA, Confidence, and Substage
    -- Returns composite record with all stage attributes
    -- =========================================================================
    CREATE OR REPLACE FUNCTION calculate_enhanced_stage(
        current_price NUMERIC,
        sma_20 NUMERIC,
        sma_50 NUMERIC,
        sma_150 NUMERIC,
        sma_200 NUMERIC,
        sma_20_prev NUMERIC,
        sma_50_prev NUMERIC,
        sma_200_prev NUMERIC,
        adx_value NUMERIC,
        volume_current BIGINT,
        volume_avg_50 BIGINT,
        atr_value NUMERIC,
        daily_range_pct NUMERIC,
        high_52week NUMERIC,
        sector VARCHAR DEFAULT 'Unknown',
        rsi_value NUMERIC DEFAULT NULL,
        mansfield_rs NUMERIC DEFAULT NULL
    ) RETURNS TABLE(
        stage TEXT,
        confidence INTEGER,
        substage TEXT,
        sata_score INTEGER
    ) AS $$
    DECLARE
        v_stage TEXT;
        v_confidence INTEGER := 50;
        v_substage TEXT;
        v_sata INTEGER := 0;
        sma_50_slope NUMERIC;
        sma_200_slope NUMERIC;
        volume_ratio NUMERIC;
    BEGIN
        -- Calculate slopes
        sma_50_slope := ((sma_50 - sma_50_prev) / NULLIF(sma_50_prev, 0)) * 100;
        sma_200_slope := ((sma_200 - sma_200_prev) / NULLIF(sma_200_prev, 0)) * 100;
        volume_ratio := volume_current::NUMERIC / NULLIF(volume_avg_50, 1);

        -- Determine stage using existing logic
        v_stage := calculate_weinstein_stage(
            current_price, sma_50, sma_200, sma_50_prev, sma_200_prev,
            adx_value, volume_current, volume_avg_50
        );

        -- Calculate SATA score using comprehensive calculate_sata_score function
        v_sata := calculate_sata_score(
            current_price,
            sma_20,
            sma_50,
            sma_150,
            sma_200,
            sma_20_prev,
            sma_50_prev,
            high_52week,
            volume_current,
            volume_avg_50,
            adx_value,
            mansfield_rs
        );

        -- Determine confidence based on alignment of indicators
        IF v_stage = 'Stage 2 - Advancing' THEN
            v_confidence := 60;
            IF sma_50_slope > 0.2 THEN v_confidence := v_confidence + 10; END IF;
            IF sma_200_slope > 0.1 THEN v_confidence := v_confidence + 10; END IF;
            IF COALESCE(adx_value, 0) > 30 THEN v_confidence := v_confidence + 10; END IF;
            IF volume_ratio > 1.2 THEN v_confidence := v_confidence + 10; END IF;

            -- Determine substage
            IF v_sata >= 9 AND COALESCE(adx_value, 0) > 35 THEN
                v_substage := 'Stage 2 - Early';
                v_confidence := LEAST(v_confidence + 5, 100);
            ELSIF v_sata >= 7 AND COALESCE(adx_value, 0) > 25 THEN
                v_substage := 'Stage 2 - Mid';
            ELSE
                v_substage := 'Stage 2 - Late';
                v_confidence := v_confidence - 10;
            END IF;

        ELSIF v_stage = 'Stage 4 - Declining' THEN
            v_confidence := 55;
            IF sma_50_slope < -0.2 THEN v_confidence := v_confidence + 10; END IF;
            IF COALESCE(adx_value, 0) > 25 THEN v_confidence := v_confidence + 10; END IF;

            IF v_sata <= 2 AND COALESCE(adx_value, 0) > 30 THEN
                v_substage := 'Stage 4 - Early';
            ELSIF v_sata <= 4 THEN
                v_substage := 'Stage 4 - Mid';
            ELSE
                v_substage := 'Stage 4 - Late';
                v_confidence := v_confidence - 10;
            END IF;

        ELSIF v_stage = 'Stage 3 - Topping' THEN
            v_confidence := 50;
            IF sma_50_slope < -0.1 THEN v_confidence := v_confidence + 10; END IF;
            IF COALESCE(rsi_value, 50) > 70 THEN v_confidence := v_confidence + 10; END IF;

            IF v_sata >= 7 AND sma_50_slope >= 0 THEN
                v_substage := 'Stage 3 - Early';
            ELSIF v_sata >= 5 THEN
                v_substage := 'Stage 3 - Mid';
            ELSE
                v_substage := 'Stage 3 - Late';
            END IF;

        ELSE  -- Stage 1 - Basing
            v_confidence := 45;
            IF ABS(sma_200_slope) < 0.05 THEN v_confidence := v_confidence + 10; END IF;
            IF COALESCE(adx_value, 0) < 20 THEN v_confidence := v_confidence + 10; END IF;
            IF atr_value IS NOT NULL AND daily_range_pct < 2.0 THEN
                v_confidence := v_confidence + 10;
            END IF;

            IF v_sata >= 5 AND sma_50_slope > 0 THEN
                v_substage := 'Stage 1 - Late';
                v_confidence := v_confidence + 10;
            ELSIF v_sata >= 3 THEN
                v_substage := 'Stage 1 - Mid';
            ELSE
                v_substage := 'Stage 1 - Early';
            END IF;
        END IF;

        -- Ensure confidence is in valid range
        v_confidence := GREATEST(0, LEAST(100, v_confidence));

        RETURN QUERY SELECT v_stage, v_confidence, v_substage, v_sata;
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)


def insert_symbol_results(cur, symbol, timeframe, df, ma_type='SMA', ma_length=50):
    insert_q = """
      INSERT INTO buy_sell_daily (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition,
        ma_filter_value, ma_filter_type, ma_filter_period,
        pivot_high_value, pivot_low_value
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO UPDATE SET
        signal = EXCLUDED.signal,
        buylevel = EXCLUDED.buylevel,
        stoplevel = EXCLUDED.stoplevel,
        inposition = EXCLUDED.inposition,
        ma_filter_value = EXCLUDED.ma_filter_value,
        ma_filter_type = EXCLUDED.ma_filter_type,
        ma_filter_period = EXCLUDED.ma_filter_period,
        pivot_high_value = EXCLUDED.pivot_high_value,
        pivot_low_value = EXCLUDED.pivot_low_value;
    """
    inserted = 0
    for idx, row in df.iterrows():
        try:
            # Check for NaNs or missing values
            vals = [
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                row.get("Signal"),
                row.get("buyLevel"),
                row.get("stopLevel"),
                row.get("inPosition"),
            ]
            if any(pd.isnull(v) for v in vals):
                logging.warning(
                    f"Skipping row {idx} for {symbol} {timeframe} due to NaN: {vals}"
                )
                continue

            # Get MA filter value (may be NaN for early rows)
            ma_filter_val = row.get("ma_filter")
            ma_filter_val = float(ma_filter_val) if pd.notna(ma_filter_val) else None

            # Get pivot values
            pivot_high_val = row.get("LastPH")
            pivot_high_val = float(pivot_high_val) if pd.notna(pivot_high_val) else None
            pivot_low_val = row.get("LastPL")
            pivot_low_val = float(pivot_low_val) if pd.notna(pivot_low_val) else None

            cur.execute(
                insert_q,
                (
                    symbol,
                    timeframe,
                    row["date"].date(),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                    row["Signal"],
                    float(row["buyLevel"]),
                    float(row["stopLevel"]),
                    bool(row["inPosition"]),
                    ma_filter_val,
                    ma_type,
                    ma_length,
                    pivot_high_val,
                    pivot_low_val,
                ),
            )
            inserted += 1
        except Exception as e:
            logging.error(
                f"Insert failed for {symbol} {timeframe} row {idx}: {e} | row={row}"
            )
    logging.info(f"Inserted {inserted} rows for {symbol} {timeframe}")


def update_swing_metrics_for_symbol(cur, symbol, timeframe='Daily'):
    """
    Calculate and update swing trading metrics for all recent records of a symbol.
    Uses SQL to fetch technical data and calculate O'Neill/Minervini metrics.
    """
    try:
        # Get the table name
        table_name = f"buy_sell_{timeframe.lower()}"
        tech_table = f"technical_data_{timeframe.lower()}"
        price_table = f"price_{timeframe.lower()}"

        logging.info(f"Updating swing metrics for {symbol} {timeframe}")

        # Update all swing metrics in one efficient SQL statement
        # Use f-strings for table names, psycopg2 parameters for values
        update_sql = f"""
        WITH signal_data AS (
            SELECT
                bsd.symbol, bsd.date, bsd.signal, bsd.buylevel, bsd.stoplevel,
                bsd.close as current_price, bsd.open, bsd.high, bsd.low,
                bsd.volume, bsd.inposition
            FROM {table_name} bsd
            WHERE bsd.symbol = %s AND bsd.timeframe = %s
        ),
        technical_data AS (
            SELECT
                td.symbol, td.date::date as date,
                td.sma_20, td.sma_50, td.sma_150, td.sma_200,
                td.ema_21, td.rsi, td.adx, td.atr,
                td.mansfield_rs,
                LAG(td.sma_20, 5) OVER (ORDER BY td.date) as sma_20_prev,
                LAG(td.sma_50, 5) OVER (ORDER BY td.date) as sma_50_prev,
                LAG(td.sma_200, 10) OVER (ORDER BY td.date) as sma_200_prev
            FROM {tech_table} td
            WHERE td.symbol = %s
        ),
        volume_data AS (
            SELECT
                pd.symbol, pd.date,
                AVG(pd.volume) OVER (
                    ORDER BY pd.date
                    ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) as volume_avg_50
            FROM {price_table} pd
            WHERE pd.symbol = %s
        ),
        high_52week_data AS (
            SELECT
                pd.symbol, pd.date,
                MAX(pd.high) OVER (
                    ORDER BY pd.date
                    ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                ) as high_52week
            FROM {price_table} pd
            WHERE pd.symbol = %s
        ),
        stage_calc AS (
            SELECT
                sd.symbol, sd.date,
                sd.current_price, sd.open, sd.high, sd.low, sd.volume, sd.inposition,
                sd.signal, sd.buylevel, sd.stoplevel,
                td.sma_20, td.sma_50, td.sma_150, td.sma_200, td.sma_20_prev, td.sma_50_prev, td.sma_200_prev,
                td.ema_21, td.rsi, td.adx, td.atr, td.mansfield_rs,
                vd.volume_avg_50,
                hd.high_52week,
                es.stage, es.confidence, es.substage, es.sata_score
            FROM signal_data sd
            JOIN technical_data td ON sd.symbol = td.symbol AND sd.date = td.date
            JOIN volume_data vd ON sd.symbol = vd.symbol AND sd.date = vd.date
            JOIN high_52week_data hd ON sd.symbol = hd.symbol AND sd.date = hd.date
            CROSS JOIN LATERAL calculate_enhanced_stage(
                sd.current_price::NUMERIC,
                td.sma_20::NUMERIC,
                td.sma_50::NUMERIC,
                td.sma_150::NUMERIC,
                td.sma_200::NUMERIC,
                td.sma_20_prev::NUMERIC,
                td.sma_50_prev::NUMERIC,
                td.sma_200_prev::NUMERIC,
                td.adx::NUMERIC,
                sd.volume,
                vd.volume_avg_50::BIGINT,
                td.atr::NUMERIC,
                ((sd.high - sd.low) / NULLIF(sd.low, 0) * 100)::NUMERIC,
                hd.high_52week::NUMERIC,
                'Unknown',
                td.rsi::NUMERIC,
                td.mansfield_rs::NUMERIC
            ) es
        ),
        stage_data AS (
            SELECT * FROM stage_calc
        ),
        calculated_metrics AS (
            SELECT
                stg.symbol, stg.date,
                -- Sell level (opposite of buy)
                CASE WHEN stg.signal = 'SELL' THEN stg.buylevel ELSE NULL END as selllevel,

                -- Target prices
                CASE
                    WHEN stg.signal = 'BUY' AND stg.buylevel IS NOT NULL THEN stg.buylevel * 1.25
                    WHEN stg.signal = 'SELL' AND stg.buylevel IS NOT NULL THEN stg.buylevel * 0.85
                    ELSE NULL
                END as target_price,

                stg.current_price,

                -- Risk/Reward ratio
                CASE
                    WHEN stg.signal = 'BUY' AND stg.buylevel IS NOT NULL AND stg.stoplevel IS NOT NULL
                    THEN ROUND((((stg.buylevel * 1.25) - stg.buylevel) / NULLIF((stg.buylevel - stg.stoplevel), 0))::NUMERIC, 2)
                    WHEN stg.signal = 'SELL' AND stg.buylevel IS NOT NULL AND stg.stoplevel IS NOT NULL
                    THEN ROUND((((stg.buylevel - (stg.buylevel * 0.85))) / NULLIF((stg.stoplevel - stg.buylevel), 0))::NUMERIC, 2)
                    ELSE NULL
                END as risk_reward_ratio,

                -- Market stage (from pre-calculated stage_data)
                stg.stage as market_stage,

                -- Stage confidence score (from pre-calculated stage_data)
                stg.confidence as stage_confidence,

                -- Substage (from pre-calculated stage_data)
                stg.substage,

                -- SATA Score (from pre-calculated stage_data)
                stg.sata_score,

                -- Stage Number (extract from stage text: "Stage 2 - Advancing" -> 2)
                CAST(SUBSTRING(stg.stage FROM 'Stage ([0-9])') AS INTEGER) as stage_number,

                -- Mansfield RS from technical data
                stg.mansfield_rs,

                -- Distance from MAs
                ROUND(((stg.current_price - stg.ema_21) / NULLIF(stg.ema_21, 0) * 100)::NUMERIC, 2) as pct_from_ema_21,
                ROUND(((stg.current_price - stg.sma_50) / NULLIF(stg.sma_50, 0) * 100)::NUMERIC, 2) as pct_from_sma_50,
                ROUND(((stg.current_price - stg.sma_200) / NULLIF(stg.sma_200, 0) * 100)::NUMERIC, 2) as pct_from_sma_200,

                -- Volume analysis (standardized labels)
                ROUND((stg.volume::NUMERIC / NULLIF(stg.volume_avg_50, 1))::NUMERIC, 2) as volume_ratio,
                CASE
                    WHEN (stg.volume::NUMERIC / NULLIF(stg.volume_avg_50, 1)) >= 2.0 THEN 'Very High'
                    WHEN (stg.volume::NUMERIC / NULLIF(stg.volume_avg_50, 1)) >= 1.5 THEN 'High'
                    WHEN (stg.volume::NUMERIC / NULLIF(stg.volume_avg_50, 1)) >= 0.9 THEN 'Average'
                    ELSE 'Low'
                END as volume_analysis,

                -- Entry quality score
                (
                    CASE WHEN stg.stage = 'Stage 2 - Advancing' THEN 40 ELSE 0 END +
                    CASE WHEN ABS((stg.current_price - stg.ema_21) / NULLIF(stg.ema_21, 0) * 100) <= 2 THEN 20 ELSE 0 END +
                    CASE WHEN (stg.volume::NUMERIC / NULLIF(stg.volume_avg_50, 1)) >= 1.5 THEN 20 ELSE 0 END +
                    CASE WHEN stg.rsi BETWEEN 40 AND 70 THEN 20 ELSE 0 END
                )::INTEGER as entry_quality_score,

                -- Profit targets (O'Neill/Minervini: 20-25%% profit targets)
                CASE WHEN stg.buylevel IS NOT NULL THEN (stg.buylevel * 1.20)::REAL ELSE NULL END as profit_target_20pct,
                CASE WHEN stg.buylevel IS NOT NULL THEN (stg.buylevel * 1.25)::REAL ELSE NULL END as profit_target_25pct,

                -- Current gain/loss
                CASE
                    WHEN stg.inposition = TRUE AND stg.buylevel IS NOT NULL
                    THEN ROUND(((stg.current_price - stg.buylevel) / NULLIF(stg.buylevel, 0) * 100)::NUMERIC, 2)
                    ELSE NULL
                END as current_gain_loss_pct,

                -- Risk %%
                CASE
                    WHEN stg.buylevel IS NOT NULL AND stg.stoplevel IS NOT NULL
                    THEN ROUND(((stg.buylevel - stg.stoplevel) / NULLIF(stg.buylevel, 0) * 100)::NUMERIC, 2)
                    ELSE NULL
                END as risk_pct,

                -- Position size
                CASE
                    WHEN stg.buylevel IS NOT NULL AND stg.stoplevel IS NOT NULL
                    THEN ROUND((1000.0 / NULLIF((stg.buylevel - stg.stoplevel), 0))::NUMERIC, 2)
                    ELSE NULL
                END as position_size_recommendation,

                -- Minervini template
                CASE
                    WHEN stg.current_price > stg.sma_50 AND stg.current_price > stg.sma_150 AND
                         stg.current_price > stg.sma_200 AND stg.sma_50 > stg.sma_150 AND
                         stg.sma_150 > stg.sma_200 AND
                         ((stg.current_price - stg.sma_200) / NULLIF(stg.sma_200, 0) * 100) BETWEEN 0 AND 30
                    THEN TRUE
                    ELSE FALSE
                END as passes_minervini_template,

                -- Technical indicators
                stg.rsi::NUMERIC(6,2), stg.adx::NUMERIC(6,2), stg.atr::NUMERIC(10,4),

                -- Daily range
                ROUND(((stg.high - stg.low) / NULLIF(stg.low, 0) * 100)::NUMERIC, 2) as daily_range_pct,

                -- Volatility profile based on ATR and daily range
                CASE
                    WHEN stg.atr IS NOT NULL AND ((stg.high - stg.low) / NULLIF(stg.low, 0) * 100) > 3.0 THEN 'high'
                    WHEN stg.atr IS NOT NULL AND ((stg.high - stg.low) / NULLIF(stg.low, 0) * 100) < 1.5 THEN 'low'
                    ELSE 'medium'
                END as volatility_profile

            FROM stage_data stg
        )
        UPDATE {table_name} bsd SET
            selllevel = cm.selllevel,
            target_price = cm.target_price,
            current_price = cm.current_price,
            risk_reward_ratio = cm.risk_reward_ratio,
            market_stage = cm.market_stage,
            stage_confidence = cm.stage_confidence,
            substage = cm.substage,
            sata_score = cm.sata_score,
            stage_number = cm.stage_number,
            mansfield_rs = cm.mansfield_rs,
            pct_from_ema_21 = cm.pct_from_ema_21,
            pct_from_sma_50 = cm.pct_from_sma_50,
            pct_from_sma_200 = cm.pct_from_sma_200,
            volume_ratio = cm.volume_ratio,
            volume_analysis = cm.volume_analysis,
            entry_quality_score = cm.entry_quality_score,
            profit_target_20pct = cm.profit_target_20pct,
            profit_target_25pct = cm.profit_target_25pct,
            current_gain_loss_pct = cm.current_gain_loss_pct,
            risk_pct = cm.risk_pct,
            position_size_recommendation = cm.position_size_recommendation,
            passes_minervini_template = cm.passes_minervini_template,
            rsi = cm.rsi,
            adx = cm.adx,
            atr = cm.atr,
            daily_range_pct = cm.daily_range_pct,
            volatility_profile = cm.volatility_profile
        FROM calculated_metrics cm
        WHERE bsd.symbol = cm.symbol AND bsd.date = cm.date
        """

        # Parameters: positional list matching %s placeholders in SQL
        cur.execute(update_sql, (symbol, timeframe, symbol, symbol, symbol))
        updated_count = cur.rowcount
        logging.info(f"✅ Updated {updated_count} swing metrics for {symbol} {timeframe}")

    except Exception as e:
        logging.error(f"❌ Failed to update swing metrics for {symbol}: {e}")
        raise


###############################################################################
# 2) RISK-FREE RATE (FRED)
###############################################################################
def get_risk_free_rate_fred(api_key):
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=DGS3MO&api_key={api_key}&file_type=json"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    return float(obs[-1]["value"]) / 100.0 if obs else 0.0


###############################################################################
# 3) FETCH FROM DB (prices + technicals)
###############################################################################
def fetch_symbol_from_db(symbol, timeframe):
    tf = timeframe.lower()
    # Table name mapping for consistency with loader scripts
    price_table_map = {
        "daily": "price_daily",
        "weekly": "price_weekly",
        "monthly": "price_monthly",
    }
    tech_table_map = {
        "daily": "technical_data_daily",
        "weekly": "technical_data_weekly",
        "monthly": "technical_data_monthly",
    }
    if tf not in price_table_map or tf not in tech_table_map:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    price_table = price_table_map[tf]
    tech_table = tech_table_map[tf]
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql = f"""
          SELECT
            p.date, p.open, p.high, p.low, p.close, p.volume,
            COALESCE(t.rsi, 50) as rsi,
            COALESCE(t.atr, 0) as atr,
            COALESCE(t.adx, 0) as adx,
            COALESCE(t.plus_di, 0) as plus_di,
            COALESCE(t.minus_di, 0) as minus_di,
            COALESCE(t.sma_50, p.close) as sma_50,
            COALESCE(t.pivot_high, 0) as pivot_high,
            COALESCE(t.pivot_low, 0) as pivot_low
          FROM {price_table} p
          LEFT JOIN {tech_table}  t
            ON p.symbol = t.symbol AND p.date = t.date
          WHERE p.symbol = %s
          ORDER BY p.date ASC;
        """
        logging.info(f"[fetch_symbol_from_db] Executing SQL for {symbol} {timeframe}")
        cur.execute(sql, (symbol,))
        rows = cur.fetchall()
        logging.info(
            f"[fetch_symbol_from_db] Got {len(rows)} rows for {symbol} {timeframe}"
        )
    except psycopg2.Error as e:
        conn.rollback()  # Rollback aborted transaction
        logging.warning(f"[fetch_symbol_from_db] Technical data table issue for {symbol} {timeframe}: {e}")
        # Fallback query with only price data
        try:
            sql = f"""
              SELECT
                date, open, high, low, close, volume,
                50 as rsi, 0 as atr, 0 as adx, 0 as plus_di, 0 as minus_di,
                close as sma_50, 0 as pivot_high, 0 as pivot_low
              FROM {price_table}
              WHERE symbol = %s
              ORDER BY date ASC;
            """
            cur.execute(sql, (symbol,))
            rows = cur.fetchall()
            logging.info(f"[fetch_symbol_from_db] Fallback query got {len(rows)} rows for {symbol} {timeframe}")
        except Exception as fallback_e:
            conn.rollback()  # Rollback aborted transaction
            logging.error(f"[fetch_symbol_from_db] Fallback SQL error for {symbol} {timeframe}: {fallback_e}")
            rows = []
    except Exception as e:
        conn.rollback()  # Rollback aborted transaction
        logging.error(f"[fetch_symbol_from_db] SQL error for {symbol} {timeframe}: {e}")
        rows = []
    finally:
        cur.close()
        conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    num_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "rsi",
        "atr",
        "adx",
        "plus_di",
        "minus_di",
        "sma_50",
        "pivot_high",
        "pivot_low",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


###############################################################################
# 4) SIGNAL GENERATION & IN-POSITION LOGIC - Pine Script Breakout Trend Follower
###############################################################################
def generate_signals(df, use_ma_filter=True, ma_type='SMA', ma_length=50):
    """
    Pine Script Breakout Trend Follower Strategy
    Based on: @millerrh's Breakout Trend Follower (TradingView)

    Entry: When high breaks above recent swing high (pivot high)
    Exit: When low breaks below recent swing low (pivot low)
    MA Filter: Optional filter to only take trades above moving average

    Pine Script Logic:
    - buyLevel = valuewhen(pvthi_, high[pvtLenR], 0)  // Last pivot high
    - stopLevel = valuewhen(pvtlo_, low[pvtLenR], 0)  // Last pivot low
    - buySignal = high > buyLevel
    - buy = buySignal and buyLevel > maFilterCheck
    - sellSignal = low < stopLevel
    - inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
    - buyStudy = buy and flat (only buy when not in position)
    - sellStudy = sellSignal and inPosition (only sell when in position)
    """
    # Calculate MA filter (matches Pine Script ma() function)
    if use_ma_filter:
        if ma_type == 'EMA':
            df['ma_filter'] = df['close'].ewm(span=ma_length, adjust=False).mean()
        else:  # SMA (default in Pine Script)
            df['ma_filter'] = df['close'].rolling(window=ma_length).mean()
    else:
        df['ma_filter'] = 0  # No filter (maFilterCheck = 0 in Pine Script)

    # Pine Script: pvthis = fixnan(pvthi), pvtlos = fixnan(pvtlo)
    # fixnan() forward fills the last non-null value
    df['LastPH'] = df['pivot_high'].ffill()
    df['LastPL'] = df['pivot_low'].ffill()

    # Pine Script: buyLevel and stopLevel from valuewhen()
    df['buyLevel'] = df['LastPH']  # Buy level at swing high
    df['stopLevel'] = df['LastPL']  # Stop level at swing low

    # Pine Script breakout conditions
    # buySignal = high > buyLevel
    # buy = buySignal and buyLevel > maFilterCheck
    df['buySignal'] = df['high'] > df['buyLevel']

    if use_ma_filter:
        # Only buy if buyLevel > ma_filter (trend filter)
        df['buySignal'] = df['buySignal'] & (df['buyLevel'] > df['ma_filter'])

    # Pine Script: sellSignal = low < stopLevel
    df['sellSignal'] = df['low'] < df['stopLevel']

    # Pine Script position tracking logic:
    # inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
    # flat := not inPosition
    # buyStudy = buy and flat
    # sellStudy = sellSignal and inPosition
    in_position = False
    signals = []
    positions = []

    for i in range(len(df)):
        buy_signal = df.loc[i, 'buySignal']
        sell_signal = df.loc[i, 'sellSignal']

        # Update position state BEFORE checking signals
        # This matches Pine Script's [1] reference (previous bar)
        flat = not in_position

        # Pine Script: buyStudy = buy and flat
        if flat and buy_signal:
            signals.append('Buy')
            in_position = True
        # Pine Script: sellStudy = sellSignal and inPosition
        elif in_position and sell_signal:
            signals.append('Sell')
            in_position = False
        else:
            signals.append('None')

        positions.append(in_position)

    df['Signal'] = signals
    df['inPosition'] = positions

    return df


###############################################################################
# 5) BACKTEST & METRICS
###############################################################################
def backtest_fixed_capital(df):
    trades = []
    buys = df.index[df["Signal"] == "Buy"].tolist()
    if not buys:
        return trades, [], [], None, None

    df2 = df.iloc[buys[0] :].reset_index(drop=True)
    pos_open = False
    for i in range(len(df2) - 1):
        sig, o, d = df2.loc[i, "Signal"], df2.loc[i + 1, "open"], df2.loc[i + 1, "date"]
        if sig == "Buy" and not pos_open:
            pos_open = True
            trades.append({"date": d, "action": "Buy", "price": o})
        elif sig == "Sell" and pos_open:
            pos_open = False
            trades.append({"date": d, "action": "Sell", "price": o})

    if pos_open:
        last = df2.iloc[-1]
        trades.append({"date": last["date"], "action": "Sell", "price": last["close"]})

    rets, durs = [], []
    i = 0
    while i < len(trades) - 1:
        if trades[i]["action"] == "Buy" and trades[i + 1]["action"] == "Sell":
            e, x = trades[i]["price"], trades[i + 1]["price"]
            if e >= 1.0:
                rets.append((x - e) / e)
                durs.append((trades[i + 1]["date"] - trades[i]["date"]).days)
            i += 2
        else:
            i += 1

    return trades, rets, durs, df["date"].iloc[0], df["date"].iloc[-1]


def compute_metrics_fixed_capital(rets, durs, annual_rfr=0.0):
    n = len(rets)
    if n == 0:
        return {}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    avg = np.mean(rets) if n else 0.0
    std = np.std(rets, ddof=1) if n > 1 else 0.0
    return {
        "num_trades": n,
        "win_rate": len(wins) / n,
        "avg_return": avg,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else float("inf"),
        "sharpe_ratio": ((avg - annual_rfr) / std * np.sqrt(n)) if std > 0 else 0.0,
    }


def analyze_trade_returns_fixed_capital(rets, durs, tag, annual_rfr=0.0):
    m = compute_metrics_fixed_capital(rets, durs, annual_rfr)
    if not m:
        logging.info(f"{tag}: No trades.")
        return
    logging.info(
        f"{tag} → Trades:{m['num_trades']} "
        f"WinRate:{m['win_rate']:.2%} "
        f"AvgRet:{m['avg_return']*100:.2f}% "
        f"PF:{m['profit_factor']:.2f} "
        f"Sharpe:{m['sharpe_ratio']:.2f}"
    )


###############################################################################
# 6) PROCESS & MAIN
###############################################################################
def process_symbol(symbol, timeframe, use_ma_filter=True, ma_type='SMA', ma_length=50):
    logging.info(f"  [process_symbol] Fetching {symbol} {timeframe}")
    df = fetch_symbol_from_db(symbol, timeframe)
    logging.info(
        f"  [process_symbol] Done fetching {symbol} {timeframe}, rows: {len(df)}"
    )
    if not df.empty:
        return generate_signals(df, use_ma_filter=use_ma_filter, ma_type=ma_type, ma_length=ma_length)
    return df


def main():

    try:
        if FRED_API_KEY:
            annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
            print(f"Annual RFR: {annual_rfr:.2%}")
        else:
            annual_rfr = 0.0
            logging.info("FRED_API_KEY not set, using 0% risk-free rate")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0

    # Get symbols with data - limit for local testing, unlimited for AWS production
    symbols = get_symbols_from_db(limit=None)
    if not symbols:
        print("No symbols in DB.")
        return

    # Daily
    conn = get_db_connection()
    cur = conn.cursor()
    create_buy_sell_table(cur)
    conn.commit()
    results = {"Daily": {"rets": [], "durs": []}}
    logging.info(f"📈 Pine Script Breakout Trend Follower Configuration:")
    logging.info(f"   MA Filter: {'Enabled' if USE_MA_FILTER else 'Disabled'}")
    logging.info(f"   MA Type: {MA_TYPE}")
    logging.info(f"   MA Length: {MA_LENGTH}")
    logging.info("=" * 80)

    for sym in symbols:
        logging.info(f"=== {sym} ===")
        tf = "Daily"
        logging.info(f"  [main] Processing {sym} {tf}")
        df = process_symbol(sym, tf, use_ma_filter=USE_MA_FILTER, ma_type=MA_TYPE, ma_length=MA_LENGTH)
        logging.info(f"  [main] Done processing {sym} {tf}")
        if df.empty:
            logging.info(f"[{tf}] no data")
            continue
        insert_symbol_results(cur, sym, tf, df, ma_type=MA_TYPE, ma_length=MA_LENGTH)
        conn.commit()

        # Calculate swing metrics (O'Neill/Minervini, Stage Analysis, SATA scores, etc.)
        try:
            logging.info(f"  [main] Calculating swing metrics for {sym} {tf}")
            update_swing_metrics_for_symbol(cur, sym, tf)
            conn.commit()
            logging.info(f"  [main] ✅ Done calculating swing metrics for {sym} {tf}")
        except Exception as e:
            logging.error(f"  [main] ❌ Swing metrics failed for {sym} {tf}: {e}")
            conn.rollback()

        _, rets, durs, _, _ = backtest_fixed_capital(df)
        results[tf]["rets"].extend(rets)
        results[tf]["durs"].extend(durs)
        analyze_trade_returns_fixed_capital(rets, durs, f"[{tf}] {sym}", annual_rfr)
    cur.close()
    conn.close()

    # Weekly and Monthly loaders run as separate ECS tasks
    # No need to import and call them here

    logging.info("=========================")
    logging.info(" AGGREGATED PERFORMANCE (FIXED $10k PER TRADE) ")
    logging.info("=========================")
    for tf in results:
        analyze_trade_returns_fixed_capital(
            results[tf]["rets"], results[tf]["durs"], f"[{tf} (Overall)]", annual_rfr
        )

    logging.info("Processing complete.")


if __name__ == "__main__":
    main()
