"""Dashboard-API Shared Contract (Single Source of Truth).

This module defines the contract between the API and dashboard:
- All endpoint definitions (path, method, schema)
- Response schemas and validation rules
- Data freshness requirements
- Panel definitions and dependencies

Both API and dashboard reference this contract to prevent drift and
ensure compatibility. When adding endpoints or changing schemas,
update this contract first.

UPDATE PROTOCOL:
1. Modify endpoint definition here
2. Update API route to match schema
3. Dashboard fetcher automatically uses new definition
4. Test contract validation with contract_validator.py
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class ResponseSchema:
    """Schema for API response validation."""

    required_fields: List[str]
    optional_fields: List[str]
    field_types: Dict[str, type]
    nested_schema: Optional[Dict[str, Any]] = None
    description: str = ""

# ============================================================================
# DASHBOARD ENDPOINTS - AUTHORITATIVE DEFINITIONS
# ============================================================================
# Each endpoint defines:
# - path: HTTP endpoint path
# - method: HTTP method (GET or POST)
# - params: Query/body parameters accepted
# - response_schema: Required response structure
# - freshness_max_age_seconds: How stale data is acceptable (None = no age check)
# - strict_fields: Fields that must never be None (fail-fast on missing data)
# - critical: If True, dashboard won't render without this data
# ============================================================================

DASHBOARD_ENDPOINTS = {
    "run": {
        "path": "/api/algo/last-run",
        "method": "GET",
        "description": "Last algo run status",
        "response_schema": ResponseSchema(
            required_fields=["run_id", "completed_at", "started_at", "success"],
            optional_fields=[
                "halted",
                "errored",
                "summary",
                "halt_reason",
                "phases_completed",
                "phases_halted",
                "phases_errored",
                "phase_results",
            ],
            field_types={
                "run_id": (str, int),
                "completed_at": str,
                "started_at": str,
                "success": bool,
                "halted": bool,
                "errored": bool,
            },
            description="Last run metadata and status",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": ["run_id", "success"],
        "critical": True,
    },
    "cfg": {
        "path": "/api/algo/config",
        "method": "GET",
        "description": "Algo configuration",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "algo_enabled",
                "trade_mode",
                "max_position_size_pct",
                "max_positions",
                "max_positions_per_sector",
                "min_swing_score",
                "base_risk_pct",
                "t1_target_r_multiple",
            ],
            field_types={
                "algo_enabled": bool,
                "trade_mode": str,
                "max_position_size_pct": (float, int),
                "max_positions": int,
            },
            description="Algo configuration and settings",
        ),
        "freshness_max_age_seconds": None,
        "strict_fields": [],
        "critical": True,
    },
    "mkt": {
        "path": "/api/algo/markets",
        "method": "GET",
        "description": "Market data (SPY, VIX, halts, regime)",
        "response_schema": ResponseSchema(
            required_fields=["spy_close", "vix_level"],
            optional_fields=[
                "timestamp",
                "last_updated",
                "exposure_pct",
                "regime",
                "halt_reasons",
                "market_stage",
                "market_trend",
                "distribution_days_4w",
                "spy_change_pct",
                "up_volume_percent",
                "advance_decline_ratio",
                "new_highs_count",
                "new_lows_count",
                "put_call_ratio",
                "breadth_momentum_10d",
                "yield_curve_slope",
                "fed_rate_environment",
            ],
            field_types={
                "spy_close": (float, int),
                "vix_level": (float, int),
                "timestamp": str,
            },
            description="Critical market data (SPY price, VIX) + indicators",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": ["spy_close", "vix_level"],
        "critical": True,
    },
    "port": {
        "path": "/api/algo/portfolio",
        "method": "GET",
        "description": "Portfolio snapshot",
        "response_schema": ResponseSchema(
            required_fields=["total_portfolio_value", "total_cash", "open_positions"],
            optional_fields=[
                "last_run",
                "total_buying_power",
                "daily_return_pct",
                "unrealized_pnl_pct",
                "cumulative_return_pct",
                "max_drawdown_pct",
                "largest_position_pct",
                "data_age_seconds",
            ],
            field_types={
                "total_portfolio_value": (float, int),
                "total_cash": (float, int),
                "open_positions": int,
            },
            description="Portfolio value, cash, positions",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": ["total_portfolio_value", "total_cash", "open_positions"],
        "critical": True,
    },
    "perf": {
        "path": "/api/algo/performance",
        "method": "GET",
        "description": "Performance metrics and statistics",
        "response_schema": ResponseSchema(
            required_fields=["total_trades", "winning_trades", "losing_trades"],
            optional_fields=[
                "timestamp",
                "last_updated",
                "win_rate_pct",
                "open_positions",
                "total_pnl_dollars",
                "unrealized_pnl",
                "current_streak",
                "sharpe_annualized",
                "max_drawdown_pct",
                "avg_win_pct",
                "avg_loss_pct",
                "profit_factor",
                "expectancy_r",
                "equity_vals",
                "recent_rets",
            ],
            field_types={
                "total_trades": int,
                "winning_trades": int,
                "losing_trades": int,
            },
            description="Trade counts and performance statistics",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": ["total_trades", "winning_trades", "losing_trades"],
        "critical": True,
    },
    "pos": {
        "path": "/api/algo/positions",
        "method": "GET",
        "description": "Open positions",
        "response_schema": ResponseSchema(
            required_fields=["items"],
            optional_fields=["timestamp"],
            field_types={"items": list},
            description="List of open positions with details",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": ["items"],
        "critical": False,
    },
    "trades": {
        "path": "/api/algo/trades",
        "method": "GET",
        "params": {"limit": 10, "status": "closed"},
        "description": "Recent trades",
        "response_schema": ResponseSchema(
            required_fields=["items"],
            optional_fields=["timestamp"],
            field_types={"items": list},
            description="List of recent trades",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": ["items"],
        "critical": False,
    },
    "sig": {
        "path": "/api/algo/dashboard-signals",
        "method": "GET",
        "description": "Dashboard signals and grades",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "n",
                "total",
                "buy_sigs",
                "grades",
                "near",
                "top_a",
                "trend",
            ],
            field_types={
                "n": int,
                "total": int,
                "buy_sigs": list,
                "grades": dict,
            },
            description="Signal counts and classifications",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "health": {
        "path": "/api/algo/data-status",
        "method": "GET",
        "description": "Data loader health status",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["ready_to_trade", "summary", "sources", "items"],
            field_types={
                "ready_to_trade": bool,
                "summary": dict,
                "sources": list,
            },
            description="Data loader health and readiness",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "cb": {
        "path": "/api/algo/circuit-breakers",
        "method": "GET",
        "description": "Circuit breaker status",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["breakers", "any_triggered", "triggered_count"],
            field_types={
                "breakers": list,
                "any_triggered": bool,
            },
            description="Circuit breaker states",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "srank": {
        "path": "/api/algo/sector-rotation",
        "method": "GET",
        "description": "Sector rankings and rotation signal",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "date", "signal", "strength", "details"],
            field_types={
                "items": list,
                "date": str,
                "signal": str,
            },
            description="Sector rotation and rankings",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "activity": {
        "path": "/api/algo/audit-log",
        "method": "GET",
        "params": {"limit": 50, "offset": 0},
        "description": "Activity and audit log",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "items",
                "run_id",
                "run_at",
                "phases",
                "recent_actions",
                "total",
            ],
            field_types={
                "items": list,
            },
            description="Recent activity and audit trail",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "exp_factors": {
        "path": "/api/algo/exposure-policy",
        "method": "GET",
        "description": "Exposure factors and policy",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "factor_quality",
                "current_exposure_pct",
                "regime",
                "factors",
            ],
            field_types={
                "factor_quality": (float, int),
                "current_exposure_pct": (float, int),
            },
            description="Exposure policy and factors",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "eco": {
        "path": "/api/algo/economic-calendar",
        "method": "GET",
        "description": "Economic indicators and calendar",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "t10",
                "t2",
                "t3m",
                "t6m",
                "yc_10_2",
                "yc_10_3m",
                "hy",
                "ig",
                "oil",
                "nfci",
                "fed_funds",
                "cpi_yoy",
                "unrate",
                "be10",
                "be5",
                "dxy",
                "mortgage",
                "umcsent",
                "items",
            ],
            field_types={
                "t10": (float, int),
                "items": list,
            },
            description="Economic data and calendar events",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "notifs": {
        "path": "/api/algo/notifications",
        "method": "GET",
        "params": {"limit": 10},
        "description": "Notifications",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="Recent notifications",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "sentiment": {
        "path": "/api/algo/sentiment",
        "method": "GET",
        "description": "Market sentiment (fear/greed index)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["fear_greed_index", "label", "date"],
            field_types={
                "fear_greed_index": (float, int),
                "label": str,
            },
            description="Fear & Greed index and label",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "econ_cal": {
        "path": "/api/algo/economic-calendar",
        "method": "GET",
        "description": "Economic calendar events",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="Economic calendar events",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "risk": {
        "path": "/api/algo/risk-metrics",
        "method": "GET",
        "description": "Risk metrics (VaR, CVaR, beta, concentration)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "report_date",
                "var_pct_95",
                "cvar_pct_95",
                "stressed_var_pct",
                "portfolio_beta",
                "top_5_concentration",
            ],
            field_types={
                "var_pct_95": (float, int),
                "portfolio_beta": (float, int),
            },
            description="Risk metrics and exposures",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "perf_anl": {
        "path": "/api/algo/performance-analytics",
        "method": "GET",
        "description": "Performance analytics (Sharpe, Sortino, Calmar)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "rolling_sharpe_252d",
                "rolling_sortino_252d",
                "calmar_ratio",
                "win_rate_50t",
                "avg_win_r_50t",
                "avg_loss_r_50t",
                "expectancy",
                "max_drawdown_pct",
            ],
            field_types={
                "rolling_sharpe_252d": (float, int),
                "calmar_ratio": (float, int),
            },
            description="Advanced performance metrics",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "sig_eval": {
        "path": "/api/algo/rejection-funnel",
        "method": "GET",
        "description": "Signal evaluation (rejection funnel stats)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "total",
                "t1",
                "t2",
                "t3",
                "t4",
                "t5",
                "avg_score",
                "signal_date",
                "rejected",
            ],
            field_types={
                "total": int,
                "t1": int,
            },
            description="Signal funnel statistics",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "sec_rot": {
        "path": "/api/algo/sector-rotation",
        "method": "GET",
        "description": "Sector rotation signal",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["date", "signal", "strength", "details"],
            field_types={
                "signal": str,
                "strength": (float, int),
            },
            description="Sector rotation signal and strength",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "algo_metrics": {
        "path": "/api/algo/metrics",
        "method": "GET",
        "description": "Algo system metrics",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="System metrics",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "irank": {
        "path": "/api/industries",
        "method": "GET",
        "description": "Industry rankings",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="Industry rankings",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "audit": {
        "path": "/api/algo/audit-log",
        "method": "GET",
        "params": {"limit": 50, "offset": 0},
        "description": "Audit log",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="Audit log entries",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "exec_hist": {
        "path": "/api/algo/execution/recent",
        "method": "GET",
        "params": {"days": 7, "limit": 10},
        "description": "Execution history",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items"],
            field_types={"items": list},
            description="Recent execution records",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
}

# ============================================================================
# DASHBOARD PANEL DEFINITIONS
# ============================================================================
# Each panel defines:
# - endpoint_deps: Which endpoints it requires
# - data_shape: Expected data structure
# - optional: If true, dashboard still renders if missing
# ============================================================================

DASHBOARD_PANELS = {
    "header": {
        "endpoint_deps": ["mkt", "sentiment"],
        "optional": False,
        "description": "Header with market status and sentiment",
    },
    "exposure": {
        "endpoint_deps": ["exp_factors"],
        "optional": True,
        "description": "Exposure factors",
    },
    "circuit": {
        "endpoint_deps": ["cb"],
        "optional": True,
        "description": "Circuit breaker status",
    },
    "health": {
        "endpoint_deps": ["run", "health", "notifs", "algo_metrics", "audit", "risk"],
        "optional": True,
        "description": "Algo health and data status",
    },
    "portfolio": {
        "endpoint_deps": ["port", "cfg", "risk", "perf"],
        "optional": False,
        "description": "Portfolio snapshot",
    },
    "performance": {
        "endpoint_deps": ["per", "trades", "perf_anl"],
        "optional": True,
        "description": "Performance metrics and sparklines",
    },
    "economic": {
        "endpoint_deps": ["eco", "econ_cal"],
        "optional": True,
        "description": "Economic pulse",
    },
    "signals": {
        "endpoint_deps": ["sig", "sig_eval"],
        "optional": True,
        "description": "Signals and funnel",
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

class EndpointRegistry:
    """Registry for querying endpoint definitions dynamically."""

    @staticmethod
    def get_endpoint(name: str) -> Optional[Dict[str, Any]]:
        """Get endpoint definition by name."""
        return DASHBOARD_ENDPOINTS.get(name)

    @staticmethod
    def get_all_endpoints() -> Dict[str, Dict[str, Any]]:
        """Get all endpoint definitions."""
        return DASHBOARD_ENDPOINTS.copy()

    @staticmethod
    def get_endpoint_path(name: str) -> Optional[str]:
        """Get endpoint path by name."""
        endpoint = DASHBOARD_ENDPOINTS.get(name)
        return endpoint.get("path") if endpoint else None

    @staticmethod
    def get_critical_endpoints() -> Dict[str, Dict[str, Any]]:
        """Get only critical endpoints (dashboard won't render without these)."""
        return {
            k: v for k, v in DASHBOARD_ENDPOINTS.items() if v.get("critical", False)
        }

    @staticmethod
    def validate_endpoint_exists(name: str) -> bool:
        """Check if endpoint is defined in contract."""
        return name in DASHBOARD_ENDPOINTS

    @staticmethod
    def get_endpoint_freshness(name: str) -> Optional[int]:
        """Get data freshness threshold in seconds for endpoint."""
        endpoint = DASHBOARD_ENDPOINTS.get(name)
        return endpoint.get("freshness_max_age_seconds") if endpoint else None

class PanelRegistry:
    """Registry for querying panel definitions."""

    @staticmethod
    def get_panel(name: str) -> Optional[Dict[str, Any]]:
        """Get panel definition by name."""
        return DASHBOARD_PANELS.get(name)

    @staticmethod
    def get_all_panels() -> Dict[str, Dict[str, Any]]:
        """Get all panel definitions."""
        return DASHBOARD_PANELS.copy()

    @staticmethod
    def get_panel_dependencies(name: str) -> List[str]:
        """Get list of endpoints required by a panel."""
        panel = DASHBOARD_PANELS.get(name)
        return panel.get("endpoint_deps", []) if panel else []

    @staticmethod
    def is_panel_optional(name: str) -> bool:
        """Check if a panel is optional."""
        panel = DASHBOARD_PANELS.get(name)
        return panel.get("optional", True) if panel else True

    @staticmethod
    def validate_panel_dependencies(name: str) -> tuple[bool, List[str]]:
        """Check if all endpoints for a panel are defined.

        Returns (is_valid, missing_endpoints)
        """
        panel = DASHBOARD_PANELS.get(name)
        if not panel:
            return False, [name]

        missing = []
        for endpoint_name in panel.get("endpoint_deps", []):
            if not EndpointRegistry.validate_endpoint_exists(endpoint_name):
                missing.append(endpoint_name)

        return len(missing) == 0, missing
