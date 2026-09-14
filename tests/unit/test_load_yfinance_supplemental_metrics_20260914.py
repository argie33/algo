"""Tests for load_yfinance_supplemental_metrics.py - held_percent_insiders via yfinance
major_holders (a non-.info DataFrame endpoint - see that loader's module docstring for why
.info/quoteSummary is deliberately avoided).
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from loaders.load_yfinance_supplemental_metrics import (
    YfinanceSupplementalMetricsLoader,
    _fetch_held_percent_insiders,
)


def _major_holders_df(insiders_pct: float) -> pd.DataFrame:
    return pd.DataFrame({"Value": [insiders_pct]}, index=["insidersPercentHeld"])


class TestFetchHeldPercentInsiders:
    def test_real_value_scaled_to_0_100(self) -> None:
        with patch("loaders.load_yfinance_supplemental_metrics.YFinanceTimeoutWrapper") as mock_wrapper_cls:
            mock_wrapper = MagicMock()
            mock_wrapper.major_holders = _major_holders_df(0.01648)
            mock_wrapper_cls.return_value = mock_wrapper

            pct, reason = _fetch_held_percent_insiders("AAPL")

        assert pct is not None
        assert abs(pct - 1.648) < 1e-6
        assert reason is None

    def test_empty_dataframe_returns_unavailable(self) -> None:
        with patch("loaders.load_yfinance_supplemental_metrics.YFinanceTimeoutWrapper") as mock_wrapper_cls:
            mock_wrapper = MagicMock()
            mock_wrapper.major_holders = pd.DataFrame()
            mock_wrapper_cls.return_value = mock_wrapper

            pct, reason = _fetch_held_percent_insiders("ZZZZ")

        assert pct is None
        assert reason == "no_insider_ownership_data"

    def test_missing_index_returns_unavailable(self) -> None:
        with patch("loaders.load_yfinance_supplemental_metrics.YFinanceTimeoutWrapper") as mock_wrapper_cls:
            mock_wrapper = MagicMock()
            mock_wrapper.major_holders = pd.DataFrame({"Value": [0.5]}, index=["institutionsPercentHeld"])
            mock_wrapper_cls.return_value = mock_wrapper

            pct, reason = _fetch_held_percent_insiders("ZZZZ")

        assert pct is None
        assert reason == "no_insider_ownership_data"

    def test_fetch_timeout_returns_unavailable(self) -> None:
        class _TimeoutOnAccess:
            @property
            def major_holders(self) -> pd.DataFrame:
                raise TimeoutError("timed out")

        with patch("loaders.load_yfinance_supplemental_metrics.YFinanceTimeoutWrapper") as mock_wrapper_cls:
            mock_wrapper_cls.return_value = _TimeoutOnAccess()

            pct, reason = _fetch_held_percent_insiders("AAPL")

        assert pct is None
        assert reason == "yfinance_fetch_failed"

    def test_out_of_range_value_flagged_implausible(self) -> None:
        with patch("loaders.load_yfinance_supplemental_metrics.YFinanceTimeoutWrapper") as mock_wrapper_cls:
            mock_wrapper = MagicMock()
            # 1.5 as a fraction -> 150% after scaling, impossible for an ownership percentage
            mock_wrapper.major_holders = _major_holders_df(1.5)
            mock_wrapper_cls.return_value = mock_wrapper

            pct, reason = _fetch_held_percent_insiders("AAPL")

        assert pct is None
        assert reason == "implausible_value"


class TestYfinanceSupplementalMetricsLoaderFetchIncremental:
    def test_already_fetched_today_returns_empty(self) -> None:
        loader = YfinanceSupplementalMetricsLoader.__new__(YfinanceSupplementalMetricsLoader)
        from datetime import datetime

        from utils.infrastructure.timezone import EASTERN_TZ

        today = datetime.now(EASTERN_TZ).date()
        assert loader.fetch_incremental("AAPL", today) == []

    def test_fetch_returns_one_row_with_source_labeled_yfinance(self) -> None:
        loader = YfinanceSupplementalMetricsLoader.__new__(YfinanceSupplementalMetricsLoader)
        with patch(
            "loaders.load_yfinance_supplemental_metrics._fetch_held_percent_insiders",
            return_value=(1.65, None),
        ):
            rows = loader.fetch_incremental("AAPL", None)

        assert len(rows) == 1
        row = rows[0]
        assert row["symbol"] == "AAPL"
        assert row["held_percent_insiders"] == 1.65
        assert row["data_source"] == "yfinance"
        assert row["data_unavailable"] is False
        assert row["held_percent_insiders_unavailable_reason"] is None

    def test_fetch_unavailable_marks_data_unavailable(self) -> None:
        loader = YfinanceSupplementalMetricsLoader.__new__(YfinanceSupplementalMetricsLoader)
        with patch(
            "loaders.load_yfinance_supplemental_metrics._fetch_held_percent_insiders",
            return_value=(None, "no_insider_ownership_data"),
        ):
            rows = loader.fetch_incremental("ZZZZ", None)

        assert len(rows) == 1
        row = rows[0]
        assert row["held_percent_insiders"] is None
        assert row["data_unavailable"] is True
        assert row["reason"] == "no_insider_ownership_data"
