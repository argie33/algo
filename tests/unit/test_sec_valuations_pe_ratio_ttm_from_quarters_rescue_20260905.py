"""Regression test (2026-09-05, goal: "get SEC/XBRL missing data to zero" campaign,
eps_scale_mismatch refinement) for `ValuationSanityCheckMixin._sanity_check_pe_ratio`'s
TTM-from-quarters rescue in loaders/helpers/sec_valuations_checks.py.

Most `eps_scale_mismatch` rejections are not a genuine XBRL scale-tagging bug: `pe_ratio` is
computed from the latest ANNUAL eps (despite the `ttm_eps_basic` name), while yfinance's PE
uses a real rolling trailing-twelve-month EPS. A stale annual EPS vs a live TTM EPS can easily
diverge >10x with no scale bug involved. If the real trailing 4 quarters (by `period_end`) are
present, recent, and their EPS sum reconciles with yfinance's PE, this method should keep the
original SEC-derived pe_ratio/peg_ratio instead of nulling them.

See eps_scale_mismatch_mostly_stale_annual_vs_live_ttm_not_true_scale_bug_20260905 in memory for
the original investigation (which incorrectly concluded this rescue wasn't feasible because it
checked the dead `quarterly_income_statement.eps` column instead of the real
`earnings_per_share` column).
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.helpers.sec_valuations_checks import ValuationSanityCheckMixin


class _FakeCursor:
    def __init__(self, quarterly_rows: list[tuple[Any, ...]]) -> None:
        self._quarterly_rows = quarterly_rows

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._quarterly_rows


def _make_mixin_with_quarters(quarterly_rows: list[tuple[Any, ...]]) -> ValuationSanityCheckMixin:
    mixin = ValuationSanityCheckMixin.__new__(ValuationSanityCheckMixin)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=_FakeCursor(quarterly_rows))
    fake_ctx.__exit__ = MagicMock(return_value=False)
    mixin._fake_ctx = fake_ctx  # keep alive
    return mixin


_TODAY = date.today()
_RECENT_QUARTERS = [
    (_TODAY - timedelta(days=10), 5.0),
    (_TODAY - timedelta(days=100), 5.0),
    (_TODAY - timedelta(days=190), 5.0),
    (_TODAY - timedelta(days=280), 5.0),
]
_STALE_QUARTERS = [
    (_TODAY - timedelta(days=500), 5.0),
    (_TODAY - timedelta(days=590), 5.0),
    (_TODAY - timedelta(days=680), 5.0),
    (_TODAY - timedelta(days=770), 5.0),
]


class TestComputeTtmEpsFromQuarters:
    def test_four_recent_quarters_sums_correctly(self) -> None:
        mixin = _make_mixin_with_quarters(_RECENT_QUARTERS)
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result == 20.0

    def test_fewer_than_four_quarters_returns_none(self) -> None:
        mixin = _make_mixin_with_quarters(_RECENT_QUARTERS[:3])
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result is None

    def test_stale_most_recent_quarter_returns_none(self) -> None:
        mixin = _make_mixin_with_quarters(_STALE_QUARTERS)
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result is None

    def test_null_eps_in_one_quarter_returns_none(self) -> None:
        rows = [*_RECENT_QUARTERS[:3], (_TODAY - timedelta(days=280), None)]
        mixin = _make_mixin_with_quarters(rows)
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result is None

    def test_duplicate_period_end_returns_none(self) -> None:
        # A restated/duplicate filing row for the same reporting period would let "4 most
        # recent rows by period_end" double-count one quarter's EPS while a genuinely
        # different quarter was never loaded - must be rejected, not silently summed.
        rows = [
            (_TODAY - timedelta(days=10), 5.0),
            (_TODAY - timedelta(days=10), 5.0),  # duplicate period_end
            (_TODAY - timedelta(days=190), 5.0),
            (_TODAY - timedelta(days=280), 5.0),
        ]
        mixin = _make_mixin_with_quarters(rows)
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result is None

    def test_gapped_quarters_returns_none(self) -> None:
        # A quarter missing between two loaded ones (e.g. Q2 never filed/loaded) leaves an
        # ~180+ day gap between consecutive period_ends instead of the normal ~91 days -
        # summing across the gap is not a true trailing-twelve-month figure.
        rows = [
            (_TODAY - timedelta(days=10), 5.0),
            (_TODAY - timedelta(days=100), 5.0),
            (_TODAY - timedelta(days=290), 5.0),  # ~190 day gap from the row above
            (_TODAY - timedelta(days=380), 5.0),
        ]
        mixin = _make_mixin_with_quarters(rows)
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_eps_from_quarters("TEST")
        assert result is None


class TestSanityCheckPeRatioTtmRescue:
    def test_reconciling_ttm_from_quarters_keeps_original_pe_ratio(self) -> None:
        # annual-EPS-based pe_ratio=94.2 (stale) vs yfinance TTM pe_ratio=9.8 (live) - a ~9.6x
        # gap alone wouldn't even trip the >10x gate, so widen it: use a >10x-triggering pair
        # where the TTM-from-quarters EPS reconciles with yfinance instead.
        mixin = _make_mixin_with_quarters(_RECENT_QUARTERS)  # sums to eps=20.0
        result = {"pe_ratio": 942.0, "current_price": 100.0}  # 100/942 implies eps~0.106 (stale)
        with (
            patch.object(mixin, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
            patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx),
        ):
            # yf pe_ratio=5.0 -> pe_from_quarters = 100/20.0 = 5.0, reconciles exactly.
            mixin._sanity_check_pe_ratio("TEST", result, yf_pe_ratio=5.0, yf_value_is_live=True)
        assert result["pe_ratio"] == 942.0
        assert result.get("reason") is None

    def test_non_reconciling_ttm_from_quarters_still_nulls(self) -> None:
        mixin = _make_mixin_with_quarters(_RECENT_QUARTERS)  # sums to eps=20.0 -> pe_from_quarters=5.0
        result = {"pe_ratio": 942.0, "current_price": 100.0}
        with (
            patch.object(mixin, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
            patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx),
        ):
            # yf pe_ratio=60.0: triggers the initial gate (942/60=15.7x) AND still diverges from
            # pe_from_quarters (5.0 vs 60.0 = 12x) - a genuine mismatch even after the rescue.
            mixin._sanity_check_pe_ratio("TEST", result, yf_pe_ratio=60.0, yf_value_is_live=True)
        assert result["pe_ratio"] is None
        assert result["peg_ratio"] is None
        assert result["reason"] == "eps_scale_mismatch"

    def test_no_quarterly_data_still_nulls(self) -> None:
        mixin = _make_mixin_with_quarters([])
        result = {"pe_ratio": 942.0, "current_price": 100.0}
        with (
            patch.object(mixin, "_fetch_live_fpi_yfinance_check_values", return_value=(None, None, None)),
            patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx),
        ):
            mixin._sanity_check_pe_ratio("TEST", result, yf_pe_ratio=5.0, yf_value_is_live=True)
        assert result["pe_ratio"] is None
        assert result["peg_ratio"] is None
        assert result["reason"] == "eps_scale_mismatch"
