"""Dashboard API contract - dashboard panel definitions.

Split out of dashboard_api_contract.py (file-size ratchet decomposition, 2026-09-05).
Data-only module: PanelDefinition-shaped dicts describing which endpoints each
dashboard panel depends on. See dashboard_api_contract.py for PanelRegistry."""

from typing import Any

DASHBOARD_PANELS: dict[str, dict[str, Any]] = {
    "header": {
        "endpoint_deps": ["mkt", "sentiment"],
        "optional": False,
        "description": "Header with market status and sentiment",
    },
    "circuit": {
        "endpoint_deps": ["cb"],
        "optional": True,
        "description": "Circuit breaker status",
    },
    "health": {
        "endpoint_deps": ["run", "health", "notifs", "algo_metrics", "audit", "risk"],
        "optional": True,
        "description": "Algo run outcome, phase execution health, run history, alerts",
    },
    "data_freshness": {
        "endpoint_deps": ["health"],
        "optional": True,
        "description": "Per-table data freshness, critical staleness, and readiness-to-trade",
    },
    "portfolio": {
        "endpoint_deps": ["port", "cfg", "risk", "perf"],
        "optional": False,
        "description": "Portfolio snapshot",
    },
    "performance": {
        "endpoint_deps": ["perf", "trades", "perf_anl"],
        "optional": True,
        "description": "Performance metrics and sparklines",
    },
    "economic": {
        "endpoint_deps": ["eco", "econ_cal"],
        "optional": True,
        "description": "Economic pulse",
    },
    "signals": {
        "endpoint_deps": ["sig", "scores"],
        "optional": True,
        "description": "Signals and composite scores",
    },
    "sectors": {
        "endpoint_deps": ["srank", "pos", "port", "sec_rot", "irank"],
        "optional": True,
        "description": "Sector analysis",
    },
    "positions": {
        "endpoint_deps": ["pos", "trades"],
        "optional": True,
        "description": "Detailed positions",
    },
}
