#!/usr/bin/env python3
"""
TimescaleDB migration — idempotent.

Steps:
  1. Verify TimescaleDB is preloaded (CREATE EXTENSION fails otherwise — RDS
     parameter group must have shared_preload_libraries=timescaledb, applied
     by template-app-stocks.yml's StocksDBParameterGroup).
  2. CREATE EXTENSION IF NOT EXISTS timescaledb.
  3. Convert price_daily and technical_data_daily to hypertables, partitioned
     by `date` with 1-month chunks. Existing rows are migrated in place.
  4. Verify hypertable status.

Safe to re-run: every step is IF NOT EXISTS / migrate_data=true.

Usage:
    python3 migrate_timescaledb.py
    python3 migrate_timescaledb.py --check    # report only, no changes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

env_file = Path(__file__).parent / ".env.local"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

HYPERTABLES = [
    # (table, time_column, chunk_interval)
    ("price_daily", "date", "1 month"),
    ("technical_data_daily", "date", "1 month"),
    ("etf_price_daily", "date", "1 month"),
]


def fetch_one(cur, query, *params):
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else None


def report_state(cur):
    print("\n=== TimescaleDB state ===")
    pg_version = fetch_one(cur, "SHOW server_version")
    print(f"  PostgreSQL version: {pg_version}")

    spl = fetch_one(cur, "SHOW shared_preload_libraries")
    print(f"  shared_preload_libraries: {spl or '(empty)'}")

    has_ext = fetch_one(
        cur,
        "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'",
    )
    print(f"  TimescaleDB extension installed: {'YES' if has_ext else 'NO'}")

    if has_ext:
        ts_version = fetch_one(
            cur, "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
        )
        print(f"  TimescaleDB version: {ts_version}")

        cur.execute(
            """
            SELECT hypertable_name, num_chunks
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public'
            ORDER BY hypertable_name
            """
        )
        rows = cur.fetchall()
        print(f"  Hypertables: {len(rows)}")
        for name, chunks in rows:
            print(f"    - {name}: {chunks} chunks")

    return {"has_ext": bool(has_ext), "spl": spl or ""}


def ensure_extension(cur):
    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    print("  ✓ extension ensured")


def is_hypertable(cur, table):
    return bool(
        fetch_one(
            cur,
            """
            SELECT 1 FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public' AND hypertable_name = %s
            """,
            table,
        )
    )


def has_table(cur, table):
    return bool(
        fetch_one(
            cur,
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            table,
        )
    )


def convert_to_hypertable(cur, table, time_col, chunk_interval):
    if not has_table(cur, table):
        print(f"  · {table}: table not found, skipping")
        return False

    if is_hypertable(cur, table):
        print(f"  · {table}: already a hypertable, skipping")
        return False

    # Hypertable conversion requires no FK constraints from other tables to
    # the converting table. price_daily/technical_data_daily/etf_price_daily
    # are leaf tables in our schema (loaders write, readers JOIN), so this is safe.
    # `migrate_data => true` rewrites existing rows into chunks in place.
    cur.execute(
        sql.SQL(
            "SELECT create_hypertable({}, {}, chunk_time_interval => INTERVAL %s, migrate_data => true)"
        ).format(sql.Literal(table), sql.Literal(time_col)),
        (chunk_interval,),
    )
    new_chunks = fetch_one(
        cur,
        """
        SELECT num_chunks FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'public' AND hypertable_name = %s
        """,
        table,
    )
    print(f"  ✓ {table}: converted ({new_chunks} chunks created)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Set up TimescaleDB hypertables")
    parser.add_argument(
        "--check", action="store_true", help="Report state only, make no changes"
    )
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        state = report_state(cur)
        if args.check:
            return 0

        if "timescaledb" not in (state["spl"] or "").lower():
            print(
                "\n  ✗ TimescaleDB not in shared_preload_libraries.\n"
                "    Apply the parameter group from template-app-stocks.yml to RDS\n"
                "    (StocksDBParameterGroup, requires reboot), then re-run.",
                file=sys.stderr,
            )
            return 2

        print("\n=== Ensure extension ===")
        ensure_extension(cur)

        print("\n=== Convert tables to hypertables ===")
        for tbl, time_col, chunk in HYPERTABLES:
            convert_to_hypertable(cur, tbl, time_col, chunk)

        conn.commit()
        print("\n=== Final state ===")
        report_state(cur)
        print("\n  ✓ Migration complete")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
