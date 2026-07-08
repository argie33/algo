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

from typing import Any, cast

from pydantic import BaseModel, Field


class ResponseSchema(BaseModel):
    """Schema for API response validation."""

    required_fields: list[str]
    optional_fields: list[str]
    field_types: dict[str, Any]
    nested_schema: dict[str, Any] | None = None
    description: str = ""


class EndpointDefinition(BaseModel):
    """Definition for a single API endpoint."""

    path: str
    method: str = Field(pattern="^(GET|POST|PUT|DELETE)$")
    description: str
    response_schema: ResponseSchema
    freshness_max_age_seconds: int | None = None
    strict_fields: list[str] = Field(default_factory=list)
    critical: bool = False
    params: dict[str, Any] | None = None


class PanelDefinition(BaseModel):
    """Definition for a dashboard panel."""

    endpoint_deps: list[str]
    optional: bool
    description: str


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
            required_fields=["run_id", "success"],
            optional_fields=[
                "completed_at",
                "started_at",
                "phases",
                "halted",
                "errored",
                "summary",
                "halt_reason",
                "phases_completed",
                "phases_halted",
                "phases_errored",
                "phase_results",
                "last_run",
                "current_phase",
                "status",
                "message",
                "portfolio",
                "data_freshness",
            ],
            field_types={
                "run_id": (str, int),
                "completed_at": (str, type(None)),
                "started_at": (str, type(None)),
                "success": bool,
                "halted": (bool, type(None)),
                "errored": (bool, type(None)),
                "last_run": (str, type(None)),
                "current_phase": (str, type(None)),
                "status": (str, type(None)),
                "message": (str, type(None)),
                "portfolio": dict,
                "data_freshness": dict,
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
                "enable_algo",
                "execution_mode",
                "max_position_size_pct",
                "max_positions",
                "max_positions_per_sector",
                "base_risk_pct",
                "t1_target_r_multiple",
                "min_swing_grade",
                "min_swing_score",
                "swing_grade_threshold_a",
                "swing_grade_threshold_aplus",
                "swing_grade_threshold_b",
                "swing_grade_threshold_c",
                "swing_grade_threshold_d",
            ],
            field_types={},
            nested_schema={"*": dict},
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
                "current",
                "market_health",
                "active_tier",
                "adr",
                "bmom",
                "fed",
                "history",
                "items",
                "nh",
                "nl",
                "pcr",
                "total",
                "ycs",
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
    "exp_factors": {
        "path": "/api/algo/markets",
        "method": "GET",
        "description": "Market exposure factors (derived from markets endpoint)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "exposure_pct",
                "raw_score",
                "regime",
                "factors",
                "regime_unavailable",
                "factors_unavailable",
            ],
            field_types={
                "exposure_pct": (float, int, type(None)),
                "raw_score": (float, int, type(None)),
                "regime": (str, type(None)),
                "factors": (list, dict, type(None)),
            },
            description="Exposure factors and market regime from markets endpoint",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "port": {
        "path": "/api/algo/portfolio",
        "method": "GET",
        "description": "Portfolio snapshot",
        "response_schema": ResponseSchema(
            required_fields=["total_portfolio_value", "total_cash", "position_count"],
            optional_fields=[
                "last_run",
                "total_buying_power",
                "daily_return_pct",
                "unrealized_pnl",
                "unrealized_pnl_pct",
                "unrealized_pnl_dollars",
                "cumulative_return_pct",
                "max_drawdown_pct",
                "largest_position_pct",
                "data_age_seconds",
            ],
            field_types={
                "total_portfolio_value": (float, int, str),
                "total_cash": (float, int, str),
                "position_count": int,
                "daily_return_pct": (float, int, str, type(None)),
                "unrealized_pnl": (dict, type(None)),
                "unrealized_pnl_pct": (float, int, str, type(None)),
                "unrealized_pnl_dollars": (float, int, type(None)),
                "cumulative_return_pct": (float, int, str, type(None)),
                "max_drawdown_pct": (float, int, str, type(None)),
                "largest_position_pct": (float, int, str, type(None)),
                "data_age_seconds": int,
            },
            description="Portfolio value, cash, positions",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": ["total_portfolio_value", "total_cash", "position_count"],
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
                "breakeven_trades",
                "win_rate",
                "win_rate_pct",
                "win_rate_confidence",
                "profit_factor",
                "total_pnl_dollars",
                "total_pnl_pct",
                "total_return_pct",
                "avg_trade_pct",
                "avg_win_pct",
                "avg_loss_pct",
                "avg_win_r",
                "avg_loss_r",
                "gross_win_dollars",
                "gross_loss_dollars",
                "open_positions_count",
                "open_losses_count",
                "total_open_losses_dollars",
                "best_trade_pct",
                "worst_trade_pct",
                "sharpe_annualized",
                "sharpe_ratio",
                "sharpe_confidence",
                "sortino_annualized",
                "sortino_ratio",
                "max_drawdown_pct",
                "calmar_ratio",
                "expectancy_r",
                "avg_hold_days",
                "avg_holding_days",
                "best_win_streak",
                "worst_loss_streak",
                "current_streak",
                "equity_vals",
                "recent_rets",
                "stale_alerts",
                "data_freshness",
            ],
            field_types={
                "total_trades": int,
                "winning_trades": int,
                "losing_trades": int,
                "breakeven_trades": (int, type(None)),
                "win_rate": (float, int, str, type(None)),
                "win_rate_pct": (float, int, str, type(None)),
                "win_rate_confidence": (str, type(None)),
                "profit_factor": (float, int, str, type(None)),
                "total_pnl_dollars": (float, int, str, type(None)),
                "total_pnl_pct": (float, int, str, type(None)),
                "total_return_pct": (float, int, str, type(None)),
                "avg_trade_pct": (float, int, str, type(None)),
                "avg_win_pct": (float, int, str, type(None)),
                "avg_loss_pct": (float, int, str, type(None)),
                "avg_win_r": (float, int, str, type(None)),
                "avg_loss_r": (float, int, str, type(None)),
                "gross_win_dollars": (float, int, str, type(None)),
                "gross_loss_dollars": (float, int, str, type(None)),
                "open_positions_count": (int, type(None)),
                "open_losses_count": (int, type(None)),
                "total_open_losses_dollars": (float, int, str, type(None)),
                "best_trade_pct": (float, int, str, type(None)),
                "worst_trade_pct": (float, int, str, type(None)),
                "sharpe_annualized": (float, int, str, type(None)),
                "sharpe_ratio": (float, int, str, type(None)),
                "sharpe_confidence": (str, type(None)),
                "sortino_annualized": (float, int, str, type(None)),
                "sortino_ratio": (float, int, str, type(None)),
                "max_drawdown_pct": (float, int, str, type(None)),
                "calmar_ratio": (float, int, str, type(None)),
                "expectancy_r": (float, int, str, type(None)),
                "avg_hold_days": (float, int, str, type(None)),
                "avg_holding_days": (float, int, str, type(None)),
                "best_win_streak": (int, type(None)),
                "worst_loss_streak": (int, type(None)),
                "current_streak": (int, type(None)),
                "equity_vals": (list, type(None)),
                "recent_rets": (list, type(None)),
                "stale_alerts": (list, type(None)),
                "data_freshness": (dict, type(None)),
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
            optional_fields=["timestamp", "coverage", "data_freshness", "pagination", "sector_allocation", "stale_alerts"],
            field_types={
                "items": list,
                "coverage": (dict, type(None)),
                "data_freshness": (dict, type(None)),
                "pagination": (dict, type(None)),
                "sector_allocation": (list, dict, type(None)),
                "stale_alerts": (list, type(None)),
            },
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
            optional_fields=["timestamp", "data_freshness", "pagination"],
            field_types={
                "items": list,
                "data_freshness": (dict, type(None)),
                "pagination": (dict, type(None)),
            },
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
                "date",
                "data_freshness",
            ],
            field_types={
                "n": int,
                "total": int,
                "buy_sigs": list,
                "grades": dict,
                "date": (str, type(None)),
                "data_freshness": dict,
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
            optional_fields=[
                "ready_to_trade",
                "summary",
                "items",
                "sources",
                "total",
                "critical_stale",
                "expected_date",
                "as_of",
                "api_route_imports",
                "freshness",
                "status",
                "timestamp",
                "version",
            ],
            field_types={
                "ready_to_trade": bool,
                "summary": dict,
                "items": list,
                "sources": list,
                "total": int,
                "critical_stale": list,
                "expected_date": str,
                "as_of": str,
                "api_route_imports": dict,
                "freshness": dict,
                "status": str,
                "timestamp": str,
                "version": str,
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
            optional_fields=["breakers", "any_triggered", "triggered_count", "data_freshness"],
            field_types={
                "breakers": list,
                "any_triggered": bool,
                "data_freshness": (dict, type(None)),
            },
            description="Circuit breaker states",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "srank": {
        "path": "/api/sectors",
        "method": "GET",
        "description": "Sector rankings with trends",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "date", "signal", "strength", "details", "data_freshness", "limit", "page", "total"],
            field_types={
                "items": list,
                "date": str,
                "signal": str,
                "data_freshness": dict,
                "limit": int,
                "page": int,
                "total": int,
            },
            description="Sector trends and rankings with pagination",
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
            optional_fields=["items", "total", "limit", "offset", "data_freshness"],
            field_types={
                "items": list,
                "total": int,
                "limit": int,
                "offset": int,
                "data_freshness": (dict, type(None)),
            },
            description="Recent activity and audit trail",
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
            optional_fields=["items", "total"],
            field_types={"items": list, "total": int},
            description="Recent notifications",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "sentiment": {
        "path": "/api/algo/sentiment",
        "method": "GET",
        "description": "Market sentiment (fear/greed index and breadth)",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["fear_greed_index", "sentiment_score", "bullish_pct", "bearish_pct", "neutral_pct", "date", "label", "data_freshness"],
            field_types={
                "fear_greed_index": (float, int),
                "sentiment_score": (float, int, type(None)),
                "bullish_pct": (float, int, type(None)),
                "bearish_pct": (float, int, type(None)),
                "neutral_pct": (float, int, type(None)),
            },
            description="Market sentiment with fear/greed index and breadth data",
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
            optional_fields=["items", "total"],
            field_types={"items": list, "total": int},
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
                "svar",
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
        "description": "Performance analytics (Sharpe, Sortino, Calmar, Expectancy, R-multiples)",
        "response_schema": ResponseSchema(
            required_fields=[
                "rolling_sharpe_252d",
                "rolling_sortino_252d",
                "calmar_ratio",
                "win_rate_50t",
                "avg_win_r_50t",
                "avg_loss_r_50t",
                "expectancy",
                "max_drawdown_pct",
            ],
            optional_fields=[],
            field_types={
                "rolling_sharpe_252d": (float, int, type(None)),
                "rolling_sortino_252d": (float, int, type(None)),
                "calmar_ratio": (float, int, type(None)),
                "win_rate_50t": (float, int, type(None)),
                "avg_win_r_50t": (float, int, type(None)),
                "avg_loss_r_50t": (float, int, type(None)),
                "expectancy": (float, int, type(None)),
                "max_drawdown_pct": (float, int, type(None)),
            },
            description="Advanced performance metrics (Sharpe, Sortino, Calmar, Win Rate, Avg Win R, Avg Loss R, Expectancy, Max Drawdown)",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [
            "rolling_sharpe_252d",
            "rolling_sortino_252d",
            "calmar_ratio",
            "win_rate_50t",
            "avg_win_r_50t",
            "avg_loss_r_50t",
            "expectancy",
            "max_drawdown_pct",
        ],
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
                "data_freshness",
            ],
            field_types={
                "total": int,
                "t1": int,
                "data_freshness": (dict, type(None)),
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
            optional_fields=["date", "signal", "strength", "details", "items", "total", "data_freshness"],
            field_types={
                "signal": str,
                "strength": (float, int),
                "items": list,
                "total": int,
                "data_freshness": (dict, type(None)),
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
    "scores": {
        "path": "/api/algo/scores",
        "method": "GET",
        "description": "Stock composite scores with multi-factor ranking",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["top", "total", "data_freshness"],
            field_types={"top": list, "total": int},
            description="Stock scores list with component factors (composite_score, growth_score, momentum_score, quality_score, value_score, positioning_score, stability_score)",
        ),
        "freshness_max_age_seconds": 14400,
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
    "industries/list": {
        "path": "/api/industries",
        "method": "GET",
        "description": "Industry rankings list with pagination",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "page", "limit", "data_freshness"],
            field_types={"items": list, "total": int, "page": int, "limit": int},
            description="Paginated industry rankings",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "industries/detail": {
        "path": "/api/industries/{name}",
        "method": "GET",
        "description": "Single industry detail",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "industry_name",
                "stock_count",
                "composite_score",
                "momentum_score",
                "value_score",
                "quality_score",
                "growth_score",
                "stability_score",
                "data_freshness",
            ],
            field_types={
                "stock_count": int,
                "composite_score": (float, type(None)),
                "momentum_score": (float, type(None)),
            },
            description="Industry detail with scores",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "industries/trend": {
        "path": "/api/industries/{name}/trend",
        "method": "GET",
        "description": "Industry price trend series",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["industry", "trendData", "data_freshness"],
            field_types={"industry": str, "trendData": list},
            description="Industry daily price trend",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "economic/indicators": {
        "path": "/api/economic/indicators",
        "method": "GET",
        "description": "Economic indicators",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["indicators"],
            field_types={"indicators": list},
            description="Leading economic indicators",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "economic/yield-curve": {
        "path": "/api/economic/yield-curve-full",
        "method": "GET",
        "description": "Yield curve and credit spreads",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=[
                "currentCurve",
                "spreads",
                "isInverted",
                "history",
                "credit",
                "breakevens",
                "stress",
            ],
            field_types={"currentCurve": dict, "spreads": dict, "isInverted": bool},
            description="Yield curve and financial stress data",
        ),
        "freshness_max_age_seconds": 3600,
        "strict_fields": [],
        "critical": False,
    },
    "financials/key-metrics": {
        "path": "/api/financials/{symbol}/key-metrics",
        "method": "GET",
        "description": "Valuation and quality key metrics for a symbol",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "data_freshness"],
            field_types={"items": list, "total": int},
            description="Key metrics (P/E, P/B, ROE, margins, etc.)",
        ),
        "freshness_max_age_seconds": 86400,
        "strict_fields": [],
        "critical": False,
    },
    "financials/income-statement": {
        "path": "/api/financials/{symbol}/income-statement",
        "method": "GET",
        "description": "Annual or quarterly income statement history for a symbol",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "data_freshness"],
            field_types={"items": list, "total": int},
            description="Income statement rows (revenue, net income, EPS, etc.)",
        ),
        "freshness_max_age_seconds": 86400,
        "strict_fields": [],
        "critical": False,
    },
    "financials/balance-sheet": {
        "path": "/api/financials/{symbol}/balance-sheet",
        "method": "GET",
        "description": "Annual or quarterly balance sheet history for a symbol",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "data_freshness"],
            field_types={"items": list, "total": int},
            description="Balance sheet rows (assets, liabilities, equity, etc.)",
        ),
        "freshness_max_age_seconds": 86400,
        "strict_fields": [],
        "critical": False,
    },
    "financials/cash-flow": {
        "path": "/api/financials/{symbol}/cash-flow",
        "method": "GET",
        "description": "Annual or quarterly cash flow history for a symbol",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "data_freshness"],
            field_types={"items": list, "total": int},
            description="Cash flow rows (operating/investing/financing activities)",
        ),
        "freshness_max_age_seconds": 86400,
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
            optional_fields=["items", "total", "limit", "offset", "data_freshness"],
            field_types={"items": list, "total": int, "limit": int, "offset": int, "data_freshness": (dict, type(None))},
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
            optional_fields=["items", "total", "limit", "data_freshness"],
            field_types={"items": list, "total": int, "limit": int, "data_freshness": (dict, type(None))},
            description="Recent execution records",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": [],
        "critical": False,
    },
    "stocks": {
        "path": "/api/stocks",
        "method": "GET",
        "params": {"limit": 500, "offset": 0, "search": None, "sector": None},
        "description": "Stocks list with screened data",
        "response_schema": ResponseSchema(
            required_fields=["items", "total"],
            optional_fields=[],
            field_types={"items": list, "total": int},
            description="Paginated list of stocks",
        ),
        "freshness_max_age_seconds": 86400,
        "strict_fields": [],
        "critical": False,
    },
    "market/status": {
        "path": "/api/market/status",
        "method": "GET",
        "description": "Market status and health indicators",
        "response_schema": ResponseSchema(
            required_fields=["date"],
            optional_fields=["market_trend", "market_stage", "advance_decline_ratio", "new_highs_count", "new_lows_count", "vix_level", "put_call_ratio"],
            field_types={"date": str, "vix_level": (int, float)},
            description="Current market status",
        ),
        "freshness_max_age_seconds": 86400,
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
    def get_endpoint(name: str) -> dict[str, Any] | None:
        """Get endpoint definition by name."""
        return DASHBOARD_ENDPOINTS.get(name)

    @staticmethod
    def get_all_endpoints() -> dict[str, dict[str, Any]]:
        """Get all endpoint definitions."""
        return DASHBOARD_ENDPOINTS.copy()

    @staticmethod
    def get_endpoint_path(name: str) -> str | None:
        """Get endpoint path by name."""
        endpoint = DASHBOARD_ENDPOINTS.get(name)
        return cast(str | None, endpoint.get("path") if endpoint else None)

    @staticmethod
    def get_critical_endpoints() -> dict[str, dict[str, Any]]:
        """Get only critical endpoints (dashboard won't render without these).

        FAIL-CLOSED: Raises exception if any endpoint is missing 'critical' field.
        Dashboard reliability depends on explicit configuration, not defaults.
        """
        critical = {}
        for k, v in DASHBOARD_ENDPOINTS.items():
            if "critical" not in v:
                raise KeyError(
                    f"Endpoint '{k}' missing required 'critical' field in dashboard contract. "
                    "All endpoints must explicitly declare critical=True/False."
                )
            if v.get("critical"):
                critical[k] = v
        return critical

    @staticmethod
    def validate_endpoint_exists(name: str) -> bool:
        """Check if endpoint is defined in contract."""
        return name in DASHBOARD_ENDPOINTS

    @staticmethod
    def get_endpoint_freshness(name: str) -> int | None:
        """Get data freshness threshold in seconds for endpoint."""
        endpoint = DASHBOARD_ENDPOINTS.get(name)
        return cast(int | None, endpoint.get("freshness_max_age_seconds") if endpoint else None)


class PanelRegistry:
    """Registry for querying panel definitions."""

    @staticmethod
    def get_panel(name: str) -> dict[str, Any] | None:
        """Get panel definition by name."""
        return DASHBOARD_PANELS.get(name)

    @staticmethod
    def get_all_panels() -> dict[str, dict[str, Any]]:
        """Get all panel definitions."""
        return DASHBOARD_PANELS.copy()

    @staticmethod
    def get_panel_dependencies(name: str) -> list[str]:
        """Get list of endpoints required by a panel.

        FAIL-CLOSED: Raises exception if panel doesn't exist or lacks endpoint_deps field.
        """
        panel = DASHBOARD_PANELS.get(name)
        if not panel:
            raise KeyError(f"Panel '{name}' not found in dashboard contract. All referenced panels must be defined.")
        if "endpoint_deps" not in panel:
            raise KeyError(
                f"Panel '{name}' missing required 'endpoint_deps' field. "
                "All panels must explicitly declare their endpoint dependencies."
            )
        return cast(list[str], panel.get("endpoint_deps"))

    @staticmethod
    def is_panel_optional(name: str) -> bool:
        """Check if a panel is optional.

        FAIL-CLOSED: Raises exception if panel doesn't exist or lacks optional field.
        All panels must explicitly declare optionality, not default to True.
        """
        panel = DASHBOARD_PANELS.get(name)
        if not panel:
            raise KeyError(f"Panel '{name}' not found in dashboard contract. All referenced panels must be defined.")
        if "optional" not in panel:
            raise KeyError(
                f"Panel '{name}' missing required 'optional' field. "
                "All panels must explicitly declare optional=True/False."
            )
        return cast(bool, panel.get("optional"))

    @staticmethod
    def validate_panel_dependencies(name: str) -> tuple[bool, list[str]]:
        """Check if all endpoints for a panel are defined.

        Returns (is_valid, missing_endpoints)
        """
        panel = DASHBOARD_PANELS.get(name)
        if not panel:
            return False, [name]

        missing = []
        endpoint_deps = cast(list[str], panel.get("endpoint_deps"))
        for endpoint_name in endpoint_deps:
            if not EndpointRegistry.validate_endpoint_exists(endpoint_name):
                missing.append(endpoint_name)

        return len(missing) == 0, missing
