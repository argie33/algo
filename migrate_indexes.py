#!/usr/bin/env python3
"""
RDS PostgreSQL time-series index migration — BRIN-driven, idempotent.

WHY BRIN, not TimescaleDB:
  AWS RDS PostgreSQL's shared_preload_libraries allowlist excludes timescaledb
  entirely. Aurora doesn't support it natively either. BRIN (Block Range INdex)
  ships in vanilla PostgreSQL — no extension required — and gives 10-100x
  speedup on time-range queries against append-only data like price_daily.
  Storage cost is ~1000x smaller than B-tree on the same column.

WHAT THIS DOES:
  For each time-series table:
    - BRIN index on (date) — range scans by date.
    - BRIN composite (date, symbol) where helpful for symbol-then-date filtering.
    - VACUUM ANALYZE to refresh the planner's stats post-index creation.
  Re-running is safe (CREATE INDEX IF NOT EXISTS).

USAGE:
    python3 migrate_indexes.py            # apply
    python3 migrate_indexes.py --check    # report only, no changes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

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

# (table, [(index_name, ddl-fragment)])
TARGETS = [
    ("price_daily", [
        ("idx_price_daily_date_brin",
         "USING BRIN (date) WITH (pages_per_range = 32)"),
        ("idx_price_daily_symbol_date_brin",
         "USING BRIN (symbol, date) WITH (pages_per_range = 32)"),
    ]),
    ("technical_data_daily", [
        ("idx_techdaily_date_brin",
         "USING BRIN (date) WITH (pages_per_range = 32)"),
        ("idx_techdaily_symbol_date_brin",
         "USING BRIN (symbol, date) WITH (pages_per_range = 32)"),
    ]),
    ("etf_price_daily", [
        ("idx_etfprice_date_brin",
         "USING BRIN (date) WITH (pages_per_range = 32)"),
    ]),
    ("buy_sell_daily", [
        ("idx_buysell_date_brin",
         "USING BRIN (date) WITH (pages_per_range = 32)"),
    ]),
    ("trend_template_data", [
        ("idx_trend_date_brin",
         "USING BRIN (date) WITH (pages_per_range = 32)"),
    ]),
]


def fetch_one(cur, query, *params):
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else None


def has_table(cur, table):
    return bool(fetch_one(
        cur,
        """SELECT 1 FROM information_schema.tables
           WHERE table_schema = 'public' AND table_name = %s""",
        table,
    ))


def has_index(cur, name):
    return bool(fetch_one(
        cur,
        "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = %s",
        name,
    ))


def report_state(cur):
    print("\n=== Time-series index state ===")
    pg_version = fetch_one(cur, "SHOW server_version")
    print(f"  PostgreSQL: {pg_version}")
    for table, idxs in TARGETS:
        if not has_table(cur, table):
            print(f"  · {table}: not present, skipping")
            continue
        rowcount = fetch_one(
            cur, "SELECT reltuples::bigint FROM pg_class WHERE relname = %s", table
        ) or 0
        existing = [name for name, _ in idxs if has_index(cur, name)]
        missing = [name for name, _ in idxs if not has_index(cur, name)]
        print(f"  · {table} (~{rowcount:,} rows): "
              f"{len(existing)}/{len(idxs)} indexes present"
              + (f" missing={missing}" if missing else ""))


def apply_indexes(cur):
    created = 0
    for table, idxs in TARGETS:
        if not has_table(cur, table):
            print(f"  · {table}: not present, skipping")
            continue
        for name, frag in idxs:
            if has_index(cur, name):
                print(f"  · {name}: already exists, skipping")
                continue
            sql = f"CREATE INDEX IF NOT EXISTS {name} ON {table} {frag}"
            print(f"  + {name}")
            cur.execute(sql)
            created += 1
    return created


def vacuum_analyze(conn, cur):
    # ANALYZE inside a transaction is fine; VACUUM is not. Use ANALYZE for
    # planner stats after index creation — that's enough.
    for table, _ in TARGETS:
        if not has_table(cur, table):
            continue
        print(f"  ANALYZE {table}")
        cur.execute(f"ANALYZE {table}")


def main():
    parser = argparse.ArgumentParser(description="Create BRIN indexes on time-series tables")
    parser.add_argument("--check", action="store_true",
                        help="Report state only, make no changes")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        report_state(cur)
        if args.check:
            return 0

        print("\n=== Apply indexes ===")
        created = apply_indexes(cur)
        conn.commit()
        print(f"\n  ✓ created {created} new index(es)")

        print("\n=== Refresh planner stats ===")
        vacuum_analyze(conn, cur)
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
