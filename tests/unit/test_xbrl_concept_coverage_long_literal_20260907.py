"""Regression test: load_known_concepts() must not silently drop already-fetched XBRL
concept literals longer than 90 characters.

Found 2026-09-07 (goal session: "make sure the list/checks are right" audit) - the concept-
literal regex in utils/external/xbrl_concept_coverage.py capped matches at 90 chars, so 9
real, already-fetched concepts (up to 110 chars, e.g. sec_income_statement.py's
"IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFrom
EquityMethodInvestments") were invisible to load_known_concepts() and reappeared as false-
positive "undismissed gaps" in xbrl_concept_coverage_scan.py output despite being fully wired
up.
"""

from utils.external.xbrl_concept_coverage import _CONCEPT_LITERAL_RE, load_known_concepts

_LONG_REAL_CONCEPT = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"
)


class TestConceptLiteralRegexAllowsLongNames:
    def test_regex_matches_110_char_literal(self) -> None:
        assert len(_LONG_REAL_CONCEPT) == 107
        text = f'CONCEPTS = [\n    "{_LONG_REAL_CONCEPT}",\n]\n'
        assert _CONCEPT_LITERAL_RE.findall(text) == [_LONG_REAL_CONCEPT]

    def test_known_concepts_includes_long_literal_already_fetched(self) -> None:
        known = load_known_concepts()
        assert _LONG_REAL_CONCEPT in known
