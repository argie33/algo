#!/usr/bin/env python3
"""Test dashboard panel rendering to identify which panels are failing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.fetchers import load_all
from dashboard.panels import (
    panel_algo_health,
    panel_circuit,
    panel_economic_pulse,
    panel_exposure_compact,
    panel_header_market,
    panel_performance_spark,
    panel_portfolio,
    panel_positions,
    panel_recent_trades,
    panel_sector_compact,
    panel_signals_compact,
)


def test_panel_rendering():
    """Test each panel render function with loaded data."""
    print("Loading all dashboard data...")
    data = load_all()

    def render_header():
        return panel_header_market(
            data.get("mkt"),
            data.get("sentiment"),
            "Mon Jan 01 12:00 PM ET",
            "Market Status",
            0.5,
            "",
            cfg=data.get("cfg"),
            data_source="AWS",
        )

    def render_circuit():
        return panel_circuit(data.get("cb"))

    def render_health():
        return panel_algo_health(
            data.get("run"),
            data.get("activity"),
            data.get("hlth"),
            data.get("notifs", []),
            algo_metrics=data.get("algo_metrics"),
            audit=data.get("audit"),
            exec_hist=data.get("exec_hist"),
            risk=data.get("risk"),
        )

    def render_portfolio():
        return panel_portfolio(
            data.get("port"),
            data.get("cfg"),
            risk=data.get("risk"),
            perf=data.get("perf"),
        )

    def render_performance():
        return panel_performance_spark(
            data.get("perf"),
            data.get("trades"),
            data.get("perf_anl"),
            pos=data.get("pos"),
        )

    def render_economic():
        return panel_economic_pulse(
            data.get("eco"),
            data.get("econ_cal"),
        )

    def render_exposure():
        return panel_exposure_compact(data.get("exp_factors"))

    def render_signals():
        return panel_signals_compact(
            data.get("sig"),
            data.get("sig_eval"),
            scores=data.get("scores"),
        )

    def render_sectors():
        return panel_sector_compact(
            data.get("srank"),
            data.get("pos"),
            data.get("port"),
            data.get("sec_rot"),
            data.get("irank"),
        )

    def render_positions():
        return panel_positions(
            data.get("pos"),
            compact=False,
            trades=data.get("trades"),
        )

    def render_trades():
        return panel_recent_trades(data.get("trades"))

    panels = {
        "header_market": render_header,
        "circuit": render_circuit,
        "health": render_health,
        "portfolio": render_portfolio,
        "performance": render_performance,
        "economic": render_economic,
        "exposure": render_exposure,
        "signals": render_signals,
        "sectors": render_sectors,
        "positions": render_positions,
        "trades": render_trades,
    }

    results = {}
    for name, render_fn in panels.items():
        try:
            result = render_fn()
            results[name] = {"status": "OK", "type": type(result).__name__}
            print(f"[OK] {name}: {type(result).__name__}")
        except Exception as e:
            results[name] = {
                "status": "ERROR",
                "type": type(e).__name__,
                "message": str(e)[:120]
            }
            print(f"[ERROR] {name}: {type(e).__name__}: {str(e)[:80]}")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    ok = [k for k, v in results.items() if v["status"] == "OK"]
    errors = [k for k, v in results.items() if v["status"] == "ERROR"]

    print(f"\n[OK] {len(ok)} panels rendered successfully:")
    for name in sorted(ok):
        print(f"  - {name}")

    if errors:
        print(f"\n[ERRORS] {len(errors)} panels failed:")
        for name in sorted(errors):
            error_info = results[name]
            print(f"  - {name}: {error_info['type']}")
            if 'message' in error_info:
                print(f"    {error_info['message']}")


if __name__ == "__main__":
    test_panel_rendering()
