#!/usr/bin/env python3
import os
import sys
import json
import time
import math
import logging
from urllib3.util import Retry
from requests import Session
from requests.adapters import HTTPAdapter
from yahooquery import Ticker
import boto3
import psycopg2
from psycopg2.extras import execute_values, DictCursor

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_NAME   = "loadfinancialdata.py"
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
CHUNK_SIZE    = 50       # number of symbols per batch
MAX_WORKERS   = 8        # number of parallel HTTP workers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("loadfinancialdata.log"),
        logging.StreamHandler(sys.stdout),
    ]
)

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def get_db_config():
    client = boto3.client("secretsmanager")
    resp   = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec    = json.loads(resp["SecretString"])
    return (
        sec["username"], sec["password"],
        sec["host"], int(sec["port"]), sec["dbname"]
    )

def chunk_list(lst, size):
    """Yield successive size-sized chunks from lst."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

def clean_row(raw: dict) -> dict:
    """Convert pandas NAs & NaNs to None."""
    clean = {}
    for k, v in raw.items():
        if isinstance(v, float) and math.isnan(v):
            clean[k] = None
        elif v is None or (hasattr(v, "isna") and v.isna()):
            clean[k] = None
        else:
            clean[k] = v
    return clean

def ensure_tables(conn):
    """Ensure our two tables exist (no DROP)."""
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS financial_data (
          symbol               VARCHAR(20) PRIMARY KEY,
          maxage               INT,
          currentprice         DOUBLE PRECISION,
          targethighprice      DOUBLE PRECISION,
          targetlowprice       DOUBLE PRECISION,
          targetmeanprice      DOUBLE PRECISION,
          targetmedianprice    DOUBLE PRECISION,
          recommendationmean   DOUBLE PRECISION,
          recommendationkey    VARCHAR(20),
          numberofanalystopinions INT,
          totalcash            DOUBLE PRECISION,
          totalcashpershare    DOUBLE PRECISION,
          ebitda               DOUBLE PRECISION,
          totaldebt            DOUBLE PRECISION,
          quickratio           DOUBLE PRECISION,
          currentratio         DOUBLE PRECISION,
          totalrevenue         DOUBLE PRECISION,
          debttoequity         DOUBLE PRECISION,
          revenuepershare      DOUBLE PRECISION,
          returnonassets       DOUBLE PRECISION,
          returnonequity       DOUBLE PRECISION,
          grossprofits         DOUBLE PRECISION,
          freecashflow         DOUBLE PRECISION,
          operatingcashflow    DOUBLE PRECISION,
          earningsgrowth       DOUBLE PRECISION,
          revenuegrowth        DOUBLE PRECISION,
          grossmargins         DOUBLE PRECISION,
          ebitdamargins        DOUBLE PRECISION,
          operatingmargins     DOUBLE PRECISION,
          profitmargins        DOUBLE PRECISION,
          financialcurrency    VARCHAR(10),
          fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
          script_name   VARCHAR(255) PRIMARY KEY,
          last_run      TIMESTAMPTZ NOT NULL
        );
        """)
    conn.commit()

def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
          ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # 1) Build a shared HTTP session with retry only—
    #    timeouts are handled by Ticker(timeout=…)
    session = Session()
    retry_strategy = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 2) Connect to Postgres
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port,
        user=user, password=pwd,
        dbname=db, sslmode="require",
        cursor_factory=DictCursor
    )

    # 3) Ensure tables exist (we’ll do incremental loads)
    ensure_tables(conn)

    # 4) Pull symbol lists (stocks + ETFs)
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols;")
        stocks = [r["symbol"] for r in cur.fetchall()]
        cur.execute("SELECT symbol FROM etf_symbols;")
        etfs   = [r["symbol"] for r in cur.fetchall()]
    symbols = stocks + etfs
    logging.info(f"Fetched {len(symbols)} symbols (stocks+ETFs)")

    # 5) Prepare UPSERT helpers
    cols = [
      "symbol","maxage","currentprice","targethighprice","targetlowprice",
      "targetmeanprice","targetmedianprice","recommendationmean","recommendationkey",
      "numberofanalystopinions","totalcash","totalcashpershare","ebitda","totaldebt",
      "quickratio","currentratio","totalrevenue","debttoequity","revenuepershare",
      "returnonassets","returnonequity","grossprofits","freecashflow","operatingcashflow",
      "earningsgrowth","revenuegrowth","grossmargins","ebitdamargins","operatingmargins",
      "profitmargins","financialcurrency"
    ]
    placeholder = "(" + ",".join(["%s"] * len(cols)) + ")"
    update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "symbol")

    # 6) Process in chunks
    for batch in chunk_list(symbols, CHUNK_SIZE):
        ticker = Ticker(
            [s.upper().replace(".", "-") for s in batch],
            asynchronous=True,
            max_workers=MAX_WORKERS,
            retry=2,            # number of retries
            backoff_factor=1,   # seconds between retries: 1,2,4…
            timeout=10,         # per‐request timeout in seconds :contentReference[oaicite:0]{index=0}
            session=session     # advanced: use our retry‐configured session
        )
        raw_data = ticker.financial_data  # dict: {SYMBOL: {...}}
        rows     = []

        for sym in batch:
            data = raw_data.get(sym.upper().replace(".", "-"))
            if not data or not isinstance(data, dict):
                logging.warning(f"  → no data for {sym}, skipping")
                continue
            cleaned = clean_row({k.lower(): v for k, v in data.items()})
            vals = [sym] + [cleaned.get(c) for c in cols[1:]]
            rows.append(vals)

        if rows:
            sql = f"""
            INSERT INTO financial_data ({",".join(cols)})
            VALUES %s
            ON CONFLICT(symbol) DO UPDATE
              SET {update_clause}, fetched_at = NOW();
            """
            with conn.cursor() as cur:
                execute_values(cur, sql, rows, page_size=100)
            conn.commit()
            logging.info(f"Upserted {len(rows)} rows in this batch")

        time.sleep(1)  # pause between batches

    # 7) Record last run & finish
    update_last_run(conn)
    conn.close()
    logging.info("✅ loadfinancialdata complete.")

if __name__ == "__main__":
    main()
