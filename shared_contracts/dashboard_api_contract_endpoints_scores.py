"""Dashboard API contract - scores/industries/stocks endpoints.

Split out of dashboard_api_contract.py (file-size ratchet decomposition, 2026-09-05).
Data-only module: composite scores, industry rankings/detail/trend, stocks list,
and earnings calendar endpoints."""

from typing import Any

from .dashboard_api_contract_models import ResponseSchema

SCORES_INDUSTRIES_ENDPOINTS: dict[str, dict[str, Any]] = {
    "scores": {
        "path": "/api/algo/scores",
        "method": "GET",
        "description": "Stock composite scores with multi-factor ranking",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["top", "total", "universe_total", "avg_composite", "grades", "data_freshness"],
            field_types={"top": list, "total": int, "universe_total": int, "avg_composite": float, "grades": dict},
            description="Stock scores list with component factors (symbol, company_name, composite_score, growth_score, momentum_score, quality_score, value_score, risk_score, sector, industry, current_price, change_percent, rs_percentile), plus universe_total/avg_composite/grades summary metrics over the full filtered universe. positioning_score REMOVED 2026-08-27 and size_score REMOVED 2026-08-28 (both retired as composite pillars - see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS); raw positioning inputs (A/D rating, institutional ownership, short interest) are still available informationally via the single-stock detail endpoint's positioning_inputs, not this list endpoint. market_cap remains available via the Value pillar's inputs.",
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
                "risk_score",
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
    "earnings": {
        "path": "/api/earnings",
        "method": "GET",
        "params": {"limit": 100},
        "description": "Recent 10-K/10-Q earnings-related filing dates across the universe",
        "response_schema": ResponseSchema(
            required_fields=[],
            optional_fields=["items", "total", "data_freshness"],
            field_types={"items": list, "total": int},
            description="Earnings filing dates (symbol, report_date, fiscal_period)",
        ),
        "freshness_max_age_seconds": 10368000,
        "strict_fields": [],
        "critical": False,
    },
}
