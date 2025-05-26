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
    return usage/1024 if sys.platform.startswith("linux") else usage/(1024*1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

log_mem("after imports")

# -------------------------------
# 0) FETCH DB CREDENTIALS & CONNECT
# -------------------------------
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN env var missing")
    sys.exit(1)

sm = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION"))
sec = json.loads(sm.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
conn = psycopg2.connect(
    host=sec["host"],
    port=sec.get("port",5432),
    dbname=sec["dbname"],
    user=sec["username"],
    password=sec["password"]
)
cursor = conn.cursor(cursor_factory=DictCursor)
log_mem("DB connected")

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
        signal     VARCHAR(10),
        buylevel   DOUBLE PRECISION,
        stoplevel  DOUBLE PRECISION,
        inposition BOOLEAN,
        UNIQUE(symbol, timeframe, date)
      );
    """)
    conn.commit()

# -------------------------------
# 3) FETCH BATCHED DATA FOR SYMBOLS
# -------------------------------
def fetch_batch_data(symbols, timeframe):
    price_t = {"Daily":"price_daily","Weekly":"price_weekly","Monthly":"price_monthly"}[timeframe]
    tech_t  = {"Daily":"technical_data_daily","Weekly":"technical_data_weekly","Monthly":"technical_data_monthly"}[timeframe]
    cursor.execute(f"""
      SELECT p.symbol, p.date, p.high, p.low,
             t.pivot_high, t.pivot_low, t.sma_50
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
# 4) SIGNAL LOGIC (Pivot Breakout Follower)
# -------------------------------
def generate_signals(data,
                     useMaFilter=True,
                     maLength=50,
                     maType="SMA"):
    # parameters from Pine script
    shunt = 1

    n = len(data)
    # extract arrays
    highs      = [r["high"] for r in data]
    lows       = [r["low"]  for r in data]
    piv_hi     = [r["pivot_high"] for r in data]
    piv_lo     = [r["pivot_low"]  for r in data]
    ma_vals    = [r["sma_50"]      for r in data]  # using sma_50 as MA filter

    # shift for confirmation
    ph_conf = [None]*n
    pl_conf = [None]*n
    for i in range(n):
        if i - shunt >= 0:
            ph_conf[i] = piv_hi[i - shunt]
            pl_conf[i] = piv_lo[i - shunt]

    # forward‐fill last pivot levels
    last_ph = None
    last_pl = None
    buyL   = [None]*n
    stopL  = [None]*n
    for i in range(n):
        if ph_conf[i] is not None:
            last_ph = ph_conf[i]
        if pl_conf[i] is not None:
            last_pl = pl_conf[i]
        buyL[i]  = last_ph
        stopL[i] = last_pl

    # warn if none ever set
    if all(x is None for x in buyL):
        logger.warning("buyLevel never set: check pivot_high data")
    if all(x is None for x in stopL):
        logger.warning("stopLevel never set: check pivot_low data")

    # in‐position logic
    in_pos = False
    signals = []
    ins = []

    for i in range(n):
        lvl_buy  = buyL[i]
        lvl_stop = stopL[i]
        hi = highs[i]
        lo = lows[i]
        ma = ma_vals[i]

        # breakout conditions
        buy_signal  = (lvl_buy is not None and hi > lvl_buy)
        sell_signal = (lvl_stop is not None and lo < lvl_stop)

        # MA filter
        if useMaFilter and ma is not None:
            buy_signal = buy_signal and (lvl_buy > ma)

        # decide signal
        if in_pos:
            if sell_signal:
                sig = "Sell"
                in_pos = False
            else:
                sig = "None"
        else:
            if buy_signal:
                sig = "Buy"
                in_pos = True
            else:
                sig = "None"

        signals.append(sig)
        ins.append(in_pos)

    # attach back to data
    for i,row in enumerate(data):
        row["Signal"]     = signals[i]
        row["inPosition"] = ins[i]
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
            row["Signal"], row["buyLevel"], row["stopLevel"], row["inPosition"]
        )
        for row in data
    ]
    sql = """
      INSERT INTO buy_sell(
        symbol, timeframe, date,
        signal, buylevel, stoplevel, inposition
      ) VALUES %s
      ON CONFLICT(symbol, timeframe, date) DO NOTHING;
    """
    execute_values(cursor, sql, vals)
    conn.commit()

# -------------------------------
# 6) MAIN DRIVER
# -------------------------------
def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def main():
    log_mem("main start")
    create_buy_sell_table()
    symbols = get_symbols()
    if not symbols:
        logger.error("No symbols found")
        return

    batch_size = int(os.getenv("SYMBOL_BATCH_SIZE", "50"))

    for timeframe in ("Daily","Weekly","Monthly"):
        logger.info(f"Processing timeframe: {timeframe}")
        for batch in chunked(symbols, batch_size):
            log_mem(f"fetching batch of {len(batch)}")
            data_map = fetch_batch_data(batch, timeframe)
            for sym in batch:
                data = data_map.get(sym)
                if data:
                    try:
                        processed = generate_signals(data)
                        insert_results(sym, timeframe, processed)
                    except Exception:
                        logger.exception(f"Error processing {sym}[{timeframe}]")
            del data_map
            gc.collect()
            log_mem("after gc")

    cursor.close()
    conn.close()
    log_mem("end")
    logger.info("All done.")

if __name__ == "__main__":
    main()
