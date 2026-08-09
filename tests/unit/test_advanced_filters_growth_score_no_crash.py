"""Regression test: missing growth_metrics data must fold into hard_fail, not crash.

_growth_score() used to propagate ValueError uncaught from evaluate_candidate(), unlike
every other CATALYST/QUALITY dimension (earnings quality, analyst, insider all catch and
fold into hard_fail). growth_metrics.eps_growth_3y coverage is only ~62% in the real DB,
so this was 6/20 of the crashes seen when empirically testing evaluate_candidate() against
real trade candidates (see advanced_filters_dead_code_investigation_20260809 memory).
"""

from datetime import date
from unittest.mock import patch

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def test_growth_score_value_error_caught_not_propagated():
    filters = AdvancedFilters(dict(BASE_CONFIG))
    filters._strong_sectors = {"Technology": 10.0}
    filters._sector_full_ranking = {"Technology": 1}
    filters._strong_industries = {"Semiconductors": 5.0}
    filters._industry_full_ranking = {"Semiconductors": 1}

    with (
        patch.object(filters, "_estimate_days_to_earnings", return_value=30),
        patch.object(filters, "_extension_pct", return_value=5.0),
        patch.object(filters, "_avg_dollar_volume", return_value=10_000_000.0),
        patch.object(filters, "_mansfield_rs_score", return_value=(10.0, 80.0)),
        patch.object(filters, "_sector_momentum_score", return_value=10.0),
        patch.object(filters, "_industry_momentum_score", return_value=5.0),
        patch.object(filters, "_volume_confirmation_score", return_value=(5.0, 1.5)),
        patch.object(filters, "_price_trend_score", return_value=4.0),
        patch.object(filters, "_setup_quality_score", return_value=(0.0, {})),
        patch.object(filters, "_ibd_composite_score", return_value=(0.0, {})),
        patch.object(filters, "_financial_quality_score", return_value=(0.0, 0.0)),
        patch.object(filters, "_earnings_quality_score", side_effect=ValueError("earnings quality missing")),
        patch.object(filters, "_growth_score", side_effect=ValueError("EPS 3-year CAGR missing for TEST")),
        patch.object(filters, "_analyst_score", side_effect=ValueError("analyst missing")),
        patch.object(filters, "_insider_score", side_effect=ValueError("insider missing")),
        patch.object(filters, "_extension_risk_score", return_value=0.0),
        patch.object(filters, "_earnings_proximity_score", return_value=0.0),
    ):
        # Must not raise - the whole point of this fix
        result = filters.evaluate_candidate("TEST", date(2026, 8, 7), 100.0, "Technology", "Semiconductors")

    assert result["pass"] is False
    assert "growth" in result["reason"].lower() or result["components"]["growth"] is None
