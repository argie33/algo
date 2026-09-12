#!/usr/bin/env python3
"""One-shot backfill of historical prices for delisted/inactive symbols from a locally
downloaded Stooq bulk archive (`d_us_txt.zip` from https://stooq.com/db/h/) - a second,
much stronger no-budget mitigation for this repo's confirmed survivorship bias, alongside
scripts/tiingo_delisted_price_backfill.py.

Added 2026-09-12, same goal-mode session continuation. Stooq's per-symbol query API is
Cloudflare-bot-blocked in this environment (confirmed earlier this session) and its bulk
download page requires solving a CAPTCHA that can't be automated - both mean the ZIP has to
be fetched manually via a real browser, then handed to this script as a local file path.

Live-verified coverage before writing this script (2026-09-12): of this repo's 546
`stock_symbols WHERE active = false` rows, 431 have a matching `<ticker>.us.txt` file in the
archive, with real, dense daily history (e.g. AFBI: 2,197 rows, 2017-04-28 through
2026-07-31 - far deeper than Tiingo's free-tier 301 rows for the same symbol). Lehman/Enron/
WorldCom/Bear Stearns/WaMu remain confirmed ABSENT under every ticker variant tried (LEH/ENE/
WCOEQ/BSC/LEHMQ/ENRNQ/WCOEQ/WAMUQ) - this script does not and cannot close that gap; it only
speeds up coverage of the already-tracked inactive-symbol backlog, exactly like the Tiingo
script's own stated scope limit.

Known false-positive risk, confirmed live during coverage-checking: a ticker CAN be reused by
an unrelated, still-active company after the original (now-inactive-in-our-DB) entity
delisted - e.g. this archive's "WM" is Waste Management (continuously active through the
file's 2018+ coverage), not Washington Mutual, which failed in 2008 and would show a hard
stop at that date if it were the same entity. This script defends against that generically:
any inactive symbol whose Stooq file's LAST date is materially recent (within
RECENT_DATA_SUSPECT_DAYS of the file's own newest date across the archive) is flagged
suspicious rather than loaded silently, since a genuinely-delisted symbol should not have
current trading data under any legitimate vendor.

Usage:
    python scripts/stooq_bulk_price_backfill.py --zip "C:\\Users\\arger\\Downloads\\d_us_txt.zip"
    python scripts/stooq_bulk_price_backfill.py --zip <path> --symbols AFBI,ALOT
    python scripts/stooq_bulk_price_backfill.py --zip <path> --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import utils.dotenv_loader  # noqa: F401,E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# A genuinely-delisted symbol trading within this many days of "today" in the archive is
# almost certainly a ticker-reuse collision (see WM/Waste-Management docstring note above),
# not real data for the entity our stock_symbols row refers to - skip and flag rather than load.
RECENT_DATA_SUSPECT_DAYS = 60


def _find_symbol_files(zf: zipfile.ZipFile, symbols: set[str]) -> dict[str, str]:
    """Maps UPPERCASE symbol -> archive member path, for every symbol found under
    data/daily/us/**/<symbol>.us.txt. Stooq shards each exchange folder into numbered/lettered
    subfolders (e.g. "nasdaq stocks/1/afbi.us.txt") - matched by filename only, not path shape.
    """
    found: dict[str, str] = {}
    for name in zf.namelist():
        if not name.endswith(".us.txt"):
            continue
        base = name.rsplit("/", 1)[-1]
        ticker = base[: -len(".us.txt")].upper()
        if ticker in symbols:
            found[ticker] = name
    return found


def _parse_stooq_txt(raw: bytes) -> list[dict[str, Any]]:
    """Stooq's per-file format: <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
    DATE is YYYYMMDD. Header line always present.
    """
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("<TICKER>"):
        raise RuntimeError(f"Unexpected Stooq file header: {lines[0] if lines else '(empty file)'}")

    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 9:
            continue
        _ticker, _per, raw_date, _time, o, h, low_, c, vol = parts[:9]
        d = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
        rows.append(
            {
                "date": d,
                "open": float(o) if o else None,
                "high": float(h) if h else None,
                "low": float(low_) if low_ else None,
                "close": float(c) if c else None,
                "volume": int(float(vol)) if vol else None,
            }
        )
    return rows


def _select_candidate_symbols(cur: Any, explicit_symbols: list[str] | None) -> list[str]:
    if explicit_symbols:
        return explicit_symbols

    # Same broad/unbiased sourcing discipline as tiingo_delisted_price_backfill.py - every
    # currently-inactive symbol is a candidate, not a curated famous-names subset. Excludes
    # symbols the Tiingo script already resolved (successfully or confirmed-absent-at-vendor)
    # so re-running both scripts doesn't duplicate work on the same already-settled symbol.
    cur.execute(
        """
        SELECT s.symbol
        FROM stock_symbols s
        LEFT JOIN tiingo_backfill_status t ON t.symbol = s.symbol
        WHERE s.active = FALSE
          AND (t.symbol IS NULL OR t.status != 'backfilled')
        ORDER BY s.symbol
        """
    )
    return [row[0] for row in cur.fetchall()]


def _upsert_price_rows(cur: Any, symbol: str, rows: list[dict[str, Any]]) -> int:
    import psycopg2.extras

    values = [
        (symbol, r["date"], r["open"], r["high"], r["low"], r["close"], r["close"], r["volume"], "stooq_bulk")
        for r in rows
        if r["close"] is not None
    ]
    if not values:
        return 0

    inserted = psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, data_source)
        VALUES %s
        ON CONFLICT (symbol, date) DO NOTHING
        RETURNING symbol
        """,
        values,
        fetch=True,
    )
    return len(inserted)


def _record_status(cur: Any, symbol: str, status: str, rows_inserted: int, detail: str) -> None:
    cur.execute(
        """
        INSERT INTO tiingo_backfill_status (symbol, status, rows_inserted, last_attempt_at, detail)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            status = EXCLUDED.status,
            rows_inserted = EXCLUDED.rows_inserted,
            last_attempt_at = EXCLUDED.last_attempt_at,
            detail = EXCLUDED.detail
        """,
        (symbol, status, rows_inserted, detail[:500]),
    )


def run(zip_path: Path, explicit_symbols: list[str] | None, dry_run: bool) -> dict[str, Any]:
    from utils.db.context import DatabaseContext

    summary: dict[str, Any] = {
        "candidates": 0,
        "matched_in_archive": 0,
        "loaded": 0,
        "suspect_recent_data": 0,
        "empty_or_bad": 0,
        "rows_inserted": 0,
    }

    mode = "read" if dry_run else "write"
    with DatabaseContext(mode) as cur:
        candidates = _select_candidate_symbols(cur, explicit_symbols)
        summary["candidates"] = len(candidates)
        if not candidates:
            logger.info("No candidate inactive symbols left to try")
            return summary

        with zipfile.ZipFile(zip_path) as zf:
            member_map = _find_symbol_files(zf, set(candidates))
            summary["matched_in_archive"] = len(member_map)
            logger.info(f"{len(member_map)}/{len(candidates)} candidates have a file in the archive")

            today = date.today()
            suspect_cutoff = today - timedelta(days=RECENT_DATA_SUSPECT_DAYS)

            for symbol, member in sorted(member_map.items()):
                raw = zf.read(member)
                try:
                    rows = _parse_stooq_txt(raw)
                except Exception as e:
                    logger.error(f"{symbol}: failed to parse {member}: {e}")
                    summary["empty_or_bad"] += 1
                    if not dry_run:
                        _record_status(cur, symbol, "error", 0, f"parse failure: {e}")
                    continue

                if not rows:
                    summary["empty_or_bad"] += 1
                    if not dry_run:
                        _record_status(cur, symbol, "no_data_at_vendor", 0, "empty Stooq file")
                    continue

                latest = max(r["date"] for r in rows)
                if latest >= suspect_cutoff and not explicit_symbols:
                    # The collision guard exists to protect the broad/unattended default-
                    # candidate path (see docstring). An explicit --symbols invocation is, by
                    # definition, a human who has already looked at the specific symbol (e.g.
                    # confirmed via security_name that it's a real operating company, not a
                    # WM/Waste-Management-style ticker reuse) and wants it loaded regardless -
                    # forcing the guard on that path would make --symbols useless for exactly
                    # the reactivation-remediation case this script exists to support.
                    # Ticker-reuse collision guard (see WM/Waste-Management docstring note) -
                    # a symbol we track as delisted/inactive should NOT have near-current
                    # trading data under any legitimate vendor. Flag, don't load, don't guess.
                    logger.warning(
                        f"{symbol}: SUSPECT - archive data runs through {latest} (within "
                        f"{RECENT_DATA_SUSPECT_DAYS}d of today), but we track this symbol as "
                        "inactive. Likely ticker reused by an unrelated active company - "
                        "skipping, needs manual verification before loading."
                    )
                    summary["suspect_recent_data"] += 1
                    if not dry_run:
                        _record_status(
                            cur, symbol, "suspect_ticker_reuse", 0, f"archive data through {latest}, not loaded"
                        )
                    continue

                if dry_run:
                    logger.info(f"{symbol}: would insert up to {len(rows)} rows (dry-run)")
                    summary["loaded"] += 1
                    continue

                inserted = _upsert_price_rows(cur, symbol, rows)
                _record_status(cur, symbol, "backfilled", inserted, f"{len(rows)} rows from stooq_bulk archive")
                logger.info(f"{symbol}: inserted {inserted} new price_daily row(s) ({len(rows)} in archive)")
                summary["loaded"] += 1
                summary["rows_inserted"] += inserted

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", type=str, required=True, help="Path to Stooq's d_us_txt.zip")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols to force-attempt")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write to the database")
    args = parser.parse_args()

    explicit_symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    zip_path = Path(args.zip)
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip not found: {zip_path}")

    summary = run(zip_path, explicit_symbols, args.dry_run)
    logger.info(f"Done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
