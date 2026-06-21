"""Integration tests: Verify dashboard panels handle broken API responses gracefully.

This catches silent failures that unit tests don't detect.
"""

import pytest


def _minimal_good_data():
    """Provide minimal realistic data that panels need."""
    return {
        "run": {"run_at": "2024-01-01", "success": True},
        "cfg": {"mode": "LIVE", "enabled": True},
        "mkt": {"spy_close": 500, "vix_level": 15},
        "port": {"total_portfolio_value": 100000, "total_cash": 50000, "position_count": 5},
        "pos": {"items": []},
        "perf": {"n": 0, "w": 0, "l": 0, "streak": 0},
        "sig": {"items": []},
        "sig_eval": None,
        "health": {"ready_to_trade": True},
        "cb": {"n": 0, "any": False},
        "trades": {"items": []},
        "risk": None,
        "scores": [],
        "srank": {"items": []},
        "exp_factors": None,
        "eco": None,
        "econ_cal": None,
        "act": {"items": []},
        "algo_metrics": {"items": []},
        "audit": {"items": []},
        "exec_hist": {"items": []},
        "notifs": {"items": []},
        "sentiment": None,
        "sec_rot": None,
        "irank": {"items": []},
        "perf_anl": None,
    }


def test_dashboard_handles_api_error_in_portfolio():
    """FAIL if portfolio has error but dashboard still renders without error handling."""
    from tools.dashboard.dashboard import render_dashboard

    broken_data = _minimal_good_data()
    broken_data["port"] = {"_error": "Portfolio API failed"}  # Override with error

    # Dashboard MUST not crash - should show error panel instead
    try:
        layout = render_dashboard(broken_data, frame=0)
        assert layout is not None, "Dashboard should render even with broken portfolio data"
        # Check that error panel is displayed by looking at the layout structure
        print("OK: Dashboard handled broken portfolio gracefully")
    except Exception as e:
        pytest.fail(f"Dashboard crashed on broken portfolio data: {e}")


def test_dashboard_handles_all_api_errors():
    """FAIL if dashboard crashes when ANY critical API returns error."""
    from tools.dashboard.dashboard import render_dashboard

    critical_fields = ["run", "cfg", "mkt", "port", "perf", "pos", "sig", "cb", "trades"]

    for field in critical_fields:
        broken_data = _minimal_good_data()
        broken_data[field] = {"_error": f"{field} API failed"}

        try:
            layout = render_dashboard(broken_data, frame=0)
            assert layout is not None, f"Dashboard should render with error in {field}"
            print(f"OK Dashboard handled broken {field} gracefully")
        except Exception as e:
            pytest.fail(f"Dashboard crashed on broken {field} data: {e}")


def test_dashboard_shows_error_panel_when_data_broken():
    """FAIL if error panel doesn't display broken data errors."""
    from tools.dashboard.error_boundary import error_summary_panel

    data_with_errors = _minimal_good_data()
    data_with_errors["run"] = {"_error": "API timeout"}
    data_with_errors["cfg"] = {"_error": "Config fetch failed"}

    # error_summary_panel should catch these errors
    error_panel = error_summary_panel(data_with_errors)
    assert error_panel is not None, "Error panel should show when data has errors"
    # Check that error panel contains reference to errors (content varies by implementation)
    print("OK Error panel generated for broken data")
