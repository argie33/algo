#!/usr/bin/env python3
"""Shared real-time quote fetching from the Alpaca Data API.

Extracted from exit_engine.py's ExitEngine._fetch_alpaca_quote (2026-08-03) so that
other real-money decision paths - not just stop/target exit evaluation - can use a
live intraday price instead of price_daily, which is written once near market open
and never refreshed intraday (confirmed live: KARO/NBIX price_daily rows for
2026-08-03 both have created_at == updated_at == 08:32, all day). position_monitor.py's
health-flag EARLY_EXIT path (RS_WEAKENING/SECTOR_WEAK/GIVING_BACK_GAINS/etc.) was
computing current_price, unrealized P&L, and r_multiple from that stale snapshot -
live-reproduced same-day: a position entered at 11:57 and health-flag-exited at 12:01
recorded exit_price identically equal to entry_price (both drawn from the same
un-refreshed price_daily row), fabricating a $0.00 P&L for what should have been a
priced market exit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from algo.config.api_endpoints import get_alpaca_data_url
from algo.config.credential_manager import get_alpaca_credentials
from algo.infrastructure import get_alpaca_timeout
from algo.infrastructure.market_calendar import MarketCalendar
from algo.trading.exceptions import ExchangeAPIError

logger = logging.getLogger(__name__)

# STALENESS GUARD (added 2026-09-01, real-money-readiness pass): the free-tier IEX feed
# this function uses can fail by silently freezing rather than erroring - it keeps
# returning HTTP 200 with the LAST quote it ever received, indistinguishable from a
# genuinely fresh quote to every check above (bid/ask present and >0). That's a distinct
# failure mode from the one this module's own docstring documents fixing (price_daily not
# being refreshed intraday at all) - this guards the live source itself going stale while
# still returning 200s. 5 minutes is generous versus a healthy feed (IEX order-book-driven
# quotes refresh far faster than that even for thin names, since NBBO reflects the resting
# book, not just print events) but tight enough to catch a feed that has actually stopped
# updating, which this callers' real-time exit/stop evaluation must not silently trust.
_MAX_QUOTE_AGE_SECONDS = 300

# SPREAD SANITY GUARD (real-money-readiness audit, found 2026-09-06): the bid/ask
# midpoint below was computed whenever both sides were present and positive, with no
# check on how far apart they actually are. A wildly wide spread - a thin/halted/broken
# quote (e.g. bid=$1, ask=$100) - passes that check silently and produces a garbage
# midpoint that this function's own docstring says feeds directly into real-time
# exit/stop evaluation (position_monitor.py's health-flag exits, exit_engine.py's
# stop/target checks). A midpoint computed from a non-tradable spread could trigger (or
# suppress) a real stop-loss/target exit on a price nobody could actually transact at.
# 10% relative spread is already very wide for a liquid equity (typical spreads are
# pennies/basis points) - conservative enough to only reject genuinely broken/illiquid
# quotes, not flag normal intraday noise.
_MAX_RELATIVE_SPREAD = 0.10


def _check_quote_freshness(symbol: str, quote: dict[str, object], log_prefix: str) -> None:
    """Raises RuntimeError if quote's own timestamp shows it's stale while the market is
    open. A missing or unparseable timestamp is logged and treated as no freshness signal
    (fail-open on the check itself, not on the underlying quote) rather than blocking an
    otherwise-valid price over a formatting quirk."""
    if not MarketCalendar.is_market_open():
        return
    quote_ts_raw = quote.get("t")
    if not quote_ts_raw:
        return
    assert isinstance(quote_ts_raw, str)
    try:
        ts_str = quote_ts_raw[:-1] + "+00:00" if quote_ts_raw.endswith("Z") else quote_ts_raw
        quote_dt = datetime.fromisoformat(ts_str)
        if quote_dt.tzinfo is None:
            quote_dt = quote_dt.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - quote_dt).total_seconds()
    except (ValueError, TypeError) as e:
        logger.warning(
            f"[{log_prefix}] {symbol}: could not parse quote timestamp {quote_ts_raw!r}: {e} - "
            f"proceeding without a freshness check for this quote."
        )
        return
    if age_seconds > _MAX_QUOTE_AGE_SECONDS:
        raise RuntimeError(
            f"Alpaca quote for {symbol} is {age_seconds:.0f}s stale (timestamp "
            f"{quote_ts_raw}) while market is open - feed has likely frozen, not "
            f"just a normal reporting gap. Refusing to feed a stale price into a "
            f"real-time exit/stop decision."
        )


def fetch_live_quote(
    symbol: str, execution_mode: str, log_prefix: str = "QUOTE_FETCHER"
) -> float | dict[str, str | bool]:
    """Fetch real-time quote from Alpaca Data API.

    Returns:
        float: Valid price from Alpaca
        dict: {"data_unavailable": True, "reason": "..."} if paper mode sandbox 404/401

    Raises on API failure or missing credentials. Raises on critical API errors in live
    ("auto") mode - callers in auto mode must not silently fall back to stale database
    prices, since the broker is the source of truth for live positions.

    When API returns status 200 but no valid price data:
    - Market open: Raises RuntimeError (API is broken, got 200 but no quote)
    - Market closed: Raises RuntimeError (caller must check market hours)
    """
    try:
        creds = get_alpaca_credentials()
        key = creds.get("key")
        secret = creds.get("secret")
        if not key or not secret:
            raise RuntimeError(f"CRITICAL: Alpaca credentials missing. Cannot fetch quote for {symbol}.")

        data_url = get_alpaca_data_url()

        # RETRY: a transient 429/503 must not raise immediately - this quote can feed
        # real-time exit/stop evaluation, and a retryable API blip shouldn't cost a
        # symbol its price check for the cycle.
        max_attempts = 3
        response = None
        for attempt in range(max_attempts):
            try:
                # /v2/stocks/quotes/latest with feed=iex: this account has no SIP
                # subscription (sip returns 403 even on the correct path); iex is the
                # free-tier feed and returns real quotes.
                response = requests.get(
                    f"{data_url}/v2/stocks/quotes/latest",
                    params={"symbols": symbol, "feed": "iex"},
                    headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                    timeout=get_alpaca_timeout(),
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[{log_prefix}] {symbol}: Alpaca quote API {type(e).__name__} - "
                        f"transient, retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                raise
            if response.status_code in (429, 503) and attempt < max_attempts - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"[{log_prefix}] {symbol}: Alpaca quote API {response.status_code} - "
                    f"transient, retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                )
                time.sleep(wait_time)
                continue
            break

        assert response is not None, "Response should be set after loop"
        if response.status_code == 200:
            data = response.json()

            if "quotes" not in data or not isinstance(data["quotes"], dict):
                raise RuntimeError(
                    f"Alpaca quote API returned 200 but missing 'quotes' key or invalid type. Response: {data}"
                )

            quotes = data["quotes"]
            if symbol not in quotes:
                raise RuntimeError(
                    f"Alpaca quote API returned 200 but no data for {symbol}. Available symbols: {list(quotes.keys())}"
                )

            quote = quotes[symbol]
            if not isinstance(quote, dict):
                raise RuntimeError(f"Alpaca quote API returned invalid data type for {symbol}: {type(quote)}")

            _check_quote_freshness(symbol, quote, log_prefix)

            bid = quote.get("bp")
            ask = quote.get("ap")
            last_price = quote.get("lp")
            if bid is not None and ask is not None and bid > 0 and ask > 0:
                bid_f, ask_f = float(bid), float(ask)
                mid = (bid_f + ask_f) / 2.0
                relative_spread = (ask_f - bid_f) / mid
                if relative_spread > _MAX_RELATIVE_SPREAD:
                    logger.warning(
                        f"[{log_prefix}] {symbol}: bid/ask spread {relative_spread:.1%} exceeds "
                        f"{_MAX_RELATIVE_SPREAD:.0%} sanity threshold (bid={bid_f}, ask={ask_f}) - "
                        f"midpoint is not a trustworthy price for a real-time exit/stop decision. "
                        f"Falling back to last trade price if available."
                    )
                else:
                    return mid

            if last_price is not None:
                return float(last_price)

            if MarketCalendar.is_market_open():
                raise RuntimeError(
                    f"Alpaca quote API returned status 200 but no valid price data for {symbol}. "
                    f"Market is open; this indicates an API issue, not market closure."
                )
            raise RuntimeError(
                f"[{log_prefix}] Cannot fetch intraday quote for {symbol}: market closed. "
                f"Caller must check market hours before requesting intraday data."
            )

        elif response.status_code == 401:
            if execution_mode == "auto":
                error_msg = (
                    f"[{log_prefix} CRITICAL] {symbol}: Alpaca authentication failed (401) in LIVE trading mode. "
                    f"Cannot fall back to database prices when broker is unreachable. "
                    f"Check: Alpaca API credentials are valid, APCA_API_BASE_URL is correct, network connectivity."
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg)
            logger.warning(
                f"[{log_prefix}] {symbol}: Alpaca quote API authentication failed (401) in {execution_mode} mode - "
                f"falling back to database prices"
            )
            return {"data_unavailable": True, "reason": "Alpaca 401 auth failed - using database fallback"}

        elif response.status_code == 404:
            if execution_mode in ("paper", "dry", "review"):
                logger.warning(
                    f"[{log_prefix}] {symbol}: Alpaca quote API returned 404 - "
                    f"symbol unavailable in {execution_mode} sandbox. Database fallback pricing will be used."
                )
                return {"data_unavailable": True, "reason": f"Alpaca 404 in {execution_mode} sandbox"}
            error_msg = (
                f"[{log_prefix} CRITICAL] {symbol}: Alpaca quote API returned 404 - "
                f"symbol unavailable in live broker system (delisted or removed). "
                f"Manual intervention required: check if symbol is delisted or account permissions changed."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        else:
            raise RuntimeError(f"Alpaca quote API error for {symbol}: status {response.status_code}")

    except requests.RequestException as e:
        raise ExchangeAPIError(f"Alpaca quote API error for {symbol}: {type(e).__name__}: {e}") from e
    except (RuntimeError, ValueError):
        raise
