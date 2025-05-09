#!/usr/bin/env python3
import sys
import os
import io
import json
import logging
import requests
import boto3
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ───────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols")

# ─── Environment variables ──────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

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
            CREATE TABLE IF NOT EXISTS stock_symbols (
                symbol             TEXT PRIMARY KEY,
                security_name      TEXT,
                market_category    TEXT,
                test_issue         TEXT,
                financial_status   TEXT,
                round_lot_size     TEXT,
                etf                TEXT,
                next_shares        TEXT
            );
        """)
        conn.commit()

        # 3) Download & parse both files
        urls = [
            "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
            "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
        ]
        dfs = []
        for url in urls:
            logger.info(f"Downloading {url}")
            resp = requests.get(url)
            resp.raise_for_status()
            txt = resp.text

            # Load into DataFrame
            df = pd.read_csv(io.StringIO(txt), sep='|', dtype=str)

            # Drop footer row that starts with "File Creation Time"
            df = df[~df.iloc[:, 0].str.contains("File Creation Time", na=False)]

            # Normalize header difference
            if "ACT Symbol" in df.columns:
                df = df.rename(columns={"ACT Symbol": "Symbol"})

            dfs.append(df)

        full_df = pd.concat(dfs, ignore_index=True, sort=False)

        # 4) Prepare upsert
        records = [
            (
                row.get("Symbol"),
                row.get("Security Name"),
                row.get("Market Category"),
                row.get("Test Issue"),
                row.get("Financial Status"),
                row.get("Round Lot Size"),
                row.get("ETF"),
                row.get("NextShares")
            )
            for _, row in full_df.iterrows()
        ]

        execute_values(
            cur,
            """
            INSERT INTO stock_symbols (
              symbol, security_name, market_category, test_issue,
              financial_status, round_lot_size, etf, next_shares
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE
              SET security_name    = EXCLUDED.security_name,
                  market_category  = EXCLUDED.market_category,
                  test_issue       = EXCLUDED.test_issue,
                  financial_status = EXCLUDED.financial_status,
                  round_lot_size   = EXCLUDED.round_lot_size,
                  etf              = EXCLUDED.etf,
                  next_shares      = EXCLUDED.next_shares;
            """,
            records
        )
        conn.commit()
        logger.info(f"✓ Inserted/updated {len(records)} symbols")

        # 5) Clean up
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({"status": "success", "count": len(records)})
        }

    except Exception as e:
        logger.exception("loadstocksymbols failed")
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(result))
    sys.stdout.flush()
