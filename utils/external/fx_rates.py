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

FIXED 2026-08-18 (goal: "no SEC data"/loader-failure audit, follow-up to the currency-
poisoning cleanup that wiped ~428 corrupted rows for 15 KRW/CLP/COP-reporting foreign
filers): KRW moved here from the "deliberately not extended" list below. Frankfurter
does cover it (live-confirmed: `GET /2023-12-31?from=KRW&to=USD` returns a real rate,
unlike CLP/COP/TWD which 404), and it's a fully convertible, actively-traded currency
with no capital controls (South Korea is an OECD/G20 advanced economy) - not
meaningfully more volatile than JPY, already on this list, which moved ~35% (115->160)
over 2022-2024 vs KRW's ~25% move over the same window. Live-verified against 3 named
still-open symbols using each one's own real historical rate for its fact's period-end
date (never a guessed/current rate): KEP (Korea Electric Power) FY2024 revenue converts
to ~$71B, matching KEPCO's real public-reported revenue; KB (KB Financial Group) FY2023
~$12.5B and SHG (Shinhan Financial Group) FY2024 ~$50B both fall in the plausible range
for Korea's largest bank holding companies - none of the 100-1000x magnitude errors the
original blanket guard existed to catch.

FIXED 2026-08-20 (goal session: coverage root-cause audit): CNY added. Live-confirmed via
GDS (GDS Holdings, Chinese data-center operator, CIK 0001526125) - its entire us-gaap
revenue/net_income history (2016-2025) is tagged exclusively in CNY, none in USD, so the
blanket guard was dropping real data for every fiscal year going all the way back to its
2016 IPO. Frankfurter serves CNY (`GET /2025-12-31?from=USD&to=CNY` returns a real rate);
year-end CNY/USD moved at most ~7.9% year-over-year across 2018-2025 (managed-float regime,
narrower band than JPY's cited ~35% 2022-2024 swing or KRW's ~25%), so it clears the same
volatility bar KRW was added under. Converting GDS's real revenue history with each
fiscal year's own historical rate produces a smooth, monotonic $152M (FY2016) -> $1.63B
(FY2025) growth curve consistent with its known real business trajectory - no 10-100x
magnitude red flag. Before this fix, annual_income_statement rows for GDS (and any other
CNY-only filer) were marked data_unavailable/"incomplete_sec_filing_income" despite having
a complete, extractable filing - see
[[financial_statements_governance_flag_downgrade_bug_20260820]] in memory for a separate,
related bug this interacts with: rows written by a PRE-guard code version had stored the
raw, unconverted CNY figure directly (a silently ~7x-too-large "USD" value, preserved by
preserve_on_missing_fields and never overwritten because every fetch since has correctly
returned None for the un-whitelisted currency) - this fix's next real fetch produces a
genuine non-NULL converted value, which overwrites the stale wrong one normally (no COALESCE
blocking involved when the new value is real, only when it's NULL).

Deliberately NOT extended to other volatile/emerging-market currencies (ARS, BRL, CLP,
COP, MXN, PEN, TRY, TWD, VND and similar) - those can move far more than developed-
market FX pairs even within a single fiscal year, and Frankfurter itself doesn't cover
several of them at all (CLP, COP, TWD live-confirmed 404). Those stay behind the
original blanket-reject guard, unconverted. Do not add another currency to
MAJOR_CURRENCIES without the same live-verification discipline: (1) confirm Frankfurter
actually serves it, (2) sanity-check the converted USD figure against at least one real
filer's known public financials.

FIXED 2026-08-22 (goal session: "Stale fiscal data" coverage audit): ZAR added. Live-
confirmed via HMY (Harmony Gold Mining, a South African gold producer, CIK 0001023514) -
its entire ifrs-full revenue/net_income history from FY2019 onward is tagged exclusively
in ZAR (FY2016-2018 alone were USD-tagged), so the blanket guard silently dropped 7
straight fiscal years of real, current 20-F data (marked "incomplete_sec_filing_income")
despite the company continuing to file real annual reports every year. Frankfurter serves
ZAR (`GET /2025-06-30?from=USD&to=ZAR` returns a real rate); year-end ZAR/USD moved at
most ~8.6% year-over-year across 2019-2025 (2.6%-8.6% range, live-checked), comparable to
or narrower than CNY's ~7.9% bar above - clears the same volatility threshold. Converting
HMY's real FY2025 revenue (ZAR 73.896B) at its own fiscal-year-end rate produces ~$4.16B,
consistent with Harmony Gold's known real, growing revenue during 2024-2025's record gold
prices - no magnitude red flag. NOT the same case as MXN or CLP: MXN's real year-over-year
move was live-checked at up to 22.4% (2023->2024) - genuinely more volatile than CNY/ZAR's
band, so it stays excluded pending its own dedicated review; CLP still 404s on Frankfurter
entirely (BCH/Bank of Chile stays unconverted for a structural source-availability reason,
not a volatility judgment).

FIXED 2026-08-29 (goal session: "full data for scores" completeness pass, root-causing
`currency_conversion_bug_remediation_20260819` markers): INR added. Live-confirmed via IBN
(ICICI Bank Ltd, one of India's largest banks) - annual_income_statement had 3 straight
fiscal years of real revenue/net_income sitting as raw, unconverted INR (pre-guard rows,
same "stale raw local-currency value" shape as the CNY/GDS case above), plus the current
fiscal year blocked entirely by the blanket guard. Frankfurter serves INR (year-end rate
live-fetched for 2018-2025); year-over-year moves were 0.6%-5% in 6 of 8 years, with a
single 11.1% outlier (2021->2022, the year the Fed's rate-hike cycle broadly hit EM
currencies) - comparable to ZAR's 8.6% high-water mark and well inside JPY's ~35%/KRW's
~25% precedent ceiling. Converting IBN's raw revenue with each year's own year-end rate
produces a smooth $16.3B (FY2023) -> $18.8B (FY2024) -> $22.8B (FY2025) growth curve
consistent with ICICI Bank's known real, growing total income - no magnitude red flag.

Same pass live-checked BRL as a candidate (found via BAK/Braskem carrying the identical
raw-unconverted-value shape) and confirmed it does NOT clear the bar: year-over-year
moves included two years of ~28%-29% (2019->2020 COVID shock, 2023->2024), well past
MXN's already-declined 22.4% - stays excluded, same volatility judgment as MXN/CLP, not
a bug. KZT (the currency behind KSPI/Kaspi.kz's gap) was also checked and, like CLP/COP/
TWD, is not served by Frankfurter at all (`GET /2024-12-31?from=USD&to=KZT` 404s) - a
structural source-availability gap, not a volatility judgment.

FOLLOW-UP (2026-08-29, same session): confirmed KSPI's gap is fully explained by the
above, not a separate ifrs-full extraction bug as first suspected - live SEC companyfacts
JSON (CIK 0001985487) shows KSPI DOES tag both `ifrs-full:Revenue` and `ifrs-full:ProfitLoss`
every fiscal year, exclusively under unit="KZT", no USD-tagged alternative anywhere. The
guard is working exactly as designed (same as BSAC/CLP); this cannot be fixed without a
different historical-FX data source for KZT, which this module deliberately doesn't add
without live verification (see the top of this docstring).
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
MAJOR_CURRENCIES = frozenset({"CAD", "GBP", "EUR", "AUD", "CHF", "JPY", "KRW", "CNY", "ZAR", "INR"})


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
