"""Regression test (2026-08-20, goal: finance-accuracy audit): DividendDataLoader's
_unavailable_record() keys its "no data" marker row on (symbol, ex_dividend_date=today) -
the real DB unique constraint - so every transient SEC fetch failure wrote a BRAND NEW
permanent row instead of updating a single "current status" record. Live-confirmed: 1,795
such rows had accumulated across 1,242 symbols, including 100+ real, active dividend payers
(e.g. ADNT, ADP, AEE) whose complete, correct dividend history now sat in the table
alongside dated "no data" noise from whatever day SEC happened to time out.

Fixed: on an unexpected fetch/parse failure, fetch_incremental() now checks whether the
symbol already has a real (dividend_per_share NOT NULL) row on file before writing a
fetch_error marker - a transient failure shouldn't record anything for a symbol whose
current state is already correctly known. See migration 1214 for the one-time cleanup of
already-accumulated rows.
"""

from unittest.mock import MagicMock, patch

from loaders.load_dividend_data import DividendDataLoader


def _make_loader() -> DividendDataLoader:
    loader = DividendDataLoader.__new__(DividendDataLoader)
    loader.sec_client = MagicMock()
    loader.sec_client.symbol_to_cik.return_value = "0000320193"
    loader.sec_client.get_company_facts.return_value = {"facts": {"us-gaap": {"SomeConcept": {}}}}
    return loader


def test_known_dividend_payer_gets_no_marker_row_on_transient_failure(monkeypatch) -> None:
    loader = _make_loader()
    monkeypatch.setattr(
        loader, "_extract_dividends_from_xbrl_concept", MagicMock(side_effect=KeyError("unexpected shape"))
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)  # symbol has a real dividend_per_share row on file

    with patch("utils.db.DatabaseContext") as mock_db:
        mock_db.return_value.__enter__.return_value = mock_cursor
        records = loader.fetch_incremental("ADNT", since=None)

    assert records == []


def test_symbol_with_no_real_history_still_gets_the_honest_marker(monkeypatch) -> None:
    loader = _make_loader()
    monkeypatch.setattr(
        loader, "_extract_dividends_from_xbrl_concept", MagicMock(side_effect=KeyError("unexpected shape"))
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # no real dividend_per_share row exists yet

    with patch("utils.db.DatabaseContext") as mock_db:
        mock_db.return_value.__enter__.return_value = mock_cursor
        records = loader.fetch_incremental("NEWCO", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable_reason"].startswith("fetch_error:")


def test_lookup_failure_falls_back_to_writing_the_marker(monkeypatch) -> None:
    """If the existing-history check itself fails (e.g. DB unavailable), fail safe by still
    writing the honest marker rather than silently dropping the failure signal entirely."""
    loader = _make_loader()
    monkeypatch.setattr(
        loader, "_extract_dividends_from_xbrl_concept", MagicMock(side_effect=KeyError("unexpected shape"))
    )

    with patch("utils.db.DatabaseContext", side_effect=RuntimeError("pool exhausted")):
        records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable_reason"].startswith("fetch_error:")
