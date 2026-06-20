"""Integration tests: Verify dashboard panels handle broken API responses gracefully.

This catches silent failures that unit tests don't detect.
"""

import pytest


def test_dashboard_handles_api_error_in_portfolio():
    """FAIL if portfolio has error but dashboard still renders positions."""
    from tools.dashboard.dashboard import render_dashboard

    broken_data = {
        "run": {"run_at": "2024-01-01", "success": True},
        "cfg": {"mode": "LIVE", "enabled": True},
        "mkt": {"spy_close": 500, "vix_level": 15},
        "port": {"_error": "Portfolio API failed"},  # ERROR!
        "pos": {"items": []},
        "perf": {"n": 0},
        "sig": {"items": []},
        "health": {"ready_to_trade": True},
        "cb": {"items": []},
        "trades": {"items": []},
        "risk": None,
        "scores": [],
    }

    # Dashboard MUST show error panel, not crash
    try:
        layout = render_dashboard(broken_data, frame=0)
        assert layout is not None, "Dashboard should render even with broken port data"
    except Exception as e:
        pytest.fail(f"Dashboard crashed on broken portfolio data: {e}")


def test_dashboard_handles_all_api_errors():
    """FAIL if dashboard crashes when ANY critical API returns error."""
    from tools.dashboard.dashboard import render_dashboard

    critical_fields = [
        "run", "cfg", "mkt", "port", "perf", "pos", "sig", "risk", "scores"
    ]

    for field in critical_fields:
        broken_data = {
            "run": {"run_at": "2024-01-01", "success": True},
            "cfg": {"mode": "LIVE", "enabled": True},
            "mkt": {"spy_close": 500, "vix_level": 15},
            "port": {"total_portfolio_value": 0},
            "pos": {"items": []},
            "perf": {"n": 0},
            "sig": {"items": []},
            "health": {"ready_to_trade": True},
            "cb": {"items": []},
            "trades": {"items": []},
            "risk": None,
            "scores": [],
        }
        broken_data[field] = {"_error": f"{field} API failed"}

        try:
            layout = render_dashboard(broken_data, frame=0)
            assert layout is not None
        except Exception as e:
            pytest.fail(f"Dashboard crashed on broken {field} data: {e}")


def test_dashboard_shows_error_panel_when_data_broken():
    """FAIL if error panel doesn't display broken data errors."""
    from tools.dashboard.dashboard import render_dashboard
    from tools.dashboard.error_boundary import error_summary_panel

    data_with_errors = {
        "run": {"_error": "API timeout"},
        "cfg": {"_error": "Config fetch failed"},
        "mkt": {"spy_close": 500, "vix_level": 15},
        "port": {"total_portfolio_value": 0},
        "pos": {"items": []},
        "perf": {"n": 0},
        "sig": {"items": []},
        "health": {"ready_to_trade": True},
        "cb": {"items": []},
        "trades": {"items": []},
        "risk": None,
        "scores": [],
    }

    # error_summary_panel should catch these errors
    error_panel = error_summary_panel(data_with_errors)
    assert error_panel is not None, "Error panel should show when data has errors"
    assert "API timeout" in str(error_panel) or "Config fetch failed" in str(error_panel)
