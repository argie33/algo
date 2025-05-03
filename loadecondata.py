#!/usr/bin/env python3
import os
import json
import logging
import boto3
import pandas as pd
from fredapi import Fred
import pymysql
from botocore.exceptions import ClientError

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
logger = logging.getLogger()

# ─── Configuration from environment ────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
FRED_API_KEY  = os.environ["FRED_API_KEY"]

# ─── FRED client ───────────────────────────────────────────────────────────────
fred = Fred(api_key=FRED_API_KEY)

def get_db_connection():
    """Retrieve DB creds from Secrets Manager and open a PyMySQL connection."""
    sm = boto3.client("secretsmanager")
    try:
        resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    except ClientError as e:
        logger.error(f"Unable to fetch secret {DB_SECRET_ARN}: {e}")
        raise
    secret = json.loads(resp["SecretString"])
    conn = pymysql.connect(
        host     = secret["host"],
        port     = int(secret.get("port", 3306)),
        user     = secret["username"],
        password = secret["password"],
        database = secret["dbname"],
        cursorclass = pymysql.cursors.DictCursor,
        connect_timeout=10
    )
    return conn

# ─── Series list ──────────────────────────────────────────────────────────────
series_ids = [
    # --- U.S. Output & Demand (National Accounts) ---
    "GDPC1", "PCECC96", "GPDI", "GCEC1", "EXPGSC1", "IMPGSC1",
    # --- U.S. Labor Market ---
    "UNRATE", "PAYEMS", "CIVPART", "CES0500000003", "AWHAE",
    "JTSJOL", "ICSA", "OPHNFB", "U6RATE",
    # --- U.S. Inflation & Prices ---
    "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIACO",
    "MICH", "T5YIFR",
    # --- U.S. Financial & Monetary ---
    "FEDFUNDS", "DGS2", "DGS10", "T10Y2Y", "MORTGAGE30US",
    "BAA", "AAA", "SP500", "VIXCLS", "M2SL", "WALCL", "IOER", "IORB",
    # --- U.S. Housing & Construction ---
    "HOUST", "PERMIT", "CSUSHPISA", "RHORUSQ156N", "RRVRUSQ156N", "USHVAC",
]

def lambda_handler(event, context):
    logger.info("Starting economic-data loader")
    conn = get_db_connection()

    # Ensure table exists
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS economic_data (
                series_id VARCHAR(32) NOT NULL,
                date      DATE         NOT NULL,
                value     DOUBLE,
                PRIMARY KEY (series_id, date)
            );
        """)
    conn.commit()

    for sid in series_ids:
        logger.info(f"Fetching {sid}…")
        try:
            ts = fred.get_series(sid)
        except Exception as e:
            logger.error(f"Failed to fetch {sid}: {e}", exc_info=True)
            continue
        if ts is None or ts.empty:
            logger.warning(f"No data for {sid}")
            continue

        rows = []
        for dt, val in ts.dropna().items():
            date_str = pd.to_datetime(dt).date().isoformat()
            rows.append((sid, date_str, float(val)))

        if not rows:
            logger.warning(f"No non-null points for {sid}")
            continue

        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO economic_data (series_id, date, value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value);
            """, rows)
        conn.commit()
        logger.info(f"Inserted/updated {len(rows)} records for {sid}")

    conn.close()
    logger.info("loadecondata complete.")
    return {"status": "success"}
