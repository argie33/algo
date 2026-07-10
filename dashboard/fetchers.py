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
        "scores",
    }
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        items = {k: v for k, v in FETCHERS.items() if k in fetcher_set}
        logger.info(f"[FETCHERS] Starting {batch_name} batch: {list(items.keys())}")
        futures: dict[Future[tuple[str, Any]], str] = {
            pool.submit(one_func, k, v, fetcher_timeout_dict.get(k, 8.0)): k for k, v in items.items()
        }
        pending_futures: set[Future[tuple[str, Any]]] = set(futures.keys())

        try:
            for f in as_completed(futures, timeout=timeout_sec):
                try:
                    n, d = f.result()
                    out[n] = d
                    logger.info(f"[FETCHERS] Completed: {n}")
                    pending_futures.discard(f)
                except Exception as e:
                    k = futures[f]
                    error_msg = format_fetcher_error(k, e)
                    logger.error("[FETCHERS] Thread exception in %s: %s", k, error_msg)
                    if k in critical_fetchers:
                        raise RuntimeError(
                            f"[DASHBOARD CRITICAL] Critical fetcher '{k}' failed: {error_msg}. "
                            f"Cannot render dashboard without {k} data."
                        ) from e
                    out[k] = {"_error": error_msg}
                    pending_futures.discard(f)
        except TimeoutError:
            logger.error(f"[FETCHERS] {batch_name} batch timeout after {timeout_sec}s")
            pending_fetchers = [futures.get(f) for f in pending_futures if futures.get(f) and not f.done()]
            logger.error(f"[FETCHERS] HANGING FETCHERS: {pending_fetchers}")
            critical_missing = []
            for f in pending_futures:
                k_opt = futures.get(f)
                if k_opt and not f.done():
                    k = k_opt
                    meta = FETCHER_METADATA.get(k)
                    if meta:
                        endpoint = meta.get("endpoint", "unknown endpoint")
                        desc = meta.get("desc", "")  # Display-only, safe empty default with logging
                        if not desc:
                            logger.debug(f"[FETCHERS] Fetcher {k} missing description")
                    else:
                        endpoint = "unknown endpoint"
                        desc = ""
                        logger.debug(f"[FETCHERS] No metadata for fetcher {k}")
                    context = f"{endpoint}" + (f": {desc}" if desc else "")
                    timeout_msg = f"Fetcher {k} ({context}) timed out (exceeded {timeout_sec}s)"
                    logger.warning(timeout_msg)
                    if k in critical_fetchers:
                        critical_missing.append((k, timeout_msg))
                    else:
                        out[k] = {"_error": timeout_msg}
            if critical_missing:
                missing_str = "; ".join(f"{k}: {msg}" for k, msg in critical_missing)
                logger.error(
                    f"[DASHBOARD CRITICAL] Critical fetcher(s) timed out: {missing_str}. "
                    f"Dashboard will render with degraded data."
                )
                for k, timeout_msg in critical_missing:
                    out[k] = {"_error": timeout_msg}

    return out


def load_all() -> dict[str, Any]:
    """Load all fetcher data with priority-based execution to prevent RDS connection exhaustion.

    FALLBACK MODE: If API endpoints are unreachable, fetchers will use direct database queries
    as a fallback. This ensures the dashboard can display data even if Lambda functions aren't
    responding. Critical for development and debugging scenarios.

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
    global_start = time.monotonic()
    # Clear perpetual caches to ensure fresh data fetching on each refresh (watch mode, scheduled tasks)
    # Without this, health and market data would be cached indefinitely and never refresh
    clear_data_status_cache()
    clear_markets_cache()

    out: dict[str, Any] = {}
    max_retries = 3
    batch_timeout = 300  # Increased from 200s to allow slow database queries to complete

    # Per-fetcher timeout limits to prevent one slow endpoint from blocking refresh
    # DASHBOARD OPTIMIZATION: Aggressive timeouts for initial load so dashboard displays quickly
    # Non-critical data degrades gracefully; critical data has 2-3s timeout for API calls
    fetcher_timeout_seconds = {
        # Critical fetchers: 3 second timeout (dashboard must display quickly)
        # Fetchers use local database fallbacks on API timeout/auth errors
        "run": 3.0,
        "cfg": 3.0,
        "mkt": 3.0,
        "port": 3.0,
        "perf": 3.0,
        "pos": 3.0,
        "trades": 3.0,
        "sig": 3.0,
        "health": 3.0,
        "cb": 3.0,
        "risk": 3.0,
        "exp_factors": 3.0,
        # Optional fetchers: 2 second timeout (nice-to-have)
        "srank": 2.0,
        "activity": 2.0,
        "eco": 2.0,
        "notifs": 2.0,
        "sentiment": 2.0,
        "econ_cal": 2.0,
        "perf_anl": 2.0,
        "sig_eval": 2.0,
        "sec_rot": 2.0,
        "algo_metrics": 2.0,
        "irank": 2.0,
        "audit": 2.0,
        "exec_hist": 2.0,
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
        "health",
        "sig",  # Dashboard-signals endpoint - REQUIRED for signals panel
        "scores",  # Stock scores endpoint - REQUIRED for multiple panels
        "risk",  # Risk metrics - REQUIRED for risk dashboard panel
        "exp_factors",  # Market exposure factors - REQUIRED for exposure panel
        "cb",  # Circuit breakers - REQUIRED for circuit breaker panel
    }
    optional_fetchers = {
        "srank",  # Nice-to-have sector rankings
        "activity",  # Activity log (informational)
        "eco",  # Economic data (optional enrichment)
        "notifs",  # Notifications (informational)
        "sentiment",  # Market sentiment (optional enrichment)
        "econ_cal",  # Economic calendar (optional enrichment)
        "perf_anl",  # Performance analytics (detailed metrics)
        "sig_eval",  # Signal evaluation (optional analysis)
        "sec_rot",  # Sector rotation (optional analysis)
        "algo_metrics",  # Algo metrics (optional enrichment)
        "irank",  # Industry rankings (optional enrichment)
        "audit",  # Audit log (optional for debugging)
        "exec_hist",  # Execution history (optional detailed view)
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

        raise AssertionError(
            f"[FETCHER INTERNAL ERROR] Retry loop for {name} exited without returning. "
            f"This indicates a logic error in the retry handler. Max retries={max_retries}. "
            f"All code paths should return explicitly."
        )

    critical_start_time = time.monotonic()
    # DASHBOARD OPTIMIZATION: Reduce batch timeout to 10s for critical fetchers
    # This prevents dashboard from hanging when API endpoints require auth or are slow
    # Fetchers degrade gracefully: return empty/error data instead of blocking
    critical_batch_timeout = min(15, batch_timeout)  # 15s for critical fetchers; graceful degradation if timeout
    critical_out = _execute_fetcher_batch(
        critical_fetchers, 15, critical_batch_timeout, one, fetcher_timeout_seconds, "critical"
    )

    # Log critical fetcher failures loudly, but degrade per-panel rather than
    # blanking the whole dashboard. Every panel renderer already has its own
    # "_error" handling (dashboard/panels/*.py: economic, health, portfolio,
    # positions, scores, signals, trades) built exactly for this — a single
    # failed fetcher (auth hiccup, transient 503, timeout) used to discard
    # the entire merged result here, which meant every OTHER panel that had
    # already fetched fine also showed nothing. Merge the error dicts through
    # instead so only the actually-failed panel shows an error state.
    critical_failures = [k for k, v in critical_out.items() if isinstance(v, dict) and "_error" in v]
    if critical_failures:
        failed_summary = "; ".join(
            f"{k}: {critical_out[k].get('_error', 'unknown error')[:100]}" for k in critical_failures
        )
        logger.error(
            f"[FETCHER] Critical fetcher failures detected: {failed_summary}. "
            f"Affected panels will show their own error state; other panels proceed normally."
        )

    out.update(critical_out)
    if critical_failures:
        out["_critical_fetcher_failures"] = critical_failures

    critical_elapsed = time.monotonic() - critical_start_time
    logger.info(f"[LOAD_ALL] Critical fetchers completed in {critical_elapsed:.2f}s")

    # Execute optional fetchers with relaxed timeout (5-10s total)
    # These enhance dashboard but don't block startup
    optional_batch_timeout = max(10, batch_timeout // 10)  # 10s for optional batch
    optional_start_time = time.monotonic()
    optional_out = _execute_fetcher_batch(
        optional_fetchers,
        6,
        optional_batch_timeout,
        one,
        fetcher_timeout_seconds,
        "optional",
    )

    optional_elapsed = time.monotonic() - optional_start_time
    optional_failures = [k for k, v in optional_out.items() if isinstance(v, dict) and "_error" in v]
    if optional_failures:
        logger.warning(
            f"[FETCHERS] Optional fetcher failures (non-blocking): "
            f"{', '.join(optional_failures)}"
        )

    out.update(optional_out)
    logger.info(
        f"[LOAD_ALL] All fetchers completed in {critical_elapsed + optional_elapsed:.2f}s "
        f"(critical: {critical_elapsed:.2f}s, optional: {optional_elapsed:.2f}s)"
    )

    return out
