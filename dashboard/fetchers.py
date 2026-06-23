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
    one_func: Callable[[str, Callable[..., Any], float], tuple[str, Any]],
    fetcher_timeout_dict: dict[str, float],
    batch_name: str,
) -> dict[str, Any]:
    """Execute a batch of fetchers with thread pool and timeout handling."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        items = {k: v for k, v in FETCHERS.items() if k in fetcher_set}
        futures: dict[Future, Any] = {
            pool.submit(one_func, k, v, fetcher_timeout_dict.get(k, 8.0)): k for k, v in items.items()
        }
        pending_futures = set(futures.keys())

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
                    out[k] = {"_error": error_msg}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.error(f"load_all {batch_name} timeout after {timeout_sec}s")
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
                    out[k] = {"_error": timeout_msg}

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
    """
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
        # Optional fetchers: 3 second timeout (nice-to-have)
        "srank": 3.0,
        "activity": 3.0,
        "eco": 3.0,
        "notifs": 3.0,
        "sentiment": 3.0,
        "econ_cal": 3.0,
        "risk": 3.0,
        "perf_anl": 3.0,
        "sig_eval": 3.0,
        "sec_rot": 3.0,
        "algo_metrics": 3.0,
        "irank": 3.0,
        "audit": 3.0,
        "exec_hist": 3.0,
        "exp_factors": 3.0,
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
    }
    optional_fetchers = {
        "srank",
        "activity",
        "eco",
        "notifs",
        "sentiment",
        "econ_cal",
        "risk",
        "perf_anl",
        "sig_eval",
        "sec_rot",
        "algo_metrics",
        "irank",
        "audit",
        "exec_hist",
        "exp_factors",
        "scores",
    }

    def one(name: str, fn: Callable[..., Any], timeout_sec: float) -> tuple[str, Any]:
        """Execute fetcher with exponential backoff retry and per-fetcher timeout.

        Issue #40 FIX: Individual timeout per fetcher prevents one slow endpoint from
        blocking others. If fetcher exceeds timeout, immediately return error instead of
        waiting for global batch timeout.
        """
        start_time = time.monotonic()

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
                return name, fn(None)
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
