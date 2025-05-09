#!/usr/bin/env python3
import sys
import os
import io
import json
import logging
import re
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

# ─── Environment & filter patterns ───────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

patterns = [
    r"\bpreferred\b",
    r"\bredeemable warrant(s)?\b",
    r"\bwarrant(s)?\b",
    r"\bunit(s)?\b",
    r"\bsubordinated\b",
    r"\bperpetual subordinated notes\b",
    r"\bconvertible\b",
    r"\bsenior note(s)?\b",
    r"\bcapital investments\b",
    r"\bnotes due\b",
    r"\bincome trust\b",
    r"\blimited partnership units\b",
    r"\bsubordinate\b",
    r"\s*-\s*(one\s+)?right(s)?\b",
    r"\bclosed end fund\b",
    r"\bpreferred securities\b",
    r"\bnon-cumulative\b",
    r"\bredeemable preferred\b",
    r"\bpreferred class\b",
    r"\bpreferred share(s)?\b",
    r"\betns\b",
    r"\bFixed-to-Floating Rate\b",
    r"\bseries d\b",
    r"\bseries b\b",
    r"\bseries f\b",
    r"\bseries h\b",
    r"\bperpetual preferred\b",
    r"\bincome fund\b",
    r"\bfltg rate\b",
    r"\bclass c-1\b",
    r"\bbeneficial interest\b",
    r"\bfund\b",
    r"\bcapital obligation notes\b",
    r"\bfixed rate\b",
    r"\bdep shs\b",
    r"\bopportunities trust\b",
    r"\bnyse tick pilot test\b",
    r"\bpreference share\b",
    r"\bseries g\b",
    r"\bfutures etn\b",
    r"\btrust for\b",
    r"\btest stock\b",
    r"\bnastdaq symbology test\b",
    r"\biex test\b",
    r"\bnasdaq test\b",
    r"\bnyse arca test\b",
    r"\bpreference\b",
    r"\bredeemable\b",
    r"\bperpetual preference\b",
    r"\btax free income\b",
    r"\bstructured products\b",
    r"\bcorporate backed trust\b",
    r"\bfloating rate\b",
    r"\btrust securities\b",
    r"\bfixed-income\b",
    r"\bpfd ser\b",
    r"\bpfd\b",
    r"\bmortgage bonds\b",
    r"\bmortgage capital\b",
    r"\bseries due\b",
    r"\btarget term\b",
    r"\bterm trust\b",
    r"\bperpetual conv\b",
    r"\bmunicipal bond\b",
    r"\bdigitalbridge group\b",
    r"\bnyse test\b",
    r"\bctest\b",
    r"\btick pilot test\b",
    r"\bexchange test\b",
    r"\bbats bzx\b",
    r"\bdividend trust\b",
    r"\bbond trust\b",
    r"\bmunicipal trust\b",
    r"\bmortgage trust\b",
    r"\btrust etf\b",
    r"\bcapital trust\b",
    r"\bopportunity trust\b",
    r"\binvestors trust\b",
    r"\bincome securities trust\b",
    r"\bresources trust\b",
    r"\benergy trust\b",
    r"\bsciences trust\b",
    r"\bequity trust\b",
    r"\bmulti-media trust\b",
    r"\bmedia trust\b",
    r"\bmicro-cap trust\b",
    r"\bmicro-cap\b",
    r"\bsmall-cap trust\b",
    r"\bglobal trust\b",
    r"\bsmall-cap\b",
    r"\bsce trust\b",
    r"\bacquisition\b",
    r"\bcontingent\b",
    r"\bii inc\b",
    r"\bnasdaq symbology\b",
]
filter_re = re.compile("|".join(patterns), flags=re.IGNORECASE)

def get_db_creds():
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
            host=host, port=port, dbname=db,
            user=user, password=pwd, sslmode="require"
        )
        cur = conn.cursor()

        # 2) Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_symbols (
                symbol           TEXT PRIMARY KEY,
                security_name    TEXT,
                market_category  TEXT,
                test_issue       TEXT,
                financial_status TEXT,
                round_lot_size   TEXT,
                etf              TEXT,
                next_shares      TEXT
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

            df = pd.read_csv(io.StringIO(txt), sep='|', dtype=str)
            df = df[~df.iloc[:, 0].str.contains("File Creation Time", na=False)]
            if "ACT Symbol" in df.columns:
                df = df.rename(columns={"ACT Symbol": "Symbol"})
            dfs.append(df)

        full_df = pd.concat(dfs, ignore_index=True, sort=False)

        # 4) Filter out any rows whose Security Name matches one of the patterns
        full_df = full_df[~full_df["Security Name"].str.contains(filter_re, na=False)]
        logger.info(f"After filtering, {len(full_df)} symbols remain")

        # 5) Prepare upsert
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
