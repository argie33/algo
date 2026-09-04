"""Regression test for _fill_eps_shares_from_dual_class_dimensional_facts()
(utils/external/sec_statements.py) - the loader-integration wiring around
loaders/helpers/sec_dual_class_eps.py's pure extraction logic (tested separately in
tests/unit/test_sec_dual_class_eps.py). See that module's docstring for the Berkshire
Hathaway root-cause writeup this closes.
"""

from utils.external.sec_statements import _fill_eps_shares_from_dual_class_dimensional_facts

_TARGET_FIELDS = (
    "earnings_per_share_basic",
    "earnings_per_share_diluted",
    "weighted_average_number_of_shares_outstanding_basic",
    "weighted_average_number_of_diluted_shares_outstanding",
)

_FIXTURE_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    <context id="c-classB-{year}">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0001067983</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><startDate>{year}-01-01</startDate><endDate>{year}-12-31</endDate></period>
    </context>
    <us-gaap:EarningsPerShareBasic contextRef="c-classB-{year}" unitRef="usd-per-share" decimals="2">31.04</us-gaap:EarningsPerShareBasic>
    <us-gaap:WeightedAverageNumberOfSharesOutstandingBasic contextRef="c-classB-{year}" unitRef="shares" decimals="0">2157335139</us-gaap:WeightedAverageNumberOfSharesOutstandingBasic>
</xbrl>
"""


class _FakeClient:
    def __init__(self) -> None:
        self.get_filing_xml_calls: list[tuple[str, str, str]] = []

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001067983"

    def get_submissions(self, cik: str) -> dict:
        years = list(range(2010, 2026))
        return {
            "filings": {
                "recent": {
                    "form": ["10-K"] * len(years),
                    "reportDate": [f"{y}-12-31" for y in years],
                    "accessionNumber": [f"acc-{y}" for y in years],
                    "filingDate": [f"{y + 1}-02-15" for y in years],
                }
            }
        }

    def get_filing_xml(self, cik: str, accession_number: str, form_type: str) -> str:
        self.get_filing_xml_calls.append((cik, accession_number, form_type))
        year = accession_number.split("-")[-1]
        return _FIXTURE_XML_TEMPLATE.format(year=year)


class TestDualClassEpsFallbackIntegration:
    def test_fills_gap_for_resolvable_dot_suffix_symbol(self) -> None:
        rows = [{"fiscal_year": 2025, **dict.fromkeys(_TARGET_FIELDS)}]
        client = _FakeClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "BRK.B")

        assert rows[0]["earnings_per_share_basic"] == 31.04
        assert rows[0]["weighted_average_number_of_shares_outstanding_basic"] == 2157335139.0
        # FIXED 2026-09-03: the fixture has no diluted facts anywhere in the filing - ASC 260
        # treats that as "no dilutive securities", so diluted now mirrors basic (see
        # loaders/helpers/sec_dual_class_eps.py's own comment for the rationale).
        assert rows[0]["earnings_per_share_diluted"] == 31.04
        assert rows[0]["weighted_average_number_of_diluted_shares_outstanding"] == 2157335139.0

    def test_never_overwrites_a_real_value(self) -> None:
        rows = [
            {
                "fiscal_year": 2025,
                "earnings_per_share_basic": 999.0,  # already resolved by an earlier tier
                "earnings_per_share_diluted": None,
                "weighted_average_number_of_shares_outstanding_basic": None,
                "weighted_average_number_of_diluted_shares_outstanding": None,
            }
        ]
        client = _FakeClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "BRK.B")

        assert rows[0]["earnings_per_share_basic"] == 999.0
        assert rows[0]["weighted_average_number_of_shares_outstanding_basic"] == 2157335139.0

    def test_unresolvable_symbol_makes_no_network_calls(self) -> None:
        # GTN (bare ticker, no security_name passed) - genuinely unresolvable: no dot suffix,
        # no security_name class text, and not in the explicit override table (unlike "V",
        # see test_explicit_override_symbol_fills_gap below).
        rows = [{"fiscal_year": 2025, **dict.fromkeys(_TARGET_FIELDS)}]
        client = _FakeClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "GTN")

        assert client.get_filing_xml_calls == []
        assert rows[0]["earnings_per_share_basic"] is None

    def test_explicit_override_symbol_fills_gap(self) -> None:
        # FIXED 2026-09-03: V (Visa) has no dot suffix and no class text in security_name, but
        # is covered by sec_dual_class_eps.py's explicit _CLASS_LETTER_OVERRIDES table (live-
        # verified against Visa's real FY2025 10-K: EPS tagged under CommonClassAMember). Reuse
        # the class-B fixture template's shape via a class-A variant to prove the override
        # actually reaches the network-fetch path, not just resolve_class_letter in isolation.
        class _FakeClassAClient(_FakeClient):
            def get_filing_xml(self, cik: str, accession_number: str, form_type: str) -> str:
                self.get_filing_xml_calls.append((cik, accession_number, form_type))
                year = accession_number.split("-")[-1]
                return _FIXTURE_XML_TEMPLATE.format(year=year).replace(
                    "us-gaap:CommonClassBMember", "us-gaap:CommonClassAMember"
                )

        rows = [{"fiscal_year": 2025, **dict.fromkeys(_TARGET_FIELDS)}]
        client = _FakeClassAClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "V")

        assert client.get_filing_xml_calls != []
        assert rows[0]["earnings_per_share_basic"] == 31.04

    def test_fully_populated_row_makes_no_network_calls(self) -> None:
        rows = [{"fiscal_year": 2025, **dict.fromkeys(_TARGET_FIELDS, 1.0)}]
        client = _FakeClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "BRK.B")

        assert client.get_filing_xml_calls == []

    def test_caps_to_three_most_recent_missing_years(self) -> None:
        rows = [{"fiscal_year": year, **dict.fromkeys(_TARGET_FIELDS)} for year in range(2015, 2025)]
        client = _FakeClient()

        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, "BRK.B")

        assert len(client.get_filing_xml_calls) == 3
        attempted = {accn for _, accn, _ in client.get_filing_xml_calls}
        assert attempted == {"acc-2024", "acc-2023", "acc-2022"}
