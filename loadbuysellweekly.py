# Updated: 2025-10-07 17:09 - Trigger deployment
# Deployment trigger: 2025-10-07 17:10:06
# Critical fixes: timeframe filtering + query optimization indexes
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
SCRIPT_NAME = "loadbuysellweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

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
    DB_NAME = os.environ.get("DB_NAME", "stocks")
    DB_USER = os.environ.get("DB_USER", "stocks")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "stocks")


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
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        q = """
          SELECT symbol
            FROM stock_symbols
           WHERE exchange IN ('NASDAQ','New York Stock Exchange')
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
    cur.execute("DROP TABLE IF EXISTS buy_sell_weekly;")
    cur.execute(
        """
      CREATE TABLE buy_sell_weekly (
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
        pct_from_sma_50 NUMERIC(6,2),
        pct_from_sma_200 NUMERIC(6,2),
        volume_ratio NUMERIC(6,2),
        volume_analysis VARCHAR(30),
        entry_quality_score INTEGER,
        profit_target_8pct REAL,
        profit_target_20pct REAL,
        current_gain_loss_pct NUMERIC(6,2),
        risk_pct NUMERIC(6,2),
        position_size_recommendation NUMERIC(18,2),
        passes_minervini_template BOOLEAN DEFAULT FALSE,
        rsi NUMERIC(6,2),
        adx NUMERIC(6,2),
        UNIQUE(symbol, timeframe, date)
      );
    """
    )
    # Create indexes for query performance
    logging.info("Creating indexes on buy_sell_weekly...")
    cur.execute("CREATE INDEX idx_buy_sell_weekly_date ON buy_sell_weekly(date DESC);")
    cur.execute("CREATE INDEX idx_buy_sell_weekly_symbol ON buy_sell_weekly(symbol);")
    cur.execute("CREATE INDEX idx_buy_sell_weekly_timeframe ON buy_sell_weekly(timeframe);")
    cur.execute("CREATE INDEX idx_buy_sell_weekly_signal ON buy_sell_weekly(signal);")
    logging.info("Indexes created successfully")


def insert_symbol_results(cur, symbol, timeframe, df):
    insert_q = """
      INSERT INTO buy_sell_weekly (
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
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
            WHERE bsd.symbol = %(symbol)s AND bsd.timeframe = %(timeframe)s
        ),
        technical_data AS (
            SELECT
                td.symbol, td.date::date as date,
                td.sma_20, td.sma_50, td.sma_150, td.sma_200,
                td.ema_21, td.rsi, td.adx, td.atr,
                NULL as mansfield_rs,
                LAG(td.sma_20, 5) OVER (ORDER BY td.date) as sma_20_prev,
                LAG(td.sma_50, 5) OVER (ORDER BY td.date) as sma_50_prev,
                LAG(td.sma_200, 10) OVER (ORDER BY td.date) as sma_200_prev
            FROM {tech_table} td
            WHERE td.symbol = %(symbol)s
        ),
        volume_data AS (
            SELECT
                pd.symbol, pd.date,
                AVG(pd.volume) OVER (
                    ORDER BY pd.date
                    ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                ) as volume_avg_50
            FROM {price_table} pd
            WHERE pd.symbol = %(symbol)s
        ),
        high_52week_data AS (
            SELECT
                pd.symbol, pd.date,
                MAX(pd.high) OVER (
                    ORDER BY pd.date
                    ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                ) as high_52week
            FROM {price_table} pd
            WHERE pd.symbol = %(symbol)s
        ),
        calculated_metrics AS (
            SELECT
                sd.symbol, sd.date,
                -- Sell level (opposite of buy)
                CASE WHEN sd.signal = 'SELL' THEN sd.buylevel ELSE NULL END as selllevel,

                -- Target prices
                CASE
                    WHEN sd.signal = 'BUY' AND sd.buylevel IS NOT NULL THEN sd.buylevel * 1.25
                    WHEN sd.signal = 'SELL' AND sd.buylevel IS NOT NULL THEN sd.buylevel * 0.85
                    ELSE NULL
                END as target_price,

                sd.current_price,

                -- Risk/Reward ratio
                CASE
                    WHEN sd.signal = 'BUY' AND sd.buylevel IS NOT NULL AND sd.stoplevel IS NOT NULL
                    THEN ROUND((((sd.buylevel * 1.25) - sd.buylevel) / NULLIF((sd.buylevel - sd.stoplevel), 0))::NUMERIC, 2)
                    WHEN sd.signal = 'SELL' AND sd.buylevel IS NOT NULL AND sd.stoplevel IS NOT NULL
                    THEN ROUND((((sd.buylevel - (sd.buylevel * 0.85))) / NULLIF((sd.stoplevel - sd.buylevel), 0))::NUMERIC, 2)
                    ELSE NULL
                END as risk_reward_ratio,

                -- Market stage (enhanced with confidence and substage)
                (SELECT stage FROM calculate_enhanced_stage(
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
                    NULL
                )) as market_stage,

                -- Stage confidence score
                (SELECT confidence FROM calculate_enhanced_stage(
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
                    NULL
                )) as stage_confidence,

                -- Substage
                (SELECT substage FROM calculate_enhanced_stage(
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
                    NULL
                )) as substage,

                -- SATA Score
                (SELECT sata_score FROM calculate_enhanced_stage(
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
                    NULL
                )) as sata_score,

                -- Stage Number (extract from stage text: "Stage 2 - Advancing" -> 2)
                CAST(SUBSTRING(
                    (SELECT stage FROM calculate_enhanced_stage(
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
                        NULL
                    )) FROM 'Stage ([0-9])'
                ) AS INTEGER) as stage_number,

                -- Mansfield RS from technical data
                NULL as mansfield_rs,

                -- Distance from MAs
                ROUND(((sd.current_price - td.ema_21) / NULLIF(td.ema_21, 0) * 100)::NUMERIC, 2) as pct_from_ema_21,
                ROUND(((sd.current_price - td.sma_50) / NULLIF(td.sma_50, 0) * 100)::NUMERIC, 2) as pct_from_sma_50,
                ROUND(((sd.current_price - td.sma_200) / NULLIF(td.sma_200, 0) * 100)::NUMERIC, 2) as pct_from_sma_200,

                -- Volume analysis (standardized labels)
                ROUND((sd.volume::NUMERIC / NULLIF(vd.volume_avg_50, 1))::NUMERIC, 2) as volume_ratio,
                CASE
                    WHEN (sd.volume::NUMERIC / NULLIF(vd.volume_avg_50, 1)) >= 2.0 THEN 'Very High'
                    WHEN (sd.volume::NUMERIC / NULLIF(vd.volume_avg_50, 1)) >= 1.5 THEN 'High'
                    WHEN (sd.volume::NUMERIC / NULLIF(vd.volume_avg_50, 1)) >= 0.9 THEN 'Average'
                    ELSE 'Low'
                END as volume_analysis,

                -- Entry quality score
                (
                    CASE WHEN calculate_weinstein_stage(
                        sd.current_price, td.sma_50, td.sma_200, td.sma_50_prev, td.sma_200_prev,
                        td.adx, sd.volume, vd.volume_avg_50::BIGINT
                    ) = 'Stage 2 - Advancing' THEN 40 ELSE 0 END +
                    CASE WHEN ABS((sd.current_price - td.ema_21) / NULLIF(td.ema_21, 0) * 100) <= 2 THEN 20 ELSE 0 END +
                    CASE WHEN (sd.volume::NUMERIC / NULLIF(vd.volume_avg_50, 1)) >= 1.5 THEN 20 ELSE 0 END +
                    CASE WHEN td.rsi BETWEEN 40 AND 70 THEN 20 ELSE 0 END
                )::INTEGER as entry_quality_score,

                -- Profit targets
                CASE WHEN sd.buylevel IS NOT NULL THEN (sd.buylevel * 1.08)::REAL ELSE NULL END as profit_target_8pct,
                CASE WHEN sd.buylevel IS NOT NULL THEN (sd.buylevel * 1.20)::REAL ELSE NULL END as profit_target_20pct,

                -- Current gain/loss
                CASE
                    WHEN sd.inposition = TRUE AND sd.buylevel IS NOT NULL
                    THEN ROUND(((sd.current_price - sd.buylevel) / NULLIF(sd.buylevel, 0) * 100)::NUMERIC, 2)
                    ELSE NULL
                END as current_gain_loss_pct,

                -- Risk %%
                CASE
                    WHEN sd.buylevel IS NOT NULL AND sd.stoplevel IS NOT NULL
                    THEN ROUND(((sd.buylevel - sd.stoplevel) / NULLIF(sd.buylevel, 0) * 100)::NUMERIC, 2)
                    ELSE NULL
                END as risk_pct,

                -- Position size
                CASE
                    WHEN sd.buylevel IS NOT NULL AND sd.stoplevel IS NOT NULL
                    THEN ROUND((1000.0 / NULLIF((sd.buylevel - sd.stoplevel), 0))::NUMERIC, 2)
                    ELSE NULL
                END as position_size_recommendation,

                -- Minervini template
                CASE
                    WHEN sd.current_price > td.sma_50 AND sd.current_price > td.sma_150 AND
                         sd.current_price > td.sma_200 AND td.sma_50 > td.sma_150 AND
                         td.sma_150 > td.sma_200 AND
                         ((sd.current_price - td.sma_200) / NULLIF(td.sma_200, 0) * 100) BETWEEN 0 AND 30
                    THEN TRUE
                    ELSE FALSE
                END as passes_minervini_template,

                -- Technical indicators
                td.rsi::NUMERIC(6,2), td.adx::NUMERIC(6,2), td.atr::NUMERIC(10,4),

                -- Daily range
                ROUND(((sd.high - sd.low) / NULLIF(sd.low, 0) * 100)::NUMERIC, 2) as daily_range_pct,

                -- Volatility profile based on ATR and daily range
                CASE
                    WHEN td.atr IS NOT NULL AND ((sd.high - sd.low) / NULLIF(sd.low, 0) * 100) > 3.0 THEN 'high'
                    WHEN td.atr IS NOT NULL AND ((sd.high - sd.low) / NULLIF(sd.low, 0) * 100) < 1.5 THEN 'low'
                    ELSE 'medium'
                END as volatility_profile

            FROM signal_data sd
            JOIN technical_data td ON sd.symbol = td.symbol AND sd.date = td.date
            JOIN volume_data vd ON sd.symbol = vd.symbol AND sd.date = vd.date
            JOIN high_52week_data hd ON sd.symbol = hd.symbol AND sd.date = hd.date
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
            profit_target_8pct = cm.profit_target_8pct,
            profit_target_20pct = cm.profit_target_20pct,
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

        # Parameters: named dict for all placeholders
        cur.execute(update_sql, {'symbol': symbol, 'timeframe': timeframe})
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
            logging.error(f"[fetch_symbol_from_db] Fallback SQL error for {symbol} {timeframe}: {fallback_e}")
            rows = []
    except Exception as e:
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
# 4) SIGNAL GENERATION & IN-POSITION LOGIC
###############################################################################
def generate_signals(df, atrMult=1.0, useADX=True, adxS=30, adxW=20):
    df["TrendOK"] = df["close"] > df["sma_50"]
    df["RSI_prev"] = df["rsi"].shift(1)
    df["rsiBuy"] = (df["rsi"] > 50) & (df["RSI_prev"] <= 50)
    df["rsiSell"] = (df["rsi"] < 50) & (df["RSI_prev"] >= 50)
    df["LastPH"] = df["pivot_high"].shift(1).ffill()
    df["LastPL"] = df["pivot_low"].shift(1).ffill()
    df["stopBuffer"] = df["atr"] * atrMult
    df["stopLevel"] = df["LastPL"] - df["stopBuffer"]
    df["buyLevel"] = df["LastPH"]
    df["breakoutBuy"] = df["high"] > df["buyLevel"]
    df["breakoutSell"] = df["low"] < df["stopLevel"]

    if useADX:
        flt = (df["adx"] > adxS) | (
            (df["adx"] > adxW) & (df["adx"] > df["adx"].shift(1))
        )
        adxOK = (df["plus_di"] > df["minus_di"]) & flt
        exitD = (df["plus_di"].shift(1) > df["minus_di"].shift(1)) & (
            df["plus_di"] < df["minus_di"]
        )
        df["finalBuy"] = (df["rsiBuy"] & df["TrendOK"] & adxOK) | df["breakoutBuy"]
        df["finalSell"] = df["rsiSell"] | df["breakoutSell"] | exitD
    else:
        df["finalBuy"] = (df["rsiBuy"] & df["TrendOK"]) | df["breakoutBuy"]
        df["finalSell"] = df["rsiSell"] | df["breakoutSell"]

    in_pos, sigs, pos = False, [], []
    for i in range(len(df)):
        if in_pos and df.loc[i, "finalSell"]:
            sigs.append("Sell")
            in_pos = False
        elif not in_pos and df.loc[i, "finalBuy"]:
            sigs.append("Buy")
            in_pos = True
        else:
            sigs.append("None")
        pos.append(in_pos)

    df["Signal"] = sigs
    df["inPosition"] = pos
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
def process_symbol(symbol, timeframe):
    logging.info(f"  [process_symbol] Fetching {symbol} {timeframe}")
    df = fetch_symbol_from_db(symbol, timeframe)
    logging.info(
        f"  [process_symbol] Done fetching {symbol} {timeframe}, rows: {len(df)}"
    )
    return generate_signals(df) if not df.empty else df


def main():

    try:
        annual_rfr = get_risk_free_rate_fred(FRED_API_KEY)
        print(f"Annual RFR: {annual_rfr:.2%}")
    except Exception as e:
        logging.warning(f"Failed to get risk-free rate: {e}")
        annual_rfr = 0.0

    symbols = get_symbols_from_db()  # Process all symbols
    if not symbols:
        print("No symbols in DB.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    create_buy_sell_table(cur)
    conn.commit()

    results = {
        "Daily": {"rets": [], "durs": []},
        "Weekly": {"rets": [], "durs": []},
        "Monthly": {"rets": [], "durs": []},
    }

    for sym in symbols:
        logging.info(f"=== {sym} ===")
        # Only process Weekly timeframe for this loader
        tf = "Weekly"
        logging.info(f"  [main] Processing {sym} {tf}")
        df = process_symbol(sym, tf)
        logging.info(f"  [main] Done processing {sym} {tf}")
        if df.empty:
            logging.info(f"[{tf}] no data")
            continue
        insert_symbol_results(cur, sym, tf, df)
        conn.commit()

        # Calculate swing trading metrics for this symbol (optional - may fail if columns don't exist)
        try:
            logging.info(f"  [main] Calculating swing metrics for {sym} {tf}")
            update_swing_metrics_for_symbol(cur, sym, tf)
            conn.commit()
            logging.info(f"  [main] Done calculating swing metrics for {sym} {tf}")
        except Exception as e:
            logging.warning(f"  [main] Swing metrics calculation skipped for {sym} {tf}: {e}")
            conn.rollback()

        _, rets, durs, _, _ = backtest_fixed_capital(df)
        results[tf]["rets"].extend(rets)
        results[tf]["durs"].extend(durs)
        analyze_trade_returns_fixed_capital(rets, durs, f"[{tf}] {sym}", annual_rfr)

    logging.info("=========================")
    logging.info(" AGGREGATED PERFORMANCE (FIXED $10k PER TRADE) ")
    logging.info("=========================")
    # Only process Weekly timeframe for this loader
    tf = "Weekly"
    analyze_trade_returns_fixed_capital(
        results[tf]["rets"], results[tf]["durs"], f"[{tf} (Overall)]", annual_rfr
    )

    logging.info("Processing complete.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
