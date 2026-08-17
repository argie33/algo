#!/usr/bin/env python3
"""Regression tests: SEC EDGAR archive URL construction.

get_filing_plaintext() and get_filing_xml() previously built URLs as
/Archives/edgar/{zero_padded_cik}/{accession}/{file} - missing the required
"data/" path segment and using the zero-padded CIK. Every real SEC filing 404s
against that URL; the correct form is
/Archives/edgar/data/{cik_no_leading_zeros}/{accession_nodash}/{file}.
Confirmed live against a real Microsoft 10-K/8-K before fixing (see
loading-situation memory) - this silently broke 8-K item classification and
segment-revenue XBRL extraction for these loaders' entire lifetime, despite the
filing list itself (get_submissions) working fine and masking the failure.
"""

import pytest

from utils.external.sec_edgar_client import SecEdgarClient

CIK_PADDED = "0000789019"
CIK_UNPADDED = "789019"


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        pass


def _client() -> SecEdgarClient:
    return SecEdgarClient(user_agent="test test@example.com")


def test_get_filing_plaintext_uses_data_segment_and_unpadded_cik(monkeypatch) -> None:
    client = _client()
    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append(url)
        return _FakeResponse(200, "filing text")

    monkeypatch.setattr(client._session, "get", fake_get)

    result = client.get_filing_plaintext(CIK_PADDED, "0001193125-26-258667")

    assert result == "filing text"
    assert len(requested_urls) == 1
    assert requested_urls[0] == (
        "https://www.sec.gov/Archives/edgar/data/789019/000119312526258667/0001193125-26-258667.txt"
    )


def test_get_filing_xml_prefers_standalone_instance_document(monkeypatch) -> None:
    client = _client()
    requested_urls = []

    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000950170-25-100235"],
                "primaryDocument": ["msft-20250630.htm"],
            }
        }
    }
    monkeypatch.setattr(client, "get_submissions", lambda cik: submissions)

    def fake_get(url, timeout):
        requested_urls.append(url)
        return _FakeResponse(200, "<xbrl></xbrl>")

    monkeypatch.setattr(client._session, "get", fake_get)

    result = client.get_filing_xml(CIK_PADDED, "0000950170-25-100235", "10-K")

    assert result == "<xbrl></xbrl>"
    assert requested_urls == ["https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630_htm.xml"]


def test_get_filing_xml_falls_back_to_primary_document_when_instance_missing(monkeypatch) -> None:
    client = _client()
    requested_urls = []

    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001193125-24-000001"],
                "primaryDocument": ["oldfiler.xml"],
            }
        }
    }
    monkeypatch.setattr(client, "get_submissions", lambda cik: submissions)

    def fake_get(url, timeout):
        requested_urls.append(url)
        if url.endswith("oldfiler_xml.xml"):
            return _FakeResponse(404, "")
        return _FakeResponse(200, "<xbrl>raw</xbrl>")

    monkeypatch.setattr(client._session, "get", fake_get)

    result = client.get_filing_xml(CIK_PADDED, "0001193125-24-000001", "10-K")

    assert result == "<xbrl>raw</xbrl>"
    # Tried the derived "_htm.xml" instance name first, then fell back to primaryDocument.
    assert requested_urls == [
        "https://www.sec.gov/Archives/edgar/data/789019/000119312524000001/oldfiler_xml.xml",
        "https://www.sec.gov/Archives/edgar/data/789019/000119312524000001/oldfiler.xml",
    ]


def test_get_filing_xml_never_falls_back_to_inline_xbrl_html(monkeypatch) -> None:
    """ROOT-CAUSE FIX 2026-08-16: for a modern inline-XBRL filer, primaryDocument is an
    .htm file. When the derived "_htm.xml" standalone instance document 404s, this must
    raise FileNotFoundError - not silently fetch and return the primaryDocument .htm
    itself as if it were XML. Live-confirmed as the root cause of sec_segment_info's
    repeated per-symbol MemoryError / eventual hard process death: multi-MB inline-XBRL
    HTML documents blew up ET.fromstring()'s memory use when this fallback fired.
    """
    client = _client()
    requested_urls = []

    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000950170-25-100235"],
                "primaryDocument": ["msft-20250630.htm"],
            }
        }
    }
    monkeypatch.setattr(client, "get_submissions", lambda cik: submissions)

    def fake_get(url, timeout):
        requested_urls.append(url)
        return _FakeResponse(404, "")

    monkeypatch.setattr(client._session, "get", fake_get)

    with pytest.raises(FileNotFoundError):
        client.get_filing_xml(CIK_PADDED, "0000950170-25-100235", "10-K")

    # Only the derived instance-document candidate was ever tried - the .htm
    # primaryDocument itself must never be requested as if it were XML.
    assert requested_urls == ["https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630_htm.xml"]
