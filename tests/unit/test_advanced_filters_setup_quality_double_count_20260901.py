"""Regression test: AdvancedFilters.evaluate_candidate() must add the setup-quality bonus
to subscores["momentum"] exactly once, not twice.

A stray, unconditional `subscores["momentum"] += setup_pts` used to sit right after the
_setup_quality_score() try/except, duplicating the addition already inside the try block.
On the success path this silently doubled the setup-quality bonus into every candidate's
momentum subscore and composite_score. On the exception path it was worse: setup_pts is
never bound when _setup_quality_score() raises, so that stray line raised an uncaught
UnboundLocalError - exactly the failure class this same method's "FIX (2026-08-09)"
comments were written to eliminate everywhere else.

Confirmed wired into the live entry-execution path via
algo/orchestrator/phase8_entry_execution.py's evaluate_candidate() call.
"""

from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def _filters():
    return AdvancedFilters(dict(BASE_CONFIG))


def _patched_db_context():
    mock_cur = MagicMock()
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return patch("algo.signals.advanced_filters.DatabaseContext", return_value=mock_db_context)


def _zeroed_subscore_mocks(filters):
    """Patches every scoring sub-method to contribute exactly 0 except setup_quality
    (5.0 pts), so subscores["momentum"] should equal exactly 5.0 if setup_pts is only
    added once."""
    return (
        patch.object(filters, "_estimate_days_to_earnings", return_value=None),
        patch.object(filters, "_extension_pct", return_value=None),
        patch.object(filters, "_avg_dollar_volume", return_value=10_000_000.0),
        patch.object(filters, "_mansfield_rs_score", return_value=(0.0, 0.0)),
        patch.object(filters, "_sector_momentum_score", return_value=0.0),
        patch.object(filters, "_industry_momentum_score", return_value=0.0),
        patch.object(filters, "_volume_confirmation_score", return_value=(0.0, 0.0)),
        patch.object(filters, "_price_trend_score", return_value=0.0),
        patch.object(filters, "_setup_quality_score", return_value=(5.0, {"score": 5.0})),
        patch.object(filters, "_ibd_composite_score", return_value=(0.0, {})),
        patch.object(filters, "_financial_quality_score", return_value=(0.0, {})),
        patch.object(filters, "_earnings_quality_score", return_value=(0.0, {})),
        patch.object(filters, "_growth_score", return_value=(0.0, {})),
        patch.object(filters, "_analyst_score", return_value=(0.0, 0)),
        patch.object(filters, "_insider_score", return_value=(0.0, 0)),
    )


class TestSetupQualityAddedOnlyOnce:
    def test_momentum_subscore_reflects_setup_pts_exactly_once(self):
        filters = _filters()
        with ExitStack() as stack:
            stack.enter_context(_patched_db_context())
            for mock_cm in _zeroed_subscore_mocks(filters):
                stack.enter_context(mock_cm)
            result = filters.evaluate_candidate(
                symbol="TEST",
                signal_date=date(2026, 6, 1),
                entry_price=100.0,
                sector="Technology",
                industry="Semiconductors",
            )

        assert result["subscores"]["momentum"] == 5.0, (
            f"setup_pts=5.0 must be added to momentum exactly once - got "
            f"{result['subscores']['momentum']} (10.0 would mean the double-count bug is back)"
        )

    def test_exception_in_setup_quality_does_not_raise_unboundlocalerror(self):
        """The exception path must produce a structured hard_fail result, not crash."""
        filters = _filters()
        with (
            _patched_db_context(),
            patch.object(filters, "_estimate_days_to_earnings", return_value=None),
            patch.object(filters, "_extension_pct", return_value=None),
            patch.object(filters, "_avg_dollar_volume", return_value=10_000_000.0),
            patch.object(filters, "_mansfield_rs_score", return_value=(0.0, 0.0)),
            patch.object(filters, "_sector_momentum_score", return_value=0.0),
            patch.object(filters, "_industry_momentum_score", return_value=0.0),
            patch.object(filters, "_volume_confirmation_score", return_value=(0.0, 0.0)),
            patch.object(filters, "_price_trend_score", return_value=0.0),
            patch.object(filters, "_setup_quality_score", side_effect=TypeError("boom")),
            patch.object(filters, "_ibd_composite_score", return_value=(0.0, {})),
            patch.object(filters, "_financial_quality_score", return_value=(0.0, {})),
            patch.object(filters, "_earnings_quality_score", return_value=(0.0, {})),
            patch.object(filters, "_growth_score", return_value=(0.0, {})),
            patch.object(filters, "_analyst_score", return_value=(0.0, 0)),
            patch.object(filters, "_insider_score", return_value=(0.0, 0)),
        ):
            result = filters.evaluate_candidate(
                symbol="TEST",
                signal_date=date(2026, 6, 1),
                entry_price=100.0,
                sector="Technology",
                industry="Semiconductors",
            )

        assert result["pass"] is False
        assert "Setup quality unavailable" in result["reason"]
