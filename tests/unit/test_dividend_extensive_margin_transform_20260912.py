"""Regression test for loaders/stock_scores/value_metrics.py's
_dividend_extensive_transform - the real, evidence-backed fix for the dividend_yield
extensive-vs-intensive margin gap (see that function's own module-level docstring,
DIVIDEND_EXTENSIVE_SATURATION_K, for the full IC-test evidence trail).

A real point-in-time IC test found dividend_yield's predictive power is ~entirely
extensive-margin (pays a dividend at all) with no robust intensive-margin (magnitude among
payers) signal. This saturating transform should therefore: (1) keep 0/negative exactly at
0.0, (2) jump most of the way to its ceiling for ANY small positive payer, (3) still be
strictly monotonic so a real ordering between two positive yields is never inverted.
"""

from loaders.stock_scores.value_metrics import _dividend_extensive_transform


class TestDividendExtensiveMarginTransform:
    def test_zero_or_negative_stays_exactly_zero(self):
        assert _dividend_extensive_transform(0.0) == 0.0
        assert _dividend_extensive_transform(-0.01) == 0.0

    def test_small_payer_reaches_most_of_ceiling(self):
        """A modest, real payer (e.g. Visa/Mastercard-style ~0.5-0.7% yield) should score
        close to a large payer, not close to a non-payer - the whole point of the fix."""
        small_payer = _dividend_extensive_transform(0.005)  # 0.5% yield
        large_payer = _dividend_extensive_transform(0.06)  # 6% yield
        non_payer = _dividend_extensive_transform(0.0)

        assert small_payer > 0.5, "a real 0.5% payer should already be over halfway to ceiling"
        assert (large_payer - small_payer) < (small_payer - non_payer), (
            "the gap from non-payer to a small payer should be bigger than the gap from a "
            "small payer to a large payer - the extensive margin dominates, per the IC evidence"
        )

    def test_strictly_monotonic_for_positive_inputs(self):
        """Never invert a real ordering between two positive yields - conservative, not a hard
        step function, per the module docstring."""
        values = [0.001, 0.005, 0.01, 0.02, 0.04, 0.06, 0.10]
        transformed = [_dividend_extensive_transform(v) for v in values]
        assert transformed == sorted(transformed)
        assert len(set(transformed)) == len(transformed)

    def test_saturates_close_to_one_for_large_yields(self):
        assert _dividend_extensive_transform(0.06) > 0.98

    def test_matches_documented_saturation_curve(self):
        """K=0.005 documented in the module docstring: 0.5% -> ~63%, 1% -> ~86%, 2%+ -> >98%."""
        assert abs(_dividend_extensive_transform(0.005) - 0.632) < 0.01
        assert abs(_dividend_extensive_transform(0.01) - 0.865) < 0.01
        assert _dividend_extensive_transform(0.02) > 0.98
