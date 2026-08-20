"""Regression test for the 2026-08-20 fix: phase7_signal_generation.py's live/inline
signal-quality scoring path had silently diverged from loaders/load_signal_quality_scores.py's
tested, weighted-sum-over-available-maxes composite formula (see
test_signal_quality_composite_weighting.py) while claiming in its own comment to be
"same as batch loader". The inline path summed only 3 of the 7 designed components
(base_quality + volume_confirmation + trend_template) with a raw, un-normalized
`min(100, ...)` clamp - never actually reaching 100 (max 95) and never accounting for
distance_from_high, institutional_ownership, market_stage, or vcp_pattern.

This matters because the live/inline path - not the batch loader's output - is what
actually gates real trade entries: Phase 8's min_signal_quality_score threshold reads
signal.get("signal_quality_score"), which Phase 7 sets via this inline computation and
writes unconditionally into buy_sell_daily.signal_quality_score BEFORE the batch loader
(whose sync only fills NULLs) ever runs.

Fixed by extracting the composite formula into
loaders/signal_quality_scorer.py::compute_signal_quality_components, a single function
now called by both the batch loader and phase7's live scoring paths (both the primary
inline scorer and the orphaned-signal backfill scorer), so the score that gates real
trades can never silently diverge from the tested formula again.
"""

import inspect

from algo.orchestrator import phase7_signal_generation
from loaders import load_signal_quality_scores
from loaders.signal_quality_scorer import COMPONENT_MAXES, compute_signal_quality_components


class TestSharedCompositeFormulaUsedEverywhere:
    def test_phase7_no_longer_reimplements_raw_sum_formula(self):
        source = inspect.getsource(phase7_signal_generation)
        assert "get_signal_scorer" not in source, (
            "phase7_signal_generation.py must not call the per-component strategy scorer "
            "directly - it must go through compute_signal_quality_components() so its "
            "composite can never diverge from the batch loader's tested formula again"
        )
        assert "base_score + volume_score + trend_score" not in source, (
            "the old raw, un-normalized 3-component sum must not reappear in phase7"
        )

    def test_phase7_imports_shared_composite_function(self):
        source = inspect.getsource(phase7_signal_generation)
        assert source.count("compute_signal_quality_components") >= 2, (
            "phase7's main inline scorer and its orphaned-signal backfill scorer must "
            "both call the shared composite function"
        )

    def test_batch_loader_uses_shared_composite_function(self):
        source = inspect.getsource(load_signal_quality_scores)
        assert "compute_signal_quality_components" in source


class TestComponentMaxesUnchanged:
    """Guards the designed per-component weighting itself (not just where it's called
    from) - a change here would silently reweight both the batch loader and live paths
    at once, so it needs to be a deliberate, visible diff."""

    def test_component_maxes(self):
        assert COMPONENT_MAXES == {
            "base_quality": 50,
            "volume_confirmation": 20,
            "trend_template": 25,
            "distance_from_high": 15,
            "institutional_ownership": 10,
            "market_stage": 10,
            "vcp_pattern": 10,
        }


class TestComputeSignalQualityComponents:
    def test_only_3_of_7_components_available_is_normalized_not_raw_capped_at_95(self):
        """This is exactly phase7's inline scenario before the fix: only base/volume/trend
        available (no 52w-high, institutional ownership, or VCP data fetched). The old bug
        would have produced a raw sum capped at 95 (base 50 + volume 20 + trend 25), never
        reaching 100 even for a maximal signal. The fixed formula normalizes over only the
        available components' maxes, so a maximal 3-component signal correctly reaches 100.
        """
        result = compute_signal_quality_components(
            signal_type="BUY",
            rsi=60.0,
            macd=1.0,
            macd_signal=0.5,
            minervini_score=3.0,
            weinstein_stage=2,
            percent_from_52w_high=None,
            institutional_ownership=None,
            vcp_strength=None,
        )
        # distance_from_high and market_stage are present-but-zero-default (not None) even
        # without input data - only institutional_ownership and vcp_pattern are genuinely
        # excluded here since no data was supplied for them.
        assert result["unavailable_components"] == ["institutional_ownership", "vcp_pattern"]
        # base=50/50, volume=20/20, trend=25/25, distance=0/15, market_stage=10/10 (stage 2)
        # -> (50+20+25+0+10) / (50+20+25+15+10) * 100 = 105/120*100 = 87
        assert result["composite_sqs"] == 87
        assert result["composite_sqs"] != min(100, 50 + 20 + 25)  # the old buggy value (95)

    def test_matches_batch_loader_composite_for_equivalent_inputs(self):
        """Cross-check: compute_signal_quality_components() must produce the exact composite
        SignalQualityScoresLoader._compute_quality_scores() would for equivalent inputs -
        the whole point of consolidating onto one function."""
        from datetime import date

        from loaders.load_signal_quality_scores import SignalQualityScoresLoader

        loader = SignalQualityScoresLoader.__new__(SignalQualityScoresLoader)
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

        loader_result = loader._compute_quality_scores(
            "TEST", buy_sell_rows, technical_rows, trend_rows, vcp_rows, positioning_data
        )[0]

        direct_result = compute_signal_quality_components(
            signal_type="BUY",
            rsi=60.0,
            macd=1.0,
            macd_signal=0.5,
            minervini_score=3.0,
            weinstein_stage=2,
            percent_from_52w_high=-2.0,
            institutional_ownership=70.0,
            vcp_strength=9,
        )

        assert loader_result["composite_sqs"] == direct_result["composite_sqs"] == 100
