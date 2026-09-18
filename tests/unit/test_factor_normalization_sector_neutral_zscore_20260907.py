"""Tests for loaders/helpers/factor_normalization.py's sector_neutral_zscore/
zscore_to_percentile_scale - the shared winsorize-then-z-score-within-sector transform
extracted for Quality's move off hand-tuned per-industry breakpoint curves onto published
multi-factor methodology (MSCI Barra/AQR QMJ/Fama-French)."""

import math

from loaders.helpers.factor_normalization import (
    _winsorize_group,
    _zscore_group,
    sector_neutral_zscore,
    zscore_to_percentile_scale,
)


class TestWinsorizeGroup:
    def test_below_min_group_size_passes_through_unchanged(self) -> None:
        values = {"A": 1.0, "B": 2.0, "C": 1000.0}
        assert _winsorize_group(values) == values

    def test_clips_extreme_outlier_within_larger_group(self) -> None:
        values = {f"S{i}": float(i) for i in range(1, 20)}
        values["OUTLIER"] = 100000.0
        result = _winsorize_group(values)
        assert result["OUTLIER"] < 100000.0
        assert result["S10"] == 10.0  # non-extreme values untouched


class TestZscoreGroup:
    def test_single_symbol_gets_zero(self) -> None:
        assert _zscore_group({"ONLY": 42.0}) == {"ONLY": 0.0}

    def test_zero_variance_group_gets_zero(self) -> None:
        assert _zscore_group({"A": 5.0, "B": 5.0, "C": 5.0}) == {"A": 0.0, "B": 0.0, "C": 0.0}

    def test_mean_value_scores_near_zero(self) -> None:
        result = _zscore_group({"LOW": 0.0, "MID": 10.0, "HIGH": 20.0})
        assert abs(result["MID"]) < 1e-9
        assert result["HIGH"] > 0.0
        assert result["LOW"] < 0.0

    def test_zscore_clipped_to_plus_minus_3(self) -> None:
        # A genuine outlier (1000 vs a tight 1-19 cluster) must not blow past the MSCI-real
        # +/-3 sigma clip, even though it's far more than 3 raw-value sigma from the mean.
        values = {f"S{i}": float(i) for i in range(1, 20)}
        values["OUTLIER"] = 1000.0
        result = _zscore_group(values)
        assert result["OUTLIER"] == 3.0
        assert all(-3.0 <= z <= 3.0 for z in result.values())

    def test_non_extreme_values_beyond_winsorize_bound_still_differentiated(self) -> None:
        # REGRESSION for the 2026-09-18 fix: before the fix, every value >= the 95th
        # percentile boundary was clipped to the SAME raw value before z-scoring, so they all
        # produced the exact same z-score. Real MSCI z-scores the ORIGINAL value against a
        # robust mean/stdev - two different top-tail values must still get different z-scores,
        # not tie, as long as neither is extreme enough to hit the final +/-3 clip.
        values = {f"S{i}": float(i) for i in range(1, 21)}  # 1..20, evenly spaced, no outliers
        result = _zscore_group(values)
        # S19 and S20 both sit above any reasonable 95th percentile of this population but are
        # genuinely different raw values - they must score differently, not tie.
        assert result["S19"] != result["S20"]
        assert result["S20"] > result["S19"]

    def test_market_cap_extreme_tie_bug_reproduction_fixed(self) -> None:
        # Directly reproduces the live-verified production symptom (15+ distinct symbols tied
        # at the exact same pillar score) on a synthetic population and confirms it's gone:
        # a broad, continuous distribution's top ~10% (which used to all collapse onto the
        # winsorize boundary) must now show real spread, with ties only among the genuinely
        # 3+ sigma outliers (if any).
        values = {f"S{i}": float(i) for i in range(1, 101)}  # 1..100
        result = _zscore_group(values)
        top_15_scores = sorted(result.values(), reverse=True)[:15]
        assert len(set(top_15_scores)) > 1, "top 15 must not all tie at one clipped value"


class TestSectorNeutralZscore:
    def test_empty_input_returns_empty(self) -> None:
        assert sector_neutral_zscore({}, {}) == {}

    def test_sectors_at_or_above_min_size_scored_within_sector(self) -> None:
        # Two sectors, 15 symbols each (meets default min_sector_size=15) - Banks' raw values
        # run far lower than Tech's, but a mid-ranked bank should still land near zero (scored
        # against bank peers), not deeply negative (which pooling with Tech would produce).
        sectors = {}
        values = {}
        for i in range(15):
            sym = f"BANK{i}"
            sectors[sym] = "Financial Services"
            values[sym] = 1.0 + i * 0.1  # tight low range
        for i in range(15):
            sym = f"TECH{i}"
            sectors[sym] = "Technology"
            values[sym] = 20.0 + i  # much higher range

        result = sector_neutral_zscore(values, sectors, min_sector_size=15)
        mid_bank = result["BANK7"]  # middle of the bank distribution
        mid_tech = result["TECH7"]
        assert abs(mid_bank) < 0.5
        assert abs(mid_tech) < 0.5

    def test_small_sector_pools_into_residual(self) -> None:
        sectors = {"A": "TinySector", "B": "TinySector", "C": None, "D": None}  # type: ignore[dict-item]
        values = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
        result = sector_neutral_zscore(values, sectors, min_sector_size=15)
        # All 4 land in one residual pool (2 below min_sector_size + 2 with no sector entry) -
        # every symbol must still get a score, none dropped.
        assert set(result.keys()) == {"A", "B", "C", "D"}

    def test_missing_sector_entry_pools_into_residual(self) -> None:
        result = sector_neutral_zscore({"X": 1.0, "Y": 2.0}, {}, min_sector_size=15)
        assert set(result.keys()) == {"X", "Y"}


class TestSectorNeutralZscoreFpiPeerGroupSplit:
    """FPI peer-group split (added 2026-09-14) - an FPI must never be scored against its
    domestic GICS-sector peers; it goes into one global cross-sector FPI pool instead."""

    def test_fpi_pooled_globally_not_scored_against_domestic_sector(self) -> None:
        sectors = {}
        values = {}
        fpi = {}
        for i in range(15):
            sym = f"US{i}"
            sectors[sym] = "Financial Services"
            values[sym] = 1.0 + i * 0.1  # tight low range
            fpi[sym] = False
        # FPI value would be a deep outlier against the domestic bank sector's tight range,
        # but sits mid-pack among other FPIs.
        for i in range(15):
            sym = f"FPI{i}"
            sectors[sym] = "Financial Services"
            values[sym] = 20.0 + i
            fpi[sym] = True

        result = sector_neutral_zscore(values, sectors, min_sector_size=15, is_foreign_private_issuer=fpi)
        assert abs(result["FPI7"]) < 0.5  # mid-pack among FPI peers, not a domestic outlier
        assert abs(result["US7"]) < 0.5

    def test_fpi_flag_defaults_to_no_split_when_omitted(self) -> None:
        sectors = {"A": "Financial Services", "B": "Financial Services"}
        values = {"A": 1.0, "B": 2.0}
        assert sector_neutral_zscore(values, sectors) == sector_neutral_zscore(
            values, sectors, is_foreign_private_issuer=None
        )

    def test_all_fpi_still_scored_none_dropped(self) -> None:
        sectors = {"A": "Financial Services", "B": "Technology"}
        values = {"A": 1.0, "B": 2.0}
        fpi = {"A": True, "B": True}
        result = sector_neutral_zscore(values, sectors, is_foreign_private_issuer=fpi)
        assert set(result.keys()) == {"A", "B"}


class TestZscoreToPercentileScale:
    def test_zero_zscore_maps_to_fifty(self) -> None:
        result = zscore_to_percentile_scale({"A": 0.0})
        assert math.isclose(result["A"], 50.0)

    def test_positive_zscore_maps_above_fifty(self) -> None:
        result = zscore_to_percentile_scale({"A": 2.0})
        assert result["A"] > 50.0

    def test_negative_zscore_maps_below_fifty(self) -> None:
        result = zscore_to_percentile_scale({"A": -2.0})
        assert result["A"] < 50.0

    def test_output_bounded_in_0_100(self) -> None:
        result = zscore_to_percentile_scale({"A": -10.0, "B": 10.0})
        assert 0.0 <= result["A"] <= 100.0
        assert 0.0 <= result["B"] <= 100.0
