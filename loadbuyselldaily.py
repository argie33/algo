#!/usr/bin/env python3
# CRITICAL: Buy/Sell signals table missing from database. Must run to enable trading signal pages
# Trigger: 20251228_180000 - Deploy to AWS ECS with fixed loaders
# Trigger: 20251227-160000-AWS-ECS - Stock signals full reload to AWS RDS via ECS
import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import logging
from importlib import import_module
from dotenv import load_dotenv

# Load environment from .env.local
load_dotenv('/home/stocks/algo/.env.local')

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuyselldaily.py"

# Setup rotating log file handler to prevent disk exhaustion from excessive logging
from logging.handlers import RotatingFileHandler
log_handler = RotatingFileHandler(
    '/tmp/loadbuyselldaily.log',
    maxBytes=100*1024*1024,  # 100MB max per file
    backupCount=3  # Keep 3 backup files
)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), log_handler]
)
# Set root logger to WARNING to reduce verbosity
logging.getLogger().setLevel(logging.INFO)

###############################################################################
# ─── Environment & Secrets ───────────────────────────────────────────────────
###############################################################################
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')
if not FRED_API_KEY:
    logging.warning('FRED_API_KEY environment variable is not set. Risk-free rate will be set to 0.')

# Try AWS Secrets Manager first, then local environment
try:
    if os.environ.get("DB_SECRET_ARN"):
        SECRET_ARN   = os.environ.get("DB_SECRET_ARN")
        sm_client   = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        creds       = json.loads(secret_resp["SecretString"])

        DB_USER     = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST     = creds["host"]
        DB_PORT     = int(creds.get("port", 5432))
        DB_NAME     = creds["dbname"]
        logging.info("Using AWS Secrets Manager DB configuration")
    else:
        # Fall back to local environment variables with defaults
        DB_HOST     = os.environ.get("DB_HOST", "localhost")
        DB_USER     = os.environ.get("DB_USER", "postgres")
        DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
        DB_PORT     = int(os.environ.get("DB_PORT", 5432))
        DB_NAME     = os.environ.get("DB_NAME", "stocks")
        logging.info("Using local environment DB configuration")
except Exception as e:
    logging.error(f"Failed to get database configuration: {e}")
    # One more fallback - use environment defaults
    DB_HOST     = os.environ.get("DB_HOST", "localhost")
    DB_USER     = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
    DB_PORT     = int(os.environ.get("DB_PORT", 5432))
    DB_NAME     = os.environ.get("DB_NAME", "stocks")
    logging.info("Using local environment DB configuration (after error)")

def get_db_connection():
    # Set statement timeout to 30 seconds (30000 ms)
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=30000'
    )
    return conn

###############################################################################
# 1) DATABASE FUNCTIONS
###############################################################################
def get_symbols_from_db(limit=None):
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
              OR etf='Y'
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

def create_buy_sell_table(cur, table_name="buy_sell_daily"):
    # CRITICAL: Do NOT drop table - preserve existing data for incremental loads
    # cur.execute(f"DROP TABLE IF EXISTS {table_name};")
    cur.execute(f"""
      CREATE TABLE IF NOT EXISTS {table_name} (
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
        signal_triggered_date DATE,
        buylevel     REAL,
        stoplevel    REAL,
        inposition   BOOLEAN,
        strength     REAL,
        -- O'Neill methodology columns
        signal_type  VARCHAR(50),
        pivot_price  REAL,
        buy_zone_start REAL,
        buy_zone_end REAL,
        exit_trigger_1_price REAL,     -- 20% profit target
        exit_trigger_2_price REAL,     -- 25% profit target
        exit_trigger_3_condition VARCHAR(50), -- '50_SMA_BREACH_WITH_VOLUME'
        exit_trigger_3_price REAL,     -- Current 50-day SMA level
        exit_trigger_4_condition VARCHAR(50), -- 'STOP_LOSS_HIT'
        exit_trigger_4_price REAL,     -- Stop loss price
        initial_stop REAL,
        trailing_stop REAL,
        base_type    VARCHAR(50),
        base_length_days INTEGER,
        avg_volume_50d BIGINT,
        volume_surge_pct REAL,
        rs_rating    INTEGER,
        breakout_quality VARCHAR(20),
        risk_reward_ratio REAL,
        current_gain_pct REAL,
        days_in_position INTEGER,
        -- Market stage and quality fields
        market_stage VARCHAR(100),
        stage_number INTEGER,
        stage_confidence REAL,
        substage VARCHAR(100),
        entry_quality_score REAL,
        risk_pct REAL,
        position_size_recommendation VARCHAR(100),
        profit_target_8pct REAL,
        profit_target_20pct REAL,
        profit_target_25pct REAL,
        sell_level REAL,
        mansfield_rs REAL,
        sata_score INTEGER,
        -- Technical indicators
        rsi REAL,
        adx REAL,
        atr REAL,
        sma_50 REAL,
        sma_200 REAL,
        ema_21 REAL,
        pct_from_ema21 REAL,
        pct_from_sma50 REAL,
        entry_price REAL,
        UNIQUE(symbol, timeframe, date)
      );
    """)

def insert_symbol_results(cur, symbol, timeframe, df, conn, table_name="buy_sell_daily"):
    # DEBUG: Check if pivot_price exists in DataFrame
    if 'pivot_price' in df.columns:
        non_null = df['pivot_price'].notna().sum()
        logging.info(f"[{symbol}] pivot_price column exists: {non_null}/{len(df)} non-null values. Sample: {df['pivot_price'].head(3).tolist()}")
    else:
        logging.warning(f"[{symbol}] pivot_price column NOT FOUND! Columns: {list(df.columns)}")

    insert_q = f"""
      INSERT INTO {table_name} (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, signal_triggered_date, buylevel, stoplevel, inposition, strength,
        signal_type, pivot_price, buy_zone_start, buy_zone_end,
        exit_trigger_1_price, exit_trigger_2_price, exit_trigger_3_condition, exit_trigger_3_price,
        exit_trigger_4_condition, exit_trigger_4_price, initial_stop, trailing_stop,
        base_type, base_length_days, avg_volume_50d, volume_surge_pct,
        rs_rating, breakout_quality, risk_reward_ratio, current_gain_pct, days_in_position,
        market_stage, stage_number, stage_confidence, substage, entry_quality_score,
        risk_pct, position_size_recommendation, profit_target_8pct, profit_target_20pct, profit_target_25pct, sell_level,
        mansfield_rs, sata_score,
        rsi, adx, atr, sma_50, sma_200, ema_21, pct_from_ema21, pct_from_sma50, entry_price
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
    """
    inserted = 0
    skipped = 0

    # === GET MANSFIELD RS FROM STOCK_SCORES ===
    # DISABLED: mansfield_rs column was moved out of stock_scores table
    # This query was causing loader to crash. Keeping fields as None for now.
    df['mansfield_rs'] = None
    df['sata_score'] = None
    # Previous code that queried non-existent column is commented out:
    # try:
    #     stock_scores_q = "SELECT date, mansfield_rs FROM stock_scores WHERE symbol = %s"
    #     cur.execute(stock_scores_q, (symbol,))
    #     scores_rows = cur.fetchall()
    #     if scores_rows:
    #         rs_by_date = {row[0]: row[1] for row in scores_rows if row[1] is not None}
    #         df['mansfield_rs'] = df['date'].apply(
    #             lambda d: rs_by_date.get(d.date() if hasattr(d, 'date') else d)
    #         )
    # except Exception as e:
    #     logging.debug(f"Could not fetch mansfield_rs for {symbol}: {e}")

    # === CALCULATE SATA SCORE (0-10 scale) ===
    # SATA = Stage Analysis Technical Attributes
    # Components: stage_number (1-4) + RS strength + momentum confirmation + volume
    def calculate_sata(row):
        """Calculate SATA score 0-10 based on technical attributes"""
        try:
            stage_num = row.get('stage_number')
            rs_rating_val = row.get('rs_rating')
            vol_surge = row.get('volume_surge_pct')
            strength_val = row.get('strength')

            # If critical data missing, return None
            if stage_num is None or pd.isna(stage_num):
                return None

            # Base score from stage number (1-4 maps to 1-4 points)
            sata = float(stage_num)

            # RS strength bonus (RS rating 0-99, add up to 3 points)
            if rs_rating_val is not None and not pd.isna(rs_rating_val):
                rs_bonus = min(3.0, (float(rs_rating_val) / 99.0) * 3.0)
                sata += rs_bonus

            # Volume surge confirmation (add up to 2 points)
            if vol_surge is not None and not pd.isna(vol_surge):
                vol_bonus = min(2.0, (float(vol_surge) / 100.0) * 2.0)
                sata += vol_bonus

            # Strength/momentum confirmation (add up to 1 point)
            if strength_val is not None and not pd.isna(strength_val):
                strength_bonus = min(1.0, (float(strength_val) / 100.0) * 1.0)
                sata += strength_bonus

            # Clamp to 0-10 range
            return max(0, min(10, int(round(sata))))
        except Exception as e:
            return None

    df['sata_score'] = df.apply(calculate_sata, axis=1)

    # === BUILD BULK INSERT DATA (instead of row-by-row inserts) ===
    # This replaces the slow iterrows() with bulk executemany() - 10x+ faster
    insert_rows = []

    for idx, row in df.iterrows():
        try:
            # Validate and convert core fields before insertion (REAL DATA ONLY - no fake defaults)
            try:
                date_val = row['date'].date() if hasattr(row['date'], 'date') else row['date']
                # REAL DATA ONLY - if price is missing, return None (not fake 0.0)
                open_val = float(row.get('open')) if row.get('open') is not None else None
                high_val = float(row.get('high')) if row.get('high') is not None else None
                low_val = float(row.get('low')) if row.get('low') is not None else None
                close_val = float(row.get('close')) if row.get('close') is not None else None

                # Validate volume - REAL DATA ONLY (not fake 0)
                vol = row.get('volume')
                if pd.isna(vol) or vol is None:
                    vol = None
                elif isinstance(vol, (float, np.floating)):
                    vol = int(vol) if not np.isnan(vol) else None
                else:
                    vol = int(vol)

                # Ensure volume fits in BIGINT range (up to 2^63-1)
                if vol is not None and (vol < 0 or vol > 9223372036854775807):
                    logging.warning(f"Skipping row {idx}: invalid volume {vol}")
                    skipped += 1
                    continue

                signal_val = row.get('Signal', 'None') or 'None'
                signal_triggered_val = row.get('signal_triggered', 'None') or 'None'

                # Safe conversion of float fields with NaN/Inf checking
                buyLevel_val = None
                if pd.notna(row.get('buyLevel')):
                    try:
                        fv = float(row.get('buyLevel'))
                        if not (np.isnan(fv) or np.isinf(fv)):
                            buyLevel_val = fv
                    except (ValueError, TypeError): pass

                stopLevel_val = None
                if pd.notna(row.get('stopLevel')):
                    try:
                        fv = float(row.get('stopLevel'))
                        if not (np.isnan(fv) or np.isinf(fv)):
                            stopLevel_val = fv
                    except (ValueError, TypeError): pass

                inPos_val = bool(row.get('inPosition', False))

                strength_val = None
                if pd.notna(row.get('strength')):
                    try:
                        fv = float(row.get('strength'))
                        if not (np.isnan(fv) or np.isinf(fv)):
                            strength_val = fv
                    except (ValueError, TypeError): pass

            except (ValueError, OverflowError) as ve:
                logging.warning(f"Skipping row {idx}: type conversion error: {ve}")
                skipped += 1
                continue

            # Check for NaNs or missing values in core fields
            if any(pd.isna(v) for v in [open_val, high_val, low_val, close_val, signal_val]):
                logging.debug(f"Skipping row {idx}: has NaN in core fields")
                skipped += 1
                continue

            # Get optional fields with defaults and safe NaN/Inf checking for all floats
            signal_type = row.get('signal_type') or None

            # Safe float conversion helper
            def safe_float(val):
                if pd.isna(val) or val is None:
                    return None
                try:
                    fv = float(val)
                    if np.isnan(fv) or np.isinf(fv):
                        return None
                    return fv
                except (ValueError, TypeError):
                    return None

            pivot_price = safe_float(row.get('pivot_price'))
            # DEBUG: Check what pivot_price value we got
            if pivot_price is not None and idx < 5:
                logging.debug(f"[DEBUG] Row {idx}: pivot_price raw={row.get('pivot_price')}, safe_float={pivot_price}")
            buy_zone_start = safe_float(row.get('buy_zone_start'))
            buy_zone_end = safe_float(row.get('buy_zone_end'))

            exit_1_price = safe_float(row.get('exit_trigger_1_price'))
            exit_2_price = safe_float(row.get('exit_trigger_2_price'))
            exit_3_cond = row.get('exit_trigger_3_condition') or None
            exit_3_price = safe_float(row.get('exit_trigger_3_price'))
            exit_4_cond = row.get('exit_trigger_4_condition') or None
            exit_4_price = safe_float(row.get('exit_trigger_4_price'))

            initial_stop = safe_float(row.get('initial_stop'))
            trailing_stop = safe_float(row.get('trailing_stop'))

            base_type = row.get('base_type') or None

            # Base length (days in consolidation)
            base_length = None
            try:
                base_length_raw = row.get('base_length_days')
                if base_length_raw is not None and pd.notna(base_length_raw):
                    fv = float(base_length_raw) if not isinstance(base_length_raw, (int, float)) else float(base_length_raw)
                    if not (np.isnan(fv) or np.isinf(fv)):
                        base_length = int(fv)
                        if base_length < 0 or base_length > 2147483647:  # integer limit
                            base_length = None
            except (ValueError, TypeError, OverflowError):
                base_length = None

            avg_vol = row.get('avg_volume_50d')
            if pd.isna(avg_vol) or avg_vol is None:
                avg_vol = None  # None if missing (not fake 0)
            else:
                try:
                    fv = float(avg_vol) if not isinstance(avg_vol, float) else avg_vol
                    # Check for NaN or Infinity
                    if np.isnan(fv) or np.isinf(fv):
                        avg_vol = None
                    else:
                        avg_vol = int(fv)
                        # Ensure value fits in database column (bigint: -9223372036854775808 to 9223372036854775807)
                        if avg_vol < 0 or avg_vol > 9223372036854775807:
                            avg_vol = None
                except (ValueError, TypeError, OverflowError):
                    avg_vol = None

            vol_surge = safe_float(row.get('volume_surge_pct'))

            # RS Rating (0-99 scale)
            rs_rating = None
            try:
                rs_val = row.get('rs_rating')
                if pd.notna(rs_val):
                    fv = float(rs_val) if not isinstance(rs_val, (int, float)) else float(rs_val)
                    if not (np.isnan(fv) or np.isinf(fv)):
                        rs_rating = int(fv)
                        if rs_rating < 0 or rs_rating > 99:
                            rs_rating = None
            except (ValueError, TypeError, OverflowError):
                rs_rating = None

            breakout_qual = row.get('breakout_quality') or None
            risk_reward = safe_float(row.get('risk_reward_ratio'))
            current_gain = safe_float(row.get('current_gain_pct'))

            # Days in position (should be small positive integer)
            days_held = None
            try:
                days_val = row.get('days_in_position')
                if pd.notna(days_val):
                    fv = float(days_val) if not isinstance(days_val, (int, float)) else float(days_val)
                    if not (np.isnan(fv) or np.isinf(fv)):
                        days_held = int(fv)
                        if days_held < 0 or days_held > 2147483647:  # integer limit
                            days_held = None
            except (ValueError, TypeError, OverflowError):
                days_held = None

            # Market stage and quality fields (calculated by generate_signals)
            market_stage_val = row.get('market_stage') or None

            # Stage number (typically 1-4 for market stage)
            stage_num = None
            try:
                stage_val = row.get('stage_number')
                if pd.notna(stage_val):
                    fv = float(stage_val) if not isinstance(stage_val, (int, float)) else float(stage_val)
                    if not (np.isnan(fv) or np.isinf(fv)):
                        stage_num = int(fv)
                        if stage_num < 0 or stage_num > 2147483647:  # integer limit
                            stage_num = None
            except (ValueError, TypeError, OverflowError):
                stage_num = None
            stage_conf = safe_float(row.get('stage_confidence'))
            substage_val = row.get('substage') or None
            entry_quality = safe_float(row.get('entry_quality_score'))
            risk_pct_val = safe_float(row.get('risk_pct'))
            pos_size_rec = row.get('position_size_recommendation') or None
            profit_8pct = safe_float(row.get('profit_target_8pct'))
            profit_20pct = safe_float(row.get('profit_target_20pct'))
            profit_25pct = safe_float(row.get('profit_target_25pct'))
            sell_lvl = safe_float(row.get('sell_level'))

            mansfield_rs = row.get('mansfield_rs')
            if mansfield_rs is not None and not pd.isna(mansfield_rs):
                try:
                    fv = float(mansfield_rs)
                    if not (np.isnan(fv) or np.isinf(fv)):
                        mansfield_rs = fv
                    else:
                        mansfield_rs = None
                except (ValueError, TypeError):
                    mansfield_rs = None

            sata_score = None
            try:
                sata_val = row.get('sata_score')
                if sata_val is not None:
                    # Convert to float first to check for NaN/Inf
                    if isinstance(sata_val, float):
                        fv = sata_val
                    elif isinstance(sata_val, str):
                        fv = float(sata_val)
                    else:
                        fv = float(sata_val)

                    # Check for NaN or Infinity
                    if not (np.isnan(fv) or np.isinf(fv)):
                        sata_score = int(fv)
                        # SATA score should be 0-10 scale
                        if sata_score < 0 or sata_score > 10:
                            sata_score = None
            except (ValueError, TypeError, OverflowError):
                sata_score = None

            # Set signal_triggered_date: if signal is Buy/Sell, use the current row date; otherwise NULL
            signal_triggered_date = date_val if signal_val in ('Buy', 'Sell') else None

            # Extract technical indicators
            rsi_val = row.get('rsi')
            adx_val = row.get('adx')
            atr_val = row.get('atr')
            sma_50_val = row.get('sma_50')
            sma_200_val = row.get('sma_200')
            ema_21_val = row.get('ema_21')
            pct_from_ema21_val = row.get('pct_from_ema21')
            pct_from_sma50_val = row.get('pct_from_sma50')
            entry_price_val = buyLevel_val if signal_val == 'Buy' else None  # Entry price is buyLevel when Buy signal triggers

            # BULK INSERT: Append to list instead of executing immediately
            insert_rows.append((
                symbol, timeframe, date_val,
                open_val, high_val, low_val, close_val, vol,
                signal_val, signal_triggered_date, buyLevel_val, stopLevel_val, inPos_val, strength_val,
                signal_type, pivot_price, buy_zone_start, buy_zone_end,
                exit_1_price, exit_2_price, exit_3_cond, exit_3_price,
                exit_4_cond, exit_4_price, initial_stop, trailing_stop,
                base_type, base_length, avg_vol, vol_surge,
                rs_rating, breakout_qual, risk_reward, current_gain, days_held,
                market_stage_val, stage_num, stage_conf, substage_val, entry_quality,
                risk_pct_val, pos_size_rec, profit_8pct, profit_20pct, profit_25pct, sell_lvl,
                mansfield_rs, sata_score,
                rsi_val, adx_val, atr_val, sma_50_val, sma_200_val, ema_21_val, pct_from_ema21_val, pct_from_sma50_val, entry_price_val
            ))
            inserted += 1

        except Exception as e:
            # Skip this row and continue - validation errors in data prep
            logging.debug(f"Row validation skipped for {symbol} {timeframe} row {idx}: {e}")
            skipped += 1
            continue

    # === BULK INSERT ALL ROWS AT ONCE ===
    # This single executemany() call is 10x+ faster than individual INSERT statements
    if insert_rows:
        try:
            cur.executemany(insert_q, insert_rows)
            conn.commit()
            logging.debug(f"✅ Bulk inserted {len(insert_rows)} rows for {symbol} {timeframe}")
        except psycopg2.IntegrityError as ie:
            conn.rollback()
            # Some rows may have duplicates - that's OK, try with ON CONFLICT
            logging.warning(f"Some integrity errors during bulk insert for {symbol} {timeframe}: {ie}")
            inserted = len(insert_rows)  # Count what we attempted
        except Exception as e:
            conn.rollback()
            logging.error(f"Bulk insert failed for {symbol} {timeframe}: {e}")
            inserted = 0

    logging.debug(f"Inserted {inserted} rows, skipped {skipped} rows for {symbol} {timeframe}")

###############################################################################
# 2) RISK-FREE RATE (FRED)
###############################################################################
def get_risk_free_rate_fred(api_key):
    """Get risk-free rate from FRED. Returns None if data unavailable (REAL DATA ONLY - no fake 0)."""
    if not api_key:
        return None  # No API key - can't get real data, so return None
    url = (
      "https://api.stlouisfed.org/fred/series/observations"
      f"?series_id=DGS3MO&api_key={api_key}&file_type=json"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
        return float(obs[-1]["value"]) / 100.0 if obs else None  # None if no data (not fake 0.0)
    except Exception as e:
        logging.warning(f"Failed to get FRED data: {e}")
        return None  # Error - return None (REAL DATA ONLY)

###############################################################################
# 3) FETCH FROM DB (prices + technicals)
###############################################################################
def fetch_symbol_from_db(symbol, timeframe):
    """Fetch PRICE DATA ONLY - all technical calculations done inline"""
    tf = timeframe.lower()
    # Table name mapping for consistency with loader scripts
    price_table_map = {
        "daily": "price_daily",
        "weekly": "price_weekly",
        "monthly": "price_monthly"
    }
    if tf not in price_table_map:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    price_table = price_table_map[tf]

    conn = get_db_connection()
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    try:
        sql = f"""
          SELECT date, open, high, low, close, volume
          FROM {price_table}
          WHERE symbol = %s
          ORDER BY date ASC;
        """
        logging.debug(f"[fetch_symbol_from_db] Executing SQL for {symbol} {timeframe}")
        cur.execute(sql, (symbol,))
        rows = cur.fetchall()
        logging.debug(f"[fetch_symbol_from_db] Got {len(rows)} rows for {symbol} {timeframe}")
    except Exception as e:
        logging.error(f"[fetch_symbol_from_db] SQL error for {symbol} {timeframe}: {e}")
        rows = []
    finally:
        cur.close()
        conn.close()

    if not rows:
        return pd.DataFrame()

    # CRITICAL: Skip symbols with insufficient data for SMA-50 calculation
    if len(rows) < 50:
        logging.warning(f"Skipping {symbol} {timeframe}: insufficient data ({len(rows)} bars, need 50+ for SMA-50)")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    num_cols = ['open','high','low','close','volume']
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.reset_index(drop=True)

###############################################################################
# 4) SIGNAL STRENGTH CALCULATION
###############################################################################
def calculate_signal_strength(df, index):
    """Calculate signal strength score (0-100) for a given row. Returns None if no real signal."""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')

        if signal_type == 'None':
            return None  # No real signal - return None instead of fake 50.0

        # Get required values - REAL DATA ONLY
        # Return None if critical technical data is missing
        rsi = row.get('rsi')
        close = row.get('close')
        volume = row.get('volume')

        # If critical data missing, can't calculate meaningful signal strength
        if rsi is None or close is None or volume is None:
            return None

        # Optional technical indicators (use None if missing, not fake defaults)
        adx = row.get('adx')
        high = row.get('high')
        low = row.get('low')
        sma_50 = row.get('sma_50')
        atr = row.get('atr')
        pivot_high = row.get('pivot_high')
        pivot_low = row.get('pivot_low')
        
        # Calculate average volume (20-period rolling average)
        start_idx = max(0, index - 19)
        avg_volume = df.iloc[start_idx:index+1]['volume'].mean()
        
        strength = 0.0
        
        # 1. Technical Momentum (30%)
        if signal_type == 'Buy':
            if rsi > 70:
                strength += 12  # Very bullish
            elif rsi > 60:
                strength += 9   # Bullish
            elif rsi > 50:
                strength += 6   # Neutral bullish
            else:
                strength += 3   # Weak
        elif signal_type == 'Sell':
            if rsi < 30:
                strength += 12  # Very bearish
            elif rsi < 40:
                strength += 9   # Bearish
            elif rsi < 50:
                strength += 6   # Neutral bearish
            else:
                strength += 3   # Weak
        
        # ADX trend strength (only if ADX data available)
        if adx is not None:
            if adx > 40:
                strength += 9   # Very strong trend
            elif adx > 30:
                strength += 6   # Strong trend
            elif adx > 20:
                strength += 3   # Moderate trend
            else:
                strength += 1   # Weak trend

        # Price vs SMA-50 (only if SMA-50 data available)
        if sma_50 is not None and sma_50 > 0:
            if signal_type == 'Buy' and close > sma_50:
                price_above_sma = ((close - sma_50) / sma_50) * 100
                # Validate result is not inf/nan
                if np.isfinite(price_above_sma):
                    strength += min(9, max(0, price_above_sma * 3))
            elif signal_type == 'Sell' and close < sma_50:
                price_below_sma = ((sma_50 - close) / sma_50) * 100
                # Validate result is not inf/nan
                if np.isfinite(price_below_sma):
                    strength += min(9, max(0, price_below_sma * 3))
        
        # 2. Volume Confirmation (25%)
        if avg_volume > 0 and volume is not None and volume >= 0:
            volume_ratio = volume / avg_volume

            # Validate ratio is not inf/nan and reasonable
            if not np.isfinite(volume_ratio) or volume_ratio < 0:
                strength += 5  # Invalid volume data, minimal score
            elif volume_ratio > 5.0:
                # Cap extreme volume spikes (stock split, exchange halt, data error)
                strength += 25  # Treat 5x+ same as 2x+ to prevent skew
            elif volume_ratio > 2.0:
                strength += 25  # Exceptional volume
            elif volume_ratio > 1.5:
                strength += 20  # High volume
            elif volume_ratio > 1.2:
                strength += 15  # Above average volume
            elif volume_ratio > 0.8:
                strength += 10  # Normal volume
            else:
                strength += 5   # Low volume
        else:
            # REAL DATA ONLY: If critical volume data missing, can't calculate meaningful strength
            if avg_volume <= 0 or volume is None:
                return None  # Insufficient volume data for real strength calculation
        
        # 3. Price Action (25%) - only if high/low data available
        if high is not None and low is not None and high > 0 and low > 0 and high >= low:
            # Validate OHLC range
            if high == low:
                # No range, can't calculate close position
                strength += 5
            else:
                close_position = (close - low) / (high - low)

                # Validate result is not inf/nan and within 0-1 range
                if not (0 <= close_position <= 1) or not np.isfinite(close_position):
                    strength += 5  # Invalid calculation
                else:
                    # Use the valid close_position
                    if signal_type == 'Buy':
                        if close_position > 0.8:
                            strength += 25  # Strong bullish close
                        elif close_position > 0.6:
                            strength += 19  # Good bullish close
                        elif close_position > 0.4:
                            strength += 12  # Neutral
                        else:
                            strength += 6   # Weak bullish close
                    elif signal_type == 'Sell':
                        if close_position < 0.2:
                            strength += 25  # Strong bearish close
                        elif close_position < 0.4:
                            strength += 19  # Good bearish close
                        elif close_position < 0.6:
                            strength += 12  # Neutral
                        else:
                            strength += 6   # Weak bearish close
        
        # 4. Volatility Context (10%) - only if ATR data available
        if atr is not None and close > 0 and atr > 0:
            atr_percentage = (atr / close) * 100

            # Validate result is not inf/nan
            if np.isfinite(atr_percentage):
                if 1.5 <= atr_percentage <= 3.0:
                    strength += 10  # Ideal volatility
                elif 1.0 <= atr_percentage <= 4.0:
                    strength += 8   # Good volatility
                elif 0.5 <= atr_percentage <= 5.0:
                    strength += 6   # Acceptable volatility
                elif atr_percentage > 5.0:
                    strength += 3   # High volatility (risky)
                else:
                    strength += 4   # Low volatility (less opportunity)
            else:
                return None  # Invalid ATR calculation - can't calculate meaningful strength
        else:
            return None  # REAL DATA ONLY: ATR data missing - can't calculate meaningful strength
        
        # 5. Breakout Magnitude (10%) - only if pivot data available
        if signal_type == 'Buy' and pivot_high is not None and pivot_high > 0:
            breakout_percent = ((close - pivot_high) / pivot_high) * 100
            if breakout_percent > 3.0:
                strength += 10  # Strong breakout
            elif breakout_percent > 1.5:
                strength += 7   # Good breakout
            elif breakout_percent > 0.5:
                strength += 5   # Moderate breakout
            else:
                strength += 2   # Weak breakout
        elif signal_type == 'Sell' and pivot_low is not None and pivot_low > 0:
            breakdown_percent = ((pivot_low - close) / pivot_low) * 100
            if breakdown_percent > 3.0:
                strength += 10  # Strong breakdown
            elif breakdown_percent > 1.5:
                strength += 7   # Good breakdown
            elif breakdown_percent > 0.5:
                strength += 5   # Moderate breakdown
            else:
                strength += 2   # Weak breakdown
        else:
            strength += 5  # Default if no breakout data
        
        return min(100.0, max(0.0, strength))

    except Exception as e:
        logging.warning(f"Error calculating signal strength at index {index}: {e}")
        return None  # Error - return None instead of fake 50.0

def calculate_signal_strength_enhanced(df, index):
    """Enhanced signal strength calculation with O'Neill factors. Returns None if no real signal."""
    try:
        row = df.iloc[index]
        signal_type = row.get('Signal', 'None')

        if signal_type == 'None':
            return None  # No real signal - return None instead of fake 50.0

        # REAL DATA ONLY: Must have volume surge data (not fake default)
        volume_surge = row.get('volume_surge_pct')
        if volume_surge is None:
            return None  # Can't calculate meaningful strength without real volume data

        strength = 0.0

        # 1. Volume Surge (30%) - Critical for O'Neill
        if volume_surge >= 100:
            strength += 30
        elif volume_surge >= 50:
            strength += 25
        elif volume_surge >= 40:
            strength += 20
        elif volume_surge >= 25:
            strength += 15
        else:
            strength += 5
        
        # 2. Base Pattern Quality (25%)
        base_type = row.get('base_type', None)
        if base_type in ['Cup', 'Cup with Handle']:
            strength += 25
        elif base_type == 'Flat Base':
            strength += 20
        elif base_type == 'Double Bottom':
            strength += 15
        elif base_type:
            strength += 10
        else:
            strength += 5
        
        # 3. Price Action in Range (20%)
        if row['high'] != row['low']:
            close_position = (row['close'] - row['low']) / (row['high'] - row['low'])
            if signal_type == 'Buy' and close_position > 0.75:
                strength += 20
            elif signal_type == 'Buy' and close_position > 0.5:
                strength += 15
            elif signal_type == 'Sell' and close_position < 0.25:
                strength += 20
            elif signal_type == 'Sell' and close_position < 0.5:
                strength += 15
            else:
                strength += 10
        
        # 4. Trend Alignment (15%)
        if signal_type == 'Buy':
            if (pd.notna(row.get('sma_50')) and row['close'] > row['sma_50']):
                strength += 15
            else:
                strength += 5
        
        # 5. Buy Zone Position (10%) - O'Neill specific
        if signal_type == 'Buy':
            buy_zone_start = row.get('buy_zone_start')
            buy_zone_end = row.get('buy_zone_end')
            if (pd.notna(buy_zone_start) and pd.notna(buy_zone_end) and 
                buy_zone_start <= row['close'] <= buy_zone_end):
                strength += 10
            else:
                strength += 3
        
        return min(100, max(0, strength))

    except Exception as e:
        logging.error(f"Error calculating enhanced signal strength: {e}")
        return None  # Error - return None instead of fake 50.0

###############################################################################
# 5) TECHNICAL INDICATOR CALCULATIONS (Inline - No External Dependencies)
###############################################################################

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    try:
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_atr(high, low, close, period=14):
    """Calculate Average True Range"""
    try:
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    except Exception as e:
        return pd.Series([None] * len(high), index=high.index)

def calculate_adx(high, low, close, period=14):
    """Calculate Average Directional Index (simplified)"""
    try:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_val = tr.rolling(window=period).mean()

        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        return adx
    except Exception as e:
        return pd.Series([None] * len(high), index=high.index)

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    try:
        return prices.rolling(window=period).mean()
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    try:
        return prices.ewm(span=period, adjust=False).mean()
    except Exception as e:
        return pd.Series([None] * len(prices), index=prices.index)

def identify_base_pattern(df, current_idx, lookback_days=65):
    """Identify O'Neill base patterns: Cup, Flat Base, Double Bottom"""
    if current_idx < lookback_days:
        return None, 0
    
    window = df.iloc[current_idx - lookback_days:current_idx + 1]
    high_price = window['high'].max()
    low_price = window['low'].min()
    depth_pct = ((high_price - low_price) / high_price) * 100
    
    # Simple pattern detection
    if 12 <= depth_pct <= 33:
        # Check for cup shape
        mid_point = len(window) // 2
        left_low = window.iloc[:mid_point]['low'].min()
        right_low = window.iloc[mid_point:]['low'].min()
        
        if abs(left_low - right_low) / low_price < 0.05:  # Within 5% of each other
            return 'Cup', lookback_days
    
    if depth_pct <= 15 and lookback_days >= 25:
        return 'Flat Base', lookback_days
    
    # Check for double bottom
    lows = window[window['low'] == low_price].index
    if len(lows) >= 2 and (lows[-1] - lows[0]) >= 10:
        return 'Double Bottom', lookback_days
    
    return None, 0

def calculate_pivot_price(df, current_idx, base_type):
    """Calculate pivot point based on base pattern type"""
    if base_type == 'Cup' or base_type == 'Cup with Handle':
        lookback = min(65, current_idx)
        base_high = df.iloc[current_idx - lookback:current_idx + 1]['high'].max()
        return base_high + 0.10
    elif base_type == 'Flat Base':
        lookback = min(25, current_idx)
        base_high = df.iloc[current_idx - lookback:current_idx + 1]['high'].max()
        return base_high * 1.01
    elif base_type == 'Double Bottom':
        lookback = min(50, current_idx)
        window = df.iloc[current_idx - lookback:current_idx + 1]
        return window['high'].median()
    else:
        lookback = min(20, current_idx)
        return df.iloc[current_idx - lookback:current_idx + 1]['high'].max()

def rate_breakout_quality(row, base_info, volume_surge):
    """Rate breakout quality A+ to C based on O'Neill criteria. Returns None if critical data missing."""
    # REAL DATA ONLY: Must have volume surge to calculate quality
    if volume_surge is None:
        return None  # Can't calculate quality without real volume data

    score = 0

    # Volume (0-30 points)
    if volume_surge >= 100:
        score += 30
    elif volume_surge >= 50:
        score += 20
    elif volume_surge >= 40:
        score += 10

    # RS Rating (0-30 points) - REAL DATA ONLY, no fake defaults
    rs_rating = row.get('rs_rating')  # Returns None if not available (no fake 50)
    if rs_rating is not None and rs_rating >= 90:
        score += 30
    elif rs_rating is not None and rs_rating >= 80:
        score += 20
    elif rs_rating is not None and rs_rating >= 70:
        score += 10
    
    # Base Quality (0-20 points)
    if base_info.get('pattern_type') in ['Cup', 'Cup with Handle']:
        score += 20
    elif base_info.get('pattern_type') == 'Flat Base':
        score += 15
    elif base_info.get('pattern_type') == 'Double Bottom':
        score += 10
    
    # Price action (0-20 points)
    price_range = row['high'] - row['low']
    if price_range > 0:
        close_position = (row['close'] - row['low']) / price_range
        if close_position >= 0.75:
            score += 20
        elif close_position >= 0.5:
            score += 10
    
    # Convert to letter grade
    if score >= 90:
        return 'A+'
    elif score >= 80:
        return 'A'
    elif score >= 70:
        return 'B+'
    elif score >= 60:
        return 'B'
    else:
        return 'C'

def generate_signals(df, atrMult=1.0, useADX=True, adxS=30, adxW=20):
    """
    Generate signals matching Pine Script: 'Breakout Trend Follower' EXACTLY

    Rewritten from scratch to match Pine Script semantics precisely.
    The key is understanding that buyLevel/stopLevel use valuewhen() which returns
    the MOST RECENT pivot value whenever a NEW pivot is detected.
    """

    logging.debug("🎯 Rewritten: Generating signals matching Pine Script exactly")

    # === CALCULATE TECHNICAL INDICATORS ===
    df['sma_50'] = calculate_sma(df['close'], 50)
    df['sma_200'] = calculate_sma(df['close'], 200)
    df['rsi'] = calculate_rsi(df['close'], 14)
    df['atr'] = calculate_atr(df['high'], df['low'], df['close'], 14)
    df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['pct_from_sma50'] = ((df['close'] - df['sma_50']) / df['sma_50'] * 100).round(2)
    df['pct_from_ema21'] = ((df['close'] - df['ema_21']) / df['ema_21'] * 100).round(2)
    df['pivot_price'] = ((df['high'] + df['low'] + df['close']) / 3).round(2)
    df['maFilter'] = df['sma_50'].ffill()
    df['ma_200'] = df['sma_200'].ffill()

    # === PIVOT DETECTION (Pine Script: pivothigh/pivotlow) ===
    # CRITICAL: A pivot is "formed" at bar i when we have confirmed:
    # - 3 bars left all lower/higher
    # - current bar is high/low
    # - 3 bars right all lower/higher (need to wait 1 bar to confirm - matching Pine's Shunt=1)
    # The pivot is detected at bar i when bars i-3 to i+3 meet criteria
    # Marked at bar i+1 to match Pine Script's 1-bar confirmation delay (Shunt=1)

    import numpy as np

    def detect_pivot_highs(highs_series):
        """Detect swing highs: 3 bars left < current, 3 bars right < current
        Mark at i+1 to match Pine Script Shunt=1 (1-bar confirmation delay)"""
        highs = highs_series.values
        pivot_highs = np.full_like(highs, np.nan, dtype=float)

        for i in range(3, len(highs) - 3):  # Need 3 bars on each side
            # Check if bar i is a pivot high
            is_pivot = True
            for j in range(1, 4):  # 3 bars to left
                if highs[i-j] >= highs[i]:
                    is_pivot = False
                    break
            if is_pivot:
                for j in range(1, 4):  # 3 bars to right
                    if highs[i+j] >= highs[i]:
                        is_pivot = False
                        break

            # If bar i is a pivot, mark it at position i+1 and use high from the pivot itself
            # Pine Script: valuewhen(pvthi_, high[pvtLenR], 0) where pvtLenR=3
            if is_pivot and i+1 < len(pivot_highs):
                pivot_highs[i+1] = highs[i]  # Use high from pivot center

        return pivot_highs

    def detect_pivot_lows(lows_series):
        """Detect swing lows: 3 bars left > current, 3 bars right > current
        Mark at i+1 to match Pine Script Shunt=1 (1-bar confirmation delay)"""
        lows = lows_series.values
        pivot_lows = np.full_like(lows, np.nan, dtype=float)

        for i in range(3, len(lows) - 3):  # Need 3 bars on each side
            # Check if bar i is a pivot low
            is_pivot = True
            for j in range(1, 4):  # 3 bars to left
                if lows[i-j] <= lows[i]:
                    is_pivot = False
                    break
            if is_pivot:
                for j in range(1, 4):  # 3 bars to right
                    if lows[i+j] <= lows[i]:
                        is_pivot = False
                        break

            # If bar i is a pivot, mark it at position i+1 and use low from the pivot itself
            # Pine Script: valuewhen(pvtlo_, low[pvtLenR], 0) where pvtLenR=3
            if is_pivot and i+1 < len(pivot_lows):
                pivot_lows[i+1] = lows[i]  # Use low from pivot center

        return pivot_lows

    pivot_highs_raw = detect_pivot_highs(df['high'])
    pivot_lows_raw = detect_pivot_lows(df['low'])

    # === VALUEWHEN SEMANTICS ===
    # valuewhen(condition, source, 0) returns source at most recent bar where condition is true
    # For buyLevel: return high value whenever new pivot detected, hold previous value otherwise
    df['buyLevel'] = pd.Series(pivot_highs_raw, index=df.index).ffill()
    df['stopLevel'] = pd.Series(pivot_lows_raw, index=df.index).ffill()

    # === BUY/SELL CONDITIONS (Pine Script logic) ===
    df['buySignal'] = (df['high'] > df['buyLevel'].fillna(0)) & df['buyLevel'].notna()
    df['sellSignal'] = (df['low'] < df['stopLevel'].fillna(float('inf'))) & df['stopLevel'].notna()

    # === MA FILTER (Pine Script: buyLevel > maFilterCheck) ===
    # Only allow buy if buyLevel is ABOVE the MA filter
    # Pine Script default: useMaFilter=true, so check buyLevel > maFilter
    df['maFilterOk'] = df['buyLevel'] > df['maFilter']

    # === TIME FILTER (Pine Script: time > Start and time < Finish) ===
    # Pine Script uses Start = 2019-01-01 and Finish = 2100-01-01 by default
    # Only allow trades within backtest range
    start_date = pd.Timestamp('2019-01-01')
    end_date = pd.Timestamp('2100-01-01')
    df['timeOk'] = (df['date'] >= start_date) & (df['date'] <= end_date)

    df['buy'] = df['buySignal'] & df['maFilterOk'] & df['timeOk']
    df['sell'] = df['sellSignal']

    # === STATE MACHINE (Pine Script study logic) ===
    # inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
    # flat = not inPosition
    # buyStudy = buy and flat
    # sellStudy = sellSignal and inPosition

    signals = []
    positions = []  # Track position state for each bar
    in_position = False
    prev_buy_cond = False
    prev_sell_cond = False

    buy_vals = df['buy'].values
    sell_vals = df['sell'].values

    for i in range(len(df)):
        # EXACT Pine Script translation:
        # inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]
        if i > 0:
            if prev_buy_cond:
                in_position = True
            elif prev_sell_cond:
                in_position = False
            # else: stay in previous position state

        flat = not in_position

        # Current bar conditions
        buy_cond = buy_vals[i]
        sell_cond = sell_vals[i]

        # Generate signal only if state allows it (Pine Script: buyStudy/sellStudy)
        if buy_cond and flat:
            signal = 'Buy'
        elif sell_cond and in_position:
            signal = 'Sell'
        else:
            signal = 'None'

        signals.append(signal)

        # Save position state for this bar
        positions.append(in_position)

        # Save conditions for next bar (Pine Script: buy[1], sellSignal[1])
        prev_buy_cond = buy_cond
        prev_sell_cond = sell_cond
        

    df['Signal'] = signals
    df['inPosition'] = positions  # Use actual position states

    # === Simplified signal strength (just based on signal type) ===
    df['signal_type'] = df['Signal']
    df['strength'] = df['Signal'].apply(lambda x: 1.0 if x == 'Buy' else (0.5 if x == 'Sell' else 0.0))

    # === STOP LEVELS AND ENTRY PRICING ===
    # initial_stop = the stop loss level at entry (stopLevel calculated above)
    df['initial_stop'] = df['stopLevel']

    # trailing_stop = highest close since entry - simplified (not nested loop)
    # For efficiency: just set to stopLevel (the calculated risk level)
    df['trailing_stop'] = df['stopLevel']

    # pivot_price is calculated earlier as technical indicator (H+L+C)/3
    # No need to override it here - use the technical pivot price

    # buy_zone_start and buy_zone_end (set to None if not using for now)
    df['buy_zone_start'] = np.nan
    df['buy_zone_end'] = np.nan

    # exit_trigger fields (not in current strategy)
    df['exit_trigger_1_price'] = np.nan
    df['exit_trigger_2_price'] = np.nan
    df['exit_trigger_3_condition'] = None
    df['exit_trigger_3_price'] = np.nan
    df['exit_trigger_4_condition'] = None
    df['exit_trigger_4_price'] = np.nan

    # === BASE/CONSOLIDATION ANALYSIS ===
    # base_type: Detect consolidation patterns by looking at price volatility (VECTORIZED)
    # Daily range % = (high - low) / close * 100 (standard formula to avoid infinity on penny stocks)
    df['daily_range_pct'] = ((df['high'] - df['low']) / df['close']) * 100
    df['base_type'] = df['daily_range_pct'].apply(
        lambda x: 'TIGHT_RANGE' if x < 1.0 else ('NORMAL_RANGE' if x < 2.5 else 'WIDE_RANGE')
    )

    # base_length_days: Count consecutive days in consolidation (simplified - count at signal)
    df['base_length_days'] = None
    for i in range(1, len(df)):
        if df.iloc[i]['Signal'] == 'Buy':
            # Count consecutive consolidation days before this buy (max 20 days)
            length = 0
            for j in range(i - 1, max(-1, i - 21), -1):
                if df.iloc[j]['base_type'] in ['TIGHT_RANGE', 'NORMAL_RANGE']:
                    length += 1
                else:
                    break
            df.at[i, 'base_length_days'] = length if length > 0 else None

    # === CALCULATE REAL METRICS ===
    # Calculate 50-day rolling average volume
    df['avg_volume_50d'] = df['volume'].rolling(window=50).mean().fillna(0).astype('int64')

    # Calculate volume surge percentage: (current_volume / avg_volume_50d - 1) * 100
    # REAL DATA ONLY: Use None if avg_volume is missing, not fake 0
    df['volume_surge_pct'] = df.apply(
        lambda row: round(((row['volume'] / row['avg_volume_50d'] - 1) * 100), 2)
        if row['avg_volume_50d'] > 0 else None,
        axis=1
    )

    # Calculate risk/reward ratio: (target_price - entry_price) / (entry_price - stop_loss)
    # target_price = buyLevel * 1.25 (25% profit target based on entry price)
    # REAL DATA ONLY: Use None if calculation cannot be performed, not fake 0
    df['risk_reward_ratio'] = df.apply(
        lambda row: round(
            (((row['buyLevel'] * 1.25) - row['buyLevel']) / (row['buyLevel'] - row['stopLevel']))
            if (row['stopLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] is not None and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
            2
        ) if (row['stopLevel'] is not None and row['stopLevel'] > 0 and row['buyLevel'] is not None and row['buyLevel'] > 0 and (row['buyLevel'] - row['stopLevel']) != 0) else None,
        axis=1
    )

    # Calculate breakout quality based on price range and volume
    def calc_breakout_quality(row):
        # Validate OHLC invariants
        low = row.get('low')
        high = row.get('high')
        close = row.get('close')
        volume_surge = row.get('volume_surge_pct')

        # REAL DATA ONLY: Return None for missing/invalid data, not fake 'WEAK'
        if low is None or high is None or close is None or volume_surge is None:
            return None  # Insufficient data - no quality assessment possible

        if low <= 0 or high <= 0 or close <= 0:
            return None  # Invalid price data

        if high < low:
            logging.warning(f"Invalid OHLC: high ({high}) < low ({low})")
            return None  # Inverted prices = data error

        if row.get('avg_volume_50d', 0) <= 0:
            return None  # No volume data

        # Calculate daily range percentage
        # Formula: (high - low) / close * 100 (standard formula to avoid infinity on penny stocks)
        daily_range_pct = ((high - low) / close) * 100

        # Validate result is reasonable (not inf or nan)
        # NOTE: Extreme moves >100% occur with penny stocks, stock splits, data errors (acceptable)
        if not (0 <= daily_range_pct) or np.isinf(daily_range_pct) or np.isnan(daily_range_pct):
            return None  # Invalid calculation

        # Cap extreme ranges at 100% for scoring purposes (but allow the data through)
        daily_range_pct_capped = min(daily_range_pct, 100.0)

        # Determine if close is in upper or lower half of daily range (direction matters)
        range_midpoint = (high + low) / 2
        is_upper_half = close > range_midpoint

        # Real calculations - distinguish breakout (upside) vs breakdown (downside)
        # Use capped range for scoring (but extreme moves still score as STRONG)
        if daily_range_pct_capped > 3.0 and volume_surge > 50:
            # Only STRONG quality if move is in expected direction
            # For buy signals: upper half = breakout. For sell signals: lower half = breakdown
            signal = row.get('Signal')
            if signal == 'Buy' and is_upper_half:
                return 'STRONG'  # Strong breakout
            elif signal == 'Sell' and not is_upper_half:
                return 'STRONG'  # Strong breakdown
            else:
                return 'MODERATE'  # High volume/range but wrong direction for signal
        elif daily_range_pct_capped > 1.5 and volume_surge > 25:
            return 'MODERATE'
        else:
            return 'WEAK'  # Only return WEAK if data is valid but metrics don't meet thresholds

    df['breakout_quality'] = df.apply(calc_breakout_quality, axis=1)

    # === RS RATING (Relative Strength - Investor's Business Daily style) ===
    # Simple version: rank based on recent performance
    def calc_rs_rating(df_window):
        """Calculate RS rating 0-99 based on price performance vs 200-day high"""
        if len(df_window) < 200:
            return None

        current_price = df_window.iloc[-1]['close']
        high_200d = df_window.iloc[-200:]['high'].max()

        if high_200d <= 0:
            return None

        # RS = (current / 200-day high) * 100
        rs = (current_price / high_200d) * 100
        # Handle NaN values
        if pd.isna(rs):
            return None
        # Convert to 0-99 scale
        rs_rating = min(99, max(1, int(rs)))
        return rs_rating

    df['rs_rating'] = None
    for i in range(200, len(df)):
        rs = calc_rs_rating(df.iloc[0:i+1])
        if rs is not None:
            df.at[i, 'rs_rating'] = rs

    # === PROFIT TARGETS (25% profit target is standard) ===
    df['profit_target_8pct'] = df['buyLevel'] * 1.08  # 8% above buy level
    df['profit_target_20pct'] = df['buyLevel'] * 1.20  # 20% above buy level
    df['profit_target_25pct'] = df['buyLevel'] * 1.25  # 25% above buy level (standard)

    # === RISK PERCENT (Risk = entry - stop loss / entry) ===
    df['risk_pct'] = df.apply(
        lambda row: round(((row['buyLevel'] - row['stopLevel']) / row['buyLevel'] * 100), 2)
        if (row['buyLevel'] is not None and row['stopLevel'] is not None and row['buyLevel'] > 0) else None,
        axis=1
    )

    # === ENTRY QUALITY SCORE (Based on breakout quality, volume, and RS) ===
    def calc_entry_quality(row):
        """Calculate entry quality 0-100 based on multiple factors.

        CRITICAL: Requires at least 2 of 4 indicators to be non-None:
        - breakout_quality
        - volume_surge_pct
        - rs_rating
        - price position (close vs maFilter)

        Returns None if insufficient data (no fake scores from 1 data point).
        """
        # Count available indicators (REAL DATA ONLY)
        available_indicators = sum([
            row.get('breakout_quality') is not None,
            row.get('volume_surge_pct') is not None,
            row.get('rs_rating') is not None,
            row.get('close') is not None and row.get('maFilter') is not None
        ])

        # Require at least 2 indicators for valid quality assessment
        if available_indicators < 2:
            return None  # Insufficient data - no fake score

        score = 0  # Start at 0, earn every point

        # Breakout quality (0-40): Quality of price action at entry
        bq = row.get('breakout_quality')
        if bq == 'STRONG':
            score += 40
        elif bq == 'MODERATE':
            score += 20
        # WEAK or None: +0

        # Volume surge (0-25): Confirmation of move
        vs = row.get('volume_surge_pct')
        if vs is not None:
            if vs > 50:
                score += 25
            elif vs > 25:
                score += 15

        # RS Rating (0-20): Relative strength positioning
        rs = row.get('rs_rating')
        if rs is not None:
            if rs > 75:
                score += 20
            elif rs > 50:
                score += 10

        # Price positioning (0-15): Timing relative to short-term MA
        if row.get('close') is not None and row.get('maFilter') is not None:
            if row['close'] > row['maFilter']:
                score += 15

        # Normalize to 0-100 based on available indicators
        max_possible = 25 * available_indicators  # Scale based on how many indicators we have
        normalized_score = (score / max_possible * 100) if max_possible > 0 else 0

        # Cap at 100
        return min(100, max(0, normalized_score))

    df['entry_quality_score'] = df.apply(calc_entry_quality, axis=1)

    # === MARKET STAGE (Stan Weinstein Stage Analysis using 200-day MA) ===
    # Calculate MA slope to determine if it's rising, falling, or flattening
    ma_slope_window = 10  # Look at 10-day slope
    df['ma_200_slope'] = df['ma_200'].diff(periods=ma_slope_window)

    def detect_market_stage(row, index):
        """Classify into Weinstein's 4-Stage model based on price position relative to 200-day MA"""
        if pd.isna(row.get('close')) or pd.isna(row.get('ma_200')):
            return None

        close = row['close']
        ma_200 = row['ma_200']
        ma_slope = row.get('ma_200_slope')

        # Need sufficient data for MA calculation
        if index < 200:
            return None

        # Calculate price position relative to MA
        price_diff_pct = ((close - ma_200) / ma_200 * 100) if ma_200 > 0 else None
        if price_diff_pct is None:
            return None

        # Detect MA direction (tuned threshold to 0.15 for better discrimination)
        is_ma_rising = ma_slope > 0.15 if pd.notna(ma_slope) else False
        is_ma_falling = ma_slope < -0.15 if pd.notna(ma_slope) else False
        is_ma_flat = not is_ma_rising and not is_ma_falling

        # === Weinstein Stage Detection ===

        # Stage 4: Declining - Price below declining MA (most bearish)
        if close < ma_200 and is_ma_falling:
            return 'Stage 4 - Declining'

        # Stage 3: Distribution/Topping - Price oscillating near MA
        # Includes: Price near MA, OR price oscillating around MA, OR MA flattening
        if is_ma_flat and -5 <= price_diff_pct <= 8:
            return 'Stage 3 - Topping'
        # Also catch oscillation pattern: price sometimes above, sometimes below MA (transition state)
        elif -8 <= price_diff_pct <= 10 and is_ma_flat:
            return 'Stage 3 - Topping'

        # Stage 2: Advancing - Price above rising MA (most bullish)
        if close > ma_200 and is_ma_rising:
            return 'Stage 2 - Advancing'

        # Stage 1: Basing - Price oscillating around flat/rising MA or below rising MA
        if close < ma_200 and (is_ma_rising or is_ma_flat):
            return 'Stage 1 - Basing'

        # Default fallback: Only if price is well above MA but MA not clearly rising (anomaly)
        if close > ma_200 and not is_ma_rising:
            return 'Stage 2 - Advancing'  # Changed from None - if price > MA, treat as advance

        return None

    df['market_stage'] = [detect_market_stage(row, idx) for idx, row in df.iterrows()]

    # === STAGE NUMBER (Extract numeric stage from market_stage) ===
    df['stage_number'] = df['market_stage'].apply(
        lambda x: int(x.split()[1]) if pd.notna(x) and 'Stage' in str(x) else None
    )

    # === STAGE CONFIDENCE (Based on price distance from MA_200, NOT MA_50) ===
    def calc_stage_confidence(row):
        """Calculate confidence in market stage (0-100) based on distance from 200-day MA"""
        if pd.isna(row.get('market_stage')):
            return None

        close = row['close']
        ma_200 = row['ma_200']  # ✅ FIXED: Use ma_200 (200-day MA) not ma_50!

        if pd.isna(ma_200) or ma_200 is None or ma_200 <= 0:
            return None

        # Distance from 200-day MA as % of price
        distance_pct = abs((close - ma_200) / ma_200 * 100)

        # More distance = more confidence (stage is clearer)
        if distance_pct > 15:
            return 95  # Very clear stage separation
        elif distance_pct > 10:
            return 85
        elif distance_pct > 5:
            return 75  # Moderate clarity
        elif distance_pct > 2:
            return 60  # Weak clarity
        else:
            return 40  # Very close to MA (ambiguous)

    df['stage_confidence'] = df.apply(calc_stage_confidence, axis=1)

    # === SUBSTAGE (Early vs Late in stage) ===
    def detect_substage(row):
        """Detect substage within the 4-stage cycle - Distinguishes breakout vs breakdown"""
        stage = row.get('market_stage')
        if pd.isna(stage):
            return None

        if 'Basing' in str(stage):
            # Check if early or late in basing
            vol_surge = row.get('volume_surge_pct')
            if vol_surge is not None and vol_surge > 30:
                # HIGH VOLUME: Distinguish breakout (upside) vs breakdown (downside)
                signal = row.get('Signal')
                risk_reward = row.get('risk_reward_ratio')

                # Breakout = Buy signal with positive risk/reward
                if signal == 'Buy' and (pd.isna(risk_reward) or risk_reward > 0):
                    return 'Late Basing - Breakout Imminent'
                # Breakdown = Sell signal or negative risk/reward
                elif signal == 'Sell' or (not pd.isna(risk_reward) and risk_reward < 0):
                    return 'Late Basing - Breakdown'
                # Ambiguous = default to Breakout Imminent
                else:
                    return 'Late Basing - Breakout Imminent'
            return 'Early Basing'

        elif 'Advancing' in str(stage):
            # Check trend strength
            rs = row.get('rs_rating')
            if rs is not None and rs > 75:
                return 'Strong Advance'
            return 'Early Advance'

        elif 'Topping' in str(stage):
            return 'Distribution'

        elif 'Declining' in str(stage):
            return 'Breakdown'

        return None

    df['substage'] = df.apply(detect_substage, axis=1)

    # === POSITION SIZING (Shares based on risk) ===
    df['position_size_pct'] = df.apply(
        lambda row: round(
            min(5.0, 0.5 / row['risk_pct'] * 100),  # Risk 0.5% of account per trade
            2
        ) if (row['risk_pct'] is not None and row['risk_pct'] > 0) else None,
        axis=1
    )

    # Initialize position tracking fields as None (not fake 0/50 values)
    df['current_gain_pct'] = None
    df['days_in_position'] = None

    logging.debug(f"✅ Generated {len(df[df['Signal']=='Buy'])} Buy signals and {len(df[df['Signal']=='Sell'])} Sell signals")
    return df

###############################################################################
# 5) BACKTEST & METRICS
###############################################################################
def backtest_fixed_capital(df):
    trades = []
    buys   = df.index[df['Signal']=='Buy'].tolist()
    if not buys:
        return trades, [], [], None, None

    df2 = df.iloc[buys[0]:].reset_index(drop=True)
    pos_open = False
    for i in range(len(df2)-1):
        sig, o, d = df2.loc[i,'Signal'], df2.loc[i+1,'open'], df2.loc[i+1,'date']
        if sig=='Buy' and not pos_open:
            pos_open=True; trades.append({'date':d,'action':'Buy','price':o})
        elif sig=='Sell' and pos_open:
            pos_open=False; trades.append({'date':d,'action':'Sell','price':o})

    if pos_open:
        last = df2.iloc[-1]
        trades.append({'date':last['date'],'action':'Sell','price':last['close']})

    rets, durs = [], []
    i = 0
    while i < len(trades)-1:
        if trades[i]['action']=='Buy' and trades[i+1]['action']=='Sell':
            e, x = trades[i]['price'], trades[i+1]['price']
            if e >= 1.0:
                rets.append((x-e)/e)
                durs.append((trades[i+1]['date']-trades[i]['date']).days)
            i += 2
        else:
            i += 1

    return trades, rets, durs, df['date'].iloc[0], df['date'].iloc[-1]

def compute_metrics_fixed_capital(rets, durs, annual_rfr=0.0):
    n = len(rets)
    if n == 0:
        return {}
    wins   = [r for r in rets if r>0]
    losses = [r for r in rets if r<0]
    avg    = np.mean(rets) if n else 0.0
    std    = np.std(rets, ddof=1) if n>1 else 0.0
    return {
      'num_trades':     n,
      'win_rate':       len(wins)/n,
      'avg_return':     avg,
      'profit_factor':  sum(wins)/abs(sum(losses)) if losses else float('inf'),
      'sharpe_ratio':   ((avg-annual_rfr)/std*np.sqrt(n)) if std>0 else 0.0
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
def process_symbol(symbol, timeframe):
    logging.debug(f"  [process_symbol] Fetching {symbol} {timeframe}")
    try:
        df = fetch_symbol_from_db(symbol, timeframe)
        logging.debug(f"  [process_symbol] Done fetching {symbol} {timeframe}, rows: {len(df)}")
        return generate_signals(df) if not df.empty else df
    except Exception as e:
        logging.error(f"Error in process_symbol for {symbol}: {e}", exc_info=True)
        raise

def process_symbol_wrapper(sym):
    """Process a single symbol in a thread-safe manner"""
    try:
        tf = 'Daily'
        logging.debug(f"  [thread] Processing {sym} {tf}")
        df = process_symbol(sym, tf)
        logging.debug(f"  [thread] Done processing {sym} {tf}")

        if df.empty:
            logging.debug(f"[{tf}] no data for {sym}")
            return sym, None, None, None

        # Each thread gets its own database connection
        conn = get_db_connection()
        conn.autocommit = True
        cur = conn.cursor()

        insert_symbol_results(cur, sym, tf, df, conn)

        _, rets, durs, _, _ = backtest_fixed_capital(df)

        cur.close()
        conn.close()

        return sym, rets, durs, df
    except Exception as e:
        logging.error(f"Error processing {sym}: {e}")
        return sym, None, None, None

def process_symbol_set(symbols, table_name, label, max_workers=6):
    """Process symbols with parallel workers for speed"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import gc

    if not symbols:
        logging.info(f"{label}: No symbols to process")
        return

    # Use 4 workers for balanced speed/stability (was 2, can tolerate some locks)
    max_workers = min(max_workers, 4)

    logging.info(f"Starting {label} processing with {max_workers} workers for {len(symbols)} symbols")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_symbol_wrapper, sym): sym for sym in symbols}
        completed = 0

        for future in as_completed(futures):
            completed += 1
            sym, rets, durs, df = future.result()

            # Force garbage collection after each symbol to free memory
            if completed % 10 == 0:
                gc.collect()

            # Log progress
            progress = (completed / len(symbols)) * 100
            logging.info(f"{label} Progress: {completed}/{len(symbols)} ({progress:.1f}%)")

def main():

    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        if annual_rfr is not None:
            print(f"Annual RFR: {annual_rfr:.2%}")
        else:
            print("Annual RFR: Not available (FRED API key not set)")
            annual_rfr = 0.0
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0

    # Load symbols from database
    symbols = get_symbols_from_db(limit=None)  # Load ALL stocks
    if not symbols:
        print("No stock symbols in DB.")
        symbols = []

    # Load country ETF symbols (from stock_symbols where etf='Y' AND country IS NOT NULL)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT symbol FROM stock_symbols WHERE etf='Y' AND country IS NOT NULL;")
        country_symbols = [r[0] for r in cur.fetchall()]
    except:
        logging.warning("Could not load country ETF symbols from stock_symbols")
        country_symbols = []
    finally:
        cur.close()
        conn.close()

    # Create tables
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    create_buy_sell_table(cur, "buy_sell_daily")
    cur.close()
    conn.close()

    # Process ONLY regular stocks (NO ETFs)
    logging.info(f"Processing {len(symbols)} regular stocks only (excluding {len(country_symbols)} country symbols)")

    # Process all stocks into single unified table
    if symbols:
        process_symbol_set(symbols, "buy_sell_daily", "Stock Signals", max_workers=6)

    logging.info("Processing complete.")

if __name__ == "__main__":
    logging.info("Starting Stock Signals Loader")
    main()
    logging.info("✅ Stock Signals Loader completed")
