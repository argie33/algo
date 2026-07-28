#!/usr/bin/env python3
"""Compare Alpaca Market Data daily bars against price_daily (yfinance-loaded).

Evaluation harness for the Alpaca migration (2026-07-14): fetches recent daily
bars for a sample of symbols from Alpaca (free plan, feed=sip for >15min-old
data = full consolidated tape) and diffs them against what yfinance loaded into
price_daily. Read-only against the database; makes ~sample/200 Alpaca API calls.

Run:
    python scripts/compare_price_sources.py                 # 200-symbol sample, 5 days
    python scripts/compare_price_sources.py --sample 1000 --days 10
    python scripts/compare_price_sources.py --symbols AAPL,MSFT,NVDA

Interpreting results (what "good" looks like before switching PRICE_DATA_SOURCE):
- close_diff_pct p95 under ~0.5%: OHLC parity. Small diffs are expected from
  consolidated-tape closing-print handling; large ones indicate feed problems.
- volume_ratio (alpaca/yfinance) median near 1.0: consolidated volume parity.
  A median near 0.02 would mean we accidentally got the IEX feed - do not switch.
- coverage: symbols Alpaca returned vs requested. Missing coverage on real,
  active symbols is disqualifying; missing OTC/tiny symbols may be acceptable.
"""

import argparse
import logging
import statistics
import sys
from datetime import date, timedelta
from typing import Any

from loaders.loader_helper import setup_imports

setup_imports()

from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.alpaca_market_data import AlpacaMarketData  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def pick_sample(sample_size: int) -> list[str]:
    """Deterministic spread across the active universe (every Nth symbol by name)."""
    with DatabaseContext("read") as cur:
        cur.execute(
            """SELECT DISTINCT symbol FROM price_daily
               WHERE date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '7 days'
               ORDER BY symbol"""
        )
        universe = [row[0] for row in cur.fetchall()]
    if not universe:
        raise RuntimeError("price_daily has no recent symbols to sample")
    step = max(1, len(universe) // sample_size)
    return universe[::step][:sample_size]


def load_db_rows(symbols: list[str], start: date) -> dict[tuple[str, str], dict[str, Any]]:
    with DatabaseContext("read") as cur:
        cur.execute(
            """SELECT symbol, date, open, high, low, close, volume FROM price_daily
               WHERE symbol = ANY(%s) AND date >= %s AND close IS NOT NULL""",
            (symbols, start),
        )
        return {
            (r[0], r[1].isoformat()): {
                "open": float(r[2]) if r[2] is not None else None,
                "high": float(r[3]) if r[3] is not None else None,
                "low": float(r[4]) if r[4] is not None else None,
                "close": float(r[5]),
                "volume": int(r[6]) if r[6] is not None else None,
            }
            for r in cur.fetchall()
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Alpaca vs yfinance-loaded daily bars")
    parser.add_argument("--sample", type=int, default=200, help="Symbols to sample from the universe")
    parser.add_argument("--days", type=int, default=5, help="Calendar days of history to compare")
    parser.add_argument("--symbols", type=str, default=None, help="Explicit comma-separated symbols")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else pick_sample(args.sample)
    start = date.today() - timedelta(days=args.days)
    logger.info(f"Comparing {len(symbols)} symbols since {start} (Alpaca feed=sip vs price_daily)")

    client = AlpacaMarketData()
    alpaca = client.fetch_daily_bars(symbols, start, date.today())
    db = load_db_rows(symbols, start)

    close_diffs: list[float] = []
    volume_ratios: list[float] = []
    mismatches: list[str] = []
    compared = 0

    for symbol, rows in alpaca.items():
        for row in rows:
            key = (symbol, row["date"])
            ref = db.get(key)
            if ref is None:
                continue
            compared += 1
            diff_pct = abs(row["close"] - ref["close"]) / ref["close"] * 100 if ref["close"] else 0.0
            close_diffs.append(diff_pct)
            if ref["volume"]:
                volume_ratios.append(row["volume"] / ref["volume"])
            if diff_pct > 1.0:
                mismatches.append(
                    f"{symbol} {row['date']}: close alpaca={row['close']} db={ref['close']} ({diff_pct:.2f}%)"
                )

    covered = {s for s, rows in alpaca.items() if rows}
    missing = sorted(set(symbols) - covered)

    print("\n===== ALPACA vs YFINANCE (price_daily) =====")
    print(f"symbols requested:  {len(symbols)}")
    print(f"symbols covered:    {len(covered)} ({len(covered) / len(symbols) * 100:.1f}%)")
    print(f"bars compared:      {compared}")
    if close_diffs:
        close_sorted = sorted(close_diffs)
        p95 = close_sorted[int(len(close_sorted) * 0.95) - 1] if len(close_sorted) > 1 else close_sorted[0]
        print(
            f"close diff pct:     median={statistics.median(close_diffs):.4f}%  p95={p95:.4f}%  max={max(close_diffs):.3f}%"
        )
    if volume_ratios:
        print(
            f"volume ratio a/y:   median={statistics.median(volume_ratios):.3f}  "
            f"min={min(volume_ratios):.3f}  max={max(volume_ratios):.3f}"
            "   (median ~1.0 = consolidated SIP; ~0.02 would mean IEX-only feed)"
        )
    if missing:
        print(f"missing from alpaca ({len(missing)}): {missing[:15]}{'...' if len(missing) > 15 else ''}")
    if mismatches:
        print(f"\nbars with >1% close divergence ({len(mismatches)}):")
        for m in mismatches[:20]:
            print(f"  {m}")

    print(
        "\nVerdict guide: switch PRICE_DATA_SOURCE=alpaca when coverage ~100% on real symbols, "
        "close p95 < 0.5%, volume median ~1.0 over several trading days."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
