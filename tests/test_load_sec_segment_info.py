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
from unittest.mock import MagicMock, patch

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


def _fake_db_context():
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


def test_symbol_not_found_for_already_covered_symbol_skips_and_retracts_marker() -> None:
    """BUG FOUND 2026-08-21 (same bug class as load_current_reports_8k.py's/the analyst
    loaders' pre-fix marker retraction fixes): the "symbol_not_found" marker's
    fiscal_year=date.today().year permanently outranks any real historical segment data
    in a "latest fiscal_year" read, and was written unconditionally with zero retry -
    live-confirmed 20 symbols including exactly the dot-suffix dual-class tickers this
    session already fixed dot/dash handling for (BRK.A, BRK.B, CRD.A, CRD.B, GEF.B,
    GTN.A, HEI.A, HVT.A, LEN.B, MOG.A, MOG.B, MKC.V) - a fresh symbol_to_cik() call
    resolves every one of them correctly, proving the stored marker was a one-off
    transient miss. A symbol with real coverage must skip the write and retract any
    pre-existing marker."""
    loader = SecSegmentInfoLoader.__new__(SecSegmentInfoLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")
    ctx, cur = _fake_db_context()

    with (
        patch.object(loader, "_has_prior_real_coverage", return_value=True),
        patch("loaders.load_sec_segment_info.DatabaseContext", return_value=ctx),
    ):
        result = loader.fetch_incremental("BRK.A", since=None)

    assert result == []
    query, params = cur.execute.call_args[0]
    assert "DELETE FROM sec_segment_info" in query
    assert "data_unavailable = true" in query
    assert params == ("BRK.A",)


def test_symbol_not_found_for_never_covered_symbol_still_gets_the_marker() -> None:
    """Control: a symbol with no real segment data on record must still get the honest
    symbol_not_found marker - this is the genuine "never resolved" case."""
    loader = SecSegmentInfoLoader.__new__(SecSegmentInfoLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")

    with patch.object(loader, "_has_prior_real_coverage", return_value=False):
        result = loader.fetch_incremental("ZZZZ", since=None)

    assert len(result) == 1
    assert result[0]["data_unavailable"] is True
    assert result[0]["reason"] == "symbol_not_found"


def test_no_segment_data_for_already_covered_symbol_skips_and_retracts_marker() -> None:
    """A DIFFERENT call site than symbol_not_found (no_segment_data, hit when no annual
    filing is found this run) must ALSO respect the coverage guard. Deliberately not
    redundant with the symbol_not_found test above even though both exercise the same
    shared _unavailable_marker() implementation: this guards against a regression in one
    call site's own wiring (e.g. a future edit reverting `marker = ...; return [marker]
    if marker else []` back to an unconditional `return [self._unavailable_marker(...)]`)
    that a single-call-site test can never catch. Live-reproduced 2026-08-24: this exact
    class of regression happened same-day (see _unavailable_marker's own docstring) - a
    "simplification" commit silently dropped the guard from 4 of 5 call sites while a
    test covering only the symbol_not_found path kept passing throughout."""
    loader = _make_loader()
    loader.sec_client.get_submissions.return_value = {"filings": {"recent": {"form": [], "accessionNumber": []}}}
    ctx, cur = _fake_db_context()

    with (
        patch.object(loader, "_has_prior_real_coverage", return_value=True),
        patch("loaders.load_sec_segment_info.DatabaseContext", return_value=ctx),
    ):
        result = loader.fetch_incremental("TEST", since=None)

    assert result == []
    query, params = cur.execute.call_args[0]
    assert "DELETE FROM sec_segment_info" in query
    assert "data_unavailable = true" in query
    assert params == ("TEST",)


def test_successful_extraction_retracts_a_stale_marker_from_before_the_symbol_resolved() -> None:
    """BUG FOUND 2026-08-30 (goal session, live-confirmed via BRNX): stale-marker
    retraction was only ever wired into the FAILURE call sites (_handle_symbol_not_found /
    _unavailable_marker, see their own docstrings and the tests above) - each of those only
    fires retraction when the SAME failure recurs on a later run and finds prior real
    coverage already on record. A symbol that fully recovers (this run's own symbol_to_cik
    succeeds, real segment data is found) never re-enters that guarded code path at all, so
    an old marker from before it resolved is never deleted. Live-confirmed via BRNX: a real
    fiscal_year=2025 segment row coexisted with an orphaned fiscal_year=2026/
    reason='symbol_not_found' marker from before its ticker resolved - exactly the
    "marker outranks real data in a naive ORDER BY fiscal_year DESC" bug class
    _unavailable_marker's own docstring already describes, just reached via a path that
    docstring's fix never covered. A successful extraction must also retract any stale
    marker for the same symbol."""
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
    ctx, cur = _fake_db_context()

    with patch("loaders.load_sec_segment_info.DatabaseContext", return_value=ctx):
        records = loader.fetch_incremental("BRNX", since=None)

    assert len(records) == 3  # 1 aggregate + 2 segments
    assert all(r["data_unavailable"] is False for r in records)
    query, params = cur.execute.call_args[0]
    assert "DELETE FROM sec_segment_info" in query
    assert "data_unavailable = true" in query
    assert params == ("BRNX",)


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


def test_find_latest_annual_filing_prefers_original_10k_over_later_10ka() -> None:
    """BUG FOUND 2026-08-29 (goal session, sec_segment_info "no_segment_dimension_contexts"
    gap audit): a 10-K/A is very commonly filed solely to add/correct Part III information
    (director/officer compensation, incorporated by reference from the proxy) and carries a
    near-empty XBRL instance with none of the primary financial statements. A plain
    most-recent-first scan over 10-K/10-K/A together always picked the later 10-K/A over
    the substantive original 10-K it amends. Live-confirmed against LAC and PDSB: both
    10-K/A instances were a few KB with zero Revenues/segment facts, while their original
    10-Ks (same reportDate, filed weeks earlier) were multi-MB instances with real segment
    data. Must now prefer the base (non-amendment) form when both exist for the same
    filing history, regardless of submissions order."""
    loader = _make_loader()
    submissions = {
        "filings": {
            "recent": {
                # SEC orders 'recent' most-recent-first; the 10-K/A (filed later,
                # amending the 10-K below) appears before the original 10-K.
                "form": ["10-K/A", "10-K"],
                "accessionNumber": ["0001193125-26-193861", "0001193125-26-115081"],
                "reportDate": ["2025-12-31", "2025-12-31"],
                "filingDate": ["2026-04-30", "2026-03-19"],
            }
        }
    }

    result = loader._find_latest_annual_filing(submissions)

    assert result is not None
    assert result["form"] == "10-K"
    assert result["accession_formatted"] == "0001193125-26-115081"


def test_find_latest_annual_filing_falls_back_to_amendment_when_no_base_form_exists() -> None:
    """A filer whose only annual filing on record is itself an amendment (e.g. the
    original 10-K predates SEC's electronic filing history, or was withdrawn) must still
    be found - only prefer the base form over an amendment when a base form actually
    exists, never skip amendments outright."""
    loader = _make_loader()
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K/A"],
                "accessionNumber": ["0001193125-26-193861"],
                "reportDate": ["2025-12-31"],
                "filingDate": ["2026-04-30"],
            }
        }
    }

    result = loader._find_latest_annual_filing(submissions)

    assert result is not None
    assert result["form"] == "10-K/A"
    assert result["accession_formatted"] == "0001193125-26-193861"
