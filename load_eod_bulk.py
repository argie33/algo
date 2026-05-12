#!/usr/bin/env python3
"""
EOD Bulk Loader — Refresh price_daily for the full universe in minutes, not hours.

PRIMARY:  Alpaca GET /v2/stocks/bars (multi-symbol) — 5000 symbols in ~10 API calls (~2s)
FALLBACK: yfinance yf.download() batch mode (~5 min) — used if Alpaca key absent or fails

Use this for the daily EOD top-up. For backfilling years of history, the
per-symbol loader with watermarks is still the right tool.

USAGE:
    python3 load_eod_bulk.py                  # all symbols, last 10 days
    python3 load_eod_bulk.py --days 30        # last 30 days
    python3 load_eod_bulk.py --batch 100      # symbols per yfinance batch (fallback only)
    python3 load_eod_bulk.py --symbols SPY,QQQ
    python3 load_eod_bulk.py --no-alpaca      # force yfinance (for testing)
"""


from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import io
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import psycopg2
import requests
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

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
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


def _get_alpaca_creds() -> Optional[tuple]:
    """Return (api_key, api_secret) or None if not configured."""
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = (
        os.getenv("ALPACA_API_SECRET")
        or os.getenv("ALPACA_API_SECRET_KEY")
        or os.getenv("APCA_API_SECRET_KEY")
    )
    return (key, secret) if key and secret else None


def fetch_alpaca(symbols: List[str], start: date, end: date) -> Dict[str, List[dict]]:
    """
    Alpaca multi-symbol bars API: ~10 API calls for 5000 symbols (~2 seconds total).

    Uses adjustment=all so `c` (close) is already split+dividend adjusted,
    equivalent to yfinance Adj Close.
    """
    creds = _get_alpaca_creds()
    if not creds:
        return {}

    api_key, api_secret = creds
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
    base_url = "https://data.alpaca.markets/v2/stocks/bars"

    out: Dict[str, List[dict]] = {}
    # Alpaca allows up to 500 symbols per request
    for chunk in chunked(symbols, 500):
        params = {
            "symbols": ",".join(chunk),
            "timeframe": "1Day",
            "start": f"{start.isoformat()}T00:00:00Z",
            "end": f"{end.isoformat()}T23:59:59Z",
            "feed": "iex",
            "adjustment": "all",
            "limit": 10000,
        }
        try:
            resp = requests.get(base_url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("Alpaca API error (chunk of %d): %s", len(chunk), e)
            return {}  # treat partial failure as total failure → fall back to yfinance

        for sym, bars in data.get("bars", {}).items():
            rows = []
            for bar in bars:
                bar_date = datetime.fromisoformat(bar["t"].replace("Z", "+00:00")).astimezone(timezone.utc).date()
                rows.append({
                    "symbol": sym,
                    "date": bar_date,
                    "open": float(bar["o"]),
                    "high": float(bar["h"]),
                    "low": float(bar["l"]),
                    "close": float(bar["c"]),
                    "adj_close": float(bar["c"]),  # adjustment=all → c IS adj close
                    "volume": int(bar.get("v", 0)),
                })
            if rows:
                out[sym] = rows

    return out


def fetch_yfinance(symbols: List[str], days: int, batch_size: int) -> Dict[str, List[dict]]:
    """yfinance batched download. Fallback when Alpaca is unavailable or fails."""
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days + 5)
    out: Dict[str, List[dict]] = {}

    for chunk in chunked(symbols, batch_size):
        try:
            df = yf.download(
                tickers=chunk,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
        except Exception as e:
            log.warning("  yfinance batch failed (%d syms): %s", len(chunk), e)
            continue

        if df is None or df.empty:
            continue

        if len(chunk) == 1:
            sym = chunk[0]
            rows = []
            for d, row in df.iterrows():
                if any(row.isna()):
                    continue
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
        else:
            for sym in chunk:
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


def fetch_batch(symbols: List[str], days: int, batch_size: int = 80, use_alpaca: bool = True) -> Dict[str, List[dict]]:
    """
    Fetch EOD bars for symbols. Tries Alpaca first (fast), falls back to yfinance.
    Returns dict of symbol -> list of row dicts.
    """
    if use_alpaca:
        end = date.today()
        start = end - timedelta(days=days + 5)
        log.info("Fetching via Alpaca API (%d symbols, %d→%d)…", len(symbols), days, (end - start).days)
        t0 = time.monotonic()
        result = fetch_alpaca(symbols, start, end)
        if result:
            elapsed = time.monotonic() - t0
            log.info("Alpaca: %d symbols in %.1fs", len(result), elapsed)
            return result
        log.info("Alpaca unavailable or failed — falling back to yfinance")

    log.info("Fetching via yfinance (%d symbols, batch=%d)…", len(symbols), batch_size)
    return fetch_yfinance(symbols, days, batch_size)


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


def run(symbol_filter=None, days=10, batch_size=80, sleep_between=0.5, use_alpaca=True):
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(**_get_db_config())
        cur = conn.cursor()

        symbols = list(symbol_filter) if symbol_filter else get_universe(cur)
        log.info("EOD BULK LOAD start: %d symbols, %dd window, alpaca=%s", len(symbols), days, use_alpaca)

        started = time.time()
        total_rows = 0
        total_failed = 0

        if use_alpaca and _get_alpaca_creds():
            # Alpaca path: fetch all symbols in one shot (batched at 500/request)
            result = fetch_batch(symbols, days, batch_size=batch_size, use_alpaca=True)
            flat_rows = []
            for sym in symbols:
                sym_rows = result.get(sym, [])
                if not sym_rows:
                    total_failed += 1
                else:
                    flat_rows.extend(sym_rows)
            inserted = bulk_upsert(conn, flat_rows)
            total_rows = inserted
            log.info("Alpaca path: %d symbols fetched, %d rows inserted, %d symbols missing",
                     len(result), inserted, total_failed)
        else:
            # yfinance path: process in smaller batches with throttling
            batches = list(chunked(symbols, batch_size))
            for idx, batch in enumerate(batches, 1):
                t0 = time.time()
                result = fetch_batch(batch, days, batch_size=batch_size, use_alpaca=False)
                flat_rows = []
                for sym in batch:
                    sym_rows = result.get(sym, [])
                    if not sym_rows:
                        total_failed += 1
                    else:
                        flat_rows.extend(sym_rows)
                inserted = bulk_upsert(conn, flat_rows)
                total_rows += inserted
                log.info("[%3d/%d] fetched %d/%d | inserted %5d rows | %.1fs",
                         idx, len(batches), len(result), len(batch), inserted, time.time() - t0)
                if sleep_between > 0 and idx < len(batches):
                    time.sleep(sleep_between)

        elapsed = time.time() - started
        log.info("DONE: %d rows, %d symbols missing, %.1fs (%.0f sym/s)",
                 total_rows, total_failed, elapsed, len(symbols) / elapsed)

        cur.execute("""SELECT date, COUNT(DISTINCT symbol) FROM price_daily
                       WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                       GROUP BY date ORDER BY date DESC""")
        log.info("Coverage by recent date:")
        for d, n in cur.fetchall():
            log.info("  %s: %d symbols", d, n)
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EOD bulk loader for price_daily")
    parser.add_argument("--days",      type=int,   default=10,  help="Days of history to fetch")
    parser.add_argument("--batch",     type=int,   default=80,  help="Symbols per yfinance batch (fallback only)")
    parser.add_argument("--sleep",     type=float, default=0.5, help="Seconds between yfinance batches")
    parser.add_argument("--symbols",                             help="Comma-separated symbols (testing)")
    parser.add_argument("--no-alpaca", action="store_true",      help="Force yfinance (skip Alpaca)")
    args = parser.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    run(symbol_filter=syms, days=args.days, batch_size=args.batch,
        sleep_between=args.sleep, use_alpaca=not args.no_alpaca)
