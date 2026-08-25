#!/usr/bin/env python3
"""Regression test for the 2026-08-25 fix to
algo/orchestrator/phase7_signal_generation.py::_resolve_min_composite_score
(see [[phase7_min_composite_score_fallback_not_fail_closed_flagged_20260825]] in memory).

Phase 7 used to independently re-call read_market_regime()/tier_for_exposure() to get
min_composite_score, a SECOND live lookup of the same regime Phase 5 already computed and
passed down as exposure_constraints - and on any transient failure of that redundant call,
fell back to the LEAST selective tier's threshold (60.0), silently admitting lower-quality
signals than the actual regime called for even when Phase 5 succeeded and reported a stricter
tier. Fixed by using Phase 5's already-fetched exposure_constraints.min_composite_score
directly, eliminating the redundant call (and its independent failure mode) entirely.
"""

from algo.orchestrator.phase7_signal_generation import _resolve_min_composite_score

CONFIG = {"phase7_min_composite_score": 60.0}


class TestResolveMinCompositeScore:
    def test_uses_phase5_constraints_value_when_present(self):
        """The core fix: a stricter tier from Phase 5 (e.g. 'caution' -> 70.0) must be used
        as-is, not silently downgraded by an independent re-lookup."""
        constraints = {"tier_name": "CAUTION", "min_composite_score": 70.0}
        assert _resolve_min_composite_score(constraints, CONFIG) == 70.0

    def test_falls_back_to_config_when_constraints_missing_the_key(self):
        """Phase 5's own halt-safe fallback dict (Phase 5 didn't run at all) has no
        min_composite_score key - halt_new_entries=True already blocks all new entries in
        that case, so a config-default fallback here is safe, not a silent quality bypass."""
        constraints = {"tier_name": "CORRECTION", "halt_new_entries": True}
        assert _resolve_min_composite_score(constraints, CONFIG) == 60.0

    def test_falls_back_to_config_when_constraints_is_none(self):
        assert _resolve_min_composite_score(None, CONFIG) == 60.0

    def test_does_not_downgrade_a_strict_tier_on_a_hypothetical_lookup_failure(self):
        """Regression for the actual bug: previously, ANY exception in a redundant regime
        re-lookup (unrelated to Phase 5's own successful result) silently substituted the
        LEAST selective 60.0 threshold. Since this fix removes that redundant lookup
        entirely, there is no code path left that can downgrade a stricter Phase-5-reported
        tier - verify a tier stricter than the config default survives untouched."""
        constraints = {"tier_name": "CORRECTION", "min_composite_score": 75.0}
        assert _resolve_min_composite_score(constraints, CONFIG) == 75.0
