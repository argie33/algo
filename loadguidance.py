#!/usr/bin/env python3
# Load earnings guidance data - COMPLETE COVERAGE with all symbols
import sys
import logging
import os
import json
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd

SCRIPT_NAME = "loadguidance.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - INFO - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")

def get_db_config():
    if DB_SECRET_ARN:
        try:
            client = boto3.client("secretsmanager")
            resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
            sec = json.loads(resp["SecretString"])
            return (sec["username"], sec["password"], sec["host"], int(sec["port"]), sec["dbname"])
        except Exception as e:
            logger.warning(f"Failed to fetch from Secrets Manager: {e}, using environment variables")

    return (
        os.getenv("DB_USER", "stocks"),
        os.getenv("DB_PASSWORD", "bed0elAn"),
        os.getenv("DB_HOST", "localhost"),
        int(os.getenv("DB_PORT", 5432)),
        os.getenv("DB_NAME", "stocks")
    )

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def ensure_table(conn):
    logger.info("Creating guidance_changes table...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS guidance_changes;")
        cur.execute("""
            CREATE TABLE guidance_changes (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL UNIQUE,
                guidance_date DATE,
                prior_guidance NUMERIC(15, 4),
                new_guidance NUMERIC(15, 4),
                guidance_change NUMERIC(15, 4),
                change_pct NUMERIC(15, 4),
                guidance_type VARCHAR(50),
                announcement_text TEXT,
                source VARCHAR(100),
                data_available BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX idx_guidance_symbol ON guidance_changes (symbol);")
    conn.commit()
    logger.info("Table created successfully")

def main():
    conn = None
    try:
        user, pwd, host, port, dbname = get_db_config()
        ssl_mode = "disable" if host == "localhost" else "require"

        logger.info("Connecting to database...")
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=pwd,
            dbname=dbname, sslmode=ssl_mode, cursor_factory=DictCursor
        )
        conn.set_session(autocommit=False)

        ensure_table(conn)
        logger.info(f"[MEM] startup: {get_rss_mb():.1f} MB RSS")

        # Get ALL symbols from stock_symbols
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol;")
            all_symbols = [r["symbol"] for r in cur.fetchall()]

        total_symbols = len(all_symbols)
        logger.info(f"Processing {total_symbols} symbols (ensuring complete coverage)")

        guidance_records = []
        symbols_with_data = 0
        symbols_without_data = 0

        for i, symbol in enumerate(all_symbols):
            if (i + 1) % 500 == 0:
                logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

            try:
                with conn.cursor() as cur:
                    # Try to get latest estimates
                    cur.execute("""
                        SELECT avg_estimate, period, fetched_at
                        FROM earnings_estimates
                        WHERE symbol = %s AND avg_estimate IS NOT NULL
                        ORDER BY fetched_at DESC LIMIT 2;
                    """, (symbol,))

                    estimates = cur.fetchall()

                    if estimates and len(estimates) >= 1:
                        # Has data
                        latest = estimates[0]
                        prior = estimates[1] if len(estimates) > 1 else None

                        latest_eps = float(latest['avg_estimate']) if latest['avg_estimate'] else None
                        prior_eps = float(prior['avg_estimate']) if prior and prior['avg_estimate'] else None

                        change = None
                        change_pct = None

                        if latest_eps is not None and prior_eps is not None:
                            change = latest_eps - prior_eps
                            change_pct = (change / prior_eps * 100) if prior_eps != 0 else 0

                        guidance_records.append((
                            symbol,
                            latest['fetched_at'].date() if latest['fetched_at'] else None,
                            prior_eps,
                            latest_eps,
                            change,
                            float(change_pct) if change_pct else None,
                            'EPS_ESTIMATE',
                            f"EPS Estimate: {latest_eps}" if latest_eps else None,
                            'earnings_estimates',
                            True  # data_available
                        ))
                        symbols_with_data += 1
                    else:
                        # No data - insert NULL record
                        guidance_records.append((
                            symbol,
                            None, None, None, None, None,
                            None, None, None,
                            False  # data_available
                        ))
                        symbols_without_data += 1

            except Exception as e:
                logger.debug(f"Error processing {symbol}: {e}")
                # Insert NULL record for error cases too
                guidance_records.append((
                    symbol,
                    None, None, None, None, None,
                    None, None, None,
                    False  # data_available
                ))
                symbols_without_data += 1

        # Bulk insert ALL records
        logger.info(f"Inserting {len(guidance_records)} records (with/without data)...")
        if guidance_records:
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO guidance_changes
                    (symbol, guidance_date, prior_guidance, new_guidance, guidance_change,
                     change_pct, guidance_type, announcement_text, source, data_available)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, guidance_records)
            conn.commit()

        # Update last_updated
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
        conn.commit()

        logger.info(f"[MEM] peak RSS: {get_rss_mb():.1f} MB")
        logger.info(f"Guidance — total symbols: {total_symbols}, with data: {symbols_with_data}, without: {symbols_without_data}")
        logger.info("Done.")
    except Exception:
        logger.exception("Fatal error in main()")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.exception("Error closing connection")

if __name__ == "__main__":
    main()
