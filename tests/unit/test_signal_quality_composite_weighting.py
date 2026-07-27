#!/usr/bin/env python3
"""Regression test: composite_sqs must preserve each component's designed weight.

load_signal_quality_scores.py._compute_quality_scores() combines seven scored
components with different point ceilings (base_quality max 50, trend_template max
25, ..., vcp_pattern max 10) into one 0-100 composite. Commit 2bd9e9433 fixed a real
bug (raw point-sum could exceed 100 and got lossily clamped) by normalizing each
component to its OWN 0-100% first and then averaging those percentages with equal
weight - which silently discarded the intended weighting: institutional_ownership
(max 10 raw points) ended up exactly as influential on the composite as base_quality
(max 50 raw points), a 5x weighting inversion from the as-designed scale. This score
is synced live into buy_sell_daily.signal_quality_score/entry_quality_score, so the
inversion affected real trade-quality signals with no test ever catching it.

Fixed to a weighted sum of available raw values over the sum of THEIR max values,
which preserves the intended per-component weighting while still naturally bounding
to [0, 100] without any lossy clamp (the original bug this all started from).
"""

from datetime import date

import pandas as pd

from loaders.load_signal_quality_scores import SignalQualityScoresLoader


def _loader() -> SignalQualityScoresLoader:
    return SignalQualityScoresLoader.__new__(SignalQualityScoresLoader)


def test_composite_weights_by_component_max_not_equal_average():
    loader = _loader()

    buy_sell_rows = [{"date": date(2026, 7, 20).isoformat(), "signal_type": "BUY"}]
    # No technical/trend confirmation data at all -> volume_confirmation, trend_template,
    # distance_from_high, and market_stage all resolve to their present-but-zero default.
    technical_rows: list = []
    trend_rows: list = []
    vcp_rows: list = []  # vcp_pattern_score stays None (genuinely unavailable)
    # institutional_ownership >= 60 -> scores the max 10 points, same raw value as the
    # (also present) trend_template zero, but on a much smaller max (10 vs 25) - this is
    # exactly the case the old equal-weighted-average formula got wrong.
    positioning_data = {"institutional_ownership": 70.0}

    results = loader._compute_quality_scores(
        "TEST", buy_sell_rows, technical_rows, trend_rows, vcp_rows, positioning_data
    )

    assert len(results) == 1
    row = results[0]

    # Available components: base_quality=50/50, volume_confirmation=0/20,
    # trend_template=0/25, distance_from_high=0/15, institutional_ownership=10/10,
    # market_stage=0/10 (vcp_pattern is None/unavailable, excluded).
    # Weighted-sum-over-available-maxes: (50+0+0+0+10+0) / (50+20+25+15+10+10) * 100
    expected_total_max = 50 + 20 + 25 + 15 + 10 + 10
    expected_numerator = 50 + 0 + 0 + 0 + 10 + 0
    expected_composite = int(expected_numerator / expected_total_max * 100)

    assert row["composite_sqs"] == expected_composite

    # The old (buggy) equal-weighted-average formula would have averaged
    # [100, 0, 0, 0, 100, 0] (each component normalized to its own 0-100%) = 33,
    # letting institutional_ownership's 10-point ceiling outweigh trend_template's
    # 25-point ceiling. Assert the fix actually changed the number, not just that a
    # plausible-looking value comes out.
    old_buggy_composite = int(sum([100, 0, 0, 0, 100, 0]) / 6)
    assert row["composite_sqs"] != old_buggy_composite
    assert row["composite_sqs"] == 46


def test_composite_is_bounded_when_all_components_present_and_maxed():
    loader = _loader()

    buy_sell_rows = [{"date": date(2026, 7, 20).isoformat(), "signal_type": "BUY"}]
    technical_rows = [{"date": date(2026, 7, 20).isoformat(), "rsi": 60.0, "macd": 1.0, "macd_signal": 0.5}]
    trend_rows = [
        {
            "date": date(2026, 7, 20).isoformat(),
            "minervini_score": 3.0,
            "weinstein_stage": 2,
            "percent_from_52w_high": -2.0,
        }
    ]
    vcp_rows = [{"date": date(2026, 7, 20).isoformat(), "vcp_strength": 9}]
    positioning_data = {"institutional_ownership": 70.0}

    results = loader._compute_quality_scores(
        "TEST", buy_sell_rows, technical_rows, trend_rows, vcp_rows, positioning_data
    )

    row = results[0]
    # Every component maxed out -> composite must be exactly 100, never more (the
    # original clamping bug this all traces back to), never distorted by unequal weights.
    assert row["composite_sqs"] == 100
    assert not pd.isna(row["composite_sqs"])
