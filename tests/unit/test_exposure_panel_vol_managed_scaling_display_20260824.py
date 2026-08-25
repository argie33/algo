"""Regression: the vol-managed multiplier (Layer 2, Moreira & Muir, activated 2026-08-24 -
see exposure_system_full_audit_and_vol_managed_multiplier_activated_20260824 in memory) is a
real, live component that scales exposure_pct day-to-day before hard-veto capping, but was
never rendered anywhere in the dashboard - panel_exposure_compact/panel_exposure_expanded
showed all 3 pillars and Macro Watch, but silently omitted `factors.vol_managed_scaling`. An
operator watching exposure_pct move would see no explanation for why, unlike every other
factor that moves the score.
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


class TestCompactPanelVolManagedScaling:
    def test_neutral_multiplier_shown_dim(self):
        exp_f = _base_exp_f(factors={"vol_managed_scaling": {"multiplier": 1.0, "note": "active"}})
        text = _render(panel_exposure_compact(exp_f))
        assert "Vol-Managed Scaling" in text
        assert "x1.00" in text

    def test_scaling_down_multiplier_shown(self):
        exp_f = _base_exp_f(factors={"vol_managed_scaling": {"multiplier": 0.61, "note": "active"}})
        text = _render(panel_exposure_compact(exp_f))
        assert "x0.61" in text

    def test_scaling_up_multiplier_shown(self):
        exp_f = _base_exp_f(factors={"vol_managed_scaling": {"multiplier": 1.37, "note": "active"}})
        text = _render(panel_exposure_compact(exp_f))
        assert "x1.37" in text

    def test_missing_multiplier_shows_unavailable_not_crash(self):
        exp_f = _base_exp_f(factors={"vol_managed_scaling": {"note": "inert"}})
        text = _render(panel_exposure_compact(exp_f))
        assert "Vol-Managed Scaling" in text
        assert "unavailable" in text

    def test_absent_key_shows_unavailable_not_crash(self):
        # Same convention as the pillar rows: degrade to a visible unavailable marker
        # rather than silently hiding the row (an older cached row predating activation).
        exp_f = _base_exp_f(factors={})
        text = _render(panel_exposure_compact(exp_f))
        assert "Vol-Managed Scaling" in text
        assert "unavailable" in text


class TestExpandedPanelVolManagedScaling:
    def test_multiplier_and_note_shown(self):
        exp_f = _base_exp_f(
            factors={
                "vol_managed_scaling": {
                    "multiplier": 1.37,
                    "note": "active since 2026-08-24 (Phase B backtest passed on SPY/QQQ)",
                }
            }
        )
        text = _render(panel_exposure_expanded(exp_f))
        assert "Vol-Managed Scaling" in text
        assert "x1.37" in text
        assert "Phase B backtest" in text

    def test_missing_multiplier_shows_unavailable_not_crash(self):
        exp_f = _base_exp_f(factors={"vol_managed_scaling": {}})
        text = _render(panel_exposure_expanded(exp_f))
        assert "Vol-Managed Scaling" in text
        assert "unavailable" in text
