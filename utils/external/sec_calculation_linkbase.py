"""Parse an SEC filing's XBRL calculation linkbase (_cal.xml) into summation-item
relationships (parent concept = sum of weight * child concept, per the filer's OWN
declared arithmetic - not our extraction code's).

Added 2026-09-10 (institutional XBRL data-quality build, layer 5/5). See
scripts/xbrl_calculation_linkbase_check.py for the check that consumes this, and its
module docstring / scripts/xbrl_yfinance_crosscheck.py's docstring for how this fits
alongside the other four layers (self-consistency, statistical outlier, negative-value
guards, independent second-opinion).

Namespace-agnostic by design: calculation linkbases vary prefix bindings across filer
software vendors (some use "link:"/"xlink:", others rebind those prefixes), but the
*local* element/attribute names (loc, calculationArc, calculationLink, href, label,
from, to, weight, order, arcrole) are fixed by the XBRL 2.1 spec regardless of prefix -
so every lookup here matches on local name only, never a qualified name.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class CalcArc:
    parent_concept: str  # "taxonomy:Concept", e.g. "us-gaap:Assets"
    child_concept: str
    weight: float
    order: float
    role: str  # extended link role URI this arc came from (one per statement/note table)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr(elem: ET.Element, name: str) -> str | None:
    for k, v in elem.attrib.items():
        if _local_name(k) == name:
            return v
    return None


def _concept_from_href(href: str) -> str | None:
    """ "{...}.xsd#us-gaap_Assets" -> "us-gaap:Assets".

    Returns None for fragments with no "prefix_Concept" shape (malformed hrefs) -
    callers skip those rather than guess a concept name.
    """
    if "#" not in href:
        return None
    frag = href.rsplit("#", 1)[-1]
    if "_" not in frag:
        return None
    prefix, _, concept = frag.partition("_")
    if not prefix or not concept:
        return None
    return f"{prefix}:{concept}"


def parse_calculation_arcs(xml_text: str) -> list[CalcArc]:
    """All summation-item calculationArc relationships across every extended link role
    (i.e. every statement - balance sheet, income statement, cash flow, and every note/
    schedule) in one filing's calculation linkbase.

    Non-summation-item arcroles are skipped - the calculation linkbase spec permits
    other arcroles but summation-item is the only one that asserts an arithmetic
    relationship checkable against reported values.
    """
    root = ET.fromstring(xml_text)
    arcs: list[CalcArc] = []
    for calc_link in root.iter():
        if _local_name(calc_link.tag) != "calculationLink":
            continue
        role = _attr(calc_link, "role") or ""

        loc_label_to_concept: dict[str, str] = {}
        for child in calc_link:
            if _local_name(child.tag) != "loc":
                continue
            href = _attr(child, "href")
            label = _attr(child, "label")
            if not href or not label:
                continue
            concept = _concept_from_href(href)
            if concept:
                loc_label_to_concept[label] = concept

        for child in calc_link:
            if _local_name(child.tag) != "calculationArc":
                continue
            arcrole = _attr(child, "arcrole") or ""
            if not arcrole.endswith("summation-item"):
                continue
            from_label = _attr(child, "from")
            to_label = _attr(child, "to")
            if from_label is None or to_label is None:
                continue
            parent = loc_label_to_concept.get(from_label)
            target = loc_label_to_concept.get(to_label)
            if parent is None or target is None:
                continue
            try:
                weight = float(_attr(child, "weight") or "1")
            except ValueError:
                weight = 1.0
            try:
                order = float(_attr(child, "order") or "1")
            except ValueError:
                order = 1.0
            arcs.append(CalcArc(parent, target, weight, order, role))
    return arcs


# SEC filers overwhelmingly follow the EDGAR dashboard/Arelle role-naming convention:
# primary face-financial-statement roles are named e.g. ".../role/CONSOLIDATEDBALANCESHEETS"
# or ".../role/StatementsOfOperations", while every note-schedule/disclosure table role
# (leases, debt maturities, segment detail, tax rate reconciliation, ...) is named with a
# "Details" or "Tables" suffix. This matters because SEC's companyfacts API (the only
# per-concept-value source cheap enough to use here) collapses ALL dimensional facts for a
# concept into one flat list with no member/axis info - so a note-schedule concept reused
# across dimensional members (e.g. a lease-maturity-by-year concept also broken out by lease
# type) can't be matched to the correct dimensional slice and looks like self-contradictory
# double-counted arithmetic that isn't real (live-confirmed on AAPL's FY2025 10-K: every one
# of 3 raw mismatches was a note-schedule concept, 0 were face-statement concepts). Filtering
# to non-Details/Tables roles restricts checking to the concepts where a bare concept+accession
# match is actually unambiguous - the primary financial statements are (by definition) rarely
# multi-instance-dimensional for the same reporting period.
_NOTE_SCHEDULE_ROLE_MARKERS = ("details", "tables")


def is_primary_statement_role(role: str) -> bool:
    lowered = role.lower()
    return not any(marker in lowered for marker in _NOTE_SCHEDULE_ROLE_MARKERS)


def group_by_parent(arcs: list[CalcArc]) -> dict[str, list[list[CalcArc]]]:
    """Group arcs into one or more independent calculation TREES per parent concept.

    A parent concept can legitimately appear in more than one extended link role with
    either the SAME child set both times (e.g. a subtotal reused across the balance
    sheet and a supporting note - deduplicated here into a single tree) or a
    GENUINELY DIFFERENT child set (e.g. OtherComprehensiveIncomeLossNetOfTax broken
    down by component - AFS securities / cash-flow hedge - in one role and by
    before-tax/tax in another). The two cases must be told apart: flattening every
    role's arcs into one combined sum (as an earlier version of this function did)
    double-counts the second case, since each distinct breakdown independently ties
    to the same parent value on its own - live-confirmed on UNTY's FY2025 10-K, which
    produced 3 false "mismatches" from this exact collapse before this fix. Returns,
    per parent concept, a list of distinct child-arc sets; callers must check the
    parent against EACH tree and only flag a real mismatch if none of them tie.

    Callers should pre-filter arcs with is_primary_statement_role first (see its
    docstring for why) - this function groups whatever it's given.
    """
    by_role_parent: dict[tuple[str, str], list[CalcArc]] = {}
    for arc in arcs:
        role_parent_arcs = by_role_parent.setdefault((arc.role, arc.parent_concept), [])
        pair = (arc.child_concept, arc.weight)
        if any((a.child_concept, a.weight) == pair for a in role_parent_arcs):
            continue
        role_parent_arcs.append(arc)

    grouped: dict[str, list[list[CalcArc]]] = {}
    for (_role, parent), child_arcs in by_role_parent.items():
        trees = grouped.setdefault(parent, [])
        child_set = {(a.child_concept, a.weight) for a in child_arcs}
        if any({(a.child_concept, a.weight) for a in tree} == child_set for tree in trees):
            continue  # identical child set already recorded from another role
        trees.append(child_arcs)
    return grouped
