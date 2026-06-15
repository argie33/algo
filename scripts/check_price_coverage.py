#!/usr/bin/env python3
import psycopg2
import os

try:
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )
    cur = conn.cursor()

    # Check price data coverage
    print("=== Price Data Coverage Analysis ===\n")

    # Get the most recent dates in price_daily
    cur.execute("""
        SELECT date, COUNT(DISTINCT symbol) as symbol_count
        FROM price_daily
        GROUP BY date
        ORDER BY date DESC
        LIMIT 5
    """)

    print("Most recent 5 dates with their symbol counts:")
    rows = cur.fetchall()
    for date_val, count in rows:
        print(f"  {date_val}: {count} symbols")

    if rows:
        latest_date, latest_count = rows[0]
        if len(rows) > 1:
            prior_date, prior_count = rows[1]
            coverage_pct = (latest_count / prior_count * 100) if prior_count > 0 else 0
            print(f"\nCoverage vs prior day: {coverage_pct:.1f}%")

        # Check how many active symbols should be loaded
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
        active_symbols = cur.fetchone()[0]
        print(f"Total active symbols: {active_symbols}")
        print(f"Loaded for latest date: {latest_count}")
        print(f"Missing: {active_symbols - latest_count}")

    # Check recent loader runs
    print("\n=== Recent Loader Runs ===")
    cur.execute("""
        SELECT symbol, completion_pct, symbols_loaded, symbols_failed, execution_started, execution_completed
        FROM data_loader_runs
        WHERE loader_name = 'stock_prices_daily'
        ORDER BY execution_started DESC
        LIMIT 5
    """)

    print("\nMost recent 5 price loader runs:")
    for symbol, completion, loaded, failed, started, completed in cur.fetchall():
        duration = (completed - started).total_seconds() if completed else None
        status = f"{completion:.0f}% complete"
        print(
            f"  {started.strftime('%Y-%m-%d %H:%M')}: {status} | Loaded: {loaded}, Failed: {failed}, Duration: {duration:.0f}s"
            if duration
            else f"  {started.strftime('%Y-%m-%d %H:%M')}: {status} | Loaded: {loaded}, Failed: {failed}"
        )

    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
