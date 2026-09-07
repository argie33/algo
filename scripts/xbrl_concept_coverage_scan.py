#!/usr/bin/env python3
"""Find us-gaap/dei XBRL concepts our SEC loaders never fetch at all.

We currently discover missing concepts reactively - one bad-looking number at a
time, per symbol, per bug report. This script instead diffs the FULL set of
concepts real filers actually tag (read from the on-disk SEC EDGAR companyfacts
cache built up by normal loader runs - see utils/external/sec_edgar_client.py's
_DISK_CACHE_DIR) against the allowlist of concepts our loader source files know
how to fetch (utils/external/sec_income_statement.py, sec_balance_sheet.py,
sec_cash_flow.py, sec_custom_xbrl_concepts.py). Anything present in real filings
but absent from our allowlist is a candidate gap - ranked by how many distinct
companies tag it, since a concept only one filer uses is far less worth chasing
than one 200 filers use.

This does NOT tell you a concept is a bug (many belong to statements we don't
score, e.g. business-combination purchase-price-allocation detail, or are pure
XBRL bookkeeping like "CommonStockParOrStatedValuePerShare" dimensional
members). It tells you where to LOOK. Read the top of each frequency bucket by
hand before adding anything.

The actual scan/diff/dismiss logic lives in utils/external/xbrl_concept_coverage.py,
shared with algo/monitoring/data_patrol/checks/xbrl_new_concepts.py (2026-09-07) -
that checker runs this same gap-detection automatically on every scheduled DataPatrol
pass instead of only when a human remembers to run this script by hand, closing the
"how do we notice a newly-adopted taxonomy tag in a future filing" gap. This script
remains the right tool for deep, filtered, one-off investigation (--grep, --top, digging
into a specific namespace) and for maintaining the dismissed-concept triage log.

Usage:
    python scripts/xbrl_concept_coverage_scan.py                  # top 100, all namespaces
    python scripts/xbrl_concept_coverage_scan.py --top 300
    python scripts/xbrl_concept_coverage_scan.py --namespace us-gaap
    python scripts/xbrl_concept_coverage_scan.py --grep revenue    # filter by substring
    python scripts/xbrl_concept_coverage_scan.py --min-companies 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.external.xbrl_concept_coverage import (  # noqa: E402
    CONCEPT_SOURCE_FILES,
    DISMISSED_FILE,
    find_gaps,
    iter_companyfacts_cache,
    load_dismissed,
    load_known_concepts,
    save_dismissed,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=100, help="How many gap concepts to print (default 100)")
    parser.add_argument(
        "--namespace",
        action="append",
        dest="namespaces",
        help="XBRL namespace to scan (repeatable). Default: us-gaap, dei. "
        "companyfacts also carries 'ffd'/'ecd' (SEC-specific, mostly executive-comp/proxy - "
        "not statement data) which are excluded unless explicitly requested.",
    )
    parser.add_argument("--min-companies", type=int, default=1, help="Drop concepts tagged by fewer than N companies")
    parser.add_argument("--grep", help="Only show concepts whose name contains this substring (case-insensitive)")
    parser.add_argument(
        "--exclude-noise",
        action="store_true",
        help="Drop concepts matching known footnote/schedule boilerplate patterns (see NOISE_SUBSTRINGS)",
    )
    parser.add_argument(
        "--include-dismissed",
        action="store_true",
        help="Show previously-dismissed concepts too (by default they're hidden - see --dismiss)",
    )
    parser.add_argument("--show-dismissed", action="store_true", help="Print the dismissed-concept log and exit")
    parser.add_argument(
        "--dismiss",
        metavar="NAMESPACE:CONCEPT",
        help="Record a concept as reviewed-and-out-of-scope (e.g. 'us-gaap:GuaranteeObligations') "
        "so future scans stop resurfacing it. Requires --reason.",
    )
    parser.add_argument("--reason", help="Why --dismiss's concept is out of scope. Required with --dismiss.")
    parser.add_argument(
        "--undismiss",
        metavar="NAMESPACE:CONCEPT",
        help="Remove a concept from the dismissed log (e.g. after adding real support for it)",
    )
    args = parser.parse_args()

    if args.show_dismissed:
        dismissed = load_dismissed()
        print(f"{len(dismissed)} dismissed concepts in {DISMISSED_FILE.relative_to(REPO_ROOT)}:\n")
        for key, reason in sorted(dismissed.items()):
            print(f"  {key:<65} {reason}")
        return

    if args.undismiss:
        dismissed = load_dismissed()
        if args.undismiss in dismissed:
            del dismissed[args.undismiss]
            save_dismissed(dismissed)
            print(f"Removed {args.undismiss} from the dismissed log.")
        else:
            print(f"{args.undismiss} was not in the dismissed log.")
        return

    if args.dismiss:
        if not args.reason:
            parser.error("--dismiss requires --reason")
        dismissed = load_dismissed()
        dismissed[args.dismiss] = args.reason
        save_dismissed(dismissed)
        print(f"Dismissed {args.dismiss}: {args.reason}")
        return

    namespaces = args.namespaces or ["us-gaap", "dei"]

    known = load_known_concepts()
    print(f"Loaded {len(known)} known concept literals from {len(CONCEPT_SOURCE_FILES)} source files.")

    if not iter_companyfacts_cache():
        print(
            "No cached companyfacts found under %TEMP%/algo-sec-edgar-cache/companyfacts.\n"
            "This scan reads the disk cache loaders already populate - run the financial "
            "statements loader (or scripts/local_loader_scheduler.py) first, or just re-run "
            "this script during/after a normal pipeline run.",
            file=sys.stderr,
        )
        return

    dismissed = load_dismissed()
    total_companies = len(iter_companyfacts_cache())
    print(f"Scanned {total_companies} cached companyfacts payloads across namespaces: {namespaces}")
    print(f"{len(dismissed)} concepts already triaged-and-dismissed (see {DISMISSED_FILE.name}), hidden by default.")

    gaps = find_gaps(
        namespaces,
        min_companies=args.min_companies,
        exclude_noise=args.exclude_noise,
        include_dismissed=args.include_dismissed,
    )
    if args.grep:
        gaps = [g for g in gaps if args.grep.lower() in g[1].split(":", 1)[1].lower()]

    print(
        f"\n{len(gaps)} undismissed concepts tagged by real filers but absent from our fetch allowlist "
        f"(showing top {args.top}):\n"
    )
    print(f"{'companies':>9}  {'concept':<70}  example filer")
    print("-" * 110)
    for n, key, example_name in gaps[: args.top]:
        print(f"{n:>9}  {key:<70}  {example_name}")

    print(
        "\nReviewed a concept above and decided it's not needed? Record it so it stops coming back:\n"
        f'  python {Path(__file__).name} --dismiss "us-gaap:SomeConcept" --reason "why"'
    )


if __name__ == "__main__":
    main()
