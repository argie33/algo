"""Tests for utils/external/sec_xbrl_instance_document.py (goal session 2026-09-11,
"under 300" push - recovering facts SEC's companyfacts API drops when a filer tags
every period of a concept exclusively under a dei:LegalEntityAxis dimensional context,
e.g. a combined REIT + operating-partnership UPREIT filing like Tanger Inc/SKT).
"""

from utils.external.sec_xbrl_instance_document import (
    fiscal_year_for_end_date,
    parse_contexts,
    parse_facts_for_concept,
    resolve_legal_entity_dimensioned_annual_facts,
)

_XBRL_NS = 'xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:dei="http://xbrl.sec.gov/dei/2025" xmlns:skt="http://example.com/skt"'


def _skt_shaped_instance_xml() -> str:
    """Two LegalEntityAxis members (parent REIT + operating partnership), each with
    3 comparative annual-duration contexts, matching SKT's real FY2025 10-K shape."""
    return f"""<?xml version="1.0"?>
<xbrli:xbrl {_XBRL_NS}>
  <xbrli:context id="c-8">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="c-9">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="c-lp">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerPropertiesLimitedPartnershipMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="c-q">
    <xbrli:entity>
      <xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier>
      <xbrli:segment>
        <xbrldi:explicitMember dimension="dei:LegalEntityAxis">skt:TangerIncMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-10-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="c-noaxis">
    <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000899715</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-8" decimals="-3" unitRef="usd">295369000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-9" decimals="-3" unitRef="usd">260678000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-lp" decimals="-3" unitRef="usd">295421000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
  <us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="c-q" decimals="-3" unitRef="usd">62918000</us-gaap:NetCashProvidedByUsedInOperatingActivities>
  <us-gaap:Assets contextRef="c-noaxis" decimals="-3" unitRef="usd">5000000000</us-gaap:Assets>
</xbrli:xbrl>"""


class TestParseContexts:
    def test_extracts_period_and_dimensions(self) -> None:
        contexts = parse_contexts(_skt_shaped_instance_xml())
        assert contexts["c-8"].start == "2025-01-01"
        assert contexts["c-8"].end == "2025-12-31"
        assert contexts["c-8"].dimensions == {"LegalEntityAxis": "TangerIncMember"}
        assert contexts["c-noaxis"].instant == "2025-12-31"
        assert contexts["c-noaxis"].dimensions == {}


class TestParseFactsForConcept:
    def test_matches_by_local_name_regardless_of_namespace_prefix(self) -> None:
        facts = parse_facts_for_concept(_skt_shaped_instance_xml(), "NetCashProvidedByUsedInOperatingActivities")
        assert {f.context_id: f.value for f in facts} == {
            "c-8": 295369000.0,
            "c-9": 260678000.0,
            "c-lp": 295421000.0,
            "c-q": 62918000.0,
        }

    def test_skips_non_numeric_facts(self) -> None:
        xml = """<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025">
  <us-gaap:SomeTextConcept contextRef="c-1">not a number</us-gaap:SomeTextConcept>
</xbrli:xbrl>"""
        assert parse_facts_for_concept(xml, "SomeTextConcept") == []


class TestResolveLegalEntityDimensionedAnnualFacts:
    def test_recovers_annual_facts_for_matching_registrant(self) -> None:
        result = resolve_legal_entity_dimensioned_annual_facts(
            _skt_shaped_instance_xml(), "NetCashProvidedByUsedInOperatingActivities", "TANGER INC."
        )
        assert result == {"2025-12-31": 295369000.0, "2024-12-31": 260678000.0}

    def test_does_not_match_a_different_legal_entity_member(self) -> None:
        result = resolve_legal_entity_dimensioned_annual_facts(
            _skt_shaped_instance_xml(),
            "NetCashProvidedByUsedInOperatingActivities",
            "TANGER PROPERTIES LIMITED PARTNERSHIP",
        )
        assert result == {"2025-12-31": 295421000.0}

    def test_excludes_quarterly_duration_even_when_entity_matches(self) -> None:
        # c-q is a Q4-only 3-month duration for TangerIncMember - must not leak into
        # the annual result even though the entity match is correct.
        result = resolve_legal_entity_dimensioned_annual_facts(
            _skt_shaped_instance_xml(), "NetCashProvidedByUsedInOperatingActivities", "TANGER INC."
        )
        assert 62918000.0 not in result.values()

    def test_refuses_short_or_no_match_registrant_name(self) -> None:
        assert (
            resolve_legal_entity_dimensioned_annual_facts(
                _skt_shaped_instance_xml(), "NetCashProvidedByUsedInOperatingActivities", "ABC"
            )
            == {}
        )
        assert (
            resolve_legal_entity_dimensioned_annual_facts(
                _skt_shaped_instance_xml(), "NetCashProvidedByUsedInOperatingActivities", "COMPLETELY UNRELATED CO"
            )
            == {}
        )

    def test_refuses_a_concept_with_no_legal_entity_dimension_at_all(self) -> None:
        # Assets is tagged only on c-noaxis (no LegalEntityAxis dimension) - must
        # never be treated as a match even though "Tanger" isn't involved.
        result = resolve_legal_entity_dimensioned_annual_facts(_skt_shaped_instance_xml(), "Assets", "TANGER INC.")
        assert result == {}


class TestFiscalYearForEndDate:
    def test_extracts_year(self) -> None:
        assert fiscal_year_for_end_date("2025-12-31") == 2025
