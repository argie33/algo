"""Regression test (2026-09-04, goal: "Missing SEC/XBRL data" reduction, real-scoring-consumption
follow-up to test_quality_row_level_unavailable_preserves_quarterly_20260904.py):
StockScoresLoader._get_growth_metrics used to wholesale-discard the entire growth_metrics row
via marker_not_applicable whenever data_unavailable=True, even when individual fields
(quarterly_growth_momentum/earnings_growth_4q_avg/sustainable_growth_rate) carried real values -
_mirror_shared_trend_fields() in load_value_quality_growth_metrics.py deliberately writes those
regardless of the row's own data_unavailable flag, but this consumer-side gate discarded them
anyway before _score_growth's own partial-availability blend ever saw them.

Live-confirmed 121 growth_metrics rows have data_unavailable=TRUE but a real mirrored value.
"""

from loaders.load_stock_scores import StockScoresLoader

# 25-column row shape: revenue_growth_1y/3y/5y, eps_growth_1y/3y/5y, book_value_growth,
# net_income_growth_yoy, operating_income_growth_yoy, sustainable_growth_rate, fcf_growth_yoy,
# ocf_growth_yoy, gross/operating/net_margin_trend, roe_trend, asset_growth_yoy,
# eps_growth_stability, quarterly_growth_momentum, earnings_growth_4q_avg,
# forward_eps_growth_current_fy, forward_eps_growth_next_fy, forward_revenue_growth_next_fy,
# eps_estimate_revision_90d_pct, data_unavailable.


def _row(quarterly_growth_momentum=None, earnings_growth_4q_avg=None, data_unavailable=True):
    row = [None] * 25
    row[18] = quarterly_growth_momentum
    row[19] = earnings_growth_4q_avg
    row[24] = data_unavailable
    return tuple(row)


def _make_loader(growth_cache):
    loader = StockScoresLoader.__new__(StockScoresLoader)
    loader._growth_cache = growth_cache
    return loader


class TestGetGrowthMetricsPartialAvailabilityDespiteRowFlag:
    def test_data_unavailable_but_real_quarterly_value_survives(self):
        loader = _make_loader({"SYM": _row(quarterly_growth_momentum=12.5, data_unavailable=True)})

        result = loader._get_growth_metrics(None, "SYM")

        assert result.get("quarterly_growth_momentum") == 12.5
        assert not result.get("data_unavailable")

    def test_fully_empty_row_with_flag_still_falls_through_safely(self):
        # No mirrored real values at all - every field None. Must not raise, and must still be
        # scoreable-as-empty (no "data_unavailable" key so _score_growth's own field-counting
        # logic correctly lands on "no_growth_inputs_available", not a crash).
        loader = _make_loader({"SYM": _row(data_unavailable=True)})

        result = loader._get_growth_metrics(None, "SYM")

        assert result.get("quarterly_growth_momentum") is None
        score = loader._score_growth(result, "SYM")
        assert isinstance(score, dict)
        assert score["reason"] == "no_growth_inputs_available"

    def test_real_row_data_unavailable_false_unaffected(self):
        loader = _make_loader({"SYM": _row(quarterly_growth_momentum=8.0, data_unavailable=False)})

        result = loader._get_growth_metrics(None, "SYM")

        assert result.get("quarterly_growth_momentum") == 8.0

    def test_no_row_at_all_still_returns_loader_failed_marker(self):
        loader = _make_loader({})

        result = loader._get_growth_metrics(None, "SYM")

        assert result.get("data_unavailable") is True
