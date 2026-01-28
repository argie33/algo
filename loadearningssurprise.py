#!/usr/bin/env python3
# Load earnings surprise data from existing database tables
# Calculates surprise by comparing actual earnings history to estimates
import sys
import time
import logging
import os
import json
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd

SCRIPT_NAME = "loadearningssurprise.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - INFO - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")

def get_db_config():
    """Fetch database config from Secrets Manager or environment."""
    if DB_SECRET_ARN:
        try:
            client = boto3.client("secretsmanager")
            resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
            sec = json.loads(resp["SecretString"])
            return (
                sec["username"],
                sec["password"],
                sec["host"],
                int(sec["port"]),
                sec["dbname"]
            )
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
    """Ensure earnings_surprises table exists."""
    logger.info("Creating earnings_surprises table...")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS earnings_surprises;")
        cur.execute("""
            CREATE TABLE earnings_surprises (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                earnings_date DATE,
                fiscal_quarter VARCHAR(20),
                actual_eps NUMERIC(15, 4),
                estimated_eps NUMERIC(15, 4),
                eps_surprise NUMERIC(15, 4),
                surprise_pct NUMERIC(15, 4),
                actual_revenue NUMERIC(18, 2),
                estimated_revenue NUMERIC(18, 2),
                revenue_surprise NUMERIC(18, 2),
                surprise_direction VARCHAR(20),
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("CREATE INDEX idx_surprise_symbol ON earnings_surprises (symbol);")
        cur.execute("CREATE INDEX idx_surprise_date ON earnings_surprises (earnings_date);")
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

        # Get surprise data from existing earnings_history and earnings_estimates
        logger.info("Fetching earnings surprise data from database tables...")

        surprise_records = []

        with conn.cursor() as cur:
            # Get all unique symbols with earnings data
            cur.execute("""
                SELECT DISTINCT symbol
                FROM earnings_history
                WHERE eps_actual IS NOT NULL
                ORDER BY symbol;
            """)
            symbols = [r["symbol"] for r in cur.fetchall()]

        total_symbols = len(symbols)
        logger.info(f"Processing {total_symbols} symbols with earnings data")

        for i, symbol in enumerate(symbols):
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{total_symbols} - {get_rss_mb():.1f} MB RSS")

            try:
                with conn.cursor() as cur:
                    # Get latest earnings report with comparison
                    cur.execute("""
                        SELECT
                            symbol,
                            quarter,
                            eps_actual,
                            eps_estimate,
                            eps_difference,
                            surprise_percent
                        FROM earnings_history
                        WHERE symbol = %s
                        AND eps_actual IS NOT NULL
                        ORDER BY quarter DESC
                        LIMIT 1;
                    """, (symbol,))

                    result = cur.fetchone()

                    if result:
                        actual_eps = float(result['eps_actual']) if result['eps_actual'] else None
                        estimated_eps = float(result['eps_estimate']) if result['eps_estimate'] else None
                        eps_surprise = float(result['eps_difference']) if result['eps_difference'] else None
                        surprise_pct = float(result['surprise_percent']) if result['surprise_percent'] else None

                        if actual_eps is not None and estimated_eps is not None:
                            if eps_surprise is None:
                                eps_surprise = actual_eps - estimated_eps
                            if surprise_pct is None:
                                surprise_pct = (eps_surprise / estimated_eps * 100) if estimated_eps != 0 else 0

                            direction = "beat" if eps_surprise > 0 else "miss" if eps_surprise < 0 else "inline"

                            surprise_records.append((
                                symbol,
                                result['quarter'],
                                None,  # fiscal_quarter
                                actual_eps,
                                estimated_eps,
                                eps_surprise,
                                float(surprise_pct),
                                None,  # actual_revenue
                                None,  # estimated_revenue
                                None,  # revenue_surprise
                                direction,
                                f"EPS Actual: {actual_eps}, Estimated: {estimated_eps}"
                            ))
            except Exception as e:
                logger.debug(f"Error processing surprise for {symbol}: {e}")

        # Insert surprise records
        logger.info(f"Inserting {len(surprise_records)} earnings surprise records...")
        if surprise_records:
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO earnings_surprises
                    (symbol, earnings_date, fiscal_quarter, actual_eps, estimated_eps,
                     eps_surprise, surprise_pct, actual_revenue, estimated_revenue,
                     revenue_surprise, surprise_direction, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, surprise_records)
            conn.commit()

        # Update last_updated
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
        conn.commit()

        logger.info(f"[MEM] peak RSS: {get_rss_mb():.1f} MB")
        logger.info(f"Earnings Surprises — total: {len(surprise_records)}, processed: {total_symbols}")
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
