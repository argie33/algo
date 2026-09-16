#!/usr/bin/env python3
"""XBRL US API client - OAuth2 (password grant + refresh) wrapper around api.xbrl.us.

Added 2026-09-15 (/goal "get our XBRL data handling all right" session - the user obtained a
real XBRL US API account/client credentials for this). XBRL US's Public Filings Database is
built from the same underlying SEC EDGAR filings our own extraction pipeline reads, but through
completely independent parsing/tagging code, maintained by the org that runs the DQC
(Data Quality Committee) rule set already wired into scripts/xbrl_dqc_arelle_check.py - a
genuinely different second opinion, same "independent re-parse of the same filing" role
utils/external/yfinance_financials.py already plays for scripts/xbrl_yfinance_crosscheck.py,
but XBRL US additionally exposes real dimensional (axis/member) context per fact, which
SEC's own companyfacts API flattens away (see scripts/xbrl_segment_sum_reconciliation.py's own
module docstring for why that flattening blocked a segment-sum check until the separate
Financial Statement and Notes Data Sets bulk download was used instead - this client is a
second, live-query-based way to get that same dimensional context for a single symbol/concept
without downloading the whole monthly bulk dataset).

AUTH: OAuth2 password grant (POST https://api.xbrl.us/oauth2/token, form-encoded
grant_type=password + client_id + client_secret + username + password) yields an
access_token (JWT, ~1h) and a refresh_token. This client persists the refresh_token to a
local cache file (not `%TEMP%/algo-sec-edgar-cache/` - a different cache root, since this is
a credential rather than fetched content) so a restart doesn't require the username/password
again until the refresh_token itself expires, at which point the password grant runs again
automatically. Never logs the raw client_secret, password, or token values themselves - only
their presence and expiry.

Requires XBRL_US_CLIENT_ID/XBRL_US_CLIENT_SECRET/XBRL_US_USERNAME/XBRL_US_PASSWORD in
.env.local (local dev) - see that file's own comment. Raises RuntimeError (not a silent
disabled-feature return) if credentials are missing, matching TIINGO_API_KEY's existing
fail-loud pattern (scripts/tiingo_delisted_price_backfill.py) - callers that want this to be
optional (e.g. a periodic cross-check script, same posture as the yfinance crosscheck) should
catch that RuntimeError themselves and skip the run, not have this client swallow it.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.xbrl.us"
_TOKEN_URL = f"{_BASE_URL}/oauth2/token"
_TOKEN_CACHE_PATH = Path(os.getenv("TEMP", "/tmp")) / "algo-xbrl-us-cache" / "token.json"
_REQUEST_TIMEOUT_SECONDS = 30
_TOKEN_REFRESH_SAFETY_MARGIN_SECONDS = 60


class XbrlUsAuthError(RuntimeError):
    """Raised when the OAuth2 grant itself fails (bad credentials, expired refresh_token)."""


def _load_credentials() -> dict[str, str]:
    """client_id/client_secret are required for every grant type. username/password are only
    ever sent on a password grant (see _get_access_token) - required here regardless so a
    refresh-token-only environment fails loudly up front instead of only once the cached
    refresh_token eventually expires."""
    creds = {
        "client_id": os.getenv("XBRL_US_CLIENT_ID", ""),
        "client_secret": os.getenv("XBRL_US_CLIENT_SECRET", ""),
        "username": os.getenv("XBRL_US_USERNAME", ""),
        "password": os.getenv("XBRL_US_PASSWORD", ""),
    }
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise RuntimeError(
            f"XBRL US credentials missing from environment: {missing} - expected in .env.local "
            "for local dev use (XBRL_US_CLIENT_ID/XBRL_US_CLIENT_SECRET/XBRL_US_USERNAME/"
            "XBRL_US_PASSWORD)."
        )
    return creds


def _load_client_credentials() -> dict[str, str]:
    """client_id/client_secret only - used for a refresh_token grant, which needs neither
    username nor password (see _get_access_token's refresh path)."""
    creds = {
        "client_id": os.getenv("XBRL_US_CLIENT_ID", ""),
        "client_secret": os.getenv("XBRL_US_CLIENT_SECRET", ""),
    }
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise RuntimeError(
            f"XBRL US credentials missing from environment: {missing} - expected in .env.local "
            "for local dev use (XBRL_US_CLIENT_ID/XBRL_US_CLIENT_SECRET)."
        )
    return creds


def _read_token_cache() -> dict[str, Any] | None:
    try:
        cached: dict[str, Any] = json.loads(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        return cached
    except (OSError, json.JSONDecodeError):
        return None


def _write_token_cache(payload: dict[str, Any]) -> None:
    _TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _request_token(grant_type: str, **extra: str) -> dict[str, Any]:
    creds = _load_client_credentials()
    form = {
        "grant_type": grant_type,
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "platform": "algo-trading-data-quality",
        **extra,
    }
    response = requests.post(_TOKEN_URL, data=form, timeout=_REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise XbrlUsAuthError(f"XBRL US {grant_type} grant failed: HTTP {response.status_code} - {response.text[:300]}")
    payload: dict[str, Any] = response.json()
    payload["_obtained_at"] = time.time()
    return payload


def _get_access_token() -> str:
    """Returns a valid access_token, refreshing or re-authenticating as needed. Never returns
    an expired token - callers don't need their own expiry logic."""
    cached = _read_token_cache()
    if cached is not None:
        expires_at = cached["_obtained_at"] + cached.get("expires_in", 0) - _TOKEN_REFRESH_SAFETY_MARGIN_SECONDS
        if time.time() < expires_at:
            return str(cached["access_token"])

        refresh_expires_at = (
            cached["_obtained_at"] + cached.get("refresh_token_expires_in", 0) - _TOKEN_REFRESH_SAFETY_MARGIN_SECONDS
        )
        if time.time() < refresh_expires_at:
            try:
                payload = _request_token("refresh_token", refresh_token=cached["refresh_token"])
                _write_token_cache(payload)
                logger.info("[XBRL_US] Access token refreshed via cached refresh_token.")
                return str(payload["access_token"])
            except XbrlUsAuthError as e:
                logger.warning(f"[XBRL_US] Cached refresh_token rejected, falling back to password grant: {e}")

    creds = _load_credentials()
    payload = _request_token("password", username=creds["username"], password=creds["password"])
    _write_token_cache(payload)
    logger.info("[XBRL_US] Obtained new access token via password grant.")
    return str(payload["access_token"])


def xbrl_us_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET against api.xbrl.us with a valid bearer token, one transparent retry on a single
    401 (covers the race where the cached token expires between _get_access_token() returning
    it and the request actually landing)."""
    token = _get_access_token()
    url = f"{_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT_SECONDS)
    if response.status_code == 401:
        try:
            _TOKEN_CACHE_PATH.unlink()
        except OSError:
            pass
        token = _get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers, params=params, timeout=_REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise RuntimeError(f"XBRL US API error: GET {path} -> HTTP {response.status_code} - {response.text[:300]}")
    result: dict[str, Any] = response.json()
    return result


def _resolve_cik(entity_ticker: str) -> str:
    """XBRL US's fact/search has no entity.ticker filter (live-confirmed 2026-09-15 -
    ParameterNotFound) - entity.code is the SEC CIK, and must be the same zero-padded
    10-digit form our own ticker cache already returns (live-confirmed: the unpadded form
    is rejected outright with "not a valid cik or cid or lei or grip"), so we resolve through
    the same ticker cache the rest of the codebase already uses rather than adding a second
    ticker->CIK mapping."""
    from utils.external.sec_ticker_cache import TickerCache

    cache = TickerCache()
    return cache.symbol_to_cik(entity_ticker)


def fact_search(
    entity_ticker: str,
    concept_local_name: str,
    fiscal_year: int,
    fiscal_period: str = "Y",
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search XBRL US's fact database for one concept/entity/period. `fiscal_period` is XBRL
    US's own vocabulary: "Y" (annual), "Q1".."Q4" (quarterly). Restricted to non-dimensional,
    "ultimus" (latest-restated-value-for-this-period) facts by default - the same "most recent
    filing wins for this period" semantics our own loaders already apply, not the full
    dimensional fact history (use `dimensions.count=0` explicitly if a caller needs to widen
    this later for a dimensional/segment query instead).

    `unit.unit-of-measure` is always requested (ADDED 2026-09-16, SKM live-confirmed): a
    foreign private issuer files in its home-market currency (SK Telecom/SKM reports in KRW),
    and this endpoint returns the raw filed value with no USD conversion - a caller comparing
    the returned value directly against a USD figure without checking this field will see an
    apparent ~1370x (or whatever the FX rate is) divergence that is a units mismatch, not a
    data or extraction bug. See scripts/xbrl_us_crosscheck.py's own USD-only filter, which
    consumes this field.
    """
    default_fields = [
        "fact.value",
        "fact.decimals",
        "fact.ultimus",
        "unit.unit-of-measure",
        "period.fiscal-year",
        "period.fiscal-period",
        "report.filing-date",
        "report.accession",
        "entity.code",
    ]
    params = {
        "entity.code": _resolve_cik(entity_ticker),
        "concept.local-name": concept_local_name,
        "period.fiscal-year": fiscal_year,
        "period.fiscal-period": fiscal_period,
        "fact.ultimus": "true",
        "dimensions.count": 0,
        "fields": ",".join(fields or default_fields),
    }
    payload = xbrl_us_get("/api/v1/fact/search", params=params)
    facts: list[dict[str, Any]] = payload.get("data", [])
    return facts
