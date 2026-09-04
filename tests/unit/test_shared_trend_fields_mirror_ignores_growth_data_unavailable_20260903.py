"""Regression test: _mirror_shared_trend_fields must not let growth's own data_unavailable

state clobber a real quality-computed value for a _SHARED_TREND_FIELDS field like
sustainable_growth_rate.

Root cause: _compute_growth_metrics's len(failed_metrics)==7 branch (all revenue/EPS growth
periods failed) stamps every _SHARED_TREND_FIELDS reason with its own blanket "Insufficient
historical data: revenue_growth_1y, ... could not be computed" string and sets
growth_dict["data_unavailable"] = True. The mirror that copies sustainable_growth_rate (computed
independently in _compute_quality_metrics from ROE/dividends, unrelated to growth's revenue/EPS
history) from quality_dict into growth_dict used to skip entirely whenever growth_dict was
data_unavailable, discarding a real quality-side value and reason. Live-confirmed 59 symbols
(PALL, AGRZ, ALMS, BXBL, MIRA, and more) had quality_metrics.sustainable_growth_rate populated
while growth_metrics.sustainable_growth_rate sat NULL with a revenue/EPS-shaped reason that had
nothing to do with sustainable_growth_rate.
"""

from loaders.load_value_quality_growth_metrics import _SHARED_TREND_FIELDS, _mirror_shared_trend_fields


class TestMirrorSharedTrendFieldsIgnoresGrowthDataUnavailable:
    def test_real_quality_value_overrides_growth_blanket_reason(self) -> None:
        quality_dict = {
            "sustainable_growth_rate": 31.09,
            "sustainable_growth_rate_unavailable_reason": None,
        }
        growth_dict = {
            "data_unavailable": True,
            "reason": "Insufficient historical data: revenue_growth_1y, eps_growth_1y could not be computed",
            "sustainable_growth_rate": None,
            "sustainable_growth_rate_unavailable_reason": (
                "Insufficient historical data: revenue_growth_1y, eps_growth_1y could not be computed"
            ),
        }

        _mirror_shared_trend_fields(quality_dict, growth_dict)

        assert growth_dict["sustainable_growth_rate"] == 31.09
        assert growth_dict["sustainable_growth_rate_unavailable_reason"] is None

    def test_quality_specific_reason_still_propagates_when_no_value(self) -> None:
        quality_dict = {
            "sustainable_growth_rate": None,
            "sustainable_growth_rate_unavailable_reason": "no_recent_balance_sheet_data_reported",
        }
        growth_dict = {
            "data_unavailable": True,
            "reason": "Insufficient historical data: revenue_growth_1y could not be computed",
            "sustainable_growth_rate": None,
            "sustainable_growth_rate_unavailable_reason": (
                "Insufficient historical data: revenue_growth_1y could not be computed"
            ),
        }

        _mirror_shared_trend_fields(quality_dict, growth_dict)

        assert growth_dict["sustainable_growth_rate"] is None
        assert growth_dict["sustainable_growth_rate_unavailable_reason"] == "no_recent_balance_sheet_data_reported"

    def test_both_sides_missing_keeps_growth_own_reason(self) -> None:
        quality_dict = {"sustainable_growth_rate": None, "sustainable_growth_rate_unavailable_reason": None}
        growth_dict = {
            "data_unavailable": True,
            "reason": "Insufficient historical data: revenue_growth_1y could not be computed",
            "sustainable_growth_rate": None,
            "sustainable_growth_rate_unavailable_reason": (
                "Insufficient historical data: revenue_growth_1y could not be computed"
            ),
        }

        _mirror_shared_trend_fields(quality_dict, growth_dict)

        assert growth_dict["sustainable_growth_rate"] is None
        assert (
            growth_dict["sustainable_growth_rate_unavailable_reason"]
            == "Insufficient historical data: revenue_growth_1y could not be computed"
        )

    def test_mirrors_every_shared_trend_field(self) -> None:
        quality_dict = dict.fromkeys(_SHARED_TREND_FIELDS, 1.0)
        quality_dict.update({f"{f}_unavailable_reason": None for f in _SHARED_TREND_FIELDS})
        growth_dict = {"data_unavailable": True, "reason": "irrelevant"}
        for f in _SHARED_TREND_FIELDS:
            growth_dict[f] = None
            growth_dict[f"{f}_unavailable_reason"] = "irrelevant"

        _mirror_shared_trend_fields(quality_dict, growth_dict)

        for f in _SHARED_TREND_FIELDS:
            assert growth_dict[f] == 1.0
            assert growth_dict[f"{f}_unavailable_reason"] is None
