"""Regression: the active policy tier (algo/risk/exposure_policy.py's EXPOSURE_TIERS, via
market.py's active_tier API field) is the concrete trading consequence of exposure_pct -
how many new positions today, how selective (min_composite_score), how concentrated a
single position can get (max_concentration_pct) - but was never rendered anywhere in the
dashboard. panel_exposure_compact/panel_exposure_expanded showed the score, 3 pillars,
vol-managed scaling, and macro watch, but nothing about what the score actually DOES to
today's trading. min_composite_score alone was retuned 3x in one day (see EXPOSURE_TIERS's
own "TUNING"/"RE-APPLIED" comments) with no dashboard surface to observe the live value.
"""

from rich.console import Console

from dashboard.panels.exposure import panel_exposure_compact, panel_exposure_expanded


def _render(panel) -> str:
    console = Console(width=140, record=True)
    console.print(panel)
    return console.export_text()


def _base_exp_f(**overrides: object) -> dict:
    row = {
        "raw_score": 62.0,
        "exposure_pct": 55.0,
        "regime": "confirmed_uptrend",
        "factors": {},
        "timestamp": None,
    }
    row.update(overrides)
    return row


_SAMPLE_TIER = {
    "name": "uptrend_under_pressure",
    "description": "Uptrend intact but weakening - reduced position size",
    "min_pct": 45,
    "max_pct": 70,
    "risk_mult": 0.65,
    "risk_multiplier": 0.65,
    "max_new": 3,
    "max_new_positions_today": 3,
    "halt": False,
    "halt_new_entries": False,
    "min_composite_score": 65.0,
    "max_concentration_pct": 22.0,
}


class TestCompactPanelActiveTier:
    def test_tier_summary_shown(self):
        exp_f = _base_exp_f(active_tier=_SAMPLE_TIER)
        text = _render(panel_exposure_compact(exp_f))
        assert "Policy Tier" in text
        assert "uptrend_under_pressure" in text
        assert "3 new/day" in text
        assert "score" in text.lower()

    def test_halted_tier_shown(self):
        halted = {**_SAMPLE_TIER, "name": "correction", "halt": True, "max_new": 0}
        exp_f = _base_exp_f(active_tier=halted)
        text = _render(panel_exposure_compact(exp_f))
        assert "HALTED" in text

    def test_missing_active_tier_shows_unavailable_not_crash(self):
        exp_f = _base_exp_f()
        text = _render(panel_exposure_compact(exp_f))
        assert "Policy Tier" in text
        assert "unavailable" in text


class TestExpandedPanelActiveTier:
    def test_tier_detail_shown(self):
        exp_f = _base_exp_f(active_tier=_SAMPLE_TIER)
        text = _render(panel_exposure_expanded(exp_f))
        assert "Active Policy Tier" in text
        assert "uptrend_under_pressure" in text
        assert "entries allowed" in text
        assert "x0.65" in text
        assert "65" in text  # min composite score
        assert "22%" in text  # max concentration

    def test_halted_tier_shows_halted_status(self):
        halted = {**_SAMPLE_TIER, "name": "correction", "halt": True}
        exp_f = _base_exp_f(active_tier=halted)
        text = _render(panel_exposure_expanded(exp_f))
        assert "HALTED" in text

    def test_missing_active_tier_shows_unavailable_not_crash(self):
        exp_f = _base_exp_f()
        text = _render(panel_exposure_expanded(exp_f))
        assert "Active Policy Tier" in text
        assert "unavailable" in text
