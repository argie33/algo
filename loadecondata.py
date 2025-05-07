#!/usr/bin/env python3
import os
import json
import logging

import boto3
import pandas as pd
from fredapi import Fred
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ─────────────────────────────────────────────────────────────── 
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── Environment variables ──────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
FRED_API_KEY  = os.environ["FRED_API_KEY"]

def get_db_creds():
    """Fetch DB creds (username, password, host, port, dbname) from Secrets Manager."""
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def handler(event, context):
    try:
        # 1) Connect
        user, pwd, host, port, db = get_db_creds()
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=pwd,
            sslmode="require"
        )
        cur = conn.cursor()

        # 2) Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS economic_data (
                series_id TEXT NOT NULL,
                date       DATE NOT NULL,
                value      DOUBLE PRECISION,
                PRIMARY KEY (series_id, date)
            );
        """)
        conn.commit()

        # 3) Series list
        series_ids = [
            # — U.S. Output & Demand —
            "GDPC1","PCECC96","GPDI","GCEC1","EXPGSC1","IMPGSC1",
            # — U.S. Labor Market —
            "UNRATE","PAYEMS","CIVPART","CES0500000003","AWHAE","JTSJOL","ICSA","OPHNFB","U6RATE",
            # — U.S. Inflation & Prices —
            "CPIAUCSL","CPILFESL","PCEPI","PCEPILFE","PPIACO","MICH","T5YIFR",
            # — U.S. Financial & Monetary —
            "FEDFUNDS","DGS2","DGS10","T10Y2Y","MORTGAGE30US","BAA","AAA","SP500","VIXCLS","M2SL","WALCL","IOER","IORB",
            # — U.S. Housing & Construction —
            "HOUST","PERMIT","CSUSHPISA","RHORUSQ156N","RRVRUSQ156N","USHVAC"
        ]

        fred = Fred(api_key=FRED_API_KEY)

        # 4) Fetch & upsert each
        for sid in series_ids:
            logger.info(f"Fetching {sid} …")
            try:
                ts = fred.get_series(sid)
            except Exception as e:
                logger.error(f"Failed to fetch {sid}: {e}")
                continue

            if ts is None or ts.empty:
                logger.warning(f"No data for {sid}")
                continue

            ts = ts.dropna()
            rows = [(sid, pd.to_datetime(dt).date(), float(val)) for dt, val in ts.items()]

            # bulk upsert
            execute_values(
                cur,
                """
                INSERT INTO economic_data (series_id, date, value)
                VALUES %s
                ON CONFLICT (series_id, date) DO UPDATE
                  SET value = EXCLUDED.value;
                """,
                rows
            )
            conn.commit()
            logger.info(f"✓ {len(rows)} rows upserted for {sid}")

        # 5) Clean up
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success"})
        }

    except Exception as e:
        logger.exception("loadecondata failed")
        # if conn was opened, attempt to close
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
