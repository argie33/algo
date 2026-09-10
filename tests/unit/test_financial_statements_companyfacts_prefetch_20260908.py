"""Tests for loaders/helpers/financial_statements_prefetch.py's cache-warming pipeline.

start_companyfacts_prefetch() is a pure performance optimization: it should never change
what _run_symbol_pass's main loop actually does, only whether get_company_facts() has
already been warmed into the shared client's cache by the time the main loop gets there.
"""

import queue
import time
from unittest.mock import MagicMock

from loaders.helpers.financial_statements_prefetch import PREFETCH_DEPTH, start_companyfacts_prefetch


def _shutdown_watcher(requested=False):
    watcher = MagicMock()
    watcher.check_shutdown_requested.return_value = requested
    return watcher


def _drain_until_done(prefetch_queue, thread, n_gets, timeout=5):
    """Mimic the real main loop: call get_nowait() up to n_gets times (once per symbol),
    letting the producer advance past its PREFETCH_DEPTH leash, then wait for it to finish."""
    deadline = time.time() + timeout
    gets_done = 0
    while thread.is_alive() and time.time() < deadline:
        if gets_done < n_gets:
            try:
                prefetch_queue.get(timeout=0.05)
                gets_done += 1
                continue
            except queue.Empty:
                pass
        time.sleep(0.01)
    thread.join(timeout=max(0.0, deadline - time.time()))


def test_prefetch_warms_cache_ahead_of_main_loop():
    client = MagicMock()
    client.symbol_to_cik.side_effect = lambda s: f"CIK_{s}"
    fetched = []
    client.get_company_facts.side_effect = lambda cik: fetched.append(cik) or {}

    symbols = ["AAA", "BBB", "CCC"]
    prefetch_queue, thread = start_companyfacts_prefetch(client, symbols, _shutdown_watcher())
    _drain_until_done(prefetch_queue, thread, len(symbols))

    assert not thread.is_alive()
    assert fetched == ["CIK_AAA", "CIK_BBB", "CIK_CCC"]


def test_unresolvable_symbol_is_skipped_not_fatal():
    """A symbol whose CIK can't be resolved must not crash the prefetch thread or block
    later symbols - the main loop's own real fetch handles that failure identically."""
    client = MagicMock()

    def _resolve(symbol):
        if symbol == "BAD":
            raise ValueError("not found")
        return f"CIK_{symbol}"

    client.symbol_to_cik.side_effect = _resolve
    fetched = []
    client.get_company_facts.side_effect = lambda cik: fetched.append(cik) or {}

    symbols = ["AAA", "BAD", "CCC"]
    prefetch_queue, thread = start_companyfacts_prefetch(client, symbols, _shutdown_watcher())
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert fetched == ["CIK_AAA", "CIK_CCC"]


def test_fetch_failure_does_not_kill_worker_or_block_later_symbols():
    """get_company_facts() raising for one symbol (network error, 404, etc.) must not stop
    the prefetch thread from continuing to warm the rest of the list."""
    client = MagicMock()
    client.symbol_to_cik.side_effect = lambda s: f"CIK_{s}"

    def _fetch(cik):
        if cik == "CIK_BBB":
            raise RuntimeError("SEC API error")
        return {}

    fetched = []
    client.get_company_facts.side_effect = lambda cik: fetched.append(cik) or _fetch(cik)

    symbols = ["AAA", "BBB", "CCC"]
    prefetch_queue, thread = start_companyfacts_prefetch(client, symbols, _shutdown_watcher())
    _drain_until_done(prefetch_queue, thread, len(symbols))

    assert not thread.is_alive()
    assert fetched == ["CIK_AAA", "CIK_BBB", "CIK_CCC"]


def test_shutdown_requested_stops_the_worker_early():
    client = MagicMock()
    client.symbol_to_cik.side_effect = lambda s: f"CIK_{s}"
    fetched = []
    client.get_company_facts.side_effect = lambda cik: fetched.append(cik) or {}

    watcher = _shutdown_watcher(requested=True)
    symbols = ["AAA", "BBB", "CCC"]
    prefetch_queue, thread = start_companyfacts_prefetch(client, symbols, watcher)
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert fetched == []


def test_never_runs_more_than_prefetch_depth_ahead_of_consumer():
    """The single background worker fetches sequentially (one companyfacts payload at a
    time), but must not race PREFETCH_DEPTH+1 symbols ahead of an idle consumer - that's what
    keeps a prefetched entry from being evicted (LRU size 4) before the main loop reaches it.
    Each fetch here returns instantly, so with zero consumption the worker should fetch
    exactly PREFETCH_DEPTH symbols and then block on the next queue slot."""
    client = MagicMock()
    client.symbol_to_cik.side_effect = lambda s: f"CIK_{s}"
    fetched_order: list[str] = []
    client.get_company_facts.side_effect = lambda cik: fetched_order.append(cik) or {}

    symbols = [f"S{i}" for i in range(10)]
    prefetch_queue, thread = start_companyfacts_prefetch(client, symbols, _shutdown_watcher())

    # Give the worker time to run as far ahead as it's allowed to, then confirm it stalls
    # there (never consumed, so it must not exceed PREFETCH_DEPTH).
    time.sleep(0.3)
    assert len(fetched_order) == PREFETCH_DEPTH
    assert thread.is_alive()

    # Draining lets exactly one more fetch through per get().
    prefetch_queue.get(timeout=2)
    time.sleep(0.1)
    assert len(fetched_order) == PREFETCH_DEPTH + 1

    _drain_until_done(prefetch_queue, thread, len(symbols))
    assert not thread.is_alive()
    assert fetched_order == [f"CIK_{s}" for s in symbols]
