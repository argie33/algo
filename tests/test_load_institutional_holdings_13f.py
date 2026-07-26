#!/usr/bin/env python3
"""Regression tests: SEC Form 13F bulk dataset discovery and parsing.

Previously this loader (1) guessed the bulk dataset filename as
"{year}-Q{quarter}_FORM13FDATA.zip", which never matches SEC's real naming
convention ("01jun2025-31aug2025_form13f.zip" - a date-range tied to the 45-day
filing deadline, not a calendar-quarter label) and 404s on every real request,
and (2) parsed the downloaded TSV assuming a "ticker"/"shrsOrPrnAmt" column pair
that does not exist - real INFOTABLE.tsv columns are NAMEOFISSUER/CUSIP/SSHPRNAMT
(13F filings identify securities by CUSIP only). Confirmed live against SEC's real
listing page and a real downloaded dataset before fixing.
"""

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader

LISTING_HTML = """
<html><body>
<a href="/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip">Q1 2026</a>
<a href="/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip">Q4 2025</a>
<a href="/files/structureddata/data/form-13f-data-sets/01sep2025-30nov2025_form13f.zip">Q3 2025</a>
</body></html>
"""


def _make_loader() -> InstitutionalHoldings13FLoader:
    return InstitutionalHoldings13FLoader.__new__(InstitutionalHoldings13FLoader)


def test_discover_picks_the_dataset_with_latest_end_date(monkeypatch) -> None:
    loader = _make_loader()

    class _FakeResponse:
        def read(self):
            return LISTING_HTML.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse())

    result = loader._discover_latest_13f_bulk_dataset()

    assert result is not None
    url, period_end = result
    assert url == "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip"
    assert period_end.isoformat() == "2026-05-31"


def test_parses_real_infotable_columns_keyed_by_cusip(monkeypatch) -> None:
    """INFOTABLE.tsv has no ticker column - holdings must be keyed by CUSIP."""
    import io
    import zipfile

    tsv = (
        "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tFIGI\tVALUE\t"
        "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\tOTHERMANAGER\t"
        "VOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE\n"
        "0001-26-000001\t1\t3M CO\tCOM\t88579Y101\t\t7377\t48\tSH\t\tSOLE\t0\t0\t0\t48\n"
        "0001-26-000002\t2\t3M CO\tCOM\t88579Y101\t\t1000\t52\tSH\t\tSOLE\t0\t0\t0\t52\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("01mar2026-31may2026_form13f/INFOTABLE.tsv", tsv)
    zip_bytes = buf.getvalue()

    loader = _make_loader()

    class _FakeResponse:
        def read(self):
            return zip_bytes

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=120: _FakeResponse())

    holdings = loader._fetch_and_parse_13f_bulk("https://www.sec.gov/files/.../fake.zip")

    # Both rows share CUSIP 88579Y101 (same issuer, different manager filings) -
    # must sum, not overwrite, and must be keyed by CUSIP since there is no ticker.
    assert holdings == {"88579Y101": 100}
