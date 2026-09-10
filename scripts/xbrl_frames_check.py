#!/usr/bin/env python3
"""Check, via SEC's XBRL frames API, whether a specific filer tags ANY of a list of
candidate concepts for a recent period - without needing that filer's companyfacts
payload already sitting in our on-disk cache.

ADDED 2026-09-10 (goal: "missing SEC/XBRL under 500" session, "resources we should be
tapping into" ask). xbrl_concept_coverage_scan.py's gap detection (utils/external/
xbrl_concept_coverage.py) only ever sees concepts used by symbols already in our own
companyfacts disk cache (iter_companyfacts_cache) - it can't tell "concept X doesn't
exist for anyone in this period" apart from "concept X exists but no cached filer of
ours happens to use it yet". SEC's frames API (one HTTP call per concept+unit+period,
returns every filer's value that period, keyed by CIK) answers this directly and is
cheap to probe a short candidate list against, since it needs no bulk companyfacts
fetch for the target filer at all.

Practical use: when a symbol is stuck on a "concept never tagged" reason (capex,
operating income, debt, etc.), use this to quickly rule candidate synonym concepts
in/out before spending time on a code change - if the filer's CIK doesn't show up in
ANY candidate's frames data for the relevant recent years, the concept genuinely isn't
in that filer's XBRL (a real filing gap, not an extraction bug); if it DOES show up,
that's a concrete concept name to add to the loader's allowlist.

Usage:
    python scripts/xbrl_frames_check.py --symbol CNQ --taxonomy ifrs-full \\
        --concepts PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities \\
        --unit CAD --years 2023 2024 2025
    python scripts/xbrl_frames_check.py --symbol AAPL --taxonomy us-gaap \\
        --concepts PaymentsToAcquirePropertyPlantAndEquipment --unit USD --years 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.external.sec_edgar_client import SecEdgarClient  # noqa: E402


def check_symbol_against_frames(
    client: SecEdgarClient,
    symbol: str,
    taxonomy: str,
    concepts: list[str],
    unit: str,
    years: list[int],
) -> list[tuple[str, int, dict[str, object]]]:
    """Return (concept, year, frame_entry) for every candidate concept/year where the
    symbol's CIK actually appears in that period's frames data."""
    cik = int(client.symbol_to_cik(symbol))
    hits: list[tuple[str, int, dict[str, object]]] = []
    for concept in concepts:
        for year in years:
            for period in (f"CY{year}", f"CY{year}Q4I"):
                try:
                    data = client.get_frames(taxonomy, concept, unit, period)
                except FileNotFoundError:
                    continue
                except RuntimeError as e:
                    print(f"  (transient error fetching {taxonomy}/{concept}/{unit}/{period}: {e})", file=sys.stderr)
                    continue
                for entry in data.get("data", []):
                    if entry.get("cik") == cik:
                        hits.append((concept, year, entry))
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", required=True, help="Ticker to check")
    parser.add_argument("--taxonomy", default="us-gaap", choices=["us-gaap", "ifrs-full"])
    parser.add_argument("--concepts", nargs="+", required=True, help="Candidate concept names to probe")
    parser.add_argument("--unit", default="USD", help="XBRL unit, e.g. USD, CAD, USD-per-shares")
    parser.add_argument(
        "--years", nargs="+", type=int, required=True, help="Fiscal years to check, e.g. 2023 2024 2025"
    )
    args = parser.parse_args()

    client = SecEdgarClient()
    print(f"Checking {args.symbol} against {len(args.concepts)} candidate concept(s), years {args.years}...")
    hits = check_symbol_against_frames(client, args.symbol, args.taxonomy, args.concepts, args.unit, args.years)

    if not hits:
        print(
            f"No hits - {args.symbol} does not tag any candidate concept in {args.taxonomy}/{args.unit} for the given years."
        )
        print("This is evidence the gap is a real filing omission, not a missing allowlist entry.")
        return

    print(f"{len(hits)} hit(s):")
    for concept, year, entry in hits:
        print(f"  {concept} ({year}): val={entry.get('val')} end={entry.get('end')} accn={entry.get('accn')}")


if __name__ == "__main__":
    main()
