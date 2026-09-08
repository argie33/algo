"""Background companyfacts cache-warming for load_financial_statements.py's symbol-major
pass, split out of that file (2026-09-08, goal session "optimize all loading activity") to
keep it under the file-size ratchet's 2000-line hard ceiling - it was already pinned at 1973
with zero headroom for this addition. Pure new logic (no existing code moved here), isolated
into its own module specifically so _run_symbol_pass's own complexity/line count didn't grow.

Design rationale (why this is safe to add mid-reload, unlike real per-symbol pipelining
across the loaders module boundary - ruled out separately as a multi-day rearchitecture):
_run_symbol_pass's main loop is a strictly serial symbol-major pass - the first statement/
period combo for each symbol blocks synchronously on SecEdgarClient.get_company_facts()'s
network fetch (a multi-MB payload; large filers can take well over 1s), then the remaining 5
combos hit that client's small LRU cache "for free". SecEdgarClient's RateLimiter is already
thread-safe (used concurrently today by OptimalLoader's _run_parallel for
company_info_sec/earnings_calendar_sec, running parallelism=2 - see
scripts/local_loader_scheduler.py's own PERF FIX), and get_company_facts()'s LRU + disk-cache
layers are already lock-protected/atomic for exactly this kind of concurrent access. A
background thread here walks ahead of the main loop, warming the cache for upcoming symbols
so the main loop's own fetch is often already-cached by the time it gets there - the main
loop's own logic, timeouts, and per-combo accounting are completely unchanged; a slow, hung,
or failed prefetch degrades to exactly the pre-existing behavior (the main loop does its own
synchronous fetch) rather than a new failure mode.
"""

import logging
import queue
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from utils.external.sec_edgar_client import SecEdgarClient

logger = logging.getLogger(__name__)

# Bounded to stay comfortably under SecEdgarClient's default companyfacts LRU size (4) - deep
# enough to overlap network latency, shallow enough that a prefetched entry is never evicted
# before the main loop reaches it.
PREFETCH_DEPTH = 2


def start_companyfacts_prefetch(
    shared_client: "SecEdgarClient",
    symbols: list[str],
    shutdown_watcher: Any,
) -> tuple["queue.Queue[None]", threading.Thread]:
    """Resolve every symbol's CIK up front, then start a daemon thread that walks ahead of
    the caller's own symbol loop warming shared_client's companyfacts cache.

    CIKs are resolved here, single-threaded, BEFORE the background thread starts -
    deliberately not inside it: TickerCache's rare browse-edgar-fallback path
    (utils/external/sec_ticker_cache.py's symbol_to_cik) does an unsynchronized read-modify-
    write file save, safe under strictly-serial access but not under two threads racing the
    same save. Resolving every CIK here keeps that path single-threaded exactly as before,
    while still letting the network fetches themselves (get_company_facts(), which IS
    lock/atomic-write safe) overlap.

    Returns (prefetch_queue, prefetch_thread) - the thread is already started. The caller
    should call `prefetch_queue.get_nowait()` (swallowing queue.Empty) once per symbol at the
    top of its own loop, purely to let the producer advance - a miss just means the caller's
    own fetch proceeds exactly as if this prefetch didn't exist.
    """
    symbol_ciks: dict[str, str] = {}
    for symbol in symbols:
        try:
            symbol_ciks[symbol] = shared_client.symbol_to_cik(symbol)
        except (ValueError, RuntimeError):
            # Unresolvable symbol - the caller's own real fetch raises/handles this
            # identically; the prefetch thread below just skips warming the cache for it.
            pass

    prefetch_queue: queue.Queue[None] = queue.Queue(maxsize=PREFETCH_DEPTH)

    def _prefetch_worker() -> None:
        for symbol in symbols:
            if shutdown_watcher.check_shutdown_requested():
                return
            cik = symbol_ciks.get(symbol)
            if cik is None:
                continue
            prefetch_queue.put(None)  # blocks once PREFETCH_DEPTH fetches are outstanding
            try:
                shared_client.get_company_facts(cik)
            except Exception as e:
                # Best-effort cache warming only - the caller's own get_company_facts() call
                # does the real fetch (and real error handling/logging) regardless of whether
                # this succeeded, failed, or hasn't run yet.
                logger.debug(f"[FINANCIAL_STATEMENTS PREFETCH] {symbol}: warming fetch failed (non-fatal): {e}")

    prefetch_thread = threading.Thread(target=_prefetch_worker, daemon=True)
    prefetch_thread.start()
    return prefetch_queue, prefetch_thread
