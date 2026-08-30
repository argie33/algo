"""Regression test for load_enhanced_quality_growth_metrics.py's estimate-revision fields.

Covers _compute_estimate_revision_metrics(): before this fix, estimate_revision_direction,
revision_activity_30d, estimate_momentum_60d/90d, and revision_trend_score were hardcoded to
None every run (0/5682 populated universe-wide, live-verified 2026-08-04) even though
yf.Ticker(symbol).eps_trend/.eps_revisions supply exactly this data for the '0q' period.

2026-08-29: the yfinance fetch itself moved from an in-process yf.Ticker call to
YfinanceProcessWorker (a persistent subprocess) - see that class's docstring and
yfinance_curl_cffi_gil_hostage_hang_diagnosed_not_fixed_20260829 for why. Tests below mock
`loader._get_yf_worker()` instead of `yfinance.Ticker` - a real yf.Ticker call now happens
inside a separate OS process the test process can't patch into.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader, YfinanceProcessWorker


def _loader() -> EnhancedQualityGrowthMetricsLoader:
    return EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)


def _eps_trend_df(current=1.97898, ago_60=2.00767, ago_90=2.00701) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "current": [current],
            "7daysAgo": [2.01686],
            "30daysAgo": [2.00836],
            "60daysAgo": [ago_60],
            "90daysAgo": [ago_90],
        },
        index=["0q"],
    )


def _eps_revisions_df(up_30d=2, down_30d=0) -> pd.DataFrame:
    return pd.DataFrame(
        {"upLast7days": [1], "upLast30days": [up_30d], "downLast30days": [down_30d], "downLast7Days": [0]},
        index=["0q"],
    )


def _mock_worker(eps_trend: pd.DataFrame, eps_revisions: pd.DataFrame) -> MagicMock:
    worker = MagicMock()
    worker.fetch.side_effect = lambda symbol, prop: {
        "eps_trend": eps_trend,
        "eps_revisions": eps_revisions,
    }[prop]
    return worker


class TestComputeEstimateRevisionMetrics:
    def test_populates_all_five_fields_from_live_shaped_data(self):
        loader = _loader()
        loader._yf_worker = _mock_worker(_eps_trend_df(), _eps_revisions_df())
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert metrics["estimate_momentum_60d"] is not None
        assert metrics["estimate_momentum_90d"] is not None
        assert metrics["revision_trend_score"] is not None
        assert metrics["revision_activity_30d"] == 2.0
        assert metrics["estimate_revision_direction"] == 2.0

    def test_missing_0q_row_leaves_fields_unset(self):
        loader = _loader()
        loader._yf_worker = _mock_worker(
            pd.DataFrame({"current": [1.0]}, index=["+1q"]),
            pd.DataFrame({"upLast30days": [1]}, index=["+1q"]),
        )
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("ZZZZ", metrics)

        assert "estimate_momentum_60d" not in metrics
        assert "estimate_momentum_90d" not in metrics
        assert "revision_activity_30d" not in metrics
        assert "estimate_revision_direction" not in metrics

    def test_empty_dataframes_leave_fields_unset(self):
        loader = _loader()
        loader._yf_worker = _mock_worker(pd.DataFrame(), pd.DataFrame())
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("ZZZZ", metrics)

        assert metrics == {}

    def test_near_zero_prior_estimate_does_not_overflow_numeric_column(self):
        # A near-zero 60/90-days-ago EPS estimate would otherwise blow the percentage-change
        # calc past this table's NUMERIC(10,4) column limit (max magnitude 999,999.9999) -
        # same overflow class already guarded against for the sibling trend fields.
        loader = _loader()
        loader._yf_worker = _mock_worker(_eps_trend_df(current=1.0, ago_60=0.0000001, ago_90=2.0), _eps_revisions_df())
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert "estimate_momentum_60d" not in metrics
        assert metrics["estimate_momentum_90d"] is not None

    def test_yfinance_exception_leaves_metrics_untouched(self):
        loader = _loader()
        worker = MagicMock()
        worker.fetch.side_effect = RuntimeError("rate limited")
        loader._yf_worker = worker
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert metrics == {}

    def test_eps_trend_and_eps_revisions_go_through_the_process_isolated_worker(self):
        """Regression test: eps_trend/eps_revisions must go through
        _get_yf_worker().fetch(), same process-isolated path as the sibling
        earnings_dates call.

        Live-reproduced 2026-08-16 (thread-timeout era): these two fetches called
        retry_with_backoff directly on `ticker.eps_trend`/`ticker.eps_revisions` with no
        timeout wrapper at all - a real hang there stalled the loader for 30+ minutes.
        A docstring already claimed timeout protection "for the same reason" as
        earnings_dates, but the code never actually applied it. Then live-reproduced
        AGAIN 2026-08-29 with the thread-based wrapper actually in place (`
        _yfinance_call_with_timeout`) - it still couldn't bound a genuine curl_cffi hang
        (~8 hours on one symbol) because Thread.join(timeout=N) itself needs the GIL,
        which the hung call appears to hold hostage. Replaced with YfinanceProcessWorker
        (process isolation - see its own docstring); this test now checks calls route
        through that boundary instead of the old thread wrapper.
        """
        loader = _loader()
        worker = _mock_worker(_eps_trend_df(), _eps_revisions_df())
        loader._yf_worker = worker
        metrics: dict = {}

        loader._compute_estimate_revision_metrics("AAPL", metrics)

        assert worker.fetch.call_count == 2
        worker.fetch.assert_any_call("AAPL", "eps_trend")
        worker.fetch.assert_any_call("AAPL", "eps_revisions")
        assert metrics["estimate_momentum_60d"] is not None


def _fake_worker_loop_echo(request_queue, response_queue) -> None:
    """Deterministic stand-in for _yfinance_worker_loop: echoes back
    f"{symbol}:{property_name}" instead of hitting real yfinance. Module-level (spawn
    needs to pickle-reference it by import path, same constraint as the real target)."""
    while True:
        item = request_queue.get()
        if item is None:
            return
        request_id, symbol, property_name = item
        response_queue.put((request_id, True, f"{symbol}:{property_name}"))


def _fake_worker_loop_hangs_forever(request_queue, response_queue) -> None:
    """Deterministic stand-in that never responds to any request - simulates the
    curl_cffi hang this whole fix targets, without depending on real network behavior.
    Module-level for the same pickling reason as the other fake worker above."""
    import time as _time

    while True:
        item = request_queue.get()
        if item is None:
            return
        _time.sleep(3600)  # Never actually returns within any test's timeout


def _fake_worker_loop_raises(request_queue, response_queue) -> None:
    """Deterministic stand-in that reports a real fetch failure for every request -
    proves a worker-side exception propagates to the caller rather than being swallowed
    or mistaken for a timeout. Module-level for the same pickling reason as the other
    fake workers above."""
    while True:
        item = request_queue.get()
        if item is None:
            return
        request_id, _symbol, _property_name = item
        response_queue.put((request_id, False, ValueError("simulated worker-side fetch failure")))


class TestYfinanceProcessWorkerTimeoutRecovery:
    """Unlike the old thread-based wrapper, a process-based timeout is genuinely testable
    against a real hang - a subprocess that never returns can actually be killed and
    replaced, which is exactly what these tests verify end-to-end (real subprocess
    spawn/kill, deterministic fake workers instead of depending on network conditions)."""

    def test_fetch_returns_data_through_a_real_subprocess_round_trip(self):
        worker = YfinanceProcessWorker(timeout_seconds=15.0, worker_target=_fake_worker_loop_echo)
        try:
            result = worker.fetch("AAPL", "eps_trend")
            assert result == "AAPL:eps_trend"
            # A second call must reuse the SAME worker process (no respawn cost) - the
            # whole point of a persistent worker instead of per-call spawning.
            pid_before = worker._process.pid
            worker.fetch("MSFT", "eps_revisions")
            assert worker._process.pid == pid_before
        finally:
            worker.shutdown()

    def test_timeout_terminates_hung_worker_and_recovers_on_next_call(self):
        """The core claim this whole fix rests on: a worker that never returns gets
        force-killed within the configured timeout (not left hanging for hours like the
        thread-based predecessor), and the NEXT call transparently succeeds through a
        freshly spawned replacement worker."""
        import time as _time

        worker = YfinanceProcessWorker(timeout_seconds=2.0, worker_target=_fake_worker_loop_hangs_forever)
        try:
            start = _time.monotonic()
            try:
                worker.fetch("HUNG_SYMBOL", "eps_trend")
                raise AssertionError("Expected TimeoutError for a hung fetch")
            except TimeoutError:
                elapsed = _time.monotonic() - start
                # Bounded by the configured 2s timeout (with generous test slack), not
                # left hanging indefinitely - this is what the old thread-based
                # `_yfinance_call_with_timeout` could NOT actually guarantee.
                assert elapsed < 10.0

            # The hung worker must have been terminated, not left running as an orphan.
            assert worker._process is None

            # Swap in the well-behaved fake worker to prove the NEXT call recovers
            # cleanly through a freshly spawned process rather than staying broken.
            worker._worker_target = _fake_worker_loop_echo
            result = worker.fetch("RECOVERED_SYMBOL", "eps_revisions")
            assert result == "RECOVERED_SYMBOL:eps_revisions"
        finally:
            worker.shutdown()

    def test_worker_exception_propagates_to_caller(self):
        """A worker-side exception must surface to the caller as a real exception, not be
        silently swallowed or turned into a spurious TimeoutError. Uses a deterministic
        fake worker (rather than depending on real yfinance's behavior for some invalid
        symbol) so this stays fast and doesn't depend on network conditions."""
        worker = YfinanceProcessWorker(timeout_seconds=15.0, worker_target=_fake_worker_loop_raises)
        try:
            with pytest.raises(ValueError, match="simulated worker-side fetch failure"):
                worker.fetch("ANY_SYMBOL", "eps_trend")
        finally:
            worker.shutdown()
