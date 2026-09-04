"""Regression test for the "Undefined" class-member EPS fallback (2026-09-04, goal session:
"under 6k the right way" sweep). See loaders/helpers/sec_dual_class_eps.py's module docstring
and the FIXED 2026-09-04 comment above `_CLASS_LETTER_OVERRIDES` for the full Coca-Cola
Consolidated (COKE) root-cause writeup.

The fixture reproduces the real structural shape live-confirmed against COKE's actual FY2024
10-K (coke-20241231.htm, accession 0000317540-25-000025, CIK 0000317540): EarningsPerShareBasic
tagged once per fiscal year under us-gaap:StatementClassOfStockAxis with member
coke:CommonClassUndefinedMember - no class letter at all - plus a decoy
coke:PreferredClassUndefinedMember context (COKE really tags this too) to lock in that the
"Undefined" match stays scoped to the common variant only.
"""

from loaders.helpers.sec_dual_class_eps import (
    extract_dual_class_eps_shares,
    resolve_class_letter,
)

_FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap" xmlns:coke="http://coca-colaconsolidated.com/coke" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    <context id="c-common-2024">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000317540</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">coke:CommonClassUndefinedMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
    </context>
    <context id="c-preferred-2024">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000317540</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">coke:PreferredClassUndefinedMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
    </context>
    <us-gaap:EarningsPerShareBasic contextRef="c-common-2024" unitRef="usdPerShare" decimals="2">70.10</us-gaap:EarningsPerShareBasic>
    <us-gaap:EarningsPerShareBasic contextRef="c-preferred-2024" unitRef="usdPerShare" decimals="2">0.00</us-gaap:EarningsPerShareBasic>
</xbrl>
"""


class TestResolveClassLetterUndefinedOverride:
    def test_coke_resolves_to_undefined_sentinel(self) -> None:
        assert resolve_class_letter("COKE", "Coca-Cola Consolidated, Inc. - Common Stock") == "UNDEFINED"

    def test_symbol_with_no_class_text_and_no_override_stays_unresolved(self) -> None:
        assert resolve_class_letter("XYZ", "Some Company - Common Stock") is None


class TestExtractDualClassEpsSharesUndefinedMember:
    def test_extracts_common_undefined_facts_not_preferred(self) -> None:
        result = extract_dual_class_eps_shares(_FIXTURE_XML, "UNDEFINED", "2024-12-31")
        assert result is not None
        assert result["eps_basic"] == 70.10

    def test_letter_class_never_matches_undefined_member(self) -> None:
        assert extract_dual_class_eps_shares(_FIXTURE_XML, "A", "2024-12-31") is None
