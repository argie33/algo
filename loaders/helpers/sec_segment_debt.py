"""Segment-dimensional XBRL debt fallback.

ROOT CAUSE (Ford, live-confirmed 2026-09-01 via direct data.sec.gov + raw instance-XML
inspection, goal session: "understand our data gaps before resuming Fama-MacBeth"): SEC's
`companyconcept`/`companyfacts` convenience APIs - the ONLY thing `SecEdgarClient.
get_annual_concept`/`get_concept` ever call - silently EXCLUDE any XBRL fact tagged inside a
dimensional context (a `<context>` whose `<segment>` carries an `<xbrldi:explicitMember>`).
They only return facts from the "default" (no-dimension) context. This is invisible from
those APIs alone - a concept simply has zero entries for a filer that only ever tags it
dimensionally, indistinguishable from "this filer genuinely never reports this concept".

Ford (CIK 37996) is the concrete case: its balance sheet legally/operationally splits into
two segments - "Company excluding Ford Credit" (the automaker) and "Ford Credit" (the
captive-finance subsidiary, which alone carries ~$140B+ of debt funding its loan/lease book).
Verified directly against Ford's real FY2025 10-K instance document
(f-20251231_htm.xml, accession 0000037996-26-000015): DebtCurrent/LongTermDebtNoncurrent are
tagged ONLY inside `us-gaap:StatementBusinessSegmentsAxis` contexts
(f:CompanyExcludingFordCreditMember / f:FordCreditMember) for recent fiscal years - there is
no undimensioned whole-company fact for either concept at all (confirmed: every existing
_DEBT_FALLBACK_ONLY_FIELDS alias also 404s/empties against Ford's companyconcept endpoint).
Summing DebtCurrent+LongTermDebtNoncurrent per segment and across both segments for FY2025
gives ~$163.3B, matching the real ~$165.7B figure (small residual gap is additional debt-type
detail not modeled here, e.g. finance-lease pieces) - this is NOT a missing-concept-alias
problem (the existing _DEBT_FALLBACK_ONLY_FIELDS pattern in load_financial_statements.py/
sec_statements.py cannot fix it no matter how many aliases are added, because the data those
aliases would need is structurally absent from the API they all read from), it requires
parsing the filing's own instance XML.

DOUBLE-COUNTING GUARD: Ford's debt note ALSO tags the same totals broken out a second way -
by `us-gaap:LongtermDebtTypeAxis` (unsecured / asset-backed / corporate-debt-securities)
*combined* with the segment axis in the same context (2 explicitMembers). Those contexts are
a finer breakdown *within* one segment's total, not additional debt - summing them on top of
the single-axis segment contexts would double/triple-count. This module therefore ONLY sums
contexts with EXACTLY ONE explicitMember, on an axis whose local name contains "Segment" -
never a context with 2+ dimensions, and never a per-instrument-type-only axis.

SCOPE (deliberately conservative for this first pass): only fires when the existing concept-
alias extraction found NO long_term_debt at all for a fiscal year (not yet wired to the
"implausibly small vs total_liabilities" case, e.g. Ford's own 2018-2020 transition years
where a tiny non-representative value WAS present via the LongTermDebtNoncurrent fallback -
a real, disclosed, narrower residual gap left for a follow-up pass, not silently unfixed).
Requires >=2 distinct segment members for a period before using the sum, so a filer with only
one dimensional context (a genuine partial fact, not a full decomposition) is left alone
rather than risking an understated "sum".
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Concept preference order for the "current" and "noncurrent" halves of a segment's debt.
# Only the FIRST present concept per context is used - never summed together (Ford, like
# many filers, dual-tags the same fact under 2 concepts, e.g. DebtCurrent ==
# LongTermDebtCurrent for the same contextRef; summing both would double-count).
_CURRENT_DEBT_CONCEPTS = ("DebtCurrent", "LongTermDebtCurrent")
_NONCURRENT_DEBT_CONCEPTS = (
    "LongTermDebtNoncurrent",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebt",
)

_CONTEXT_RE = re.compile(r'<context id="(?P<id>[^"]+)"[^>]*>(?P<body>.*?)</context>', re.S)
_MEMBER_RE = re.compile(
    r'<xbrldi:explicitMember dimension="(?P<axis>[^"]+)">\s*(?P<member>[^<\s][^<]*?)\s*</xbrldi:explicitMember>'
)
_INSTANT_RE = re.compile(r"<instant>([^<]+)</instant>")


def _parse_contexts(xml_text: str) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for m in _CONTEXT_RE.finditer(xml_text):
        body = m.group("body")
        instant_m = _INSTANT_RE.search(body)
        if instant_m is None:
            continue  # duration-period context, not relevant to instant balance-sheet facts
        contexts[m.group("id")] = {
            "members": _MEMBER_RE.findall(body),
            "instant": instant_m.group(1),
        }
    return contexts


def _fact_values_by_context(xml_text: str, concept: str) -> dict[str, float]:
    """contextRef -> value for every tagged instance of `concept`, any namespace prefix."""
    pattern = re.compile(
        rf'<[A-Za-z][\w.-]*:{concept}\b[^>]*contextRef="(?P<ctx>[^"]+)"[^>]*>(?P<val>-?[0-9]+(?:\.[0-9]+)?)</[A-Za-z][\w.-]*:{concept}>'
    )
    return {m.group("ctx"): float(m.group("val")) for m in pattern.finditer(xml_text)}


# EXACT axis match only - live-confirmed against Ford's FY2024 10-K that a loose "Segment"
# substring match false-positives on "us-gaap:FinancingReceivablePortfolioSegmentAxis" (Ford
# Credit's loan-portfolio classification - consumer vs. commercial receivables - a completely
# different, debt-irrelevant dimension that happens to also contain the word "Segment").
_ENTITY_SEGMENT_AXES = frozenset(
    {"us-gaap:StatementBusinessSegmentsAxis", "us-gaap:StatementOperatingActivitiesSegmentAxis"}
)


def _single_axis_segment_contexts(contexts: dict[str, dict[str, Any]], period_end: str) -> dict[str, str]:
    """context_id -> member name, for contexts with exactly one entity-segment-axis member at period_end."""
    out = {}
    for cid, cdata in contexts.items():
        if cdata["instant"] != period_end:
            continue
        members = cdata["members"]
        if len(members) != 1:
            continue  # 0 members = undimensioned (handled elsewhere); 2+ = a finer sub-breakdown, skip
        axis, member = members[0]
        if axis not in _ENTITY_SEGMENT_AXES:
            continue
        out[cid] = member
    return out


def sum_segment_dimensional_debt(xml_text: str, period_end: str) -> tuple[float, int] | None:
    """Sum current+noncurrent debt across single-axis business-segment contexts for `period_end`.

    Returns (total, segment_count) if >=2 distinct segments were found and summed, else None.
    Never mixes in multi-dimensional (2+ explicitMember) contexts - see module docstring.
    """
    contexts = _parse_contexts(xml_text)
    segment_contexts = _single_axis_segment_contexts(contexts, period_end)
    if len(set(segment_contexts.values())) < 2:
        return None

    current_by_ctx: dict[str, float] = {}
    for concept in _CURRENT_DEBT_CONCEPTS:
        values = _fact_values_by_context(xml_text, concept)
        for ctx in segment_contexts:
            if ctx not in current_by_ctx and ctx in values:
                current_by_ctx[ctx] = values[ctx]

    noncurrent_by_ctx: dict[str, float] = {}
    for concept in _NONCURRENT_DEBT_CONCEPTS:
        values = _fact_values_by_context(xml_text, concept)
        for ctx in segment_contexts:
            if ctx not in noncurrent_by_ctx and ctx in values:
                noncurrent_by_ctx[ctx] = values[ctx]

    contexts_with_any_debt = set(current_by_ctx) | set(noncurrent_by_ctx)
    segments_covered = {segment_contexts[c] for c in contexts_with_any_debt}
    if len(segments_covered) < 2:
        return None

    total = sum(current_by_ctx.get(c, 0.0) + noncurrent_by_ctx.get(c, 0.0) for c in contexts_with_any_debt)
    return total, len(segments_covered)


def find_10k_for_fiscal_year(submissions: dict[str, Any], fiscal_year: int) -> tuple[str, str] | None:
    """Most recent 10-K (or 10-K/A) accession + reportDate for a calendar `fiscal_year`.

    Matches by the reportDate's own year, not an exact date string - `get_balance_sheet()`'s
    aggregated rows don't retain the raw period_end (stripped by `_aggregate_concepts` to cut
    log noise elsewhere), only the int fiscal_year, so this is the accession lookup's only
    available key. Deliberately narrow: a 52/53-week filer whose year-end crosses into early
    January (see sec_statements.py's SWK comment) can miss here and simply gets no dimensional
    fallback attempt, rather than risk matching the wrong fiscal year's filing.
    """
    # No dict/list-literal .get() defaults here (fail-fast governance, loaders/ path) - a
    # submissions payload missing "filings"/"recent" or any of the 4 parallel arrays is a
    # real malformed-response signal, not something to silently paper over into an empty
    # scan. Made visible via explicit None-checks instead of defaulting to {}/[].
    filings = submissions.get("filings")
    recent = filings.get("recent") if filings else None
    if not recent:
        return None
    forms = recent.get("form")
    report_dates = recent.get("reportDate")
    accessions = recent.get("accessionNumber")
    filed_dates = recent.get("filingDate")
    if not forms or not report_dates or not accessions:
        return None
    filed_dates = filed_dates or []

    candidates = [
        (filed_dates[i] if i < len(filed_dates) else "", accessions[i], report_dates[i])
        for i, form in enumerate(forms)
        if form.startswith("10-K")
        and i < len(report_dates)
        and report_dates[i][:4].isdigit()
        and int(report_dates[i][:4]) == fiscal_year
        and i < len(accessions)
    ]
    if not candidates:
        return None
    candidates.sort()  # latest filing (e.g. a 10-K/A amendment) wins
    _, accession, report_date = candidates[-1]
    return accession, report_date
