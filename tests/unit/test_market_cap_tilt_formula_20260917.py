"""Tests for algo/signals/market_cap_tilt.py's compute_tilted_weights()/tilt_score_from_zscore()
- the MSCI Tilt Index formula, now the single shared implementation every API endpoint that
displays a tilted weight imports directly, computed at request time rather than read from a
stored stock_scores column (migration 1308 dropped the 6 *_tilted_weight columns migration
1294 had added - see this module's own docstring for the full rationale).

SUPERSEDES tests/unit/test_market_cap_tilted_weights_20260915.py (deleted 2026-09-17), which
tested loaders/stock_scores/market_cap_tilt.py's now-deleted batch pass
(update_market_cap_tilted_weights) - same formula, different (removed) call site. The
assertions below migrate that file's meaningful invariants to the pure function directly.
"""

from algo.signals.market_cap_tilt import compute_tilted_weights, tilt_score_from_zscore


class TestTiltScoreFromZscore:
    def test_zero_z_is_neutral_multiplier_one(self) -> None:
        assert tilt_score_from_zscore(0.0) == 1.0

    def test_positive_z_uses_one_plus_z(self) -> None:
        assert tilt_score_from_zscore(1.0) == 2.0

    def test_negative_z_uses_reciprocal_form(self) -> None:
        assert tilt_score_from_zscore(-1.0) == 0.5

    def test_winsorized_at_plus_minus_three(self) -> None:
        assert tilt_score_from_zscore(10.0) == tilt_score_from_zscore(3.0)
        assert tilt_score_from_zscore(-10.0) == tilt_score_from_zscore(-3.0)


class TestComputeTiltedWeights:
    def test_larger_market_cap_gets_larger_tilted_weight_at_equal_score(self) -> None:
        # Three symbols with identical score (same z, same tilt multiplier) must rank by
        # market_cap alone. A 4th differently-scored symbol gives the population nonzero
        # variance (stdev=0 would otherwise make every z-score 0/tilt 1.0, masking this).
        scores = {"BIG": 50.0, "MED": 50.0, "SMALL": 50.0, "OTHER": 80.0}
        caps = {"BIG": 3_000_000_000.0, "MED": 1_000_000_000.0, "SMALL": 100_000_000.0, "OTHER": 500_000_000.0}
        weights = compute_tilted_weights(scores, caps)
        assert weights["BIG"] > weights["MED"] > weights["SMALL"]

    def test_higher_score_tilts_weight_up_at_equal_market_cap(self) -> None:
        scores = {"HIGH": 90.0, "LOW": 10.0, "MID": 50.0}
        caps = {"HIGH": 1_000_000_000.0, "LOW": 1_000_000_000.0, "MID": 1_000_000_000.0}
        weights = compute_tilted_weights(scores, caps)
        assert weights["HIGH"] > weights["MID"] > weights["LOW"]

    def test_missing_market_cap_excluded_not_fabricated(self) -> None:
        scores = {"A": 50.0, "B": 60.0, "NO_CAP": 70.0}
        caps = {"A": 1_000_000_000.0, "B": 2_000_000_000.0}
        weights = compute_tilted_weights(scores, caps)
        assert "NO_CAP" not in weights
        assert "A" in weights and "B" in weights

    def test_non_positive_market_cap_excluded(self) -> None:
        scores = {"A": 50.0, "B": 60.0, "ZERO_CAP": 70.0}
        caps = {"A": 1_000_000_000.0, "B": 2_000_000_000.0, "ZERO_CAP": 0.0}
        weights = compute_tilted_weights(scores, caps)
        assert "ZERO_CAP" not in weights

    def test_single_symbol_population_produces_no_signal_not_a_crash(self) -> None:
        assert compute_tilted_weights({"ONLY": 50.0}, {"ONLY": 1_000_000_000.0}) == {}

    def test_weights_sum_to_100(self) -> None:
        scores = {"A": 50.0, "B": 60.0, "C": 40.0, "D": 70.0}
        caps = {"A": 1e9, "B": 2e9, "C": 3e9, "D": 4e9}
        weights = compute_tilted_weights(scores, caps)
        assert abs(sum(weights.values()) - 100.0) < 1e-9
