"""Regression test: _industry_momentum_score must not crash for non-top-quartile industries.

Before this fix, _industry_momentum_score() raised ValueError for ANY industry outside
_strong_industries (the top 25% by momentum_score) - conflating "not a momentum leader
right now" (true for ~75% of industries at any time, by construction) with "industry data
is missing/invalid". Empirically this crashed AdvancedFilters.evaluate_candidate() for
20/20 real recent trade candidates tested live against the `stocks` DB (2026-08-09).
Fixed to use a full industry ranking (mirroring _sector_momentum_score's existing pattern)
so a valid-but-weak industry scores 0 instead of raising; only a genuinely unranked/unknown
industry name still raises (fail-closed, matching original intent).
"""

from unittest.mock import Mock

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def _filters_with_context(strong, full_ranking):
    filters = AdvancedFilters(dict(BASE_CONFIG))
    filters._strong_industries = strong
    filters._industry_full_ranking = full_ranking
    return filters


def test_top_quartile_industry_scores_full_weight():
    filters = _filters_with_context(
        strong={"Semiconductors": 10.0},
        full_ranking={"Semiconductors": 1, "Carpets & Rugs": 50},
    )
    score = filters._industry_momentum_score("Semiconductors")
    assert score > 0.0


def test_ranked_but_not_top_quartile_industry_scores_zero_not_raise():
    filters = _filters_with_context(
        strong={"Semiconductors": 10.0},
        full_ranking={"Semiconductors": 1, "Carpets & Rugs": 50},
    )
    score = filters._industry_momentum_score("Carpets & Rugs")
    assert score == 0.0


def test_unranked_industry_still_raises():
    filters = _filters_with_context(
        strong={"Semiconductors": 10.0},
        full_ranking={"Semiconductors": 1, "Carpets & Rugs": 50},
    )
    try:
        filters._industry_momentum_score("Not A Real Industry")
        raised = False
    except ValueError:
        raised = True
    assert raised, "an industry absent from the full ranking is a genuine data problem and must still hard-fail"


def test_context_not_loaded_raises():
    filters = AdvancedFilters(dict(BASE_CONFIG))
    try:
        filters._industry_momentum_score("Semiconductors")
        raised = False
    except ValueError:
        raised = True
    assert raised
