#!/usr/bin/env python3
"""Shared logic for finding us-gaap/dei/ifrs-full XBRL concepts our SEC loaders never fetch.

Extracted from scripts/xbrl_concept_coverage_scan.py (2026-09-07, goal session: "is there a
better way to deal with XBRL validation than checking every symbol by hand") so the same
concept-gap-detection logic can be reused both as a manually-run CLI tool (the script) and as
an automated DataPatrol check (algo/monitoring/data_patrol/checks/xbrl_new_concepts.py) that
runs on every scheduled pipeline pass instead of only when a human remembers to invoke the
script. See that checker's module docstring for why: this is the "future filings" gap - a
newly-adopted taxonomy tag previously sat invisible until someone thought to re-run the script
or a tie-out check happened to catch a downstream symptom.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Persistent triage state - see scripts/xbrl_concept_coverage_scan.py's original comment for the
# full rationale. Checked into git, shared across both the manual script and the automated check.
DISMISSED_FILE = REPO_ROOT / "scripts" / "xbrl_concept_coverage_dismissed.json"

# Every place a real (non-test, non-fallback-table) concept list lives today.
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

# A real us-gaap/dei/ifrs-full concept name is PascalCase, letters+digits only, at least ~5
# characters. Matches some non-concept PascalCase identifiers too, but those simply never
# appear in real companyfacts data and get filtered out at diff time.
_CONCEPT_LITERAL_RE = re.compile(r'"([A-Z][A-Za-z0-9]{4,90})"')

# Concept-name substrings that are almost always footnote/disclosure detail rather than a
# statement-level number we'd ever score - see scripts/xbrl_concept_coverage_scan.py's
# original comment for detail on each category.
NOISE_SUBSTRINGS = [
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


def load_dismissed() -> dict[str, str]:
    if not DISMISSED_FILE.exists():
        # Not an error - no dismissals have been recorded yet, not that data is missing.
        return {}
    try:
        return cast(dict[str, str], json.loads(DISMISSED_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def save_dismissed(dismissed: dict[str, str]) -> None:
    DISMISSED_FILE.write_text(json.dumps(dict(sorted(dismissed.items())), indent=2) + "\n", encoding="utf-8")


def load_known_concepts() -> set[str]:
    known: set[str] = set()
    for rel in CONCEPT_SOURCE_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        known.update(_CONCEPT_LITERAL_RE.findall(text))
    return known


def iter_companyfacts_cache() -> list[Path]:
    cache_dir = Path(tempfile.gettempdir()) / "algo-sec-edgar-cache" / "companyfacts"
    if not cache_dir.exists():
        # Not an error - not yet initialized by a loader run. Callers that need to
        # distinguish this from "scanned and found nothing" check this function themselves.
        return []
    return sorted(cache_dir.glob("*.json"))


def scan_cache(namespaces: list[str]) -> tuple[Counter[str], dict[str, str]]:
    """Return (concept -> #companies tagging it, one example entityName per concept)."""
    files = iter_companyfacts_cache()
    if not files:
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


def find_gaps(
    namespaces: list[str],
    min_companies: int = 1,
    exclude_noise: bool = False,
    include_dismissed: bool = False,
) -> list[tuple[int, str, str]]:
    """Return (company_count, "namespace:Concept", example_filer) tuples, sorted descending.

    Empty list also means "no cached companyfacts data available" - callers that need to
    distinguish that from "scanned and found nothing" should check iter_companyfacts_cache()
    themselves first.
    """
    known = load_known_concepts()
    dismissed = load_dismissed()
    counts, examples = scan_cache(namespaces)

    gaps = []
    for key, n in counts.items():
        _ns, concept = key.split(":", 1)
        if concept in known:
            continue
        if n < min_companies:
            continue
        if exclude_noise and any(noise in concept for noise in NOISE_SUBSTRINGS):
            continue
        if key in dismissed and not include_dismissed:
            continue
        gaps.append((n, key, examples[key]))
    gaps.sort(reverse=True)
    return gaps
