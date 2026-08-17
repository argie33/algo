#!/usr/bin/env python3
"""Regression tests for the cross-loader SEC EDGAR disk cache.

get_company_facts()/get_submissions() are each called independently by several
separate loader subprocesses for the same CIK on the same day (financial_statements,
company_info_sec, segment_info, dividend_data for companyfacts; company_info_sec,
segment_info, current_reports_8k, earnings_calendar_sec for submissions) - see
utils/external/sec_edgar_client.py's "CROSS-LOADER DISK CACHE" comment. These tests
verify the shared per-CIK disk cache actually eliminates the redundant HTTP fetch
across separate SecEdgarClient instances (standing in for separate processes), respects
its TTL, and never persists a negative (404) result.
"""

import time
from pathlib import Path
from typing import Any

import pytest

from utils.external import sec_edgar_client as sec_edgar_client_module
from utils.external.sec_edgar_client import SecEdgarClient


@pytest.fixture(autouse=True)
def _isolated_disk_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the module's disk cache at a throwaway directory per test."""
    monkeypatch.setattr(sec_edgar_client_module, "_DISK_CACHE_DIR", tmp_path / "sec-edgar-cache")


def _client() -> SecEdgarClient:
    return SecEdgarClient(user_agent="test test@example.com", companyfacts_cache_size=4)


def test_get_company_facts_reuses_disk_cache_across_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_calls: list[str] = []

    def fake_get_json(self: SecEdgarClient, url: str) -> dict[str, Any]:
        fetch_calls.append(url)
        return {"cik": 320193, "entityName": "Apple Inc."}

    monkeypatch.setattr(SecEdgarClient, "_get_json", fake_get_json)

    first = _client()
    result1 = first.get_company_facts("320193")
    assert result1["entityName"] == "Apple Inc."
    assert len(fetch_calls) == 1

    # A brand-new client (standing in for a separate loader subprocess) has an empty
    # in-process LRU, so this must come from the shared disk cache, not a new HTTP call.
    second = _client()
    result2 = second.get_company_facts("320193")
    assert result2["entityName"] == "Apple Inc."
    assert len(fetch_calls) == 1


def test_get_submissions_reuses_disk_cache_across_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_calls: list[str] = []

    def fake_get_json(self: SecEdgarClient, url: str) -> dict[str, Any]:
        fetch_calls.append(url)
        return {"name": "Apple Inc.", "filings": {"recent": {}}}

    monkeypatch.setattr(SecEdgarClient, "_get_json", fake_get_json)

    first = _client()
    first.get_submissions("320193")
    assert len(fetch_calls) == 1

    second = _client()
    second.get_submissions("320193")
    assert len(fetch_calls) == 1


def test_disk_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_calls: list[str] = []

    def fake_get_json(self: SecEdgarClient, url: str) -> dict[str, Any]:
        fetch_calls.append(url)
        return {"cik": 320193, "call": len(fetch_calls)}

    monkeypatch.setattr(SecEdgarClient, "_get_json", fake_get_json)
    monkeypatch.setattr(sec_edgar_client_module, "_DISK_CACHE_TTL_SECONDS", 1.0)

    first = _client()
    first.get_company_facts("320193")
    assert len(fetch_calls) == 1

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 2.0)

    second = _client()
    second.get_company_facts("320193")
    assert len(fetch_calls) == 2


def test_404_is_not_persisted_to_disk_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_calls: list[str] = []

    def fake_get_json(self: SecEdgarClient, url: str) -> dict[str, Any]:
        fetch_calls.append(url)
        raise FileNotFoundError(f"SEC filing not found: {url}")

    monkeypatch.setattr(SecEdgarClient, "_get_json", fake_get_json)

    first = _client()
    with pytest.raises(FileNotFoundError):
        first.get_company_facts("999999")
    assert len(fetch_calls) == 1

    # A fresh client (empty in-process negative cache) must hit the network again -
    # a permanently-cached 404 on disk would incorrectly block a symbol that later
    # gets a real CIK assigned (new listing, spinoff).
    second = _client()
    with pytest.raises(FileNotFoundError):
        second.get_company_facts("999999")
    assert len(fetch_calls) == 2
