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


def test_foreign_private_issuer_with_no_8k_filings_gets_unavailable_marker_on_first_check() -> None:
    """FIX 2026-08-18: a symbol with valid SEC submissions but zero Form 8-K filings among
    them (foreign private issuers file Form 6-K instead, not 8-K - live-confirmed on
    AEM/AEG/AGRO/AER/ACB, all real companies with real CIKs/submissions) used to return a
    bare empty list here, indistinguishable from "not checked yet". No row ever got written,
    so the symbol never got a watermark and was re-fetched from scratch every single run
    forever - confirmed live via data_loader_status_history: this loader FAILED every run
    since 2026-08-16, completion climbing 0%->83% over 2+ days without ever reaching the 98%
    threshold, because 837/4934 universe symbols (mostly foreign private issuers) could never
    accumulate a row. On the symbol's first-ever check (since=None, no existing watermark),
    a checked-and-empty result must now write a real marker row instead.
    """
    loader = _make_loader()
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["6-K", "20-F", "6-K"],
                "filingDate": ["2026-01-15", "2025-11-01", "2025-08-01"],
                "accessionNumber": ["0001-26-000111", "0001-25-000222", "0001-25-000333"],
            }
        }
    }

    records = loader.fetch_incremental("AEM", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable"] is True
    assert records[0]["data_unavailable_reason"] == "no_8k_filings_in_recent_submissions"
    assert records[0]["accession_number"] == "UNAVAILABLE"


def test_no_new_8k_since_existing_watermark_stays_empty_not_remarked() -> None:
    """Companion to the first-check case above: once a symbol already has a watermark
    (since is a real date, not None - meaning it was already checked before, whether that
    produced a real filing or the unavailable marker above), a run that still finds no new
    8-K must return a plain empty list, not write another marker every run. Same "before
    writing the marker, check for prior coverage first" precedent as
    marker_masks_real_data_in_event_log_tables_bug_class_20260818 - re-marking on every
    incremental run would pollute the table without adding information.
    """
    from datetime import date

    loader = _make_loader()
    loader.sec_client.get_submissions.return_value = {
        "filings": {
            "recent": {
                "form": ["6-K"],
                "filingDate": ["2025-08-01"],
                "accessionNumber": ["0001-25-000333"],
            }
        }
    }

    records = loader.fetch_incremental("AEM", since=date(2026, 1, 1))

    assert records == []


def test_unavailable_marker_accession_number_is_not_empty_string(monkeypatch) -> None:
    """LIVE-REPRODUCED 2026-08-16: accession_number is NOT NULL (part of the composite PK
    with symbol). BulkInsertManager's COPY path applies FORCE_NULL to every column and
    collapses None->"" before writing the CSV buffer, so it can't tell a deliberate empty
    string apart from a real None - an "" here round-trips back to a real NULL and fails
    the NOT NULL/PK constraint on every single unavailable-marker row. Confirmed live: every
    ETF/foreign-issuer symbol with no SEC 8-K coverage (AEP, AFBI, AGG, ...) failed with
    'null value in column accession_number' during a full-universe run.
    """
    monkeypatch.setattr("utils.loaders.retry_helper.time.sleep", lambda *_: None)
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


def test_cik_lookup_retries_once_before_giving_up(monkeypatch) -> None:
    """FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): a single
    symbol_to_cik() ValueError used to be treated as permanent "not in SEC" with zero
    retry at this layer. Live-confirmed via AEP (a real S&P 500 utility, CIK 4904,
    explicitly documented in sec_ticker_cache.py as the canary case for tickers missing
    from SEC's bulk ticker files) - got permanently marked "symbol_not_found" in this
    table from what a fresh, unretried call today proves was a transient failure. One
    retry with backoff must be given a chance to recover before writing a marker that,
    per the incremental-scheduling test above, effectively never gets re-checked.
    """
    monkeypatch.setattr("utils.loaders.retry_helper.time.sleep", lambda *_: None)
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = [ValueError("transient"), "0000004904"]

    records = loader.fetch_incremental("AEP", since=None)

    assert loader.sec_client.symbol_to_cik.call_count == 2
    assert records
    assert records[0].get("data_unavailable_reason") != "symbol_not_found"


def test_cik_lookup_gives_up_as_not_found_after_retry_exhausted(monkeypatch) -> None:
    """The retry is bounded, not infinite - a symbol that genuinely isn't in SEC (or
    whose transient failure doesn't clear within one retry) must still resolve to the
    honest "symbol_not_found" marker, not hang or raise."""
    monkeypatch.setattr("utils.loaders.retry_helper.time.sleep", lambda *_: None)
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = ValueError("not found")

    records = loader.fetch_incremental("NOPE", since=None)

    assert loader.sec_client.symbol_to_cik.call_count == 2
    assert records[0]["data_unavailable_reason"] == "symbol_not_found"
