"""Regression test for the dual-class-stock dimensional XBRL EPS/shares fallback (2026-09-02,
goal session: "understand our XBRL data gaps"). See loaders/helpers/sec_dual_class_eps.py's
module docstring for the full Berkshire Hathaway root-cause writeup.

The fixture below is a minimal, hand-built XBRL instance snippet reproducing the real
structural shape live-confirmed against Berkshire's actual FY2025 10-K instance document
(brka-20251231_htm.xml, accession 0001193125-26-083899, CIK 1067983) - not the real filing
itself (13.5MB, not worth committing) - with the same pattern: one single-member
StatementClassOfStockAxis context per (class, fiscal year), plus a decoy context that uses the
SAME axis for an unrelated debt instrument (Berkshire really does this - senior notes tagged
under StatementClassOfStockAxis with non-"Class{LETTER}" member names) to lock in the
false-positive guard.
"""

from loaders.helpers.sec_dual_class_eps import (
    extract_dual_class_eps_shares,
    resolve_class_letter,
)

_FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    <context id="c-classA-2025">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    </context>
    <context id="c-classB-2025">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    </context>
    <context id="c-note-2025">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">brka:MTwoPointOneFiveZeroSeniorNotesDueTwoThousandTwentyEightMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
    </context>
    <context id="c-classA-2024">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period>
    </context>
    <us-gaap:EarningsPerShareBasic contextRef="c-classA-2025" unitRef="usd-per-share" decimals="0">46563</us-gaap:EarningsPerShareBasic>
    <us-gaap:WeightedAverageNumberOfSharesOutstandingBasic contextRef="c-classA-2025" unitRef="shares" decimals="0">1438223</us-gaap:WeightedAverageNumberOfSharesOutstandingBasic>
    <us-gaap:EarningsPerShareBasic contextRef="c-classB-2025" unitRef="usd-per-share" decimals="2">31.04</us-gaap:EarningsPerShareBasic>
    <us-gaap:WeightedAverageNumberOfSharesOutstandingBasic contextRef="c-classB-2025" unitRef="shares" decimals="0">2157335139</us-gaap:WeightedAverageNumberOfSharesOutstandingBasic>
    <us-gaap:EarningsPerShareBasic contextRef="c-note-2025" unitRef="usd-per-share" decimals="2">2.15</us-gaap:EarningsPerShareBasic>
    <us-gaap:EarningsPerShareBasic contextRef="c-classA-2024" unitRef="usd-per-share" decimals="0">61900</us-gaap:EarningsPerShareBasic>
</xbrl>
"""


class TestExtractDualClassEpsShares:
    def test_extracts_class_a_facts_for_period(self) -> None:
        result = extract_dual_class_eps_shares(_FIXTURE_XML, "A", "2025-12-31")
        assert result == {"eps_basic": 46563.0, "shares_basic": 1438223.0}

    def test_extracts_class_b_facts_for_period(self) -> None:
        result = extract_dual_class_eps_shares(_FIXTURE_XML, "B", "2025-12-31")
        assert result == {"eps_basic": 31.04, "shares_basic": 2157335139.0}

    def test_never_returns_diluted_facts_that_do_not_exist(self) -> None:
        # Berkshire tags no diluted EPS/share-count facts at all - the fallback must return
        # only what it actually finds, never fabricate the rest.
        result = extract_dual_class_eps_shares(_FIXTURE_XML, "A", "2025-12-31")
        assert result is not None
        assert "eps_diluted" not in result
        assert "shares_diluted" not in result

    def test_same_axis_debt_instrument_context_never_matches(self) -> None:
        # The decoy note context tags EarningsPerShareBasic=2.15 under the SAME
        # StatementClassOfStockAxis but a member name with no "Class{LETTER}" - must never be
        # mistaken for a real class fact (would corrupt class A's real 46563 value if summed
        # or averaged in, or be picked up as a phantom third class).
        result_a = extract_dual_class_eps_shares(_FIXTURE_XML, "A", "2025-12-31")
        result_b = extract_dual_class_eps_shares(_FIXTURE_XML, "B", "2025-12-31")
        assert result_a is not None and result_a["eps_basic"] == 46563.0
        assert result_b is not None and result_b["eps_basic"] == 31.04

    def test_wrong_period_returns_none(self) -> None:
        assert extract_dual_class_eps_shares(_FIXTURE_XML, "B", "2025-12-31") is not None
        assert extract_dual_class_eps_shares(_FIXTURE_XML, "B", "2023-12-31") is None

    def test_different_fiscal_year_resolves_independently(self) -> None:
        result = extract_dual_class_eps_shares(_FIXTURE_XML, "A", "2024-12-31")
        assert result == {"eps_basic": 61900.0}

    def test_unresolvable_class_letter_returns_none(self) -> None:
        assert extract_dual_class_eps_shares(_FIXTURE_XML, "C", "2025-12-31") is None


class TestResolveClassLetter:
    def test_dot_suffix_resolves_directly(self) -> None:
        assert resolve_class_letter("BRK.A") == "A"
        assert resolve_class_letter("BRK.B") == "B"
        assert resolve_class_letter("CRD.A") == "A"
        assert resolve_class_letter("GTN.A") == "A"

    def test_bare_ticker_stays_unresolved_without_security_name(self) -> None:
        # Deliberately conservative - a bare ticker (V, GEF, GTN, SENEA) needs a
        # security_name lookup to resolve at all.
        assert resolve_class_letter("V") is None
        assert resolve_class_letter("GEF") is None
        assert resolve_class_letter("GTN") is None
        assert resolve_class_letter("SENEA") is None

    def test_multi_letter_dot_suffix_stays_unresolved(self) -> None:
        # Not a real class-letter convention (e.g. a preferred-share ticker suffix) -
        # only a genuine single letter is trusted.
        assert resolve_class_letter("WRB.PRE") is None

    def test_bare_ticker_resolves_via_security_name_class_text(self) -> None:
        # Real stock_symbols.security_name values, live-verified 2026-09-02.
        assert resolve_class_letter("GEF", "Greif Inc. Class A Common Stock") == "A"
        assert resolve_class_letter("SENEA", "Seneca Foods Corp. - Class A Common Stock") == "A"
        assert resolve_class_letter("SENEB", "Seneca Foods Corp. - Class B Common Stock") == "B"

    def test_bare_ticker_without_class_text_stays_unresolved(self) -> None:
        # Real values, live-verified 2026-09-02 - GTN's own security_name has no class text
        # (only its dot-suffix sibling GTN.A does), and V's has none at all. Must not guess.
        assert resolve_class_letter("GTN", "Gray Media, Inc. Common Stock") is None
        assert resolve_class_letter("V", "Visa Inc.") is None

    def test_dot_suffix_wins_over_security_name_when_both_present(self) -> None:
        # The dot suffix is the more direct/trusted signal - checked first regardless of
        # what security_name says (even a contradictory one, which shouldn't occur in
        # practice but must not cause ambiguity).
        assert resolve_class_letter("BRK.A", "Berkshire Hathaway Inc. Common Stock") == "A"
