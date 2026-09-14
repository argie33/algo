"""Regression test for a reporting gap in NewXbrlConceptChecker
(algo/monitoring/data_patrol/checks/xbrl_new_concepts.py):

find_gaps() sorts purely by company count, and the checker only ever reports the top
_MAX_REPORTED of potentially hundreds of gaps (460 live at audit time) - live-confirmed via
SalesRevenueGoodsGross (61 tagging filers, the real gap behind the MGPI quarantine fix) and
SalesRevenueServicesNet (465 tagging filers, the real gap behind the ARCB quarantine fix)
never once surfacing in this check's own alert `examples` despite the WARN firing
continuously every run, both buried below higher-count-but-lower-value generic footnote/
disclosure concepts.

Fix: a gap whose concept name suggests it's a financial-statement revenue/sales line item
always gets a reporting slot, on top of (not instead of) the existing top-count-overall list -
this is exactly the highest-value kind of gap this check exists to catch.
"""

from unittest.mock import patch

from algo.monitoring.data_patrol.checks.xbrl_new_concepts import NewXbrlConceptChecker


class TestXbrlNewConceptsPriorityRanking:
    def _make_checker(self):
        checker = NewXbrlConceptChecker.__new__(NewXbrlConceptChecker)
        checker.results = []
        checker.log = lambda check_name, severity, table, message, details=None: checker.results.append(
            {"check_name": check_name, "severity": severity, "message": message, "details": details}
        )
        return checker

    def test_low_ranked_revenue_concept_still_reported(self):
        """20 high-count noise concepts plus one low-ranked, real revenue concept - the
        revenue concept must still appear in the reported examples even though a plain
        top-20-by-count cutoff would exclude it entirely."""
        noise_gaps = [(1000 - i, f"us-gaap:SomeDisclosureDetail{i}", "SOME CORP") for i in range(20)]
        real_gap = (61, "us-gaap:SalesRevenueGoodsGross", "MGP INGREDIENTS, INC.")
        all_gaps = [*noise_gaps, real_gap]

        checker = self._make_checker()
        with (
            patch("algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache", return_value=[1]),
            patch("algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps", return_value=all_gaps),
        ):
            checker.check_new_concepts()

        assert len(checker.results) == 1
        examples = checker.results[0]["details"]["examples"]
        reported_concepts = {e["concept"] for e in examples}
        assert "us-gaap:SalesRevenueGoodsGross" in reported_concepts

    def test_no_priority_gaps_falls_back_to_top_count(self):
        noise_gaps = [(1000 - i, f"us-gaap:SomeDisclosureDetail{i}", "SOME CORP") for i in range(25)]

        checker = self._make_checker()
        with (
            patch("algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache", return_value=[1]),
            patch("algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps", return_value=noise_gaps),
        ):
            checker.check_new_concepts()

        examples = checker.results[0]["details"]["examples"]
        assert len(examples) == 20
        assert examples[0]["concept"] == "us-gaap:SomeDisclosureDetail0"
