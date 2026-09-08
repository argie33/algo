"""Regression test for the 2026-09-07 fix: `_percent_rank_cheap_high_sector_relative` used to
rank raw P/E/P/B/P/S with no winsorization - the single most extreme raw ratio in a sector
always won percentile 100 alone, even when that extremeness was a data/accounting artifact
rather than genuine mispricing (live-confirmed: VCIG's pb_ratio=0.01/ps_ratio=0.02, tied for the
cheapest in a 4,500+-symbol universe, both won percentile 100/99.8 outright).

Fix (`_winsorize_group_values`, [1st, 99th] percentile clip per sector/residual group before
ranking): validated via algo/research/value_percentile_rank_winsorization_test_20260907.py
(Fama-MacBeth + Spearman IC, fit 2017-2021 / holdout 2022-2026) to be statistically
indistinguishable from the old unwinsorized ranking on every aggregate spec, while closing the
single-observation-monopoly gap. See loaders/stock_scores/value_metrics.py's
_winsorize_group_values docstring for the full evidence trail.
"""

from loaders.stock_scores.value_metrics import ValueMetricsMixin


class TestWinsorizeGroupValues:
    def test_small_group_passes_through_unclipped(self):
        """Below _WINSORIZE_MIN_GROUP_SIZE (5), a quantile isn't a trustworthy clip boundary -
        values must pass through unchanged."""
        values = {"A": 1.0, "B": 2.0, "C": 100.0}

        result = ValueMetricsMixin._winsorize_group_values(values)

        assert result == values

    def test_extreme_outlier_clipped_to_boundary(self):
        """A single extreme value (VCIG-shaped: near-zero ratio far below its peers) gets
        clipped up to the group's 1st-percentile boundary instead of staying uniquely extreme."""
        values = {f"SYM{i}": float(i) for i in range(1, 21)}  # 1.0..20.0, evenly spaced
        values["OUTLIER"] = 0.0001  # far below SYM1=1.0

        result = ValueMetricsMixin._winsorize_group_values(values)

        assert result["OUTLIER"] > values["OUTLIER"]
        assert result["OUTLIER"] < result["SYM1"] or result["OUTLIER"] == result["SYM1"]
        # Everything comfortably inside the band is untouched.
        assert result["SYM10"] == values["SYM10"]

    def test_mid_range_values_unaffected(self):
        """Normal, non-extreme values in the interior of the distribution must be untouched."""
        values = {f"SYM{i}": float(i) for i in range(1, 51)}

        result = ValueMetricsMixin._winsorize_group_values(values)

        for sym in ("SYM20", "SYM25", "SYM30"):
            assert result[sym] == values[sym]


class TestPercentRankCheapHighSectorRelativeWinsorized:
    def test_two_extreme_outliers_tie_instead_of_one_monopolizing_top(self):
        """VCIG-shaped case, generalized: TWO symbols' raw ratios are both far cheaper than
        everyone else's real peer group (both fall below the 1st-percentile clip boundary - a
        big-enough group, 150 members, is needed for the interpolated 1st-percentile boundary to
        actually fall strictly above BOTH extreme points, matching realistic sector sizes which
        run into the hundreds/thousands live). Before this fix, one would arbitrarily rank #1
        (percentile 100) and the other #2 purely off noise in which near-zero value happened to
        be marginally smaller. After the fix, clipping pulls both up to the SAME winsorized
        boundary, so they TIE and share percentile 100 together instead of one monopolizing it
        alone."""
        n_real = 148
        sector_map = {f"SYM{i}": "Technology" for i in range(1, n_real + 1)}
        sector_map["OUTLIER_A"] = "Technology"
        sector_map["OUTLIER_B"] = "Technology"
        values = {f"SYM{i}": float(i) for i in range(1, n_real + 1)}  # 1.0 (cheapest real) .. 148.0
        values["OUTLIER_A"] = 0.0001
        values["OUTLIER_B"] = 0.0002  # both far cheaper than SYM1, and of each other

        result = ValueMetricsMixin._percent_rank_cheap_high_sector_relative(values, sector_map)

        assert result["OUTLIER_A"] == result["OUTLIER_B"] == 100.0
        # SYM1 (the cheapest REAL value) still ranks below the tied outlier pair, unaffected.
        assert result["SYM1"] < 100.0

    def test_normal_ranking_unaffected_for_typical_values(self):
        """No extreme outliers present - winsorization must not change the ranking at all."""
        sector_map = {f"SYM{i}": "Healthcare" for i in range(1, 31)}
        values = {f"SYM{i}": float(i) for i in range(1, 31)}

        result = ValueMetricsMixin._percent_rank_cheap_high_sector_relative(values, sector_map)

        assert result["SYM1"] == 100.0  # cheapest still wins
        assert result["SYM30"] == 0.0  # priciest still floors
        assert result["SYM15"] > result["SYM16"]  # relative order preserved throughout

    def test_residual_pool_fallback_still_winsorized(self):
        """Symbols with no sector still get winsorized via the residual-pool path (not just the
        per-sector path) - same 150-member, two-outlier construction as the sector-path test
        above, but with no sector_map entries at all so every symbol routes through `residual`."""
        n_real = 148
        sector_map: dict[str, str] = {}  # no sector for anyone -> all 150 fall into residual
        values = {f"SYM{i}": float(i) for i in range(1, n_real + 1)}
        values["OUTLIER_A"] = 0.0001
        values["OUTLIER_B"] = 0.0002

        result = ValueMetricsMixin._percent_rank_cheap_high_sector_relative(values, sector_map)

        assert result["OUTLIER_A"] == result["OUTLIER_B"] == 100.0
        assert result["SYM1"] < 100.0
