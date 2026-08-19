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


_XML_WITH_GEOGRAPHIC_SEGMENTS = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c1">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">us-gaap:AmericasMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c2">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementGeographicalAxis">us-gaap:EuropeMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="c1">1000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c2">500000</us-gaap:Revenues>
</xbrl>"""


def test_geographic_only_filer_writes_geographic_not_operating() -> None:
    """A filer with no StatementBusinessSegmentsAxis tagging (only geographic) must
    have segment_type='geographic' written to the DB - sec_segment_info.segment_type
    is an indexed column with distinct meaning per migration 1157, and
    load_sec_segment_metrics.py branches on segment_type == 'geographic' explicitly.
    Hardcoding 'operating' regardless of the parser's actual finding silently
    mislabeled every geographic-only filer's segment data."""
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
    loader.sec_client.get_filing_xml.return_value = _XML_WITH_GEOGRAPHIC_SEGMENTS

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 3  # 1 aggregate + 2 segments
    for record in records:
        assert record["segment_type"] == "geographic"


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


_XML_WITH_UNCONVERTED_FOREIGN_CURRENCY_SEGMENT = """<?xml version="1.0"?>
<xbrl xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <context id="c1">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">us-gaap:CarSegmentMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <context id="c2">
    <entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">us-gaap:SegBMember</xbrldi:explicitMember></segment></entity>
    <period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="c1">78861662000000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="c2">500000</us-gaap:Revenues>
</xbrl>"""


def test_implausible_segment_revenue_nulled_not_crashed() -> None:
    """A segment revenue value that overflows NUMERIC(15,2) (>= $1 trillion, e.g. an
    unconverted foreign-currency XBRL fact like VFS/VinFast's raw VND figures) must be
    nulled out for that one field, not left in the record to crash the whole symbol's
    COPY at insert time. Live-confirmed 2026-08-19: VFS's CarSegmentMember revenue of
    78,861,662,000,000 (raw VND) overflowed NUMERIC(15,2)'s 10^13 ceiling and failed
    VFS's entire sec_segment_info write - every segment plus the AGGREGATE row, not just
    the one bad field - on every run."""
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
    loader.sec_client.get_filing_xml.return_value = _XML_WITH_UNCONVERTED_FOREIGN_CURRENCY_SEGMENT

    records = loader.fetch_incremental("VFS", since=None)

    assert len(records) == 3  # 1 aggregate + 2 segments - the write is NOT dropped
    segment_rows = [r for r in records if r["segment_name"] != "AGGREGATE"]
    car_segment = next(r for r in segment_rows if "Car" in r["segment_name"])
    assert car_segment["segment_revenue"] is None
    other_segment = next(r for r in segment_rows if "Car" not in r["segment_name"])
    assert other_segment["segment_revenue"] == 500000


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
