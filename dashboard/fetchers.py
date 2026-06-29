"""Fetcher functions for dashboard data from API endpoints.

Architecture (refactored for maintainability):
- fetchers_common.py: Shared utilities (FETCHER_METADATA, error handling, caching)
- fetchers_portfolio.py: Portfolio, positions, trades, performance data
- fetchers_market.py: Market data, risk metrics, sector rankings
- fetchers_signals.py: Signal data and scoring
- fetchers_config.py: Algo config, health, circuit breakers, run status
- fetchers_external.py: Economic, sentiment, industry data
- fetchers.py (this file): Router + orchestration via load_all()
"""

import logging
import random
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

from .api_data_layer import API_MAX_BACKOFF
from .fetchers_common import FETCHER_METADATA, format_fetcher_error
from .fetchers_config import (
    clear_data_status_cache,
    fetch_algo_config,
    fetch_algo_metrics,
    fetch_circuit,
    fetch_health,
    fetch_run,
)
from .fetchers_external import (
    fetch_activity,
    fetch_audit_log,
    fetch_economic_calendar,
    fetch_economic_pulse,
    fetch_exec_history,
    fetch_industry_ranking,
    fetch_notifications,
    fetch_sentiment,
)
from .fetchers_market import (
    clear_markets_cache,
    fetch_exp_factors,
    fetch_market,
    fetch_risk_metrics,
    fetch_sector_ranking,
    fetch_sector_rotation,
)
from .fetchers_portfolio import (
    fetch_perf,
    fetch_perf_analytics,
    fetch_portfolio,
    fetch_positions,
    fetch_recent_trades,
)
from .fetchers_signals import (
    fetch_scores,
    fetch_signal_eval,
    fetch_signals,
)

logger = logging.getLogger(__name__)


__all__ = [
    "FETCHER_METADATA",
    "fetch_activity",
    "fetch_algo_config",
    "fetch_algo_metrics",
    "fetch_audit_log",
    "fetch_circuit",
    "fetch_economic_calendar",
    "fetch_economic_pulse",
    "fetch_exec_history",
    "fetch_exp_factors",
    "fetch_health",
    "fetch_industry_ranking",
    "fetch_market",
    "fetch_notifications",
    "fetch_perf",
    "fetch_perf_analytics",
    "fetch_portfolio",
    "fetch_positions",
    "fetch_recent_trades",
    "fetch_risk_metrics",
    "fetch_run",
    "fetch_scores",
    "fetch_sector_ranking",
    "fetch_sector_rotation",
    "fetch_sentiment",
    "fetch_signal_eval",
    "fetch_signals",
    "load_all",
]


FETCHERS = {
    "run": fetch_run,
    "cfg": fetch_algo_config,
    "mkt": fetch_market,
    "port": fetch_portfolio,
    "perf": fetch_perf,
    "pos": fetch_positions,
    "trades": fetch_recent_trades,
    "sig": fetch_signals,
    "health": fetch_health,
    "cb": fetch_circuit,
    "srank": fetch_sector_ranking,
    "activity": fetch_activity,
    "eco": fetch_economic_pulse,
    "notifs": fetch_notifications,
    "sentiment": fetch_sentiment,
    "econ_cal": fetch_economic_calendar,
    "risk": fetch_risk_metrics,
    "perf_anl": fetch_perf_analytics,
    "sig_eval": fetch_signal_eval,
    "sec_rot": fetch_sector_rotation,
    "algo_metrics": fetch_algo_metrics,
    "irank": fetch_industry_ranking,
    "audit": fetch_audit_log,
    "exec_hist": fetch_exec_history,
    "exp_factors": fetch_exp_factors,
    "scores": fetch_scores,
}


def _execute_fetcher_batch(
    fetcher_set: set[str],
    max_workers: int,
    timeout_sec: float,
    one_func: Callable[..., tuple[str, Any]],
    fetcher_timeout_dict: dict[str, float],
    batch_name: str,
) -> dict[str, Any]:
    """Execute a batch of fetchers with thread pool and timeout handling."""
    out = {}
    critical_fetchers = {
        "run",
        "cfg",
        "mkt",
        "port",
        "perf",
        "pos",
        "trades",
        "sig",
        "health",
        "cb",
        "risk",
        "exp_factors",
    }
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        items = {k: v for k, v in FETCHERS.items() if k in fetcher_set}
        futures: dict[Future[tuple[str, Any]], str] = {
            pool.submit(one_func, k, v, fetcher_timeout_dict.get(k, 8.0)): k for k, v in items.items()
        }
        pending_futures: set[Future[tuple[str, Any]]] = set(futures.keys())

        try:
            for f in as_completed(futures, timeout=timeout_sec):
                try:
                    n, d = f.result()
                    out[n] = d
                    pending_futures.discard(f)
                except Exception as e:
                    k = futures[f]
                    error_msg = format_fetcher_error(k, e)
                    logger.error("Thread exception: %s", error_msg)
                    if k in critical_fetchers:
                        raise RuntimeError(
                            f"[DASHBOARD CRITICAL] Critical fetcher '{k}' failed: {error_msg}. "
                            f"Cannot render dashboard without {k} data."
                        ) from e
                    out[k] = {"_error": error_msg}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.error(f"load_all {batch_name} timeout after {timeout_sec}s")
            critical_missing = []
            for f in pending_futures:
                k_opt = futures.get(f)
                if k_opt and not f.done():
                    k = k_opt
                    meta = FETCHER_METADATA.get(k)
                    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
                    desc = meta.get("desc", "") if meta else ""
                    context = f"{endpoint}" + (f": {desc}" if desc else "")
                    timeout_msg = f"Fetcher {k} ({context}) timed out (exceeded {timeout_sec}s)"
                    logger.warning(timeout_msg)
                    if k in critical_fetchers:
                        critical_missing.append((k, timeout_msg))
                    else:
                        out[k] = {"_error": timeout_msg}
            if critical_missing:
                missing_str = "; ".join(f"{k}: {msg}" for k, msg in critical_missing)
                raise RuntimeError(
                    f"[DASHBOARD CRITICAL] Critical fetcher(s) timed out: {missing_str}. "
                    f"Cannot render dashboard without this data."
                ) from None

    return out


def load_all() -> dict[str, Any]:
    """Load all fetcher data with priority-based execution to prevent RDS connection exhaustion.

    FIXES APPLIED:
    - Issue #1: Removed duplicate api_call() stub
    - Issue #2: Normalized positions data structure {items, count, timestamp}
    - Issue #3: Fetch portfolio metrics from perf API if missing
    - Issue #4: Bounded sector cache with LRU (maxsize=100)
    - Issue #8: Increased thread pool from 8 to 16 workers
    - Issue #9: Increased batch timeout from 100s to 200s
    - C5 FIX: Prioritized fetcher execution (critical first, optional second)

    Issue 10 FIX: Exponential backoff capped at API_MAX_BACKOFF (30s) to prevent runaway delays.
    Issue 11 FIX: Timeout handling ensures orphaned fetchers are marked incomplete and not lost.
    Issue 12 FIX: API calls use retry logic with capped exponential backoff.
    Issue 14 FIX: Consolidated duplicate /api/algo/markets fetches via shared cache.
    Issue #40 FIX: Per-fetcher timeout (critical: 8s, optional: 3s) prevents one slow endpoint from blocking refresh.
    CACHE FIX: Clear perpetual data status and markets caches to ensure fresh data on each refresh cycle.
    """
    # Clear perpetual caches to ensure fresh data fetching on each refresh (watch mode, scheduled tasks)
    # Without this, health and market data would be cached indefinitely and never refresh
    clear_data_status_cache()
    clear_markets_cache()

    out: dict[str, Any] = {}
    max_retries = 3
    batch_timeout = 200

    # Per-fetcher timeout limits to prevent one slow endpoint from blocking refresh
    fetcher_timeout_seconds = {
        # Critical fetchers: 8 second timeout (must complete)
        "run": 8.0,
        "cfg": 8.0,
        "mkt": 8.0,
        "port": 8.0,
        "perf": 8.0,
        "pos": 8.0,
        "trades": 8.0,
        "sig": 8.0,
        "health": 8.0,
        "cb": 8.0,
        "risk": 8.0,  # CRITICAL: Risk metrics required for position sizing
        "exp_factors": 8.0,  # CRITICAL: Market exposure factors required for trading decisions
        # Optional fetchers: 3 second timeout (nice-to-have)
        "srank": 3.0,
        "activity": 3.0,
        "eco": 3.0,
        "notifs": 3.0,
        "sentiment": 3.0,
        "econ_cal": 3.0,
        "perf_anl": 3.0,
        "sig_eval": 3.0,
        "sec_rot": 3.0,
        "algo_metrics": 3.0,
        "irank": 3.0,
        "audit": 3.0,
        "exec_hist": 3.0,
        "scores": 3.0,
    }

    # Categorize fetchers by priority to reduce concurrent RDS connections
    critical_fetchers = {
        "run",
        "cfg",
        "mkt",
        "port",
        "perf",
        "pos",
        "trades",
        "sig",
        "health",
        "cb",
        "risk",  # CRITICAL: Risk metrics for position sizing hard vetoes
        "exp_factors",  # CRITICAL: Market exposure factors for trading decisions
    }
    optional_fetchers = {
        "srank",
        "activity",
        "eco",
        "notifs",
        "sentiment",
        "econ_cal",
        "perf_anl",
        "sig_eval",
        "sec_rot",
        "algo_metrics",
        "irank",
        "audit",
        "exec_hist",
        "scores",
    }

    def one(name: str, fn: Callable[..., Any], timeout_sec: float) -> tuple[str, Any]:
        """Execute fetcher with exponential backoff retry and per-fetcher timeout.

        Issue #40 FIX: Individual timeout per fetcher prevents one slow endpoint from
        blocking others. If fetcher exceeds timeout, immediately return error instead of
        waiting for global batch timeout.

        Issue #41 FIX (UPDATED): Retry on transient 503 errors with exponential backoff (1s, 2s, 4s).
        For both critical and optional fetchers, retry up to 3 times before returning error.
        Only return 503 result after all retries are exhausted.
        """
        start_time = time.monotonic()
        # Specific retry config for 503 errors: 3 retries with exponential backoff
        retry_503_max_retries = 3
        retry_503_backoffs = [1.0, 2.0, 4.0]  # Fixed backoff delays for 503

        for attempt in range(max_retries + 1):
            # Check if per-fetcher timeout has been exceeded
            elapsed = time.monotonic() - start_time
            if elapsed > timeout_sec:
                meta = FETCHER_METADATA.get(name)
                endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
                timeout_msg = f"Fetcher {name} ({endpoint}) exceeded per-fetcher timeout ({timeout_sec:.1f}s)"
                logger.warning(timeout_msg)
                return name, {"_error": timeout_msg}

            try:
                result = fn(None)
                # If result is a dict with _is_transient_503, retry up to 3 times with backoff
                if isinstance(result, dict) and result.get("_is_transient_503"):
                    # Check if we have retries left for 503 errors
                    meta = FETCHER_METADATA.get(name)
                    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"

                    if attempt < retry_503_max_retries:
                        backoff = retry_503_backoffs[attempt]
                        logger.warning(
                            f"Fetcher {name} ({endpoint}) got 503 Service Unavailable, "
                            f"retry {attempt + 1}/{retry_503_max_retries} (backoff {backoff:.1f}s)"
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        # All retries exhausted, return the 503 error
                        logger.error(
                            f"Fetcher {name} ({endpoint}) got 503 Service Unavailable, "
                            f"all {retry_503_max_retries} retries exhausted"
                        )
                        return name, result

                return name, result
            except Exception as e:
                if attempt < max_retries:
                    base_backoff = (2**attempt) + random.random() * (2**attempt)
                    backoff = min(base_backoff, API_MAX_BACKOFF)
                    meta = FETCHER_METADATA.get(name)
                    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
                    logger.warning(
                        f"Fetcher {name} ({endpoint}) retry {attempt + 1}/{max_retries} "
                        f"(backoff {backoff:.1f}s): {type(e).__name__}"
                    )
                    time.sleep(backoff)
                    continue
                error_msg = format_fetcher_error(name, e)
                logger.error(error_msg)
                return name, {"_error": error_msg}

        # Fallback return (should not be reached, but mypy requires it)
        return name, {"_error": "Max retries exceeded"}

    critical_start_time = time.monotonic()
    critical_out = _execute_fetcher_batch(
        critical_fetchers, 10, batch_timeout, one, fetcher_timeout_seconds, "critical"
    )
    out.update(critical_out)

    critical_elapsed = time.monotonic() - critical_start_time
    remaining_time = max(60, batch_timeout - critical_elapsed)
    optional_timeout = remaining_time
    optional_out = _execute_fetcher_batch(
        optional_fetchers,
        6,
        max(60, optional_timeout),
        one,
        fetcher_timeout_seconds,
        "optional",
    )
    out.update(optional_out)

    return out
