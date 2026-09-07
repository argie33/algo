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

Usage:
    python scripts/xbrl_concept_coverage_scan.py                  # top 100, all namespaces
    python scripts/xbrl_concept_coverage_scan.py --top 300
    python scripts/xbrl_concept_coverage_scan.py --namespace us-gaap
    python scripts/xbrl_concept_coverage_scan.py --grep revenue    # filter by substring
    python scripts/xbrl_concept_coverage_scan.py --min-companies 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent

# Persistent triage state. Without this, every re-run re-surfaces every already-reviewed
# footnote/table concept from scratch and the tool degenerates into exactly the "finding
# them one here and one there" noise it's meant to fix. Once a human has looked at a
# concept and decided it's genuinely out of scope (not a bug, not worth a field_mapping
# entry), record it here with `--dismiss` so future scans only surface what's actually
# NEW - a fresh symbol added to the universe, a newly-adopted taxonomy tag, or something
# nobody has triaged yet. Checked into git (not in .gitignore) so the triage history is
# shared across sessions/machines, same rationale as .file-size-baseline.json.
_DISMISSED_FILE = REPO_ROOT / "scripts" / "xbrl_concept_coverage_dismissed.json"


def load_dismissed() -> dict[str, str]:
    if not _DISMISSED_FILE.exists():
        return {}
    try:
        return cast(dict[str, str], json.loads(_DISMISSED_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def save_dismissed(dismissed: dict[str, str]) -> None:
    _DISMISSED_FILE.write_text(json.dumps(dict(sorted(dismissed.items())), indent=2) + "\n", encoding="utf-8")


# Every place a real (non-test, non-fallback-table) concept list lives today.
# Kept as a flat list of files rather than importing the modules: importing
# would require full DB/env setup these loader modules assume at import time,
# while the concept literals themselves are just string constants we can pull
# out with a regex - far cheaper and has no side effects.
CONCEPT_SOURCE_FILES = [
    "utils/external/sec_income_statement.py",
    "utils/external/sec_income_statement_fallbacks.py",
    "utils/external/sec_balance_sheet.py",
    "utils/external/sec_cash_flow.py",
    "utils/external/sec_custom_xbrl_concepts.py",
    "utils/external/sec_xbrl_segments.py",
    "utils/external/sec_xbrl_segment_revenue.py",
    "utils/external/sec_xbrl_segment_revenue_2.py",
    "utils/external/sec_statements.py",
    "utils/external/sec_statements_aggregate.py",
    "utils/external/sec_statements_entry_resolution.py",
    "utils/external/sec_statements_shared.py",
    "utils/external/sec_statements_unit_context.py",
    "loaders/helpers/sec_dual_class_eps.py",
    "loaders/helpers/sec_segment_debt.py",
    "loaders/helpers/sec_valuations_dcf.py",
    "loaders/helpers/sec_valuations_income_context.py",
    "loaders/helpers/sec_valuations_ratios.py",
    "loaders/helpers/sec_valuations_shares.py",
    "loaders/helpers/sec_valuations_yield_dcf.py",
    "loaders/load_sec_segment_info.py",
    "loaders/load_sec_segment_metrics.py",
]

# A real us-gaap/dei/ifrs-full concept name is PascalCase, letters+digits only,
# and (per the XBRL US-GAAP taxonomy) always at least ~5 characters. This same
# pattern also matches plenty of non-concept PascalCase identifiers (class
# names, exception names, dict keys unrelated to XBRL) that happen to live in
# these files - that's fine, those simply won't appear in real companyfacts
# data and get silently filtered out at diff time below, since we only ever
# ask "is this string a key some real filer's companyfacts actually used."
_CONCEPT_LITERAL_RE = re.compile(r'"([A-Z][A-Za-z0-9]{4,90})"')

# Concept-name substrings that are almost always footnote/disclosure detail rather
# than a statement-level number we'd ever score (lease payment-by-year schedules, tax
# rate reconciliation percentages, dilutive-securities tables, related-party detail,
# etc.) - --exclude-noise drops any concept containing one of these. This is a
# convenience filter for faster triage, not a claim any of these are permanently
# irrelevant: re-run without --exclude-noise (or narrow with --grep) if a specific
# missing score field's XBRL tag might actually live in one of these buckets.
_NOISE_SUBSTRINGS = [
    "TaxRateReconciliation",
    "PaymentsDue",
    "WeightedAverageNumberOf",
    "AntidilutiveSecurities",
    "RelatedParty",
    "SegmentReportingInformation",
    "ScheduleOf",
    "RangeMin",
    "RangeMax",
    "ShareBasedCompensationArrangementByShareBasedPaymentAward",
    "BusinessCombination",
    "IncomeLossFromDiscontinuedOperations",
    "AssetImpairmentCharges",
    "GuaranteeObligations",
    "DerivativeInstrument",
    "FairValue",
]


def load_known_concepts() -> set[str]:
    known: set[str] = set()
    for rel in CONCEPT_SOURCE_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"warning: concept source file missing, skipping: {rel}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        known.update(_CONCEPT_LITERAL_RE.findall(text))
    return known


def iter_companyfacts_cache() -> list[Path]:
    cache_dir = Path(tempfile.gettempdir()) / "algo-sec-edgar-cache" / "companyfacts"
    if not cache_dir.exists():
        return []
    return sorted(cache_dir.glob("*.json"))


def scan_cache(namespaces: list[str]) -> tuple[Counter[str], dict[str, str]]:
    """Return (concept -> #companies tagging it, one example entityName per concept)."""
    files = iter_companyfacts_cache()
    if not files:
        print(
            "No cached companyfacts found under %TEMP%/algo-sec-edgar-cache/companyfacts.\n"
            "This scan reads the disk cache loaders already populate - run the financial "
            "statements loader (or scripts/local_loader_scheduler.py) first, or just re-run "
            "this script during/after a normal pipeline run.",
            file=sys.stderr,
        )
        return Counter(), {}

    company_count: Counter[str] = Counter()
    example: dict[str, str] = {}
    for fp in files:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data") or {}
        entity_name = data.get("entityName", fp.stem)
        facts = data.get("facts") or {}
        seen_this_company: set[str] = set()
        for ns in namespaces:
            for concept in (facts.get(ns) or {}).keys():
                key = f"{ns}:{concept}"
                if key in seen_this_company:
                    continue
                seen_this_company.add(key)
                company_count[key] += 1
                example.setdefault(key, entity_name)
    return company_count, example


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
        help="Drop concepts matching known footnote/schedule boilerplate patterns (see _NOISE_SUBSTRINGS)",
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
        print(f"{len(dismissed)} dismissed concepts in {_DISMISSED_FILE.relative_to(REPO_ROOT)}:\n")
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

    dismissed = load_dismissed()

    counts, examples = scan_cache(namespaces)
    if not counts:
        return
    total_companies = len(iter_companyfacts_cache())
    print(f"Scanned {total_companies} cached companyfacts payloads across namespaces: {namespaces}")
    print(f"{len(dismissed)} concepts already triaged-and-dismissed (see {_DISMISSED_FILE.name}), hidden by default.")

    gaps = []
    for key, n in counts.items():
        _ns, concept = key.split(":", 1)
        if concept in known:
            continue
        if n < args.min_companies:
            continue
        if args.grep and args.grep.lower() not in concept.lower():
            continue
        if args.exclude_noise and any(noise in concept for noise in _NOISE_SUBSTRINGS):
            continue
        if key in dismissed and not args.include_dismissed:
            continue
        gaps.append((n, key, examples[key]))
    gaps.sort(reverse=True)

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
