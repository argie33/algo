#!/usr/bin/env python3
"""Systematic "concept never tagged" gap-filler: runs xbrl_dera_bulk_scan.py's per-accession
tag-discovery across the WHOLE current population of scored symbols stuck on a "this filer
never tags concept X" reason - not a hand-picked batch.

ADDED 2026-09-11 (goal: "SEC/XBRL missing data under 200" push, "resources we should be
tapping into" ask). `xbrl_dera_bulk_scan.py` (same session, earlier) already proved DERA's
bulk quarterly num.txt can answer "what does this filer's real accession actually tag" for a
batch with one cached download instead of N rate-limited companyfacts calls - but it only ever
ran against symbols a human typed in by hand. `xbrl_concept_coverage_scan.py` answers a related
but different question ("what concept does the WHOLE universe tag that we've never fetched at
all") and is noise-dominated at universe scale (0 undismissed candidates as of this session -
see MEMORY.md xbrl_under200_20260911_pm_session_floor_reconfirmed) because most gaps it finds
belong to filers we already handle fine for every OTHER field.

This script instead starts from the exact population that's actually stuck right now (queried
live from the DB, not a memory citation - see this session's "assume all the memory is wrong"
directive) and asks the narrower, more actionable question: "of the concepts THESE specific
stuck filers' most recent 10-K/20-F/40-F really tag, which aren't in our allowlist?" - reusing
utils/external/xbrl_concept_coverage.py's load_known_concepts()/NOISE_SUBSTRINGS/dismissed-list
so a candidate here is filtered exactly like the coverage-scan tool's candidates are, just
ranked by "how many of the stuck symbols would this actually unblock" instead of raw universe
frequency.

This is a READ-ONLY reporting tool - it does not touch any loader allowlist, DB row, or
unavailable_reason. It tells you where to look (same posture as xbrl_concept_coverage_scan.py's
own docstring); a human (or a follow-up session) still reviews each candidate against real
companyfacts before wiring it into utils/external/sec_income_statement.py etc.

Usage:
    python scripts/xbrl_dera_bulk_gap_filler.py                  # scan every stuck symbol found live
    python scripts/xbrl_dera_bulk_gap_filler.py --reasons capex_never_tagged_in_recent_filings
    python scripts/xbrl_dera_bulk_gap_filler.py --min-symbols 2  # drop candidates only 1 stuck symbol tags
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.xbrl_dera_bulk_scan import (  # noqa: E402
    _resolve_target_accessions,
    download_quarter,
    scan_quarters_for_accessions,
)
from utils.external.xbrl_concept_coverage import NOISE_SUBSTRINGS, load_dismissed, load_known_concepts  # noqa: E402

# The "this specific filer never tags concept X" reason class (see coverage_category_rules.py's
# own inline history for where each of these is wired) - deliberately excludes the broader
# "no filing exists at all" dead-end reasons (no_income_statement, net_income_not_reported,
# missing_sec_data, unsupported_currency_no_fx_rate, cik_not_found, no_annual_report_filing)
# since DERA can't recover a concept from a filer with no companyfacts payload at all - those
# are a different, already-exhausted dead-end class (see MEMORY.md), not what this tool targets.
_CONCEPT_GAP_REASONS: set[str] = {
    "total_debt_not_itemized",
    "interest_expense_not_itemized",
    "stockholders_equity_not_reported",
    "stockholders_equity_never_tagged_in_filings",
    "operating_income_not_itemized",
    "no_dividend_xbrl_concepts",
    "no_us_gaap_facts",
    "no_recent_balance_sheet_data_reported",
    "no_recent_free_cash_flow_reported",
    "no_recent_operating_cash_flow_reported",
    "no_recent_total_assets_reported",
    "eps_never_tagged_in_filings",
    "capex_never_tagged_in_recent_filings",
    "no_recent_current_assets_reported",
    "no_recent_current_liabilities_reported",
    "no_recent_cash_reported",
    "missing_cash_flow_data",
}

# (table, reason_column) for every column that has actually carried one of the reasons above -
# see this session's live coverage-report breakdown (MEMORY.md xbrl_under200_20260911_pm_
# session_floor_reconfirmed). Deliberately a flat list, not a schema-introspection query - the
# scored factor set is a known, small, stable list (coverage_classification.py's own _UNSCORED_
# FACTORS split already documents it), not worth reverse-engineering from information_schema.
_REASON_COLUMNS: list[tuple[str, str]] = [
    ("quality_metrics", "roe_unavailable_reason"),
    ("quality_metrics", "roa_unavailable_reason"),
    ("quality_metrics", "roce_pct_unavailable_reason"),
    ("quality_metrics", "debt_to_equity_unavailable_reason"),
    ("quality_metrics", "fcf_margin_unavailable_reason"),
    ("quality_metrics", "gross_profitability_unavailable_reason"),
    ("quality_metrics", "asset_turnover_unavailable_reason"),
    ("quality_metrics", "quality_score_unavailable_reason"),
    ("growth_metrics", "sustainable_growth_rate_unavailable_reason"),
    ("value_metrics", "pe_ratio_unavailable_reason"),
    ("value_metrics", "pb_ratio_unavailable_reason"),
    ("value_metrics", "ps_ratio_unavailable_reason"),
    ("sec_valuations", "dcf_fcf_unavailable_reason"),
]


def _find_stuck_symbols(cur: Any, reasons: set[str]) -> dict[str, set[str]]:
    """symbol -> set of reasons it's currently stuck on, across every _REASON_COLUMNS entry."""
    stuck: dict[str, set[str]] = defaultdict(set)
    for table, column in _REASON_COLUMNS:
        cur.execute(f"SELECT symbol, {column} FROM {table} WHERE {column} = ANY(%s)", (list(reasons),))
        for symbol, reason in cur.fetchall():
            stuck[symbol].add(reason)
    return stuck


def run(reasons: set[str], min_symbols: int) -> None:
    from utils.db.context import DatabaseContext

    with DatabaseContext("read") as cur:
        stuck = _find_stuck_symbols(cur, reasons)

    if not stuck:
        print("No symbols currently stuck on any of the targeted concept-gap reasons.")
        return
    symbols = sorted(stuck)
    print(f"Found {len(symbols)} stuck symbol(s) across {len(reasons)} reason(s): {symbols}\n")

    print("Resolving CIK/accession for each stuck symbol...")
    resolved = _resolve_target_accessions(symbols)
    unresolved = [s for s in symbols if s not in resolved]
    if unresolved:
        print(f"  {len(unresolved)} symbol(s) had no resolvable 10-K/20-F/40-F accession: {unresolved}")
    if not resolved:
        print("No symbols resolved to a usable accession - nothing to scan.")
        return

    adsh_to_symbol = {accn: sym for sym, (_cik, accn, _quarters) in resolved.items()}
    needed_quarters = sorted({q for *_rest, quarters in resolved.values() for q in quarters})
    print(f"Downloading/caching {len(needed_quarters)} DERA quarter file(s): {needed_quarters}")
    quarter_paths = [p for p in (download_quarter(q) for q in needed_quarters) if p is not None]

    print(f"Scanning for {len(adsh_to_symbol)} target accession(s)...")
    tags_by_symbol = scan_quarters_for_accessions(quarter_paths, adsh_to_symbol)
    no_tags = [s for s in resolved if not tags_by_symbol.get(s)]
    if no_tags:
        print(
            f"  {len(no_tags)} symbol(s) resolved an accession but it wasn't found in the scanned "
            f"quarter(s) (try re-running with an earlier --quarters override): {no_tags}"
        )

    known = load_known_concepts()
    dismissed = load_dismissed()

    # candidate concept -> set of stuck symbols that tag it
    candidates: dict[str, set[str]] = defaultdict(set)
    for symbol, tags in tags_by_symbol.items():
        for tag in tags:
            if tag in known:
                continue
            if any(noise in tag for noise in NOISE_SUBSTRINGS):
                continue
            if any(f"us-gaap:{tag}" == k or f"ifrs-full:{tag}" == k for k in dismissed):
                continue
            candidates[tag].add(symbol)

    ranked = sorted(
        ((len(syms), tag, syms) for tag, syms in candidates.items() if len(syms) >= min_symbols),
        reverse=True,
    )

    print(f"\n{'=' * 70}")
    print(
        f"{len(ranked)} candidate concept(s) (min {min_symbols} stuck symbol(s) each, "
        f"already-known/noise/dismissed excluded):\n"
    )
    for count, tag, syms in ranked:
        reasons_for = sorted({r for s in syms for r in stuck[s]})
        print(f"  {tag}  ({count} stuck symbol(s): {sorted(syms)})")
        print(f"      reasons this would address: {reasons_for}")
    if not ranked:
        print(
            "  (none - every real tag these stuck filers carry is already known/noise/dismissed. "
            "This confirms, rather than closes, the structural-floor conclusion for this batch.)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--reasons",
        nargs="*",
        default=None,
        help="Restrict to these unavailable_reason value(s) instead of the full concept-gap set",
    )
    parser.add_argument("--min-symbols", type=int, default=1, help="Drop candidates tagged by fewer stuck symbols")
    args = parser.parse_args()

    reasons = set(args.reasons) if args.reasons else _CONCEPT_GAP_REASONS
    unknown = reasons - _CONCEPT_GAP_REASONS
    if unknown:
        print(f"Warning: {unknown} not in the known concept-gap reason set - scanning anyway.")
    run(reasons, args.min_symbols)


if __name__ == "__main__":
    main()
