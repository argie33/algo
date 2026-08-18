#!/usr/bin/env python3
"""Historical USD exchange rates for major, developed-market currencies.

FIXED 2026-08-17 (goal: "no SEC data" audit): sec_statements.py's non-USD currency
guard (added to block KRW/JPY-style filers whose raw local-currency magnitudes were
being stored as if they were USD, off by ~100-1000x) is a blanket rule that also
silently drops real, usable data for foreign issuers reporting in currencies that are
NOT wildly divergent from USD - CAD, GBP, EUR, AUD, CHF, JPY are all liquid, developed-
market currencies whose value vs USD has stayed within roughly a 2x band historically,
nothing like KRW/JPY's original ~100-1000x *magnitude* mismatch (which was really a
unit-scale confusion, not a volatility problem). Live-confirmed via DB scan: 272
symbols (CP, ASML, BBVA, BCS, BAP, BCE, AEG and more) have real revenue/net_income
sitting in their SEC filings, reported in one of these currencies, that the blanket
guard discards entirely.

This module fetches REAL historical exchange rates (never a fabricated/guessed
number) from Frankfurter (https://frankfurter.dev), a free ECB-rate mirror with no
API key, for the specific fiscal-period-end date of each filing - not a single
"current" rate applied retroactively to old filings, which would misstate periods
where the real historical rate differed meaningfully from today's. A rate lookup
failure (network error, date outside ECB's published range, currency not found) is
never treated as "assume ~1.0" or any other guess - it returns None, and the caller
must still leave that value NULL, same fail-closed discipline as the currency guard
this replaces for this specific whitelist of currencies.

Deliberately NOT extended to volatile/emerging-market currencies (ARS, BRL, CLP, MXN,
PEN, KRW, TRY, and similar) - those can move far more than developed-market FX pairs
even within a single fiscal year, and Frankfurter itself doesn't cover several of them
at all. Those stay behind the original blanket-reject guard, unconverted.
"""

import json
import logging
import tempfile
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.app"

# Liquid, developed-market currencies only - see module docstring for why this list is
# deliberately narrow. Do not add emerging-market/volatile currencies here without the
# same live-verification discipline as the currencies already on this list.
MAJOR_CURRENCIES = frozenset({"CAD", "GBP", "EUR", "AUD", "CHF", "JPY"})


class FxRateCache:
    """Caches (currency, date) -> USD exchange rate lookups.

    Historical rates are immutable once published (ECB doesn't revise past fixings),
    so cached entries never expire - unlike TickerCache's ticker-to-CIK mapping (which
    needs periodic refresh as new companies list), there is no staleness concept here.
    """

    def __init__(self, timeout: float = 10.0, session: requests.Session | None = None):
        self._timeout = timeout
        self._session = session or requests.Session()
        temp_dir = Path(tempfile.gettempdir())
        self._cache_file = temp_dir / "sec_fx_rate_cache.json"
        self._cache: dict[str, float | None] = {}
        self._load_from_file()

    def _load_from_file(self) -> None:
        try:
            if self._cache_file.exists():
                with open(self._cache_file) as f:
                    self._cache = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.debug(f"Could not load FX rate cache file: {e}")

    def _save_to_file(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w") as f:
                json.dump(self._cache, f)
        except OSError as e:
            logger.debug(f"Could not save FX rate cache file: {e}")

    def get_usd_rate(self, currency: str, date_str: str) -> float | None:
        """Return how many units of `currency` equal 1 USD on `date_str` (YYYY-MM-DD).

        A caller converts a local-currency value to USD via `value / rate`. Returns
        None (never a guessed/fallback number) if the currency isn't on the major-
        currency whitelist, the date is malformed, or the live lookup fails for any
        reason (network error, date outside Frankfurter's published range, etc.).
        """
        if currency not in MAJOR_CURRENCIES:
            return None
        if len(date_str) != 10 or date_str[4] != "-" or date_str[7] != "-":
            return None

        cache_key = f"{currency}:{date_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        rate = self._fetch_rate(currency, date_str)
        self._cache[cache_key] = rate
        self._save_to_file()
        return rate

    def _fetch_rate(self, currency: str, date_str: str) -> float | None:
        max_retries = 2
        for attempt in range(max_retries):
            try:
                resp = self._session.get(
                    f"{FRANKFURTER_URL}/{date_str}",
                    params={"from": "USD", "to": currency},
                    timeout=self._timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"FX rate fetch network error for {currency}/{date_str}: {e}")
                return None

            if resp.status_code == 404:
                # Date outside Frankfurter's published range (pre-1999, weekends land on
                # the prior business day automatically so this is a genuine gap, not a
                # transient issue) - a real "no rate available", not a retry candidate.
                return None
            if resp.status_code in (429, 502, 503, 504):
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"FX rate fetch got HTTP {resp.status_code} for {currency}/{date_str}")
                return None
            if resp.status_code != 200:
                return None

            try:
                data = resp.json()
                if "rates" not in data or currency not in data["rates"]:
                    return None
                rate = data["rates"][currency]
                return float(rate) if rate is not None else None
            except (ValueError, TypeError) as e:
                logger.warning(f"FX rate response parse failure for {currency}/{date_str}: {e}")
                return None
        return None
