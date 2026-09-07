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

# Separate triage log for find_continuity_gaps() below - a different failure mode from the
# above (a concept we've never fetched at all) so it gets its own dismiss log rather than
# overloading DISMISSED_FILE's "namespace:Concept" keys with a second, incompatible key shape
# ("CIK:Concept", since a continuity gap is filer-specific, not concept-wide).
CONTINUITY_DISMISSED_FILE = REPO_ROOT / "scripts" / "xbrl_concept_continuity_dismissed.json"

# Concepts virtually every operating 10-K filer tags every single fiscal year, regardless of
# industry (financials/REITs/insurers included) - deliberately a short, conservative list.
# Anything broader (e.g. a specific debt or lease concept) legitimately appears/disappears
# for ordinary business reasons (a company pays off its only debt, adopts a new accounting
# standard, etc.) and would make this check noisy rather than high-signal. These three are the
# closest thing to "if this stops being tagged, something is wrong" for any going concern -
# either the filer switched to a synonym/renamed taxonomy tag (the actual "taxonomy migration"
# case this check exists for) or a real discontinuation (bankruptcy, going-private, final 10-K).
CORE_CONTINUITY_CONCEPTS = ["Assets", "Liabilities", "NetIncomeLoss"]

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
#
# FIXED 2026-09-07 (goal session: "make sure the list/checks are right" audit): the {4,90}
# upper bound silently excluded any ALREADY-fetched concept whose literal is over 90 chars
# from load_known_concepts()'s output - live-confirmed 9 real concepts we do fetch exceed 90
# chars (up to 110, e.g. sec_income_statement.py's "IncomeLossFromContinuingOperationsBefore
# IncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments", sec_cash_flow.py's two
# Cash...RestrictedCash...PeriodIncreaseDecrease variants). Each falsely reappeared as an
# "undismissed gap" in xbrl_concept_coverage_scan.py output despite being fully wired up - a
# false positive in the checker itself, not a real gap. Raised to 160 (headroom above the
# longest real concept literal found, 110 chars) rather than removing the cap entirely, so a
# truly malformed/non-concept PascalCase run-on string still gets excluded.
_CONCEPT_LITERAL_RE = re.compile(r'"([A-Z][A-Za-z0-9]{4,160})"')

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
    # Added 2026-09-07 (goal session: comprehensive tie-out/XBRL coverage audit) after
    # reviewing the top ~250 undismissed gaps by company count and finding every single one
    # fell into one of these same already-established categories (deferred-tax schedule detail,
    # tax-reconciliation footnote lines, equity/APIC rollforward detail, debt-maturity/lease
    # schedules, cash-flow footnote detail already reflected net at the aggregate level this
    # schema tracks, etc) - see scripts/xbrl_concept_coverage_dismissed.json for the individual
    # per-concept precedents each pattern generalizes (e.g. "DeferredTaxAssetsNet" already
    # dismissed as "Deferred-tax footnote schedule component" - every DeferredTax* sibling is
    # the same class of footnote breakdown, not worth re-litigating one at a time).
    "DeferredTax",
    "IncomeTaxReconciliation",
    "UnrecognizedTaxBenefit",
    "IncomeTaxPaid",  # jurisdiction/refund-split variants of the already-dismissed IncomeTaxesPaidNet
    "TreasuryStock",
    "AdjustmentsToAdditionalPaidInCapital",
    "AdditionalPaidInCapital",
    "StockIssuedDuringPeriod",
    "StockRepurchase",
    "LongTermDebtMaturitiesRepaymentsOfPrincipal",
    "FiniteLivedIntangibleAssetsAmortizationExpense",
    "FiniteLivedIntangibleAssets",
    "FinanceLease",
    "OperatingLease",
    "ClassOfWarrantOrRight",
    "RestrictedCash",
    "DefinedContributionPlan",
    "DefinedBenefitPlan",
    "AvailableForSale",
    "ContractWithCustomerLiability",
    # Cash-flow-statement working-capital/investing/financing footnote detail already
    # reflected net in this schema's operating_cash_flow/investing_cash_flow/
    # financing_cash_flow totals - same rationale as the already-dismissed
    # IncreaseDecreaseInAccountsReceivable/PaymentsToAcquireBusinessesNetOfCashAcquired.
    "IncreaseDecreaseIn",
    "ProceedsFrom",
    "PaymentsFor",
    "PaymentsTo",
    "RepaymentsOf",
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


def load_continuity_dismissed() -> dict[str, str]:
    if not CONTINUITY_DISMISSED_FILE.exists():
        return {}
    try:
        return cast(dict[str, str], json.loads(CONTINUITY_DISMISSED_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def save_continuity_dismissed(dismissed: dict[str, str]) -> None:
    CONTINUITY_DISMISSED_FILE.write_text(json.dumps(dict(sorted(dismissed.items())), indent=2) + "\n", encoding="utf-8")


def _annual_end_dates(fact_entries: list[dict[str, object]]) -> set[str]:
    """Distinct fiscal-period-end dates ('end') this concept has an annual (10-K/10-K/A) fact
    for, in ANY unit (USD covers the three CORE_CONTINUITY_CONCEPTS; a filer using a non-USD
    reporting currency still tags Assets/Liabilities/NetIncomeLoss, just under a different unit
    key, so this checks every unit rather than assuming "USD").
    """
    ends: set[str] = set()
    for entry in fact_entries:
        form = cast(str, entry.get("form") or "")
        end = entry.get("end")
        if form.startswith("10-K") and isinstance(end, str):
            ends.add(end)
    return ends


def find_continuity_gaps(min_prior_years: int = 3) -> list[dict[str, object]]:
    """Find filers where a CORE_CONTINUITY_CONCEPTS concept was tagged every year for at least
    `min_prior_years` straight prior annual filings but is absent from the most recent one -
    the "taxonomy migration" / "filer switched tags" gap that find_gaps() above cannot see
    (find_gaps() only catches a concept appearing for the FIRST time anywhere in the universe;
    this catches one disappearing for a SPECIFIC filer that used to report it every year).

    A concept that was never tagged by a filer at all is not a continuity gap (that is either
    a genuine business difference - e.g. a REIT with no NetIncomeLoss concept some year - or
    the plain coverage gap find_gaps() already handles) - only "had it consistently, then
    suddenly didn't" counts here.

    Uses each filer's OWN reporting history as the anchor timeline (the union of annual end-
    dates across all three core concepts), not a global fiscal calendar - avoids false positives
    for non-calendar fiscal years and filers that report late/early relative to peers.
    """
    files = iter_companyfacts_cache()
    if not files:
        return []
    dismissed = load_continuity_dismissed()

    gaps: list[dict[str, object]] = []
    for fp in files:
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data") or {}
        entity_name = data.get("entityName", fp.stem)
        usgaap = (data.get("facts") or {}).get("us-gaap") or {}

        per_concept_ends: dict[str, set[str]] = {}
        anchor_ends: set[str] = set()
        for concept in CORE_CONTINUITY_CONCEPTS:
            concept_data = usgaap.get(concept)
            if not concept_data:
                per_concept_ends[concept] = set()
                continue
            entries: list[dict[str, object]] = []
            for unit_entries in (concept_data.get("units") or {}).values():
                entries.extend(unit_entries)
            ends = _annual_end_dates(entries)
            per_concept_ends[concept] = ends
            anchor_ends.update(ends)

        if len(anchor_ends) < min_prior_years + 1:
            continue  # Not enough of this filer's own history to judge "used to report every year"

        sorted_ends = sorted(anchor_ends, reverse=True)
        latest = sorted_ends[0]
        prior_window = sorted_ends[1 : min_prior_years + 1]

        for concept in CORE_CONTINUITY_CONCEPTS:
            own_ends = per_concept_ends[concept]
            if not own_ends:
                continue  # Never tagged at all - a coverage gap, not a continuity regression
            if latest in own_ends:
                continue  # Still present this year - no gap
            if not all(p in own_ends for p in prior_window):
                continue  # Wasn't consistently present before either - not a new regression
            key = f"{fp.stem}:{concept}"
            if key in dismissed:
                continue
            gaps.append(
                {
                    "cik": fp.stem,
                    "entity_name": entity_name,
                    "concept": f"us-gaap:{concept}",
                    "latest_expected_end": latest,
                    "prior_years_present": prior_window,
                }
            )
    gaps.sort(key=lambda g: (cast(str, g["concept"]), cast(str, g["entity_name"])))
    return gaps


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
