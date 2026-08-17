#!/usr/bin/env python3
"""Regression test: an 8-K whose filing text fails to fetch/parse must be flagged
data_unavailable, not silently recorded as "no material items disclosed".

Previously, a get_filing_plaintext() exception (e.g. the URL-construction bug fixed
in sec_edgar_client.py, or any transient fetch failure) fell back to items={}, which
meant every item_X_YY column was omitted from the row entirely (written as NULL by
BulkInsertManager) while data_unavailable stayed False - a material-event signal
(bankruptcy, M&A, leadership change) could be silently missing for a filing that was
never actually read, with no marker distinguishing it from a filing that was read and
genuinely had no material items.
"""

from unittest.mock import MagicMock

from loaders.load_current_reports_8k import CurrentReports8KLoader


def _make_loader() -> CurrentReports8KLoader:
    loader = CurrentReports8KLoader.__new__(CurrentReports8KLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.return_value = "0000320193"
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2026-01-15"],
                "accessionNumber": ["0001193125-26-000111"],
            }
        }
    }
    return loader


def test_filing_text_fetch_failure_is_flagged_unavailable_not_silently_clean() -> None:
    loader = _make_loader()
    loader.sec_client.get_filing_plaintext.side_effect = RuntimeError("404: not found")

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    record = records[0]
    assert record["data_unavailable"] is True
    assert record["data_unavailable_reason"] == "item_extraction_failed:RuntimeError"
    # Item flags are unknown, not "false" - still written as the schema's False
    # default so the row's columns stay consistent, but the row is clearly marked
    # unavailable so callers don't mistake it for a genuinely clean filing.
    assert record["item_1_01"] is False
    assert record["item_8_01"] is False


def test_successful_parse_is_not_flagged_unavailable() -> None:
    loader = _make_loader()
    loader.sec_client.get_filing_plaintext.return_value = "Item 5.02 Departure of Directors..."

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    record = records[0]
    assert record["data_unavailable"] is False
    assert record["data_unavailable_reason"] is None
    assert record["item_5_02"] is True
    assert record["item_1_01"] is False


def test_get_filing_plaintext_called_with_dashed_accession_number() -> None:
    """get_filing_plaintext() needs the SEC submissions API's raw dashed accession
    number (e.g. "0001193125-26-000111") to build the archive .txt filename - SEC's
    convention dashes the filename but not the containing directory. Passing the
    dash-stripped form (used for the DB primary key) as the fetch argument builds a
    URL that 404s on every real filing (confirmed live against SEC EDGAR before this
    fix), silently defeating item extraction for the loader's entire life.
    """
    loader = _make_loader()
    loader.sec_client.get_filing_plaintext.return_value = "Item 5.02 Departure of Directors..."

    records = loader.fetch_incremental("TEST", since=None)

    loader.sec_client.get_filing_plaintext.assert_called_once_with("0000320193", "0001193125-26-000111")
    # The DB primary key column must still stay dash-stripped (existing convention).
    assert records[0]["accession_number"] == "000119312526000111"


def test_unavailable_marker_accession_number_is_not_empty_string() -> None:
    """LIVE-REPRODUCED 2026-08-16: accession_number is NOT NULL (part of the composite PK
    with symbol). BulkInsertManager's COPY path applies FORCE_NULL to every column and
    collapses None->"" before writing the CSV buffer, so it can't tell a deliberate empty
    string apart from a real None - an "" here round-trips back to a real NULL and fails
    the NOT NULL/PK constraint on every single unavailable-marker row. Confirmed live: every
    ETF/foreign-issuer symbol with no SEC 8-K coverage (AEP, AFBI, AGG, ...) failed with
    'null value in column accession_number' during a full-universe run.
    """
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")

    records = loader.fetch_incremental("ETFX", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable"] is True
    assert records[0]["data_unavailable_reason"] == "symbol_not_found"
    accession = records[0]["accession_number"]
    assert accession != ""
    assert accession is not None
    assert len(accession) <= 20  # DB column is varchar(20)
