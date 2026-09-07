#!/usr/bin/env python3
"""Manual deep-dive CLI for find_continuity_gaps() (utils/external/xbrl_concept_coverage.py) -
find filers where a core XBRL concept (Assets/Liabilities/NetIncomeLoss) was tagged every year
for 3+ straight prior annual filings but is absent from the most recent one.

Added 2026-09-07, paired with algo/monitoring/data_patrol/checks/xbrl_concept_continuity.py the
same way scripts/xbrl_concept_coverage_scan.py is paired with xbrl_new_concepts.py: that checker
runs this same diff logic automatically on every scheduled DataPatrol pass; this script remains
the right tool for a deliberate one-off deep-dive (--min-prior-years, a specific CIK) and for
maintaining the dismissed-finding triage log.

Each flagged pair is either a taxonomy/tag migration (the filer's XBRL agent switched to a
renamed/synonym concept we don't also fetch - the actual "what happens when companies change
things" gap this exists for) or a real one-off (final 10-K before going private/bankrupt/
acquired). Read the filing before dismissing - --dismiss is for the second case only; the
first case needs a real fetch-support fix, not a dismissal.

Usage:
    python scripts/xbrl_concept_continuity_scan.py                     # default 3-prior-year window
    python scripts/xbrl_concept_continuity_scan.py --min-prior-years 5 # stricter, fewer false positives
    python scripts/xbrl_concept_continuity_scan.py --show-dismissed
    python scripts/xbrl_concept_continuity_scan.py --dismiss 0000012345:NetIncomeLoss --reason "final 10-K before going private"
    python scripts/xbrl_concept_continuity_scan.py --undismiss 0000012345:NetIncomeLoss
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.external.xbrl_concept_coverage import (  # noqa: E402
    CONTINUITY_DISMISSED_FILE,
    find_continuity_gaps,
    iter_companyfacts_cache,
    load_continuity_dismissed,
    save_continuity_dismissed,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--min-prior-years",
        type=int,
        default=3,
        help="Consecutive prior annual filings a concept must have before flagging its absence "
        "in the latest one (default 3 - higher is stricter, fewer false positives)",
    )
    parser.add_argument("--show-dismissed", action="store_true", help="Print the dismissed-finding log and exit")
    parser.add_argument(
        "--dismiss",
        metavar="CIK:CONCEPT",
        help="Record a filer/concept pair as reviewed-and-legitimate (e.g. "
        "'0000012345:NetIncomeLoss') so future scans stop resurfacing it. Requires --reason.",
    )
    parser.add_argument("--reason", help="Why --dismiss's pair is legitimate. Required with --dismiss.")
    parser.add_argument(
        "--undismiss",
        metavar="CIK:CONCEPT",
        help="Remove a filer/concept pair from the dismissed log",
    )
    args = parser.parse_args()

    if args.show_dismissed:
        dismissed = load_continuity_dismissed()
        print(
            f"{len(dismissed)} dismissed filer/concept pairs in {CONTINUITY_DISMISSED_FILE.relative_to(REPO_ROOT)}:\n"
        )
        for key, reason in sorted(dismissed.items()):
            print(f"  {key:<30} {reason}")
        return

    if args.undismiss:
        dismissed = load_continuity_dismissed()
        if args.undismiss in dismissed:
            del dismissed[args.undismiss]
            save_continuity_dismissed(dismissed)
            print(f"Removed {args.undismiss} from the dismissed log.")
        else:
            print(f"{args.undismiss} was not in the dismissed log.")
        return

    if args.dismiss:
        if not args.reason:
            parser.error("--dismiss requires --reason")
        dismissed = load_continuity_dismissed()
        dismissed[args.dismiss] = args.reason
        save_continuity_dismissed(dismissed)
        print(f"Dismissed {args.dismiss}: {args.reason}")
        return

    if not iter_companyfacts_cache():
        print(
            "No cached companyfacts found under %TEMP%/algo-sec-edgar-cache/companyfacts.\n"
            "This scan reads the disk cache loaders already populate - run the financial "
            "statements loader at least once first."
        )
        return

    gaps = find_continuity_gaps(min_prior_years=args.min_prior_years)
    if not gaps:
        print(f"No continuity gaps found (min_prior_years={args.min_prior_years}).")
        return

    print(f"{len(gaps)} filer/concept continuity gap(s) (min_prior_years={args.min_prior_years}):\n")
    for gap in gaps:
        print(f"  {gap['concept']:<25} {gap['entity_name']} (CIK {gap['cik']})")
        print(f"    present every year through {gap['prior_years_present']}, absent in {gap['latest_expected_end']}")


if __name__ == "__main__":
    main()
