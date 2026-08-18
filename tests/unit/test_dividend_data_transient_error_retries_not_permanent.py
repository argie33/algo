"""Regression test for the 2026-08-17 "no SEC data" audit finding: DividendDataLoader's
fetch_incremental() used to catch every exception - including a SEC timeout or the SEC client's
own already-exhausted-retry RuntimeError (utils/external/sec_edgar_client.py's 8-attempt
exponential-backoff, worst case minutes) - and write a permanent `fetch_error:<Type>` data-
unavailable record on the very first attempt. That completely bypassed
OptimalLoader.load_symbol()'s built-in 3-attempt retry-with-backoff for exactly this class of
error (utils/optimal_loader.py:316-352), which only fires on TransientAPIError
(utils/loaders/transient_errors.py) - infrastructure no loader in the codebase actually raised
before this fix. Live-confirmed against the local DB: 1854 symbols' latest dividend_data row was
stuck on a fetch_error reason, most plausibly from SEC rate-limiting/timeouts that a real retry
would have recovered from.

fetch_incremental() must now raise TransientAPIError for a timeout or exhausted-retries SEC API
error (not swallow it into a written DB record), and a genuine 404 (no XBRL filings at all - a
real, permanent case, e.g. mutual funds/shells) must get the honest "no_xbrl_filings" label
instead of the alarming generic "fetch_error:FileNotFoundError".
"""

from unittest.mock import MagicMock

import pytest

from loaders.load_dividend_data import DividendDataLoader
from utils.loaders.transient_errors import TransientAPIError


def _make_loader() -> DividendDataLoader:
    loader = DividendDataLoader.__new__(DividendDataLoader)
    loader.sec_client = MagicMock()
    return loader


def test_sec_timeout_raises_transient_not_written_as_permanent_unavailable() -> None:
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = TimeoutError("simulated hang")

    with pytest.raises(TransientAPIError):
        loader.fetch_incremental("TEST", since=None)


def test_sec_client_exhausted_retries_raises_transient_not_written_as_permanent_unavailable() -> None:
    """The SEC client itself raises a plain RuntimeError once ITS OWN 8-attempt retry budget
    is exhausted (e.g. repeated 429/503 from SEC). That must still be treated as transient at
    this layer - OptimalLoader gives 3 more independent attempts, each with its own fresh
    20s window and the SEC client's own retry budget, rather than giving up after just one."""
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = RuntimeError(
        "SEC API failed after 8 retries on transient error 503 Service Unavailable"
    )

    with pytest.raises(TransientAPIError):
        loader.fetch_incremental("TEST", since=None)


def test_404_no_filings_gets_honest_label_not_generic_fetch_error() -> None:
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.return_value = "0000000000"
    loader.sec_client.get_company_facts.side_effect = FileNotFoundError("SEC filing not found")

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable_reason"] == "no_xbrl_filings"


def test_cik_not_found_gets_honest_label_and_is_not_treated_as_transient() -> None:
    """FIXED 2026-08-18: symbol_to_cik() raises ValueError when a ticker isn't resolvable to a
    CIK via any lookup method - a PERMANENT condition (e.g. HIFS - Hingham Institution for
    Savings - reports to the FDIC under Exchange Act Section 12(i), never has an SEC CIK at
    all). This used to fall into the generic `except Exception` branch, get wrapped as
    TransientAPIError, and waste 3 OptimalLoader retries redoing a lookup that can never
    succeed before finally surfacing as an opaque "fetch_error:RuntimeError". Must resolve
    immediately to a real "cik_not_found" record, no retry."""
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.side_effect = ValueError("Symbol HIFS not found in SEC ticker cache")

    records = loader.fetch_incremental("HIFS", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable_reason"] == "cik_not_found"


def test_unexpected_parse_bug_still_written_as_fetch_error_not_silently_retried_forever(monkeypatch) -> None:
    """A genuinely unexpected error in this loader's OWN parsing logic (not the SEC client call,
    which _fetch_sec_data_with_timeout now treats as transient by design - see that method's
    except Exception branch) must still be caught and marked unavailable rather than propagating
    forever - this loader's safety net for real bugs, unchanged by this fix."""
    loader = _make_loader()
    loader.sec_client.symbol_to_cik.return_value = "0000320193"
    loader.sec_client.get_company_facts.return_value = {"facts": {"us-gaap": {"SomeConcept": {}}}}
    monkeypatch.setattr(
        loader, "_extract_dividends_from_xbrl_concept", MagicMock(side_effect=KeyError("unexpected shape"))
    )

    records = loader.fetch_incremental("TEST", since=None)

    assert len(records) == 1
    assert records[0]["data_unavailable_reason"].startswith("fetch_error:")
