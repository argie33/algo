#!/usr/bin/env python3
"""Regression test: segment records must be dated from the actual 10-K's SEC-reported
dates (reportDate/filingDate), not fabricated as today() when a companyfacts-wide date
scan happens to fail.

Previously, fiscal_year/filing_date came from _extract_filing_date() scanning the
*entire* companyfacts response for the max 'filed' date across all XBRL concepts -
which can reflect an unrelated, later filing (e.g. an interim 10-Q) rather than the
specific 10-K whose raw XML was parsed for segment revenue. And if that scan found
nothing, the code silently defaulted fiscal_year/filing_date to date.today() - real
segment revenue data getting stamped with today's date/year instead of its actual
fiscal period, corrupting any time-series or freshness use of those columns.
"""

from datetime import date
from unittest.mock import MagicMock

from loaders.load_sec_segment_info import SecSegmentInfoLoader


def _make_loader() -> SecSegmentInfoLoader:
    loader = SecSegmentInfoLoader.__new__(SecSegmentInfoLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.return_value = "0000320193"
    # companyfacts never has segment data available (parse_companyfacts always
    # reports data_available=False - see sec_xbrl_segments.py) but is still used to
    # confirm the symbol has facts at all.
    loader.sec_client.get_company_facts.return_value = {"facts": {"us-gaap": {}}}
    return loader


_XML_WITH_SEGMENTS = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c1">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">us-gaap:SegAMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c2">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">us-gaap:SegBMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="c1">1000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c2">500000</us-gaap:Revenues>
</xbrl>"""


def test_uses_10k_report_date_not_todays_date() -> None:
    loader = _make_loader()
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0001193125-26-000111"],
                "reportDate": ["2025-12-31"],
                "filingDate": ["2026-02-10"],
            }
        }
    }
    loader.sec_client.get_filing_xml.return_value = _XML_WITH_SEGMENTS

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 3  # 1 aggregate + 2 segments
    for record in records:
        assert record["filing_date"] == date(2025, 12, 31)
        assert record["fiscal_year"] == 2025
        assert record["data_unavailable"] is False
    assert record["filing_date"] != date.today()


def test_falls_back_to_filing_date_when_report_date_missing() -> None:
    loader = _make_loader()
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0001193125-26-000111"],
                "reportDate": [""],
                "filingDate": ["2026-02-10"],
            }
        }
    }
    loader.sec_client.get_filing_xml.return_value = _XML_WITH_SEGMENTS

    records = loader.fetch_incremental("TEST", since=None)

    assert records[0]["filing_date"] == date(2026, 2, 10)
    assert records[0]["fiscal_year"] == 2026


def test_marks_unavailable_instead_of_fabricating_todays_date_when_no_date_found() -> None:
    loader = _make_loader()
    # 10-K found (so segment revenue is successfully extracted from its XML) but SEC's
    # own date columns are both missing, and companyfacts has no 'filed' dates either.
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0001193125-26-000111"],
                "reportDate": [""],
                "filingDate": [""],
            }
        }
    }
    loader.sec_client.get_filing_xml.return_value = _XML_WITH_SEGMENTS

    records = loader.fetch_incremental("TEST", since=None)

    # Real segment revenue was found, but with no attributable date the loader must
    # fail-fast rather than silently stamp the row with today()'s date.
    assert len(records) == 1
    assert records[0]["data_unavailable"] is True
    assert records[0]["reason"] == "filing_date_unavailable"
