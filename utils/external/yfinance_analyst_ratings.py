#!/usr/bin/env python3
"""Analyst ratings/sentiment from yfinance - upgrades_downgrades and recommendations_summary.

GOVERNANCE: no free official analyst-ratings feed exists (real-time analyst
upgrades/downgrades and recommendation aggregates are proprietary, typically a paid feed
like Refinitiv/FactSet - SEC/EDGAR doesn't publish this). This is the same "unofficial but
real, transparently documented" tradeoff already used for put/call ratio
(loaders/market_health_fetchers.py::PutCallRatioFetcher) rather than a departure from this
codebase's "official sources only" default - it's used because nothing official and free
exists, not as a substitute for one that does.

Live-verified 2026-07-27 (user pointed out yf.Ticker.upgrades_downgrades exists and works -
a prior audit pass had wrongly concluded no usable free source existed at all for either
table this module feeds):
- yf.Ticker(symbol).upgrades_downgrades: real DataFrame indexed by GradeDate with columns
  Firm/ToGrade/FromGrade/Action/priceTargetAction/currentPriceTarget/priorPriceTarget.
  Action values observed live: 'up', 'down', 'main' (reiterate at same grade), 'init'
  (initiate coverage), 'reit' (reiterate). 'up'/'down' map directly to what
  algo/signals/advanced_filters.py::_analyst_score() already expects. Feeds
  analyst_upgrade_downgrade (loaders/load_analyst_upgrade_downgrade.py).
- yf.Ticker(symbol).recommendations_summary: real DataFrame, one row per lookback period
  ('0m'=current, '-1m', '-2m', '-3m') with strongBuy/buy/hold/sell/strongSell counts.
  yf.Ticker(symbol).analyst_price_targets: dict with current/high/low/mean/median target
  price. Together these are the same shape analyst_sentiment_analysis was designed for.
  Deliberately NOT using yfinance's `.info`/quoteSummary `recommendationKey` field here -
  that whole API surface was already removed from this codebase (see
  steering/DATA_LOADERS.md's "dead yfinance quoteSummary" fix) for being fragile/401-prone;
  recommendation_key below is derived from the real recommendations_summary counts instead.
  Feeds analyst_sentiment_analysis (loaders/load_analyst_sentiment_analysis.py).

Live-verified 2026-08-03: yf.Ticker(symbol).earnings_estimate is a real DataFrame indexed by
period ('0q'/'+1q'/'0y'/'+1y') with avg/low/high/yearAgoEps/numberOfAnalysts/growth columns -
same non-`.info` API family as upgrades_downgrades/recommendations_summary above. The '+1y'
row's 'avg' column is the consensus next-fiscal-year EPS estimate, which SEC filings never
carry (forward-looking estimates are inherently third-party). Feeds
analyst_earnings_estimates (loaders/load_analyst_earnings_estimates.py), consumed by
load_value_quality_growth_metrics.py to compute value_metrics.forward_pe.

Uses the SHARED cross-ECS-task IP circuit breaker (utils/external/yfinance_circuit_breaker.py)
rather than a local per-process one, since a full-universe run hits these endpoints once per
symbol (thousands of calls/run) - the same class of shared-IP-ban risk the OHLCV yfinance
fallback in utils/data/source_router.py already guards against, not the lighter single-SPY-call
case PutCallRatioFetcher was written for.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

from utils.external.yfinance_circuit_breaker import YFinanceStillBannedError, get_circuit_breaker

logger = logging.getLogger(__name__)

# Real Action values seen live map straight onto the existing up/down convention
# _analyst_score() already filters on (LOWER(action) IN ('up','upgrade') / ('down','downgrade')).
_VALID_ACTIONS = {"up", "down", "main", "init", "reit"}


def _fetch_with_circuit_breaker(symbol: str, attr: str, timeout_sec: float = 10.0) -> Any:
    """Fetch one yf.Ticker attribute under the shared cross-ECS-task circuit breaker.

    CRITICAL FIX (2026-08-06): Added per-request timeout to prevent earnings_calendar
    loader from timing out on large symbol universes. yfinance requests can hang
    indefinitely without explicit timeout.

    Args:
        symbol: Stock symbol to fetch
        attr: yfinance Ticker attribute name (e.g., 'earnings_dates')
        timeout_sec: Per-request timeout in seconds (default 10s)

    Raises:
        RuntimeError: on a real fetch failure (network, rate limit, parse error, timeout)
    """
    circuit_breaker = get_circuit_breaker()
    try:
        circuit_breaker.wait_or_raise()
    except YFinanceStillBannedError as e:
        raise RuntimeError(f"yfinance shared IP ban active: {e}") from e

    import yfinance as yf
    import socket

    # Set socket timeout for this request
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_sec)

    try:
        result = getattr(yf.Ticker(symbol), attr)
    except socket.timeout:
        raise RuntimeError(f"yfinance {attr} fetch timeout for {symbol} (>{timeout_sec}s)") from None
    except Exception as e:
        if _is_rate_limit_error(e):
            circuit_breaker.report_rate_limit_error()
        raise RuntimeError(f"yfinance {attr} fetch failed for {symbol}: {e}") from e
    finally:
        socket.setdefaulttimeout(old_timeout)

    circuit_breaker.report_success()
    return result


def fetch_analyst_actions(symbol: str, lookback_days: int = 730) -> list[dict[str, Any]] | None:
    """Fetch recent analyst rating actions for one symbol from yfinance.

    Returns:
        List of row dicts (symbol, action_date, firm, old_rating, new_rating, action,
        company_name) ready for analyst_upgrade_downgrade, or None if the symbol has no
        analyst coverage (not an error - most small/micro-caps genuinely have none).

    Raises:
        RuntimeError: on a real fetch failure (network, rate limit, parse error) - the
        caller is expected to record this as data_unavailable, not silently skip it,
        per this codebase's fail-explicit governance.
    """
    try:
        df = _fetch_with_circuit_breaker(symbol, "upgrades_downgrades")
    except RuntimeError as e:
        if _is_no_fundamentals_404(str(e)):
            return None
        raise

    if df is None or df.empty:
        return None

    cutoff = datetime.now(timezone.utc).date().toordinal() - lookback_days
    # (action_date, firm) -> row. GradeDate carries a real timestamp but analyst_upgrade_downgrade
    # only stores a DATE, and the same firm occasionally issues more than one action for the same
    # symbol on the same calendar date (e.g. a price-target-only update same day as a rating
    # change) - those collapse onto the same (symbol, action_date, firm) uniqueness key. A single
    # INSERT batch can't upsert two rows that hit the same conflict target (Postgres raises
    # CardinalityViolation), so dedupe here, keeping the row with the latest real timestamp.
    by_key: dict[tuple[date, str], tuple[Any, dict[str, Any]]] = {}
    for grade_date, row in df.iterrows():
        try:
            action_date: date = grade_date.date() if hasattr(grade_date, "date") else grade_date
        except (AttributeError, ValueError):
            continue
        if action_date.toordinal() < cutoff:
            continue

        firm = row.get("Firm") if "Firm" in row else None
        if firm is None or (isinstance(firm, float) and firm != firm):  # NaN check w/o pandas import
            continue  # firm is part of the uniqueness key - a row without one can't be upserted safely
        firm_str = str(firm)[:100]

        action_raw = str(row.get("Action") if "Action" in row else "").strip().lower()
        action = action_raw if action_raw in _VALID_ACTIONS else None

        key = (action_date, firm_str)
        existing = by_key.get(key)
        if existing is not None and existing[0] >= grade_date:
            continue  # already have a same-or-later timestamp for this (date, firm)

        by_key[key] = (
            grade_date,
            {
                "symbol": symbol,
                "action_date": action_date,
                "firm": firm_str,
                "old_rating": _clean_str(row.get("FromGrade")),
                "new_rating": _clean_str(row.get("ToGrade")),
                "action": action,
            },
        )

    rows = [v[1] for v in by_key.values()]
    return rows or None


def fetch_analyst_sentiment(symbol: str) -> dict[str, Any] | None:
    """Fetch a current analyst-recommendation summary for one symbol from yfinance.

    Combines recommendations_summary (strongBuy/buy/hold/sell/strongSell counts for the
    current period) with analyst_price_targets (current/mean target price) into the shape
    analyst_sentiment_analysis expects.

    Returns:
        Row dict (symbol, analyst_count, bullish_count, bearish_count, neutral_count,
        target_price, current_price, upside_downside_percent) or None if the symbol has no
        analyst coverage (not an error - most small/micro-caps genuinely have none).

    Raises:
        RuntimeError: on a real fetch failure - see _fetch_with_circuit_breaker.
    """
    try:
        summary = _fetch_with_circuit_breaker(symbol, "recommendations_summary")
    except RuntimeError as e:
        if _is_no_fundamentals_404(str(e)):
            return None
        raise
    if summary is None or summary.empty or "period" not in summary.columns:
        return None

    current = summary[summary["period"] == "0m"]
    if current.empty:
        return None
    row = current.iloc[0]

    def _count(col: str) -> int:
        val = row.get(col)
        try:
            return int(val) if val is not None and val == val else 0  # NaN check
        except (TypeError, ValueError):
            return 0

    strong_buy, buy, hold, sell, strong_sell = (
        _count("strongBuy"),
        _count("buy"),
        _count("hold"),
        _count("sell"),
        _count("strongSell"),
    )
    bullish_count = strong_buy + buy
    bearish_count = strong_sell + sell
    neutral_count = hold
    analyst_count = bullish_count + bearish_count + neutral_count
    if analyst_count == 0:
        return None

    targets = _fetch_with_circuit_breaker(symbol, "analyst_price_targets") or {}
    target_price = targets.get("mean")
    current_price = targets.get("current")
    upside_downside_percent = None
    if target_price is not None and current_price:
        upside_downside_percent = round((float(target_price) - float(current_price)) / float(current_price) * 100, 2)

    return {
        "symbol": symbol,
        "analyst_count": analyst_count,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "target_price": target_price,
        "current_price": current_price,
        "upside_downside_percent": upside_downside_percent,
    }


def fetch_forward_eps(symbol: str) -> float | None:
    """Fetch the next-fiscal-year consensus EPS estimate for one symbol from yfinance.

    Uses Ticker.earnings_estimate (period '+1y' row, 'avg' column) - a real DataFrame of
    consensus analyst EPS estimates by period (0q/+1q/0y/+1y), NOT the deprecated `.info`/
    quoteSummary surface (see this module's docstring). Feeds value_metrics.forward_pe =
    current_price / forward_eps, since SEC filings never carry forward-looking estimates
    (analyst_estimates_not_in_sec_filings - see load_value_quality_growth_metrics.py).

    Returns:
        Consensus next-FY EPS estimate, or None if the symbol has no analyst coverage
        (not an error - most small/micro-caps genuinely have none).

    Raises:
        RuntimeError: on a real fetch failure - see _fetch_with_circuit_breaker.
    """
    try:
        df = _fetch_with_circuit_breaker(symbol, "earnings_estimate")
    except RuntimeError as e:
        if _is_no_fundamentals_404(str(e)):
            return None
        raise
    if df is None or df.empty or "avg" not in df.columns:
        return None

    if "+1y" not in df.index:
        return None
    val = df.loc["+1y", "avg"]
    try:
        val = float(val)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN check w/o pandas import
        return None
    return val


def fetch_earnings_calendar(symbol: str, timeout_sec: float = 10.0) -> list[dict[str, Any]] | None:
    """Fetch recent-past and upcoming earnings dates for one symbol from yfinance.

    Uses Ticker.earnings_dates (real DataFrame indexed by earnings timestamp, columns
    'EPS Estimate'/'Reported EPS'/'Surprise(%)', ~12 past + 1 upcoming row by default) -
    same non-`.info` API family as upgrades_downgrades/recommendations_summary/
    earnings_estimate above. Feeds earnings_calendar, consumed by
    algo/risk/earnings_blackout.py to gate entries around real earnings announcements -
    see loaders/load_earnings_calendar.py's module docstring for why this table needed a
    live writer restored.

    Args:
        symbol: Stock symbol
        timeout_sec: Per-request timeout in seconds (default 10s)

    Returns:
        List of row dicts (symbol, earnings_date, eps_estimate, actual_eps, surprise_pct),
        or None if the symbol has no earnings-date coverage (not an error - some
        OTC/delisted/pre-IPO symbols genuinely have none).

    Raises:
        RuntimeError: on a real fetch failure (including timeout) - see _fetch_with_circuit_breaker.
    """
    try:
        df = _fetch_with_circuit_breaker(symbol, "earnings_dates", timeout_sec=timeout_sec)
    except RuntimeError as e:
        if _is_no_fundamentals_404(str(e)):
            return None
        raise
    if df is None or df.empty:
        return None

    def _num(row: Any, col: str) -> float | None:
        val = row.get(col)
        try:
            val = float(val)
        except (TypeError, ValueError):
            return None
        return None if val != val else val  # NaN check

    rows: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        try:
            earnings_date = ts.date() if hasattr(ts, "date") else ts
        except (AttributeError, ValueError):
            continue

        rows.append(
            {
                "symbol": symbol,
                "earnings_date": earnings_date,
                "eps_estimate": _num(row, "EPS Estimate"),
                "actual_eps": _num(row, "Reported EPS"),
                "surprise_pct": _num(row, "Surprise(%)"),
            }
        )

    return rows or None


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s[:50]


_RATE_LIMIT_KEYWORDS = ("429", "rate", "too many", "invalid crumb", "unauthorized")
_NO_FUNDAMENTALS_KEYWORDS = ("404", "no fundamentals data", "not found")


def _is_rate_limit_error(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(keyword in error_str for keyword in _RATE_LIMIT_KEYWORDS)


def _is_no_fundamentals_404(error_str: str) -> bool:
    """Check if error is a yfinance 404 for no fundamentals data (legitimate no-coverage case)."""
    error_lower = error_str.lower()
    return any(keyword in error_lower for keyword in _NO_FUNDAMENTALS_KEYWORDS)
