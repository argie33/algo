#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import psycopg2
from psycopg2.extras import DictCursor, execute_values
from datetime import datetime, timedelta
import calendar
import boto3

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadbuysell.py"
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory‐logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024 if sys.platform.startswith("linux") else usage / (1024*1024)

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
# Prepare date ranges (if you need them later)
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
def get_symbols():
    cursor.execute("""
      SELECT symbol
      FROM stock_symbols
      WHERE exchange IN ('NASDAQ','New York Stock Exchange')
    """)
    return [r["symbol"] for r in cursor.fetchall()]

# -------------------------------
# 2) CREATE buy_sell TABLE
# -------------------------------
def create_buy_sell_table():
    cursor.execute("DROP TABLE IF EXISTS buy_sell;")
    cursor.execute("""
      CREATE TABLE buy_sell (
        id         SERIAL        PRIMARY KEY,
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
# 3) FETCH BATCHED DATA FOR A SYMBOL LIST
# -------------------------------
def fetch_batch_data(symbols, timeframe):
    price_t = {"Daily":"price_daily","Weekly":"price_weekly","Monthly":"price_monthly"}[timeframe]
    tech_t  = {"Daily":"technical_data_daily","Weekly":"technical_data_weekly","Monthly":"technical_data_monthly"}[timeframe]
    cursor.execute(f"""
      SELECT p.symbol, p.date, p.open, p.high, p.low, p.close, p.volume,
             t.rsi, t.adx, t.plus_di, t.minus_di,
             t.atr, t.pivot_high, t.pivot_low, t.sma_50
      FROM {price_t} p
      JOIN {tech_t} t
        ON p.symbol = t.symbol AND p.date = t.date
      WHERE p.symbol = ANY(%s)
      ORDER BY p.symbol, p.date;
    """, (symbols,))
    data = {}
    for row in cursor:
        d = dict(row)
        sym = d.pop("symbol")
        data.setdefault(sym, []).append(d)
    return data

# -------------------------------
# 4) SIGNAL LOGIC (unchanged, guards None)
# -------------------------------
def generate_signals(data,
                     atrMult=1.0,
                     useTrendMA=True,
                     adxStrong=30, adxWeak=20):
    n = len(data)
    RSI       = [r["rsi"]        for r in data]
    RSI_prev  = [None] + RSI[:-1]
    ADX       = [r["adx"]        for r in data]
    plusDI    = [r["plus_di"]    for r in data]
    minusDI   = [r["minus_di"]   for r in data]
    ATR       = [r["atr"]        for r in data]
    PH        = [r["pivot_high"] for r in data]
    PL        = [r["pivot_low"]  for r in data]
    MA        = [r["sma_50"]     for r in data]
    H         = [r["high"]       for r in data]
    L         = [r["low"]        for r in data]
    C         = [r["close"]      for r in data]

    # RSI crosses
    rsiBuy  = [
        bool(RSI[i] is not None and RSI_prev[i] is not None and RSI[i]>50 and RSI_prev[i]<=50)
        for i in range(n)
    ]
    rsiSell = [
        bool(RSI[i] is not None and RSI_prev[i] is not None and RSI[i]<50 and RSI_prev[i]>=50)
        for i in range(n)
    ]

    # Trend filter
    trendOK = [
        (not useTrendMA) or (MA[i] is not None and C[i]>MA[i])
        for i in range(n)
    ]

    # Pivot breakout
    phc= [None]+PH[:-1]
    plc= [None]+PL[:-1]
    lastPH=lastPL=None
    buyL=[None]*n; stopL=[None]*n
    bBuy=[False]*n; bSell=[False]*n
    for i in range(n):
        if phc[i] is not None: lastPH=phc[i]
        if plc[i] is not None: lastPL=plc[i]
        if lastPH is not None:
            buyL[i]=lastPH; bBuy[i]= H[i]>lastPH
        if lastPL is not None:
            buf = (ATR[i] or 0)*atrMult
            stopL[i]=lastPL-buf; bSell[i]= L[i]<stopL[i]

    # ADX/DMI filter
    finalBuy=[False]*n; finalSell=[False]*n
    for i in range(n):
        if ADX[i] is None:
            adx_ok=True
        else:
            rising = bool(i>0 and ADX[i-1] is not None and ADX[i]>ADX[i-1])
            adx_ok = (ADX[i]>adxStrong) or ((ADX[i]>adxWeak) and rising)
        dmi_ok  = (plusDI[i] or 0) > (minusDI[i] or 0)
        exitDmi = bool(
            i>0 and (plusDI[i-1] or 0)>(minusDI[i-1] or 0)
               and (plusDI[i] or 0)<(minusDI[i] or 0)
        )
        if useTrendMA:
            finalBuy[i]  = (rsiBuy[i] and trendOK[i] and adx_ok and dmi_ok) or bBuy[i]
            finalSell[i] = rsiSell[i] or bSell[i] or exitDmi
        else:
            finalBuy[i]  = (rsiBuy[i] and adx_ok and dmi_ok) or bBuy[i]
            finalSell[i] = rsiSell[i] or bSell[i]

    # in-position & signals
    in_pos=False; signals=[]; inPos=[]
    for i in range(n):
        if in_pos and finalSell[i]:
            sig="Sell"; in_pos=False
        elif not in_pos and finalBuy[i]:
            sig="Buy"; in_pos=True
        else:
            sig="None"
        signals.append(sig); inPos.append(in_pos)

    for i,row in enumerate(data):
        row["Signal"]     = signals[i]
        row["inPosition"] = inPos[i]
        row["buyLevel"]   = buyL[i]
        row["stopLevel"]  = stopL[i]

    return data

# -------------------------------
# 5) BATCH INSERT RESULTS
# -------------------------------
def insert_results(symbol, timeframe, data):
    if not data:
        return
    vals = [
        (
            symbol, timeframe, row["date"],
            row["open"], row["high"], row["low"], row["close"], row["volume"],
            row["Signal"], row["buyLevel"], row["stopLevel"], row["inPosition"]
        )
        for row in data
    ]
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
# 6) MAIN DRIVER with chunking
# -------------------------------
def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def main():
    log_mem("main start")

    create_buy_sell_table()
    log_mem("table ready")

    symbols = get_symbols()
    if not symbols:
        logger.error("No symbols, exiting")
        return

    batch_size = int(os.getenv("SYMBOL_BATCH_SIZE", "50"))
    for timeframe in ("Daily","Weekly","Monthly"):
        log_mem(f"begin {timeframe}")
        for batch in chunked(symbols, batch_size):
            log_mem(f"fetch batch {len(batch)}")
            data_map = fetch_batch_data(batch, timeframe)
            for sym in batch:
                data = data_map.get(sym)
                if data:
                    try:
                        processed = generate_signals(data)
                        insert_results(sym, timeframe, processed)
                    except Exception:
                        logger.exception(f"Error {sym}[{timeframe}]")
            del data_map
            gc.collect()
            log_mem("after GC")
        log_mem(f"end {timeframe}")

    cursor.close()
    conn.close()
    log_mem("end")
    logger.info("All processing complete.")

if __name__ == "__main__":
    main()
