#!/usr/bin/env python3
"""
EOD Bulk Loader — Refresh price_daily for the full universe in minutes, not hours.

The per-symbol loader (loadpricedaily.py) hits yfinance one symbol at a time
and gets rate-limited after ~150 symbols. This loader uses yf.download()'s
batched mode: 50-100 symbols per HTTP call, threaded. Full universe (~5000
symbols) refreshes in ~5 minutes.

Use this for the daily EOD top-up. For backfilling years of history, the
per-symbol loader with watermarks is still the right tool.

USAGE:
    python3 load_eod_bulk.py                  # all symbols, last 10 days
    python3 load_eod_bulk.py --days 30        # last 30 days
    python3 load_eod_bulk.py --batch 100      # symbols per HTTP call
    python3 load_eod_bulk.py --symbols SPY,QQQ
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List

import psycopg2
import yfinance as yf
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("eod_bulk")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def get_universe(cur) -> List[str]:
    """Read full symbol universe from the canonical table."""
    cur.execute(
        """SELECT EXISTS (SELECT 1 FROM information_schema.tables
                          WHERE table_schema='public' AND table_name='stock_symbols')"""
    )
    if cur.fetchone()[0]:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol IS NOT NULL ORDER BY symbol")
    else:
        cur.execute("SELECT DISTINCT ticker FROM company_profile WHERE ticker IS NOT NULL ORDER BY ticker")
    return [r[0] for r in cur.fetchall()]


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_batch(symbols: List[str], days: int):
    """Use yfinance batched download. Returns dict of symbol -> rows."""
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days + 5)  # add slack to ensure incl. weekends

    try:
        df = yf.download(
            tickers=symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
        )
    except Exception as e:
        log.warning(f"  batch failed ({len(symbols)} syms): {e}")
        return {}

    if df is None or df.empty:
        return {}

    out = {}
    if len(symbols) == 1:
        # Single-symbol: single-level columns
        sym = symbols[0]
        rows = []
        for d, row in df.iterrows():
            if any(row.isna()): continue
            rows.append({
                "symbol": sym,
                "date": d.date() if hasattr(d, "date") else d,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "adj_close": float(row.get("Adj Close", row["Close"])),
                "volume": int(row["Volume"]) if not (row["Volume"] != row["Volume"]) else 0,
            })
        out[sym] = rows
    else:
        # Multi-symbol: MultiIndex columns
        for sym in symbols:
            if sym not in df.columns.get_level_values(0).unique():
                continue
            sub = df[sym].dropna()
            rows = []
            for d, row in sub.iterrows():
                rows.append({
                    "symbol": sym,
                    "date": d.date() if hasattr(d, "date") else d,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "adj_close": float(row.get("Adj Close", row["Close"])),
                    "volume": int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                })
            out[sym] = rows
    return out


def bulk_upsert(conn, rows: List[dict]) -> int:
    """COPY into staging table then INSERT...ON CONFLICT into price_daily."""
    if not rows:
        return 0
    cur = conn.cursor()
    try:
        staging = f"_eod_stage_{int(time.time() * 1000)}"
        cur.execute(f"CREATE UNLOGGED TABLE {staging} (LIKE price_daily INCLUDING DEFAULTS)")

        cols = ["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"]
        buf = io.StringIO()
        for r in rows:
            line = "\t".join(str(r[c]) if r[c] is not None else "\\N" for c in cols)
            buf.write(line + "\n")
        buf.seek(0)
        cur.copy_expert(
            f"COPY {staging} ({','.join(cols)}) FROM STDIN WITH (FORMAT TEXT, NULL '\\N')",
            buf,
        )

        cur.execute(
            f"""INSERT INTO price_daily ({','.join(cols)})
                SELECT {','.join(cols)} FROM {staging}
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume"""
        )
        inserted = cur.rowcount
        cur.execute(f"DROP TABLE {staging}")
        conn.commit()
        return inserted
    except Exception as e:
        conn.rollback()
        log.error(f"  bulk_upsert error: {e}")
        return 0
    finally:
        cur.close()


def run(symbol_filter=None, days=10, batch_size=80, sleep_between=1.0):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    if symbol_filter:
        symbols = list(symbol_filter)
    else:
        symbols = get_universe(cur)

    log.info(f"EOD BULK LOAD start: {len(symbols)} symbols, {days}d window, batch={batch_size}")

    started = time.time()
    total_rows = 0
    total_failed = 0
    batches = list(chunked(symbols, batch_size))
    for idx, batch in enumerate(batches, 1):
        t0 = time.time()
        result = fetch_batch(batch, days)
        flat_rows = []
        for sym in batch:
            sym_rows = result.get(sym, [])
            if not sym_rows:
                total_failed += 1
                continue
            flat_rows.extend(sym_rows)

        inserted = bulk_upsert(conn, flat_rows)
        total_rows += inserted
        log.info(
            f"[{idx:>3}/{len(batches)}] batch {idx*batch_size:>5}: "
            f"fetched {len(result)}/{len(batch)} | inserted {inserted:>5} rows | "
            f"{time.time()-t0:.1f}s"
        )

        # Throttle between batches
        if sleep_between > 0 and idx < len(batches):
            time.sleep(sleep_between)

    elapsed = time.time() - started
    log.info(f"\nDONE: {total_rows} rows total, {total_failed} symbols failed, "
             f"{elapsed:.1f}s ({len(symbols)/elapsed:.1f} sym/s)")

    # Sanity check — what dates do we have for the latest?
    cur.execute("""SELECT date, COUNT(DISTINCT symbol) FROM price_daily
                   WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                   GROUP BY date ORDER BY date DESC""")
    log.info("\nCoverage by recent date:")
    for d, n in cur.fetchall():
        log.info(f"  {d}: {n} symbols")
    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EOD bulk loader for price_daily")
    parser.add_argument("--days", type=int, default=10, help="Days of history to fetch")
    parser.add_argument("--batch", type=int, default=80, help="Symbols per HTTP batch")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between batches")
    parser.add_argument("--symbols", help="Comma-separated symbols (testing)")
    args = parser.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    run(symbol_filter=syms, days=args.days, batch_size=args.batch, sleep_between=args.sleep)
