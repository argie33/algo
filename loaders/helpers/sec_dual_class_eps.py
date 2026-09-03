"""Dual-class-stock dimensional XBRL EPS/weighted-average-shares fallback.

ROOT CAUSE (Berkshire Hathaway, live-confirmed 2026-09-02 via BRK.A/BRK.B's real FY2023-2025
10-K instance document, accession 0001193125-26-083899): same root cause FAMILY as
loaders/helpers/sec_segment_debt.py's Ford debt gap (SEC's companyconcept/companyfacts
convenience APIs - the only thing sec_statements.py's _aggregate_concepts ever reads from -
structurally exclude any fact tagged inside a dimensional context), a different axis
(us-gaap:StatementClassOfStockAxis) and different concepts (EPS/weighted-average shares
instead of debt). A multi-class filer that reports EPS/share-count once per class - Berkshire
(Class A/B), Crawford & Company (CRD.A/CRD.B), Greif (GEF/GEF.B), Gray Media (GTN/GTN.A), and
others - has ZERO undimensioned entries for EarningsPerShareBasic/Diluted or
WeightedAverageNumberOfShares*, indistinguishable via companyfacts from "this filer never
reports EPS at all". See [[eps_shares_annual_income_statement_gap_scoped_20260901]] for the
~53-symbol gap this was scoped from - this module closes the dot-suffix-resolvable subset
directly, and the bare-ticker subset (GEF, SENEA, SENEB, ...) when a caller passes
`security_name` (see `resolve_class_letter`'s docstring). Ambiguous cases like Visa's A/B/C
structure (no "Class {LETTER}" text in its `security_name` at all) stay unresolved by design -
this module never guesses.

Live-verified against BRK's real instance XML: EarningsPerShareBasic tagged once per
(class, fiscal year) under a single-member us-gaap:StatementClassOfStockAxis context -
Class A FY2025=$46,563/share (1,438,223 shares), Class B FY2025=$31.04/share
(2,157,335,139 shares) - both match Berkshire's real known per-class scale. Berkshire tags no
EarningsPerShareDiluted/diluted-share-count facts at all (no dilutive securities to report) -
this module correctly returns only the fields it actually finds, never fabricating the rest.

FALSE-POSITIVE GUARD: Berkshire (and presumably other filers) also tags several debt
instruments (senior notes) under this SAME us-gaap:StatementClassOfStockAxis with member names
like "brka:MTwoPointOneFiveZeroSeniorNotesDueTwoThousandTwentyEightMember" - axis-matching
alone is not enough. `_class_letter_for_context` additionally requires the member's own name to
contain a literal "Class{LETTER}[Member]" substring (same convention already proven correct in
loaders/load_company_info_sec.py's `_CLASS_LETTER_FROM_MEMBER_RE`), which none of the debt
instrument members do - they're excluded by construction, not by an axis exclusion list.

SCOPE (deliberately conservative, same discipline as sec_segment_debt.py): only fires when a
fiscal year is missing ANY of the 4 target fields after every existing concept-alias tier;
never overwrites a real value; requires an exact single-member class match at the exact
period-end date with an annual-length (330-380 day) span, so an ambiguous or partial context
is left alone rather than risking a wrong-class or wrong-period value.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_CONTEXT_RE = re.compile(r'<context id="(?P<id>[^"]+)"[^>]*>(?P<body>.*?)</context>', re.S)
_MEMBER_RE = re.compile(
    r'<xbrldi:explicitMember dimension="(?P<axis>[^"]+)">\s*(?P<member>[^<\s][^<]*?)\s*</xbrldi:explicitMember>'
)
_START_RE = re.compile(r"<startDate>([^<]+)</startDate>")
_END_RE = re.compile(r"<endDate>([^<]+)</endDate>")

# EXACT axis match only, same discipline as sec_segment_debt.py's _ENTITY_SEGMENT_AXES.
_CLASS_OF_STOCK_AXES = frozenset({"us-gaap:StatementClassOfStockAxis"})
# Matches "CommonClassAMember", "brka:EquivalentClassBMember", etc. - same convention as
# load_company_info_sec.py's _CLASS_LETTER_FROM_MEMBER_RE.
_CLASS_LETTER_FROM_MEMBER_RE = re.compile(r"Class([A-Z])(?:Member)?\b")

# A dot-suffix ticker (BRK.A, CRD.B, GTN.A, ...) already encodes its own class letter directly
# in the internal symbol convention - trusted with no further check. A bare ticker with a dual-
# class sibling (GEF, SENEA/SENEB) needs its `stock_symbols.security_name` to state the class
# explicitly (e.g. "Greif Inc. Class A Common Stock") - only trusted when that exact "Class
# {LETTER}" text is present, never inferred from context (same convention already proven correct
# in load_company_info_sec.py's `_target_class_letter`/`_CLASS_LETTER_FROM_SECURITY_NAME_RE`).
# This module stays DB-free itself - callers with DB access (loaders/helpers/sec_base.py) pass
# security_name in.
_DOT_SUFFIX_RE = re.compile(r"\.([A-Za-z])$")
_CLASS_LETTER_FROM_SECURITY_NAME_RE = re.compile(r"\bClass\s+([A-Z])\b")

# Explicit, human-verified overrides for symbols neither auto-resolution source reaches: no
# dot suffix, and `security_name` never states a class (Visa's is literally just "Visa Inc.").
# Not a guess - each entry is a public, unambiguous fact confirmed against the filer's own real
# XBRL instance document, same evidentiary bar as the dot-suffix/security_name paths above.
# FIXED 2026-09-03 (goal: "missing SEC/XBRL data" sweep, eps_never_tagged_in_filings follow-up):
# Visa's ticker V trades exclusively as Class A common stock (Visa Inc.'s Class B and Class C
# common stock are not publicly listed) - live-confirmed via Visa's real FY2025 10-K instance
# XML (CIK 0001403161, accession 0001403161-25-000089): EarningsPerShareBasic is tagged once per
# fiscal year under us-gaap:StatementClassOfStockAxis with member us-gaap:CommonClassAMember
# (FY2025 = $10.22, context start=2024-10-01/end=2025-09-30, a clean 364-day annual span) -
# exactly the single-member/annual-span shape extract_dual_class_eps_shares already handles,
# never reached before this fix because V had no automatic way to resolve to "A". Visa's
# companyfacts convenience API has zero undimensioned EarningsPerShareBasic/Diluted or
# WeightedAverageNumberOfShares* facts at all (live-confirmed same session), so every fiscal
# year's eps/diluted_eps/shares_outstanding_basic/shares_outstanding_diluted was NULL for one
# of the largest S&P 500 constituents before this override.
_CLASS_LETTER_OVERRIDES: dict[str, str] = {
    "V": "A",
}

_EPS_BASIC_CONCEPT = "EarningsPerShareBasic"
_EPS_DILUTED_CONCEPT = "EarningsPerShareDiluted"
_SHARES_BASIC_CONCEPT = "WeightedAverageNumberOfSharesOutstandingBasic"
_SHARES_DILUTED_CONCEPT = "WeightedAverageNumberOfDilutedSharesOutstanding"


def resolve_class_letter(symbol: str, security_name: str | None = None) -> str | None:
    """This symbol's own share-class letter, if determinable with confidence.

    Three sources, all conservative (return None rather than guess) - same two-source design as
    load_company_info_sec.py's `_target_class_letter`, plus a small explicit override table:
    1. A single-letter dot suffix (BRK.A -> "A", CRD.B -> "B") - the internal symbol convention
       already encodes the class directly, no further check needed.
    2. For a BARE ticker (no dot), `security_name` sometimes states the class explicitly
       (e.g. "Greif Inc. Class A Common Stock") - only trusted when that exact "Class {LETTER}"
       text is present. `security_name` is optional so this module stays DB-free; a caller with
       no DB access (or that hasn't looked it up) simply gets the dot-suffix-only behavior.
    3. `_CLASS_LETTER_OVERRIDES` - a handful of tickers neither source above reaches, each a
       human-verified fact (see that table's own docstring), not an inference.
    """
    m = _DOT_SUFFIX_RE.search(symbol)
    if m and len(m.group(1)) == 1:
        return m.group(1).upper()
    if security_name:
        name_m = _CLASS_LETTER_FROM_SECURITY_NAME_RE.search(security_name)
        if name_m:
            return name_m.group(1).upper()
    return _CLASS_LETTER_OVERRIDES.get(symbol)


def _parse_duration_contexts(xml_text: str) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for m in _CONTEXT_RE.finditer(xml_text):
        body = m.group("body")
        start_m = _START_RE.search(body)
        end_m = _END_RE.search(body)
        if start_m is None or end_m is None:
            continue  # instant context (balance-sheet fact) - not relevant here
        contexts[m.group("id")] = {
            "members": _MEMBER_RE.findall(body),
            "start": start_m.group(1),
            "end": end_m.group(1),
        }
    return contexts


def _is_annual_span(start: str, end: str) -> bool:
    try:
        s = date.fromisoformat(start[:10])
        e = date.fromisoformat(end[:10])
    except ValueError:
        return False
    return 330 <= (e - s).days <= 380


def _class_letter_for_context(cdata: dict[str, Any], target_letter: str) -> bool:
    members = cdata["members"]
    if len(members) != 1:
        return False  # 0 = undimensioned (handled by the normal concept-alias tiers already);
        # 2+ = a finer cross-tab (e.g. class x product-line), ambiguous - skip rather than guess.
    axis, member = members[0]
    if axis not in _CLASS_OF_STOCK_AXES:
        return False
    letter_m = _CLASS_LETTER_FROM_MEMBER_RE.search(member)
    if letter_m is None:
        return False
    return letter_m.group(1).upper() == target_letter


def _fact_values_by_context(xml_text: str, concept: str) -> dict[str, float]:
    """contextRef -> value for every tagged instance of `concept`, any namespace prefix.

    Same pattern as sec_segment_debt.py's identical helper.
    """
    pattern = re.compile(
        rf'<[A-Za-z][\w.-]*:{concept}\b[^>]*contextRef="(?P<ctx>[^"]+)"[^>]*>'
        rf"(?P<val>-?[0-9]+(?:\.[0-9]+)?)</[A-Za-z][\w.-]*:{concept}>"
    )
    return {m.group("ctx"): float(m.group("val")) for m in pattern.finditer(xml_text)}


def extract_dual_class_eps_shares(xml_text: str, class_letter: str, period_end: str) -> dict[str, float] | None:
    """EPS/weighted-average-share facts tagged under this symbol's own class, for the annual
    duration ending `period_end`.

    Returns a dict with whichever of eps_basic/eps_diluted/shares_basic/shares_diluted was
    actually found (never all four guaranteed - see Berkshire's no-diluted-facts case in the
    module docstring), or None if nothing was found for this class+period at all.
    """
    contexts = _parse_duration_contexts(xml_text)
    class_contexts = {
        cid
        for cid, cdata in contexts.items()
        if cdata["end"] == period_end
        and _is_annual_span(cdata["start"], cdata["end"])
        and _class_letter_for_context(cdata, class_letter)
    }
    if not class_contexts:
        return None

    result: dict[str, float] = {}
    for result_key, concept in (
        ("eps_basic", _EPS_BASIC_CONCEPT),
        ("eps_diluted", _EPS_DILUTED_CONCEPT),
        ("shares_basic", _SHARES_BASIC_CONCEPT),
        ("shares_diluted", _SHARES_DILUTED_CONCEPT),
    ):
        values = _fact_values_by_context(xml_text, concept)
        for ctx in class_contexts:
            if ctx in values:
                result[result_key] = values[ctx]
                break

    return result or None
