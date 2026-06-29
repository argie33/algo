#!/usr/bin/env python3
"""Check AWS health status after deployment."""

import os
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

try:
    # FAIL-FAST: All database credentials must be explicitly provided
    db_host = os.environ.get("DB_HOST")
    db_port_str = os.environ.get("DB_PORT")
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")

    missing = []
    if not db_host:
        missing.append("DB_HOST")
    if not db_port_str:
        missing.append("DB_PORT")
    if not db_name:
        missing.append("DB_NAME")
    if not db_user:
        missing.append("DB_USER")
    if not db_password:
        missing.append("DB_PASSWORD")

    if missing:
        raise ValueError(
            f"[CRITICAL] Missing required database environment variables: {', '.join(missing)}. "
            "Cannot proceed without explicit database configuration."
        )

    conn = psycopg2.connect(
        host=db_host,
        port=int(db_port_str),
        database=db_name,
        user=db_user,
        password=db_password,
    )

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get all loaders except pipeline-removed ones
    pipeline_removed = {"technical_data_daily", "buy_sell_daily", "signal_quality_scores"}
    cur.execute(
        "SELECT table_name, last_updated FROM data_loader_status WHERE table_name NOT IN (%s, %s, %s) ORDER BY table_name",
        tuple(pipeline_removed),
    )
    rows = cur.fetchall()

    from algo.infrastructure import MarketCalendar

    today = date.today()
    expected_date = today - timedelta(days=1)
    for _ in range(10):
        if MarketCalendar.is_trading_day(expected_date):
            break
        expected_date -= timedelta(days=1)

    ok = stale = 0
    fresh_tables = []
    stale_tables = []

    for row in rows:
        last_updated = row["last_updated"]
        table_name = row["table_name"]
        if not last_updated or (last_updated.date() if hasattr(last_updated, "date") else last_updated) < expected_date:
            stale += 1
            stale_tables.append(table_name)
        else:
            ok += 1
            fresh_tables.append(table_name)

    print(f"\n{'=' * 60}")
    print("AWS DASHBOARD HEALTH STATUS")
    print(f"{'=' * 60}")
    print(f"Freshness: {ok}/{ok + stale} fresh  {stale} stale")
    print(f"Status: {'[OK] READY' if ok == len(rows) else '[WARN] NOT READY'}")
    print(f"\nFresh tables ({ok}): {', '.join(fresh_tables[:5])}{'...' if len(fresh_tables) > 5 else ''}")
    if stale_tables:
        print(f"Stale tables ({stale}): {', '.join(stale_tables[:5])}{'...' if len(stale_tables) > 5 else ''}")
    print(f"{'=' * 60}\n")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
