#!/usr/bin/env python3
"""Analyst upgrade/downgrade ratings from yfinance's Ticker.upgrades_downgrades.

GOVERNANCE: no free official analyst-ratings feed exists (real-time analyst
upgrades/downgrades is proprietary, typically a paid feed like Refinitiv/FactSet -
SEC/EDGAR doesn't publish this). This is the same "unofficial but real, transparently
documented" tradeoff already used for put/call ratio
(loaders/market_health_fetchers.py::PutCallRatioFetcher) rather than a departure from
this codebase's "official sources only" default - it's used because nothing official
and free exists, not as a substitute for one that does.

Live-verified 2026-07-27 (user pointed out this yfinance endpoint exists and works -
a prior audit pass had wrongly concluded no usable free source existed at all):
yf.Ticker(symbol).upgrades_downgrades returns a real DataFrame indexed by GradeDate with
columns Firm/ToGrade/FromGrade/Action/priceTargetAction/currentPriceTarget/priorPriceTarget.
Action values observed live: 'up', 'down', 'main' (reiterate at same grade), 'init'
(initiate coverage), 'reit' (reiterate). 'up'/'down' map directly to what
algo/signals/advanced_filters.py::_analyst_score() already expects.

Uses the SHARED cross-ECS-task IP circuit breaker (utils/external/yfinance_circuit_breaker.py)
rather than a local per-process one, since a full-universe run hits this endpoint once per
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
    circuit_breaker = get_circuit_breaker()
    try:
        circuit_breaker.wait_or_raise()
    except YFinanceStillBannedError as e:
        raise RuntimeError(f"yfinance shared IP ban active: {e}") from e

    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.upgrades_downgrades
    except Exception as e:
        if _is_rate_limit_error(e):
            circuit_breaker.report_rate_limit_error()
        raise RuntimeError(f"yfinance upgrades_downgrades fetch failed for {symbol}: {e}") from e

    circuit_breaker.report_success()

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

        firm = row.get("Firm")
        if firm is None or (isinstance(firm, float) and firm != firm):  # NaN check w/o pandas import
            continue  # firm is part of the uniqueness key - a row without one can't be upserted safely
        firm_str = str(firm)[:100]

        action_raw = str(row.get("Action", "")).strip().lower()
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


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s[:50]


_RATE_LIMIT_KEYWORDS = ("429", "rate", "too many", "invalid crumb", "unauthorized")


def _is_rate_limit_error(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(keyword in error_str for keyword in _RATE_LIMIT_KEYWORDS)
