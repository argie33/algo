"""Regression test for the segment-dimensional XBRL debt fallback (2026-09-01, goal session:
"understand our data gaps before resuming Fama-MacBeth"). See
loaders/helpers/sec_segment_debt.py's module docstring for the full Ford root-cause writeup.

The fixture below is a minimal, hand-built XBRL instance snippet reproducing the real
structural shape live-confirmed against Ford's actual FY2025 10-K instance document
(f-20251231_htm.xml, accession 0000037996-26-000015) - not the real filing itself (5.5MB,
not worth committing) - with the same context/dimension pattern: two single-axis
StatementBusinessSegmentsAxis contexts per period (real decomposition), plus a second set of
contexts that combine the segment axis with LongtermDebtTypeAxis (a finer breakdown WITHIN
one segment, which must NOT be additionally summed - the double-counting guard this test
exists to lock in).
"""

from loaders.helpers.sec_segment_debt import (
    find_10k_for_fiscal_year,
    sum_segment_dimensional_debt,
)

_FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:f="http://example.com/f">
    <context id="c-undim">
        <entity><identifier scheme="http://www.sec.gov/CIK">0000037996</identifier></entity>
        <period><instant>2025-12-31</instant></period>
    </context>
    <context id="c-auto">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000037996</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">f:CompanyExcludingFordCreditMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><instant>2025-12-31</instant></period>
    </context>
    <context id="c-credit">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000037996</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">f:FordCreditMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><instant>2025-12-31</instant></period>
    </context>
    <context id="c-credit-unsecured">
        <entity>
            <identifier scheme="http://www.sec.gov/CIK">0000037996</identifier>
            <segment>
                <xbrldi:explicitMember dimension="us-gaap:LongtermDebtTypeAxis">us-gaap:UnsecuredDebtMember</xbrldi:explicitMember>
                <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">f:FordCreditMember</xbrldi:explicitMember>
            </segment>
        </entity>
        <period><instant>2025-12-31</instant></period>
    </context>
    <us-gaap:DebtCurrent contextRef="c-auto" unitRef="usd" decimals="-6">5550000000</us-gaap:DebtCurrent>
    <us-gaap:LongTermDebtNoncurrent contextRef="c-auto" unitRef="usd" decimals="-6">16369000000</us-gaap:LongTermDebtNoncurrent>
    <us-gaap:DebtCurrent contextRef="c-credit" unitRef="usd" decimals="-6">51752000000</us-gaap:DebtCurrent>
    <us-gaap:LongTermDebtNoncurrent contextRef="c-credit" unitRef="usd" decimals="-6">89665000000</us-gaap:LongTermDebtNoncurrent>
    <us-gaap:LongTermDebtNoncurrent contextRef="c-credit-unsecured" unitRef="usd" decimals="-6">52357000000</us-gaap:LongTermDebtNoncurrent>
</xbrl>
"""


class TestSumSegmentDimensionalDebt:
    def test_sums_single_axis_segment_contexts(self) -> None:
        result = sum_segment_dimensional_debt(_FIXTURE_XML, "2025-12-31")
        assert result is not None
        total, segment_count = result
        assert segment_count == 2
        # 5,550M + 16,369M (auto) + 51,752M + 89,665M (credit) = 163,336M - the
        # multi-dimensional c-credit-unsecured context (LongtermDebtTypeAxis combined with
        # the segment axis) must NOT be added on top.
        assert total == 163_336_000_000.0

    def test_wrong_period_returns_none(self) -> None:
        assert sum_segment_dimensional_debt(_FIXTURE_XML, "2024-12-31") is None

    def test_single_segment_only_returns_none(self) -> None:
        # A filer with only one dimensional context isn't a full decomposition - must not
        # be treated as "the whole company", see module docstring.
        one_segment_xml = _FIXTURE_XML.replace(
            '<us-gaap:DebtCurrent contextRef="c-credit" unitRef="usd" decimals="-6">51752000000</us-gaap:DebtCurrent>\n'
            '    <us-gaap:LongTermDebtNoncurrent contextRef="c-credit" unitRef="usd" decimals="-6">89665000000</us-gaap:LongTermDebtNoncurrent>',
            "",
        )
        assert sum_segment_dimensional_debt(one_segment_xml, "2025-12-31") is None


class TestFind10KForFiscalYear:
    def test_matches_by_report_date_year(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "10-K"],
                    "reportDate": ["2025-12-31", "2025-09-30", "2024-12-31"],
                    "accessionNumber": ["0000037996-26-000015", "0000037996-25-000099", "0000037996-25-000013"],
                    "filingDate": ["2026-02-11", "2025-11-01", "2025-02-06"],
                }
            }
        }
        assert find_10k_for_fiscal_year(submissions, 2025) == ("0000037996-26-000015", "2025-12-31")
        assert find_10k_for_fiscal_year(submissions, 2024) == ("0000037996-25-000013", "2024-12-31")

    def test_no_match_returns_none(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "reportDate": ["2025-09-30"],
                    "accessionNumber": ["x"],
                    "filingDate": ["2025-11-01"],
                }
            }
        }
        assert find_10k_for_fiscal_year(submissions, 2025) is None

    def test_amendment_wins_over_original_when_both_present(self) -> None:
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-K/A"],
                    "reportDate": ["2025-12-31", "2025-12-31"],
                    "accessionNumber": ["orig", "amended"],
                    "filingDate": ["2026-02-11", "2026-03-01"],
                }
            }
        }
        accession, _ = find_10k_for_fiscal_year(submissions, 2025)
        assert accession == "amended"
