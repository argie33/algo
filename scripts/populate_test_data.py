#!/usr/bin/env python3
"""
Populate test data into the database for orchestrator integration testing.

Inserts minimal data needed for Phase 1 to pass:
  - price_daily rows (SPY and a few test symbols)
  - market_health_daily row
  - trend_template_data rows
  - data_loader_status entries

Usage:
    python3 scripts/populate_test_data.py --date 2026-05-29 \
        --host <rds-host> --port 5432 --dbname algo --user stocks --password <pw>
"""

import argparse
import sys
from datetime import date, timedelta

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


def get_args():
    p = argparse.ArgumentParser(description="Populate test data for orchestrator CI testing")
    p.add_argument("--date", required=True, help="Test date YYYY-MM-DD")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=5432)
    p.add_argument("--dbname", default="algo")
    p.add_argument("--user", default="stocks")
    p.add_argument("--password", required=True)
    p.add_argument("--coverage", type=int, default=100, help="Price data coverage pct (unused, kept for compatibility)")
    return p.parse_args()


TEST_SYMBOLS = ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V"]


def connect(args):
    return psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
        connect_timeout=30,
    )


def populate_price_daily(cur, run_date):
    """Insert SPY and test symbol prices for run_date and 10 preceding trading days."""
    # Generate last 10 weekday dates up to and including run_date
    dates = []
    d = run_date
    while len(dates) < 10:
        if d.weekday() < 5:  # Mon-Fri
            dates.append(d)
        d -= timedelta(days=1)

    base_prices = {
        "SPY": 530.0, "AAPL": 195.0, "MSFT": 425.0, "GOOGL": 175.0,
        "AMZN": 185.0, "META": 490.0, "NVDA": 1100.0, "TSLA": 180.0,
        "JPM": 210.0, "V": 275.0,
    }

    rows = []
    for sym, base in base_prices.items():
        for i, dt in enumerate(reversed(dates)):
            drift = 1 + (i * 0.002)
            close = round(base * drift, 4)
            rows.append((sym, dt, close * 0.99, close * 1.005, close * 0.98, close,
                         int(1e7 if sym == "SPY" else 5e6), close))

    cur.executemany("""
        INSERT INTO price_daily (symbol, date, open, high, low, close, volume, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET
            close = EXCLUDED.close, adj_close = EXCLUDED.adj_close
    """, rows)
    print(f"  price_daily: inserted/updated {len(rows)} rows for {len(TEST_SYMBOLS)} symbols")


def populate_etf_price_daily(cur, run_date):
    """Mirror SPY in etf_price_daily so Phase 1 fallback also works."""
    dates = []
    d = run_date
    while len(dates) < 10:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)

    rows = []
    for dt in reversed(dates):
        close = 530.0
        rows.append(("SPY", dt, close * 0.99, close * 1.005, close * 0.98, close, int(1e7), close))

    cur.executemany("""
        INSERT INTO etf_price_daily (symbol, date, open, high, low, close, volume, adj_close)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET close = EXCLUDED.close
    """, rows)
    print(f"  etf_price_daily: inserted/updated {len(rows)} rows for SPY")


def populate_market_health_daily(cur, run_date):
    """Insert a healthy market_health_daily row for run_date."""
    dates = []
    d = run_date
    while len(dates) < 5:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)

    rows = [(dt, "uptrend", 2, 2, 3, 65.0, 1.3, 120, 30, 0.6, 15.5, 0.85, 0.3, "neutral", "Test data")
            for dt in reversed(dates)]

    cur.executemany("""
        INSERT INTO market_health_daily (
            date, market_trend, market_stage, distribution_days_4w, distribution_days_20d,
            up_volume_percent, advance_decline_ratio, new_highs_count, new_lows_count,
            breadth_momentum_10d, vix_level, put_call_ratio, yield_curve_slope,
            fed_rate_environment, market_comment
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET market_stage = EXCLUDED.market_stage
    """, rows)
    print(f"  market_health_daily: inserted/updated {len(rows)} rows")


def populate_trend_template_data(cur, run_date):
    """Insert trend template data (Minervini stage 2 qualifying) for test symbols."""
    dates = []
    d = run_date
    while len(dates) < 3:
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)

    rows = []
    for sym in TEST_SYMBOLS:
        for dt in reversed(dates):
            rows.append((
                sym, dt,
                220.0, 140.0,   # 52w high/low
                35.0, -15.0,    # pct from 52w low/high
                0.002, 0.001,   # sma50/200 slope
                True, True, True,  # above sma50, sma200, sma50>sma200
                5.0,            # ma_spread_percent
                6, 2,           # minervini_trend_score, weinstein_stage
                "up", False,    # trend_direction, consolidation_flag
            ))

    cur.executemany("""
        INSERT INTO trend_template_data (
            symbol, date, price_52w_high, price_52w_low,
            percent_from_52w_low, percent_from_52w_high,
            sma_50_slope, sma_200_slope,
            price_above_sma50, price_above_sma200, sma50_above_sma200,
            ma_spread_percent, minervini_trend_score, weinstein_stage,
            trend_direction, consolidation_flag
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET weinstein_stage = EXCLUDED.weinstein_stage
    """, rows)
    print(f"  trend_template_data: inserted/updated {len(rows)} rows")


def populate_data_loader_status(cur, run_date):
    """Insert data_loader_status so Phase 1 fast-path reads fresh dates."""
    entries = [
        ("price_daily",           "daily",   "prices",   run_date),
        ("etf_price_daily",       "daily",   "prices",   run_date),
        ("market_health_daily",   "daily",   "market",   run_date),
        ("trend_template_data",   "daily",   "signals",  run_date),
        ("technical_data_daily",  "daily",   "signals",  run_date),
        ("buy_sell_daily",        "daily",   "signals",  run_date),
        ("signal_quality_scores", "daily",   "signals",  run_date),
        ("swing_trader_scores",   "daily",   "signals",  run_date),
        ("algo_metrics_daily",    "daily",   "metrics",  run_date),
    ]

    from datetime import datetime
    now = datetime.utcnow()
    rows = [(tbl, freq, role, dt, 0, 1000, 2, "ok", now, None)
            for tbl, freq, role, dt in entries]

    cur.executemany("""
        INSERT INTO data_loader_status (
            table_name, frequency, role, latest_date, age_days,
            row_count, stale_threshold_days, status, last_updated, error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (table_name) DO UPDATE SET
            latest_date = EXCLUDED.latest_date,
            status = EXCLUDED.status,
            last_updated = EXCLUDED.last_updated
    """, rows)
    print(f"  data_loader_status: upserted {len(rows)} entries for {run_date}")


def populate_stock_symbols(cur):
    """Ensure test symbols exist in stock_symbols."""
    rows = [(sym, sym, "NASDAQ", "CS", True) for sym in TEST_SYMBOLS]
    cur.executemany("""
        INSERT INTO stock_symbols (symbol, name, exchange, asset_type, is_active)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (symbol) DO NOTHING
    """, rows)
    print(f"  stock_symbols: ensured {len(rows)} test symbols exist")


def main():
    args = get_args()
    try:
        run_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"ERROR: Invalid date format '{args.date}', expected YYYY-MM-DD")
        sys.exit(1)

    print(f"Populating test data for {run_date} into {args.host}:{args.port}/{args.dbname}")

    conn = connect(args)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        populate_stock_symbols(cur)
        populate_price_daily(cur, run_date)
        populate_etf_price_daily(cur, run_date)
        populate_market_health_daily(cur, run_date)
        populate_trend_template_data(cur, run_date)
        populate_data_loader_status(cur, run_date)
        conn.commit()
        print(f"\nOK: Test data populated successfully for {run_date}")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
