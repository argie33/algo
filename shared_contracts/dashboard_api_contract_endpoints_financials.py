"""Dashboard API contract - financials/prices endpoints.

Split out of dashboard_api_contract.py (file-size ratchet decomposition, 2026-09-05).
Data-only module: per-symbol financial statement endpoints and batch price history."""

from typing import Any

from .dashboard_api_contract_models import ResponseSchema

FINANCIALS_PRICES_ENDPOINTS: dict[str, dict[str, Any]] = {
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
    "prices": {
        "path": "/api/prices/batch-history",
        "method": "GET",
        "description": "Historical price data for multiple symbols",
        "response_schema": ResponseSchema(
            required_fields=["symbols", "limit"],
            optional_fields=["data_freshness"],
            field_types={
                "symbols": dict,
                "limit": int,
                "data_freshness": (dict, type(None)),
            },
            nested_schema={"symbols": {"*": list}},
            description="Batch historical prices with symbols keyed to lists of OHLCV data",
        ),
        "freshness_max_age_seconds": 300,
        "strict_fields": ["symbols", "limit"],
        "critical": False,
    },
}
