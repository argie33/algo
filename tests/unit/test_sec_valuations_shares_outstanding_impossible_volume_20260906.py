"""Regression test for _sanity_check_shares_outstanding_vs_volume (2026-09-06, stock_scores
symbol spot-check goal session - see shares_outstanding_impossible_volume_gate in memory for
the full writeup).

_sanity_check_market_cap already catches a >10x disagreement with yfinance_snapshot.market_cap,
but that ratio gate missed CISS: its SEC-derived shares_outstanding (274,402) implied
market_cap=$408,859 vs yfinance's $2,595,698 - only a 6.35x gap, under the 10x bar. An
independent, always-available signal proves it wrong anyway: CISS traded 12,332,426 shares in a
single day within the prior 30 days - mathematically impossible for a stock with only 274,402
total shares. price_daily's own recorded volume doesn't depend on yfinance being fresh/available
at all.
"""

from typing import Any

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, max_volume: float | None):
        self._max_volume = max_volume
        self.executed_params: tuple[Any, ...] | None = None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed_params = params

    def fetchone(self) -> tuple[float | None] | None:
        return (self._max_volume,)


class TestSharesOutstandingImpossibleVolumeCheck:
    def test_impossible_volume_nulls_dependent_fields(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {
            "shares_outstanding": 274_402.0,
            "market_cap": 408_858.98,
            "pb_ratio": 1.5,
            "ps_ratio": 2.0,
            "fcf_yield": 847.41,
            "pe_ratio": 12.0,
        }
        cur = _FakeCursor(max_volume=12_332_426.0)

        loader._sanity_check_shares_outstanding_vs_volume("CISS", result, cur)

        assert result["market_cap"] is None
        assert result["pb_ratio"] is None
        assert result["ps_ratio"] is None
        assert result["fcf_yield"] is None
        assert result["reason"] == "shares_outstanding_scale_mismatch"
        # pe_ratio doesn't depend on shares_outstanding - untouched, same as
        # _sanity_check_market_cap's own convention.
        assert result["pe_ratio"] == 12.0

    def test_plausible_volume_leaves_result_untouched(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {
            "shares_outstanding": 5_541_670.0,
            "market_cap": 4_045_419.10,
            "fcf_yield": 423.22,
        }
        # TOPS-shaped case: real, extreme value but shares_outstanding is internally consistent
        # with its own trading volume - must not be touched.
        cur = _FakeCursor(max_volume=331_400.0)

        loader._sanity_check_shares_outstanding_vs_volume("TOPS", result, cur)

        assert result["market_cap"] == 4_045_419.10
        assert result["fcf_yield"] == 423.22
        assert result.get("reason") is None

    def test_volume_exactly_equal_to_shares_outstanding_is_not_flagged(self) -> None:
        # Boundary: trading every single share in one day is unusual but not impossible
        # (unlike exceeding the total count) - only a strict > triggers the guard.
        loader = _make_loader()
        result: dict[str, Any] = {"shares_outstanding": 1_000_000.0, "market_cap": 5_000_000.0}
        cur = _FakeCursor(max_volume=1_000_000.0)

        loader._sanity_check_shares_outstanding_vs_volume("EDGECO", result, cur)

        assert result["market_cap"] == 5_000_000.0
        assert result.get("reason") is None

    def test_missing_shares_outstanding_is_a_noop(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"shares_outstanding": None, "market_cap": 5_000_000.0}
        cur = _FakeCursor(max_volume=999_999_999.0)

        loader._sanity_check_shares_outstanding_vs_volume("NOSHARES", result, cur)

        assert result["market_cap"] == 5_000_000.0
        assert result.get("reason") is None

    def test_no_recent_volume_data_is_a_noop(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {"shares_outstanding": 274_402.0, "market_cap": 408_858.98}
        cur = _FakeCursor(max_volume=None)

        loader._sanity_check_shares_outstanding_vs_volume("QUIETCO", result, cur)

        assert result["market_cap"] == 408_858.98
        assert result.get("reason") is None

    def test_existing_more_specific_reason_is_not_overwritten(self) -> None:
        loader = _make_loader()
        result: dict[str, Any] = {
            "shares_outstanding": 274_402.0,
            "market_cap": 408_858.98,
            "reason": "some_other_independent_cause",
        }
        cur = _FakeCursor(max_volume=12_332_426.0)

        loader._sanity_check_shares_outstanding_vs_volume("CISS", result, cur)

        assert result["market_cap"] is None
        assert result["reason"] == "some_other_independent_cause"
