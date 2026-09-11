#!/usr/bin/env python3
"""Cross-check a batch of symbols' real XBRL tags against SEC DERA's bulk quarterly
"Financial Statement Data Sets" (num.txt/sub.txt), without any per-symbol companyfacts/
frames HTTP call.

ADDED 2026-09-11 (goal: "SEC/XBRL missing data" push, "resources we should be tapping into"
ask). `scripts/xbrl_frames_check.py` (2026-09-10) answers "does this ONE filer tag ANY of
these candidate concepts" with one HTTP call per concept+unit+period - fine for a single
symbol, but it doesn't scale to "which of these 50 stuck symbols actually have a usable
concept under some other name" without 50+ HTTP calls against the same shared SEC rate-limit
budget every loader depends on. DERA's bulk files cover every filer's every tagged fact for
filings ACCEPTED in that calendar quarter (note: keyed by acceptance date, not fiscal period -
a FY2025 10-K accepted in 2026Q2 shows up in the 2026q2 file even though its own `period`
column says 2025-12-31) in one download, so a whole batch of symbols can be checked in a
single linear scan of one cached file - no per-symbol network call, no rate-limit/ban risk.

Practical use: when a batch of symbols is stuck on a "concept never tagged" reason (operating
income, total debt, etc.), run this to see EVERY real us-gaap/ifrs-full tag each symbol's most
recent 10-K/10-K-A/20-F actually carries - if a tag we don't currently fetch shows up for
several of them, that's a concrete allowlist candidate; if none do, the gap is a real filing
omission, not a missing allowlist entry.

Usage:
    python scripts/xbrl_dera_bulk_scan.py --symbols RCBC,MOBI,KARD --keyword Operating Debt
    python scripts/xbrl_dera_bulk_scan.py --symbols BEPC --quarters 2026q2 2026q1

Deliberately NOT wired into any loader or DataPatrol check - this is a research/investigation
tool (like xbrl_frames_check.py), not a production data path. The quarterly zip is cached
under %TEMP%/algo-dera-cache so a repeat run against a different symbol batch is free.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.external.sec_edgar_client import SecEdgarClient  # noqa: E402

_DERA_CACHE_DIR = Path(tempfile.gettempdir()) / "algo-dera-cache"
_DERA_BASE_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
_USER_AGENT = "algo-research contact@example.com"


def _quarter_zip_path(quarter: str) -> Path:
    return _DERA_CACHE_DIR / f"{quarter}.zip"


def download_quarter(quarter: str) -> Path | None:
    """Downloads (if not already cached) the DERA bulk zip for one quarter, e.g. "2026q2".
    Returns None (not an error) for a quarter SEC hasn't published yet - _next_quarter's
    "current quarter + 1" heuristic can land on a not-yet-published quarter near the
    boundary, which should just be skipped, not crash the whole batch."""
    path = _quarter_zip_path(quarter)
    if path.exists():
        return path
    _DERA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{_DERA_BASE_URL}/{quarter}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    print(f"Downloading {url} ...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  {quarter}: not yet published by SEC (404) - skipping", file=sys.stderr)
            return None
        raise
    path.write_bytes(data)
    return path


def _quarter_for_date(filing_date: str) -> str:
    """ "2025-10-31" -> "2025q4". DERA quarter files are keyed by the accession's ACCEPTANCE
    date, not fiscal period - a late-quarter filing can land in the FOLLOWING quarter's file
    (SEC's own processing lag), so callers should try this quarter and the next one."""
    year, month, _day = filing_date.split("-")
    q = (int(month) - 1) // 3 + 1
    return f"{year}q{q}"


def _next_quarter(quarter: str) -> str:
    year_str, q_str = quarter.split("q")
    year, q = int(year_str), int(q_str)
    return f"{year}q{q + 1}" if q < 4 else f"{year + 1}q1"


def _resolve_target_accessions(symbols: list[str]) -> dict[str, tuple[str, str, list[str]]]:
    """symbol -> (cik, accession, candidate_quarters) for the most recent 10-K/10-K-A/20-F/
    40-F, reusing the existing ticker-cache + submissions.json infra (both already disk-
    cached, so this is cheap even across a large batch). candidate_quarters is the filing's
    own acceptance quarter plus the next one (see _quarter_for_date's docstring)."""
    client = SecEdgarClient()
    annual_forms = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
    out: dict[str, tuple[str, str, list[str]]] = {}
    for symbol in symbols:
        try:
            cik = client.symbol_to_cik(symbol)
            submissions = client.get_submissions(cik)
        except (FileNotFoundError, ValueError) as e:
            print(f"  {symbol}: could not resolve CIK/submissions ({e})", file=sys.stderr)
            continue
        recent = (submissions.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        dates = recent.get("filingDate") or []
        idx = next((i for i, f in enumerate(forms) if f in annual_forms), None)
        if idx is None or idx >= len(accessions) or idx >= len(dates):
            print(f"  {symbol}: no 10-K/20-F/40-F in recent filings", file=sys.stderr)
            continue
        accession = accessions[idx]
        quarter = _quarter_for_date(dates[idx])
        out[symbol] = (cik.lstrip("0") or "0", accession, [quarter, _next_quarter(quarter)])
    return out


def scan_quarters_for_accessions(
    quarter_paths: list[Path], target_adsh_to_symbol: dict[str, str]
) -> dict[str, set[str]]:
    """Single streaming pass per quarter file's num.txt - never loads the whole (500MB+)
    file into memory. Returns symbol -> set of distinct tag names found."""
    found: dict[str, set[str]] = {sym: set() for sym in target_adsh_to_symbol.values()}
    remaining_adsh = set(target_adsh_to_symbol)
    for path in quarter_paths:
        if not remaining_adsh:
            break
        with zipfile.ZipFile(path) as zf, zf.open("num.txt") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter="\t")
            header = next(reader)
            adsh_idx = header.index("adsh")
            tag_idx = header.index("tag")
            for row in reader:
                if not row:
                    continue
                adsh = row[adsh_idx]
                if adsh in remaining_adsh:
                    found[target_adsh_to_symbol[adsh]].add(row[tag_idx])
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", required=True, help="Comma-separated tickers to check")
    parser.add_argument(
        "--quarters",
        nargs="+",
        default=None,
        help="Override: scan exactly these DERA quarter file(s) instead of auto-detecting "
        "each symbol's own filing-acceptance quarter (+ the following one, for processing lag)",
    )
    parser.add_argument(
        "--keyword",
        nargs="*",
        default=None,
        help="Only print tags containing any of these (case-insensitive) substrings",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Resolving CIK/accession for {len(symbols)} symbol(s)...")
    resolved = _resolve_target_accessions(symbols)
    if not resolved:
        print("No symbols resolved to a usable accession - nothing to scan.")
        return

    adsh_to_symbol = {accn: sym for sym, (_cik, accn, _quarters) in resolved.items()}
    needed_quarters = args.quarters or sorted({q for *_rest, quarters in resolved.values() for q in quarters})
    quarter_paths = [p for p in (download_quarter(q) for q in needed_quarters) if p is not None]

    print(f"Scanning {len(quarter_paths)} quarter file(s) for {len(adsh_to_symbol)} target accession(s)...")
    found = scan_quarters_for_accessions(quarter_paths, adsh_to_symbol)

    for symbol in symbols:
        if symbol not in resolved:
            print(f"\n{symbol}: SKIPPED (no resolvable accession)")
            continue
        _cik, accession, quarters = resolved[symbol]
        tags = found.get(symbol)
        if not tags:
            print(f"\n{symbol}: accession {accession} not found in {quarters} - try --quarters with an earlier value")
            continue
        shown = sorted(tags)
        if args.keyword:
            needles = [k.lower() for k in args.keyword]
            shown = [t for t in shown if any(n in t.lower() for n in needles)]
        print(f"\n{symbol}: {len(tags)} distinct tag(s) in accession {accession}")
        for t in shown:
            print(f"  {t}")
        if args.keyword and not shown:
            print(
                f"  (none matched keyword filter {args.keyword} - {len(tags)} total tags exist, see without --keyword)"
            )


if __name__ == "__main__":
    main()
