"""Regression test: load_sec_valuations.py's three narrow yfinance-fallback fetches
(_fetch_live_fpi_yfinance_check_values, _fetch_live_dual_class_shares_outstanding,
_fetch_live_fpi_shares_outstanding_yfinance) must go through the shared, process-isolated
_YfinanceAttrProcessWorker rather than an in-process yf.Ticker(...).info call.

FIXED 2026-08-29 (goal: "full data" audit, loading-issues sweep): all three used the same
socket.setdefaulttimeout()-wrapped in-process fetch already proven ineffective against a
curl_cffi hang at 4 other call sites this session (yfinance 0.2.40+ requires curl_cffi,
which isn't built on Python's socket module). No live multi-hour hang incident found for
this specific file, but it's the identical architectural vulnerability - fixed proactively.

Mocks `_get_module_worker()` (utils/external/yfinance_analyst_ratings.py) rather than
`yfinance.Ticker` - a real yf.Ticker call now happens inside a separate OS process the test
process can't patch into.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader

_WORKER_PATCH_TARGET = "utils.external.yfinance_analyst_ratings._get_module_worker"


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


def _mock_worker(info: dict[str, Any] | None) -> MagicMock:
    worker = MagicMock()
    worker.fetch.return_value = info
    return worker


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with patch("utils.external.yfinance_circuit_breaker.get_circuit_breaker") as mock_get_cb:
        mock_get_cb.return_value = MagicMock()
        yield mock_get_cb.return_value


class TestFetchLiveFpiYfinanceCheckValues:
    def test_returns_market_cap_and_pe_from_worker(self):
        loader = _make_loader()
        worker = _mock_worker({"marketCap": 5_000_000_000.0, "trailingPE": 22.5})
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            mcap, pe = loader._fetch_live_fpi_yfinance_check_values("SAP")

        assert mcap == 5_000_000_000.0
        assert pe == 22.5
        worker.fetch.assert_called_once_with("SAP", "info", timeout_seconds=10.0)

    def test_worker_timeout_fails_open_to_none_none(self):
        """A hung/timed-out worker must not block or crash this sanity-check path - it
        fails open (None, None), same as any other fetch error."""
        loader = _make_loader()
        worker = MagicMock()
        worker.fetch.side_effect = TimeoutError("worker terminated")
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            mcap, pe = loader._fetch_live_fpi_yfinance_check_values("SAP")

        assert (mcap, pe) == (None, None)

    def test_non_dict_info_fails_open(self):
        loader = _make_loader()
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_worker(None)):
            mcap, pe = loader._fetch_live_fpi_yfinance_check_values("SAP")

        assert (mcap, pe) == (None, None)


class TestFetchLiveDualClassSharesOutstanding:
    def test_returns_shares_from_worker(self):
        loader = _make_loader()
        worker = _mock_worker({"sharesOutstanding": 1_500_000_000.0})
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            shares = loader._fetch_live_dual_class_shares_outstanding("BRK-B")

        assert shares == 1_500_000_000.0

    def test_worker_timeout_fails_open_to_none(self):
        loader = _make_loader()
        worker = MagicMock()
        worker.fetch.side_effect = TimeoutError("worker terminated")
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            assert loader._fetch_live_dual_class_shares_outstanding("BRK-B") is None


class TestFetchLiveFpiSharesOutstandingYfinance:
    def test_returns_shares_from_worker(self):
        loader = _make_loader()
        worker = _mock_worker({"sharesOutstanding": 2_500_000_000.0})
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            shares = loader._fetch_live_fpi_shares_outstanding_yfinance("TSM")

        assert shares == 2_500_000_000.0

    def test_worker_timeout_fails_open_to_none(self):
        loader = _make_loader()
        worker = MagicMock()
        worker.fetch.side_effect = TimeoutError("worker terminated")
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            assert loader._fetch_live_fpi_shares_outstanding_yfinance("TSM") is None
