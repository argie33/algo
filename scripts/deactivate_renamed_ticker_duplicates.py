#!/usr/bin/env python3
"""One-off, reviewed migration for the "same-CIK duplicate active symbol" case
load_market_constituents.py's `_detect_same_cik_duplicate_active_symbols` deliberately only
detects and never acts on (see that method's own docstring: "Deliberately detection-only ...
this surfaces the candidate list ... for a human (or a deliberately separate, reviewed
migration script) to act on"). This is that script.

Goal-session context (2026-09-11/12, "SEC/XBRL missing data under 200" push): KWM->NXAT
(K Wave Media Ltd. -> Nexus Advanced Technologies Inc., CIK 0002000756) and CYCN->KRSA
(Cyclerion Therapeutics, Inc. -> Korsana Biosciences, Inc., CIK 0001755237) were both still
`active=true` in stock_symbols for BOTH the old and new ticker, inflating the "Missing
SEC/XBRL data" coverage count for the (empty, newly-added) new-ticker rows while the old
ticker sat on real historical data no longer worth scoring.

IMPORTANT - do not trust SEC submissions.json or yfinance market cap/name to decide
direction here: both were live-checked this session and are actively MISLEADING for this
exact case. SEC's own `tickers` field for both CIKs still lists only the OLD ticker (SEC's
per-CIK index lags a real exchange symbol change, same documented lag as GLMD/EOCN/other
renames this session). yfinance shows a real-looking market cap for the OLD ticker and a
garbled one for the NEW ticker (stale/wrong share count carried over on the new symbol - the
same yfinance-staleness bug class already documented elsewhere in this codebase, e.g.
FPI_YFINANCE_STALE_SHARES_TRUST_SEC_DEI_SYMBOLS), which would have pointed this migration in
exactly the WRONG direction if trusted.

The one authoritative signal that actually resolved this: nasdaqtrader.com's live
nasdaqlisted.txt/otherlisted.txt feed (the same feed load_market_constituents.py itself
treats as ground truth for what's currently trading) lists ONLY NXAT/KRSA today - KWM/CYCN
are entirely absent from both files. That is a real, current ticker-symbol change on the
exchange itself, not just a legal-entity rename. This script re-verifies that live before
touching anything, rather than hardcoding today's one-time check as permanent truth.

Usage:
    python scripts/deactivate_renamed_ticker_duplicates.py [--dry-run]

Safe to re-run: a symbol already deactivated is skipped (WHERE active = true in the update),
and the downstream purge is a no-op once those rows are already gone.
"""

import argparse
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loaders.load_market_constituents import NASDAQ_URL, OTHER_URL
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.url_validator import validate_url

# old_ticker -> new_ticker, each independently verified this session against SEC's
# formerNames history (real, dated legal-entity rename) AND the live NASDAQ symbol feed
# (old ticker absent, new ticker present) - see module docstring. Do not add an entry here
# without the same two-source verification; a single source (SEC tickers[] alone, or
# yfinance alone) has been shown to point the wrong way for this exact case.
VERIFIED_RENAMES: dict[str, str] = {
    "KWM": "NXAT",
    "CYCN": "KRSA",
}

_DOWNSTREAM_SCORE_TABLES = (
    "stock_scores",
    "value_metrics",
    "stability_metrics",
    "growth_metrics",
    "momentum_metrics",
    "quality_metrics",
)


def _fetch_live_symbol_set(url: str) -> set[str]:
    is_valid, error_msg = validate_url(url, allowed_domains=["nasdaqtrader.com"])
    if not is_valid:
        raise RuntimeError(f"SSRF validation failed for {url}: {error_msg}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    lines = resp.text.splitlines()
    symbols = set()
    for line in lines[1:-1]:  # header row + trailing "File Creation Time" footer
        parts = line.split("|")
        if parts and parts[0]:
            symbols.add(parts[0].strip().upper())
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions, write nothing")
    args = parser.parse_args()

    live_symbols = _fetch_live_symbol_set(NASDAQ_URL) | _fetch_live_symbol_set(OTHER_URL)

    to_deactivate: list[str] = []
    for old, new in VERIFIED_RENAMES.items():
        if old in live_symbols:
            print(f"SKIP {old}->{new}: {old} is still present in today's live NASDAQ/otherlisted feed")
            continue
        if new not in live_symbols:
            print(f"SKIP {old}->{new}: {new} is NOT present in today's live feed - re-verify before acting")
            continue
        to_deactivate.append(old)
        print(f"CONFIRMED {old}->{new}: {old} absent from live feed, {new} present")

    if not to_deactivate:
        print("Nothing to do.")
        return

    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol FROM stock_symbols WHERE symbol = ANY(%s) AND active = true", (to_deactivate,))
        still_active = [r[0] for r in cur.fetchall()]

    if not still_active:
        print("All verified old tickers already inactive - nothing to do.")
        return

    print(f"Deactivating: {still_active}")
    if args.dry_run:
        print("--dry-run: no changes written")
        return

    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE stock_symbols
            SET active = false, data_unavailable = true,
                data_unavailable_reason = 'renamed_ticker_superseded_by_new_symbol'
            WHERE symbol = ANY(%s) AND active = true
            """,
            (still_active,),
        )
        for table in _DOWNSTREAM_SCORE_TABLES:
            table_safe = assert_safe_table(table)
            cur.execute(f"DELETE FROM {table_safe} WHERE symbol = ANY(%s)", (still_active,))

    print(f"Done. Deactivated + purged downstream score rows for: {still_active}")


if __name__ == "__main__":
    main()
