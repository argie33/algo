"""Parse an SEC filing's raw XBRL instance document to recover facts SEC's companyfacts
API drops entirely - specifically, facts tagged ONLY under a `dei:LegalEntityAxis`
dimensional context (a combined filer covering a parent REIT and its operating
partnership as two "members" of the same filing, e.g. Tanger Inc./SKT + Tanger
Properties Limited Partnership) with no non-dimensional "default" counterpart.

ADDED 2026-09-11 (goal: "SEC/XBRL missing data under 300" push, "resources we should be
tapping into" ask). CLAUDE.md's calculation-linkbase section already documents WHY this
happens: SEC's companyfacts API flattens every dimensional fact for a concept into one
list with no axis/member info exposed - `scripts/xbrl_calculation_linkbase_check.py`
works around the same limitation for a different purpose (note-schedule dimensional
facts) by parsing the raw XBRL directly instead of trusting companyfacts. This module
does the equivalent for a filer that reports EVERY period of a concept exclusively under
a `dei:LegalEntityAxis` member - live-confirmed via SKT (Tanger Inc, CIK 899715)'s
FY2025 10-K: `NetCashProvidedByUsedInOperatingActivities` has ZERO facts in companyfacts
for any 10-K-form accession, but the raw instance document
(`skt-20251231_htm.xml`, fetched via `SecEdgarClient.get_filing_xml`) has real values
for FY2023/2024/2025 under two members: "TangerIncMember" ($229.6M/$260.7M/$295.4M) and
"TangerPropertiesLimitedPartnershipMember" (near-identical, off by <1%) - the registrant
we score under ticker SKT is "TANGER INC." per its own SEC submissions `name` field,
matching "TangerIncMember" by substring.

Namespace-agnostic (matches `sec_calculation_linkbase.py`'s own convention): filer
software vendors vary prefix bindings, so every lookup here matches on local element/
attribute names only, never a qualified name with a specific prefix.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _local(qname: str) -> str:
    """Strip a namespace PREFIX (not URI - this is for attribute VALUES like
    "dei:LegalEntityAxis"/"skt:TangerIncMember", not element tags), e.g.
    "dei:LegalEntityAxis" -> "LegalEntityAxis"."""
    return qname.rsplit(":", 1)[-1] if ":" in qname else qname


def _attr(elem: ET.Element, name: str) -> str | None:
    for k, v in elem.attrib.items():
        if _local_name(k) == name:
            return v
    return None


@dataclass(frozen=True)
class InstanceContext:
    context_id: str
    start: str | None
    end: str | None
    instant: str | None
    dimensions: dict[str, str]  # axis local name -> member local name


def parse_contexts(xml_text: str) -> dict[str, InstanceContext]:
    """Every `<context>` element's period and explicit-member dimensions, keyed by id."""
    root = ET.fromstring(xml_text)
    contexts: dict[str, InstanceContext] = {}
    for ctx in root.iter():
        if _local_name(ctx.tag) != "context":
            continue
        ctx_id = _attr(ctx, "id")
        if not ctx_id:
            continue
        start = end = instant = None
        dims: dict[str, str] = {}
        for node in ctx.iter():
            ln = _local_name(node.tag)
            if ln == "startDate":
                start = (node.text or "").strip()
            elif ln == "endDate":
                end = (node.text or "").strip()
            elif ln == "instant":
                instant = (node.text or "").strip()
            elif ln == "explicitMember":
                axis = _attr(node, "dimension")
                member = (node.text or "").strip()
                if axis and member:
                    dims[_local(axis)] = _local(member)
        contexts[ctx_id] = InstanceContext(ctx_id, start, end, instant, dims)
    return contexts


@dataclass(frozen=True)
class InstanceFact:
    context_id: str
    value: float


def parse_facts_for_concept(xml_text: str, concept_local_name: str) -> list[InstanceFact]:
    """Every tagged fact for one concept (matched by LOCAL element name only, e.g.
    "NetCashProvidedByUsedInOperatingActivities" - taxonomy-agnostic since a filer's
    namespace prefix for us-gaap/ifrs-full varies). Non-numeric facts (nil, text) are
    skipped, never coerced to 0."""
    root = ET.fromstring(xml_text)
    facts: list[InstanceFact] = []
    for elem in root.iter():
        if _local_name(elem.tag) != concept_local_name:
            continue
        ctx_ref = _attr(elem, "contextRef")
        text = (elem.text or "").strip()
        if not ctx_ref or not text:
            continue
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            continue
        facts.append(InstanceFact(ctx_ref, value))
    return facts


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_legal_entity_dimensioned_annual_facts(
    xml_text: str,
    concept_local_name: str,
    registrant_name: str,
    min_duration_days: int = 330,
) -> dict[str, float]:
    """Annual-duration facts for `concept_local_name` tagged ONLY under a
    `dei:LegalEntityAxis` dimension whose member matches `registrant_name` (the
    filer's own SEC-registered name, e.g. submissions.json's "name" field) - the
    combined-UPREIT-filer recovery this module exists for.

    Returns {end_date: value}, one entry per distinct fiscal-year-end found (a single
    10-K typically carries 2-3 comparative years). Empty dict if nothing qualifies -
    never a guessed/partial value.

    Deliberately conservative on every axis, matching this codebase's "no confidently-
    wrong data" discipline:
    - The context's dimensions must be EXACTLY {"LegalEntityAxis": <member>} - any
      additional real dimension (a genuine segment/product breakdown, not just an
      entity choice) is refused rather than guessed at.
    - The period must be a real annual duration (>= min_duration_days) - instants and
      quarterly/YTD partial periods are excluded.
    - The member must contain the full normalized registrant name as a substring
      (e.g. "TANGER INC." -> "tangerinc" is found inside "TangerIncMember" ->
      "tangerincmember") - never a positional/first-candidate guess. Registrant names
      shorter than 4 normalized characters are refused (too generic to trust a
      substring match on).
    """
    registrant_key = _normalize_name(registrant_name)
    if len(registrant_key) < 4:
        # Not an error: a registrant name too short/generic to trust a substring match
        # on means there is nothing safe to search for - an empty result here is the
        # correct, deliberate answer (the caller's "no recovery possible" fallthrough
        # behaves identically to any other empty result from this function), not data
        # loss requiring a raise or an explicit unavailable marker.
        return {}
    contexts = parse_contexts(xml_text)
    facts = parse_facts_for_concept(xml_text, concept_local_name)
    out: dict[str, float] = {}
    for fact in facts:
        ctx = contexts.get(fact.context_id)
        if ctx is None or not ctx.start or not ctx.end:
            continue
        if list(ctx.dimensions.keys()) != ["LegalEntityAxis"]:
            continue
        member = ctx.dimensions["LegalEntityAxis"]
        if registrant_key not in _normalize_name(member):
            continue
        try:
            start_dt = datetime.fromisoformat(ctx.start).date()
            end_dt = datetime.fromisoformat(ctx.end).date()
        except ValueError:
            continue
        if (end_dt - start_dt).days < min_duration_days:
            continue
        # A filer can report the same period under more than one matching context
        # (e.g. current-year and prior-year comparative columns overlapping across
        # 10-Ks) - last-write-wins, same convention as this codebase's other
        # "last-listed/most-recent overwrite" fallback chains.
        out[ctx.end] = fact.value
    return out


def fiscal_year_for_end_date(end_date: str) -> int:
    return date.fromisoformat(end_date).year
