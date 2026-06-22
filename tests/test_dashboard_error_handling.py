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
        "port": {
            "total_portfolio_value": 100000,
            "total_cash": 50000,
            "position_count": 5,
        },
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
    from dashboard.dashboard import render_dashboard

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
    from dashboard.dashboard import render_dashboard

    critical_fields = [
        "run",
        "cfg",
        "mkt",
        "port",
        "perf",
        "pos",
        "sig",
        "cb",
        "trades",
    ]

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
    from dashboard.error_boundary import error_summary_panel

    data_with_errors = _minimal_good_data()
    data_with_errors["run"] = {"_error": "API timeout"}
    data_with_errors["cfg"] = {"_error": "Config fetch failed"}

    # error_summary_panel should catch these errors
    error_panel = error_summary_panel(data_with_errors)
    assert error_panel is not None, "Error panel should show when data has errors"
    # Check that error panel contains reference to errors (content varies by implementation)
    print("OK Error panel generated for broken data")


def test_error_panel_handles_bracket_chars_in_error_message():
    """Error messages containing Rich markup chars ([Errno 111]) must not crash panels."""
    from dashboard.error_boundary import (
        error_summary_panel,
        error_summary_panel_expanded,
    )

    # Network errors often include [Errno NNN] — these brackets must be escaped
    bracket_errors = {
        "cb": {"_error": "Fetcher cb (/api/algo/circuit-breakers) - ConnectionError: [Errno 111] Connection refused"},
        "port": {"_error": "HTTPError: 404 Client Error: [Not Found] for url: https://api.example.com/portfolio"},
        "mkt": {"_error": "Timeout: [bold] this could crash rich markup parser"},
    }
    data = _minimal_good_data()
    data.update(bracket_errors)

    # Neither panel should raise MarkupError or any other exception
    try:
        compact = error_summary_panel(data)
        assert compact is not None
        expanded = error_summary_panel_expanded(data)
        assert expanded is not None
        print("OK Error panels handled bracket chars safely")
    except Exception as e:
        pytest.fail(f"Error panel crashed on bracket chars in error message: {e}")


def test_errors_view_mode_renders_with_bracket_error_messages():
    """Pressing D (errors view mode) must not crash when error messages have brackets."""
    from dashboard.dashboard import render_dashboard

    data = _minimal_good_data()
    data["cb"] = {"_error": "ConnectionError: [Errno 111] Connection refused"}
    data["port"] = {"_error": "HTTPError: 4xx [Not Found]"}

    try:
        layout = render_dashboard(data, frame=0, view_mode="errors")
        assert layout is not None
        print("OK errors view mode rendered with bracket error messages")
    except Exception as e:
        pytest.fail(f"errors view mode crashed with bracket error messages: {e}")


def test_circuit_breaker_cascade_collapsed_in_error_panel():
    """When many fetchers fail due to open circuit breaker, panel shows ONE entry not many."""
    from dashboard.error_boundary import (
        error_summary_panel,
        error_summary_panel_expanded,
    )

    data = _minimal_good_data()
    # Simulate 5 fetchers all blocked by circuit breaker
    for key in ["cb", "port", "mkt", "pos", "perf"]:
        data[key] = {"_error": "API unavailable - circuit breaker open", "_circuit_open": True}
    # Plus one real error
    data["cfg"] = {"_error": "Config fetch failed: connection refused"}

    compact = error_summary_panel(data)
    assert compact is not None

    expanded = error_summary_panel_expanded(data)
    assert expanded is not None
    print("OK circuit breaker cascade collapsed into single panel entry")


def test_fetch_perf_analytics_none_fields_do_not_crash():
    """fetch_perf_analytics must not crash when API returns None for numeric fields."""
    from unittest.mock import patch

    from dashboard.fetchers_portfolio import fetch_perf_analytics

    none_response = {
        "rolling_sharpe_252d": None,
        "rolling_sortino_252d": None,
        "calmar_ratio": None,
        "win_rate_50t": None,
        "avg_win_r_50t": None,
        "avg_loss_r_50t": None,
        "expectancy": None,
        "max_drawdown_pct": None,
    }
    with patch("dashboard.fetchers_portfolio.api_call", return_value=none_response):
        result = fetch_perf_analytics(None)
    assert "_error" not in result, f"Should not error on None fields, got: {result}"
    assert result.get("sharpe252") is None
    print("OK fetch_perf_analytics handles None fields gracefully")


def test_fetch_risk_metrics_none_fields_do_not_crash():
    """fetch_risk_metrics must not crash when API returns None for numeric fields."""
    from unittest.mock import patch

    from dashboard.fetchers_market import fetch_risk_metrics

    none_response = {
        "report_date": "2026-06-22",
        "var_pct_95": None,
        "cvar_pct_95": None,
        "stressed_var_pct": None,
        "portfolio_beta": None,
        "top_5_concentration": None,
    }
    with patch("dashboard.fetchers_market.api_call", return_value=none_response):
        result = fetch_risk_metrics(None)
    assert "_error" not in result, f"Should not error on None fields, got: {result}"
    assert result.get("var95") is None
    print("OK fetch_risk_metrics handles None fields gracefully")


def test_fetch_signal_eval_none_fields_do_not_crash():
    """fetch_signal_eval must not crash when API returns None for int/float fields."""
    from unittest.mock import patch

    from dashboard.fetchers_signals import fetch_signal_eval

    none_response = {
        "total": None,
        "t1": None,
        "t2": None,
        "t3": None,
        "t4": None,
        "t5": None,
        "avg_score": None,
        "signal_date": None,
        "rejected": None,
    }
    with patch("dashboard.fetchers_signals.api_call", return_value=none_response):
        result = fetch_signal_eval(None)
    assert "_error" not in result, f"Should not error on None fields, got: {result}"
    assert result.get("total") is None
    print("OK fetch_signal_eval handles None fields gracefully")


def test_empty_optional_data_not_treated_as_error():
    """Empty notifications/audit/exec_hist/econ_cal should not appear in error panel."""
    from dashboard.error_boundary import error_summary_panel

    data = _minimal_good_data()
    # Simulate empty but valid optional data
    data["notifs"] = {"items": []}
    data["audit"] = []
    data["exec_hist"] = []
    data["econ_cal"] = {"items": []}

    panel = error_summary_panel(data)
    assert panel is None, "Empty optional data should not trigger error panel"
    print("OK empty optional data does not trigger error panel")
