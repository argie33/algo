#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import calendar
import boto3
from psycopg2.extras import DictCursor, execute_values

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "buy_sell_signals.py"
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

log_mem("after imports")

# -------------------------------
# 0) FETCH DB CREDENTIALS & CONNECT
# -------------------------------
log_mem("start")
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

log_mem("before secrets fetch")
sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
secrets = json.loads(resp["SecretString"])
log_mem("after secrets fetch")

pg_host     = secrets["host"]
pg_port     = secrets.get("port", 5432)
pg_db       = secrets["dbname"]
pg_user     = secrets["username"]
pg_password = secrets["password"]

log_mem("before DB connect")
conn = psycopg2.connect(
    host=pg_host,
    port=pg_port,
    dbname=pg_db,
    user=pg_user,
    password=pg_password
)
cursor = conn.cursor(cursor_factory=DictCursor)
log_mem("after DB connect")

# -------------------------------
# Prepare date ranges
# -------------------------------
log_mem("before date calc")
today = datetime.now()
current_month_start = today.replace(day=1)
last_day            = calendar.monthrange(today.year, today.month)[1]
current_month_end   = today.replace(day=last_day)
current_week_start  = today - timedelta(days=today.weekday())
current_week_end    = current_week_start + timedelta(days=6)
last_4_weeks_start  = current_week_start - timedelta(weeks=3)
last_4_weeks_end    = current_week_end
two_weeks_start     = today - timedelta(days=13)
two_weeks_end       = today
log_mem("after date calc")

# -------------------------------
# 1) READ SYMBOLS
# -------------------------------
def get_symbols(limit=None):
    q = """
      SELECT symbol
      FROM stock_symbols
      WHERE exchange IN ('NASDAQ','New York Stock Exchange')
    """
    if limit:
        q += " LIMIT %s"
        cursor.execute(q, (limit,))
    else:
        cursor.execute(q)
    return [r["symbol"] for r in cursor.fetchall()]

# -------------------------------
# 2) CREATE buy_sell TABLE
# -------------------------------
def create_buy_sell_table():
    cursor.execute("DROP TABLE IF EXISTS buy_sell;")
    cursor.execute("""
    CREATE TABLE buy_sell (
      id         SERIAL PRIMARY KEY,
      symbol     VARCHAR(20),
      timeframe  VARCHAR(10),
      date       DATE,
      open       DOUBLE PRECISION,
      high       DOUBLE PRECISION,
      low        DOUBLE PRECISION,
      close      DOUBLE PRECISION,
      volume     BIGINT,
      signal     VARCHAR(10),
      buylevel   DOUBLE PRECISION,
      stoplevel  DOUBLE PRECISION,
      inposition BOOLEAN,
      UNIQUE(symbol, timeframe, date)
    );
    """)
    conn.commit()

# -------------------------------
# 3) FETCH PRICE + TECH DATA
# -------------------------------
def fetch_data(symbol, timeframe, start_date=None, end_date=None):
    price_table = {
        "Daily":   "price_daily",
        "Weekly":  "price_weekly",
        "Monthly": "price_monthly"
    }[timeframe]
    tech_table = {
        "Daily":   "technical_data_daily",
        "Weekly":  "technical_data_weekly",
        "Monthly": "technical_data_monthly"
    }[timeframe]

    q = f"""
    SELECT
      p.date, p.open, p.high, p.low, p.close, p.volume,
      t.rsi, t.adx, t.plus_di AS plusDI, t.minus_di AS minusDI,
      t.atr AS ATR,
      t.pivot_high AS PivotHighRaw, t.pivot_low AS PivotLowRaw,
      t.sma_50 AS TrendMA
    FROM {price_table} p
    JOIN {tech_table} t
      ON p.symbol = t.symbol AND p.date = t.date
    WHERE p.symbol = %s
      {"AND p.date >= %s" if start_date else ""}
      {"AND p.date <= %s" if end_date else ""}
    ORDER BY p.date;
    """
    params = [symbol]
    if start_date: params.append(start_date)
    if end_date:   params.append(end_date)
    cursor.execute(q, params)
    rows = cursor.fetchall()
    if not rows:
        return []

    return [dict(r) for r in rows]

# -------------------------------
# 4) SIGNAL LOGIC (mirrors your original)
# -------------------------------
def generate_signals(data,
                     atrMult=1.0,
                     useTrendMA=True,
                     adxStrong=30, adxWeak=20):
    n = len(data)
    # prepare arrays
    RSI = [row["rsi"] for row in data]
    RSI_prev = [None] + RSI[:-1]
    ADX = [row["ADX"] for row in data]
    plusDI = [row["plusDI"] for row in data]
    minusDI= [row["minusDI"] for row in data]
    ATR    = [row["ATR"] for row in data]
    PivotHigh = [row["PivotHighRaw"] for row in data]
    PivotLow  = [row["PivotLowRaw"] for row in data]
    TrendMA   = [row["TrendMA"] for row in data]
    highs  = [row["high"] for row in data]
    lows   = [row["low"] for row in data]
    closes = [row["close"] for row in data]

    # compute filters/signals
    rsiBuy   = [ (RSI[i]>50 and (RSI_prev[i] or 0)<=50) for i in range(n) ]
    rsiSell  = [ (RSI[i]<50 and (RSI_prev[i] or 100)>=50) for i in range(n) ]
    trendOK  = [ (closes[i] > TrendMA[i]) if useTrendMA else True for i in range(n) ]

    # pivot-based
    phConf = [None] + PivotHigh[:-1]
    plConf = [None] + PivotLow[:-1]
    lastPH, lastPL = None, None
    buyLevel, stopLevel = [None]*n, [None]*n
    breakoutBuy = [False]*n
    breakoutSell= [False]*n
    for i in range(n):
        if phConf[i] is not None: lastPH = phConf[i]
        if plConf[i] is not None: lastPL = plConf[i]
        if lastPH is not None:
            buyLevel[i] = lastPH
            breakoutBuy[i]  = highs[i] > lastPH
        if lastPL is not None:
            buff = ATR[i] * atrMult
            stopLevel[i] = lastPL - buff
            breakoutSell[i] = lows[i] < stopLevel[i]

    # ADX/DMI filter
    finalBuy, finalSell = [False]*n, [False]*n
    for i in range(n):
        if ADX[i] is None:
            adx_ok = True
        else:
            rising = (i>0 and ADX[i]>ADX[i-1])
            adx_ok = (ADX[i]>adxStrong) or ((ADX[i]>adxWeak) and rising)
        dmi_ok = plusDI[i] > minusDI[i]
        adxTrendOK = adx_ok and dmi_ok
        exitDMI   = (i>0 and plusDI[i-1]>minusDI[i-1] and plusDI[i]<minusDI[i])

        if useTrendMA:
            finalBuy[i]  = (rsiBuy[i] and trendOK[i] and adxTrendOK) or breakoutBuy[i]
            finalSell[i] = rsiSell[i] or breakoutSell[i] or exitDMI
        else:
            finalBuy[i]  = (rsiBuy[i] and adxTrendOK) or breakoutBuy[i]
            finalSell[i] = rsiSell[i] or breakoutSell[i]

    # in-position & assign “Signal”
    in_pos = False
    signals = []
    inPositions = []
    for i in range(n):
        if in_pos and finalSell[i]:
            sig = "Sell"; in_pos = False
        elif not in_pos and finalBuy[i]:
            sig = "Buy"; in_pos = True
        else:
            sig = "None"
        signals.append(sig)
        inPositions.append(in_pos)

    # attach back to rows
    for i,row in enumerate(data):
        row["Signal"]     = signals[i]
        row["inPosition"] = inPositions[i]
        row["buyLevel"]   = buyLevel[i]
        row["stopLevel"]  = stopLevel[i]

    return data

# -------------------------------
# 5) INSERT INTO buy_sell
# -------------------------------
def insert_results(symbol, timeframe, data):
    if not data:
        return
    vals = []
    for row in data:
        vals.append((
            symbol, timeframe, row["date"],
            row["open"], row["high"], row["low"], row["close"], row["volume"],
            row["Signal"], row["buyLevel"], row["stopLevel"], row["inPosition"]
        ))
    sql = """
      INSERT INTO buy_sell(
        symbol, timeframe, date,
        open, high, low, close, volume,
        signal, buylevel, stoplevel, inposition
      ) VALUES %s
      ON CONFLICT (symbol, timeframe, date) DO NOTHING;
    """
    execute_values(cursor, sql, vals)
    conn.commit()

# -------------------------------
# 6) MAIN DRIVER
# -------------------------------
def main():
    log_mem("main start")

    # 1) FMP/FRED keys no longer needed

    # 2) Prepare buy_sell table
    create_buy_sell_table()
    log_mem("table created")

    # 3) fetch symbols
    symbols = get_symbols()
    if not symbols:
        logger.error("No symbols, exiting")
        return

    # 4) process per timeframe
    for timeframe in ("Daily","Weekly","Monthly"):
        for sym in symbols:
            logger.info(f"Processing {sym} [{timeframe}]")
            try:
                data = fetch_data(sym, timeframe)
                if not data:
                    logger.info(f"No rows for {sym} {timeframe}")
                    continue
                data = generate_signals(data)
                insert_results(sym, timeframe, data)
                log_mem(f"done {sym} {timeframe}")
            except Exception:
                logger.exception(f"Error {sym} {timeframe}")

    # 7) CLEAN UP
    cursor.close()
    conn.close()
    log_mem("end")
    logger.info("Processing complete.")

if __name__ == "__main__":
    main()
