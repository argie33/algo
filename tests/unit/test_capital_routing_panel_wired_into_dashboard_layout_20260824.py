"""Regression test: panel_capital_routing (dashboard/panels/exposure.py) was registered with
the panel registry (2026-08-24) but never actually imported/placed into the visible dashboard
layout in dashboard/renderers/pipeline.py - the panel existed, its tests passed, but no
operator could ever see it. This locks in the fix (wired into row "r2" alongside portfolio/
perf/eco) by asserting an end-to-end render of the real layout actually contains it, not just
that the panel function itself renders in isolation (that was already covered separately).
"""

from rich.console import Console
from rich.layout import Layout

from dashboard.core import DashboardContext
from dashboard.renderers.pipeline import render_dashboard_body

_BASE_DATA: dict[str, object] = {
    "cb": {"n": 0, "any": False},
    "run": {"run_id": "1", "success": True, "status": "completed"},
    "health": {"ready_to_trade": True},
    "activity": {"items": []},
    "notifs": {"items": []},
    "algo_metrics": {"items": []},
    "audit": {"items": []},
    "exec_hist": {"items": []},
    "exec_stats": {},
    "risk": {},
    "port": {"total_portfolio_value": 100000.0, "total_cash": 50000.0, "position_count": 0},
    "cfg": {"enable_algo": True},
    "perf": {"total_trades": 0},
    "trades": {"items": []},
    "perf_anl": None,
    "pos": {"items": []},
    "eco": {},
    "econ_cal": {},
    "scores": {"top": []},
    "sig": {"items": []},
    "sig_eval": None,
    "srank": {"items": []},
    "sec_rot": None,
    "irank": {"items": []},
}


def _render(data: dict[str, object]) -> str:
    ctx = DashboardContext(data)
    outer = Layout()
    outer.split_column(
        Layout(name="r1", ratio=2),
        Layout(name="r2", ratio=2),
        Layout(name="r3", ratio=2),
        Layout(name="pos", ratio=3),
    )
    render_dashboard_body(outer, ctx, compact=False)
    console = Console(width=200)
    with console.capture() as cap:
        console.print(outer)
    return cap.get()


def test_capital_routing_panel_appears_in_rendered_layout() -> None:
    data = dict(_BASE_DATA)
    data["capital_routing"] = {
        "data_unavailable": False,
        "uninvested_capital_pct": 35.0,
        "gld_trend_up": True,
        "gld_weight": 1.0,
        "ief_trend_up": False,
        "ief_weight": 0.0,
        "dbc_trend_up": False,
        "dbc_weight": 0.0,
        "cash_weight": 0.0,
        "move_index": 95.0,
        "move_veto": False,
    }
    out = _render(data)
    assert "CAPITAL ROUTING" in out
    assert "GLD" in out


def test_missing_capital_routing_key_degrades_gracefully_in_layout() -> None:
    """Older/partial API responses without a "capital_routing" key must not crash the
    whole dashboard render - the panel itself should show its own unavailable state."""
    out = _render(dict(_BASE_DATA))
    assert "CAPITAL ROUTING" in out
    assert "unavailable" in out.lower()
