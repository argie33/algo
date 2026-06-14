"""OpenAPI/Swagger specification generator for the API.

Provides complete OpenAPI 3.0 spec for:
- Route documentation
- Request/response type definitions
- Authentication requirements
- Status codes and error handling
- Data freshness metadata
"""

import json
from datetime import datetime


def generate_openapi_spec():
    """Generate complete OpenAPI 3.0 specification.

    Returns:
        dict: OpenAPI spec with all routes, schemas, and documentation
    """
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Algo Trading API",
            "version": "v2-2026-06-14",
            "description": "RESTful API for algorithmic trading signals, market data, and portfolio management",
            "contact": {
                "name": "API Support",
                "email": "argeropolos@gmail.com"
            }
        },
        "servers": [
            {
                "url": "https://api.algotrading.com",
                "description": "Production API"
            },
            {
                "url": "http://localhost:8000",
                "description": "Local development"
            }
        ],
        "security": [
            {"bearerAuth": []}
        ],
        "tags": [
            {"name": "Health", "description": "Health check endpoints"},
            {"name": "Stocks", "description": "Stock data and information"},
            {"name": "Signals", "description": "Trading signals"},
            {"name": "Financials", "description": "Financial statements and metrics"},
            {"name": "Prices", "description": "Historical price data"},
            {"name": "Market", "description": "Market data and indices"},
            {"name": "Sectors & Industries", "description": "Sector and industry data"},
            {"name": "Scores & Rankings", "description": "Stock quality scores and rankings"},
            {"name": "Earnings", "description": "Earnings reports"},
            {"name": "Economic", "description": "Economic indicators"},
            {"name": "Trades", "description": "Trading records"},
            {"name": "Admin", "description": "Administrative endpoints"},
            {"name": "Audit", "description": "Audit logs"},
            {"name": "Settings", "description": "User settings"},
            {"name": "Research", "description": "Research and analysis"},
            {"name": "Contact", "description": "Contact form"},
            {"name": "Logs", "description": "Frontend logging"},
            {"name": "Data Coverage", "description": "Data freshness and coverage"},
        ],
        "paths": _get_paths(),
        "components": {
            "schemas": _get_schemas(),
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT token from Cognito"
                }
            },
            "responses": _get_common_responses(),
        }
    }
    return spec


def _get_paths():
    """Generate API paths for all endpoints."""
    return {
        "/api/health": {
            "get": {
                "tags": ["Health"],
                "summary": "Basic health check",
                "description": "Fast health check with DB connectivity and key metrics. No authentication required.",
                "security": [],
                "responses": {
                    "200": {
                        "description": "API is healthy",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthResponse"}
                            }
                        }
                    },
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/health/cognito": {
            "get": {
                "tags": ["Health"],
                "summary": "Cognito configuration check",
                "description": "Verify Cognito client ID matches AWS configuration. Used in pre-deploy validation.",
                "security": [],
                "responses": {
                    "200": {"description": "Cognito configuration is valid"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/health/detailed": {
            "get": {
                "tags": ["Health"],
                "summary": "Detailed health check",
                "description": "Exposes database schema information. Requires authentication.",
                "responses": {
                    "200": {"description": "Detailed health status"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/health/pipeline": {
            "get": {
                "tags": ["Health"],
                "summary": "Pipeline data freshness check",
                "description": "Check freshness of critical data loaders. Requires authentication.",
                "responses": {
                    "200": {"description": "Pipeline status"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/stocks/{symbol}": {
            "get": {
                "tags": ["Stocks"],
                "summary": "Get stock profile",
                "description": "Retrieve company profile, sector, industry, and exchange information",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "pattern": "^[A-Z0-9\\-\\^]{1,10}$"},
                        "description": "Stock symbol (e.g., AAPL, BRK-A)"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Stock profile",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StockProfileResponse"}
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/stocks/deep-value": {
            "get": {
                "tags": ["Stocks"],
                "summary": "Deep value stocks screener",
                "description": "Find undervalued stocks based on multiple value metrics",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 200, "maximum": 1000},
                        "description": "Maximum number of results"
                    }
                ],
                "responses": {
                    "200": {"description": "List of deep value stocks"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/signals": {
            "get": {
                "tags": ["Signals"],
                "summary": "Get trading signals",
                "description": "Retrieve recent buy/sell trading signals with technical indicators",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 500, "maximum": 10000},
                        "description": "Maximum number of signals"
                    },
                    {
                        "name": "timeframe",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["daily"], "default": "daily"},
                        "description": "Signal timeframe"
                    },
                    {
                        "name": "symbol",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Filter by stock symbol"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Trading signals",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SignalsResponse"}
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/signals/etf": {
            "get": {
                "tags": ["Signals"],
                "summary": "Get ETF signals",
                "description": "Retrieve buy/sell signals for major ETFs (SPY, QQQ, IWM, etc.)",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 500},
                        "description": "Maximum number of signals"
                    }
                ],
                "responses": {
                    "200": {"description": "ETF signals"}
                }
            }
        },
        "/api/financials/{symbol}/key-metrics": {
            "get": {
                "tags": ["Financials"],
                "summary": "Get key financial metrics",
                "description": "P/E ratio, price-to-book, ROE, debt-to-equity, and other key metrics",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Key metrics",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/KeyMetricsResponse"}
                            }
                        }
                    },
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/financials/{symbol}/income-statement": {
            "get": {
                "tags": ["Financials"],
                "summary": "Get income statement",
                "description": "Annual or quarterly income statement data",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "period",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"}
                    }
                ],
                "responses": {
                    "200": {"description": "Income statement data"},
                    "503": {"$ref": "#/components/responses/ServiceUnavailable"}
                }
            }
        },
        "/api/financials/{symbol}/balance-sheet": {
            "get": {
                "tags": ["Financials"],
                "summary": "Get balance sheet",
                "description": "Annual or quarterly balance sheet data",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "period",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"}
                    }
                ],
                "responses": {
                    "200": {"description": "Balance sheet data"}
                }
            }
        },
        "/api/financials/{symbol}/cash-flow": {
            "get": {
                "tags": ["Financials"],
                "summary": "Get cash flow statement",
                "description": "Annual or quarterly cash flow statement data",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "period",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"}
                    }
                ],
                "responses": {
                    "200": {"description": "Cash flow statement data"}
                }
            }
        },
        "/api/sectors": {
            "get": {
                "tags": ["Sectors & Industries"],
                "summary": "List sectors",
                "description": "Get list of market sectors with summary statistics",
                "responses": {
                    "200": {"description": "List of sectors"}
                }
            }
        },
        "/api/industries": {
            "get": {
                "tags": ["Sectors & Industries"],
                "summary": "List industries",
                "description": "Get list of industries with sector classification",
                "responses": {
                    "200": {"description": "List of industries"}
                }
            }
        },
        "/api/prices/{symbol}": {
            "get": {
                "tags": ["Prices"],
                "summary": "Get historical prices",
                "description": "Daily OHLCV data for a stock",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "days",
                        "in": "query",
                        "schema": {"type": "integer", "default": 252},
                        "description": "Number of trading days"
                    }
                ],
                "responses": {
                    "200": {"description": "Historical price data"}
                }
            }
        },
        "/api/market": {
            "get": {
                "tags": ["Market"],
                "summary": "Get market overview",
                "description": "Market summary with key indices and breadth data",
                "responses": {
                    "200": {"description": "Market overview"}
                }
            }
        },
        "/api/earnings": {
            "get": {
                "tags": ["Earnings"],
                "summary": "Get earnings calendar",
                "description": "Upcoming and recent earnings reports",
                "responses": {
                    "200": {"description": "Earnings data"}
                }
            }
        },
        "/api/economic": {
            "get": {
                "tags": ["Economic"],
                "summary": "Get economic indicators",
                "description": "Key economic indicators and forecasts",
                "responses": {
                    "200": {"description": "Economic indicators"}
                }
            }
        },
        "/api/scores": {
            "get": {
                "tags": ["Scores & Rankings"],
                "summary": "Get stock quality scores",
                "description": "Quality composite scores and component breakdowns",
                "parameters": [
                    {
                        "name": "sector",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Filter by sector"
                    }
                ],
                "responses": {
                    "200": {"description": "Stock scores"}
                }
            }
        },
        "/api/trades": {
            "get": {
                "tags": ["Trades"],
                "summary": "Get trades",
                "description": "Retrieve trading records and performance",
                "responses": {
                    "200": {"description": "Trading records"}
                }
            }
        },
        "/api/contact": {
            "post": {
                "tags": ["Contact"],
                "summary": "Submit contact form",
                "description": "Submit feedback or support request",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string", "format": "email"},
                                    "subject": {"type": "string"},
                                    "message": {"type": "string"}
                                },
                                "required": ["email", "subject", "message"]
                            }
                        }
                    }
                },
                "security": [],
                "responses": {
                    "200": {"description": "Contact form submitted"},
                    "400": {"$ref": "#/components/responses/BadRequest"}
                }
            }
        },
        "/api/settings": {
            "get": {
                "tags": ["Settings"],
                "summary": "Get user settings",
                "description": "Retrieve user preferences and settings",
                "responses": {
                    "200": {"description": "User settings"}
                }
            },
            "put": {
                "tags": ["Settings"],
                "summary": "Update user settings",
                "description": "Update user preferences",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "theme": {"type": "string"},
                                    "notifications": {"type": "boolean"},
                                    "language": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Settings updated"}
                }
            }
        },
        "/api/data-coverage": {
            "get": {
                "tags": ["Data Coverage"],
                "summary": "Get data freshness status",
                "description": "Check data completeness and freshness for all tables",
                "responses": {
                    "200": {"description": "Data coverage status"}
                }
            }
        },
        "/api/openapi.json": {
            "get": {
                "tags": ["API Documentation"],
                "summary": "Get OpenAPI specification",
                "description": "Machine-readable OpenAPI 3.0 specification",
                "security": [],
                "responses": {
                    "200": {
                        "description": "OpenAPI specification",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    }
                }
            }
        },
        "/api/swagger": {
            "get": {
                "tags": ["API Documentation"],
                "summary": "Swagger UI interactive documentation",
                "description": "Interactive API documentation with Swagger UI",
                "security": [],
                "responses": {
                    "200": {
                        "description": "Swagger UI HTML page",
                        "content": {
                            "text/html": {
                                "schema": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "/api/redoc": {
            "get": {
                "tags": ["API Documentation"],
                "summary": "ReDoc interactive documentation",
                "description": "Alternative interactive API documentation with ReDoc",
                "security": [],
                "responses": {
                    "200": {
                        "description": "ReDoc HTML page",
                        "content": {
                            "text/html": {
                                "schema": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
    }


def _get_schemas():
    """Generate JSON schemas for all response types."""
    return {
        "DataFreshness": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["OK", "WARNING", "STALE", "CRITICAL"]},
                "table_name": {"type": "string"},
                "age_hours": {"type": "number"},
                "age_days": {"type": "number"},
                "last_updated": {"type": "string", "format": "date-time"},
                "warning_threshold_days": {"type": "integer"}
            },
            "required": ["status"]
        },
        "HealthStatus": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["healthy", "degraded", "unhealthy"]},
                "version": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "api_route_imports": {"type": "object"},
                "freshness": {"type": "object"},
                "last_load_time": {"type": "string", "format": "date-time"}
            },
            "required": ["status", "version", "timestamp"]
        },
        "HealthResponse": {
            "type": "object",
            "properties": {
                "statusCode": {"type": "integer", "example": 200},
                "data": {"$ref": "#/components/schemas/HealthStatus"},
                "data_freshness": {"$ref": "#/components/schemas/DataFreshness"}
            },
            "required": ["statusCode", "data"]
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "statusCode": {"type": "integer"},
                "errorType": {"type": "string"},
                "message": {"type": "string"},
                "_error": {"type": "string"},
                "_diagnostic": {"type": "object"}
            },
            "required": ["statusCode", "errorType", "message", "_error"]
        },
        "StockProfile": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "company_name": {"type": "string"},
                "sector": {"type": "string"},
                "industry": {"type": "string"},
                "website": {"type": "string"},
                "employees": {"type": "integer"},
                "exchange": {"type": "string"}
            },
            "required": ["symbol"]
        },
        "StockProfileResponse": {
            "type": "object",
            "properties": {
                "statusCode": {"type": "integer", "example": 200},
                "data": {"$ref": "#/components/schemas/StockProfile"}
            },
            "required": ["statusCode", "data"]
        },
        "Signal": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "symbol": {"type": "string"},
                "signal": {"type": "string", "enum": ["BUY", "SELL"]},
                "date": {"type": "string", "format": "date-time"},
                "strength": {"type": "number"},
                "signal_quality_score": {"type": "number"},
                "rsi": {"type": "number"},
                "sma_50": {"type": "number"},
                "sma_200": {"type": "number"},
                "sector": {"type": "string"},
                "industry": {"type": "string"},
                "_is_fallback": {"type": "boolean"}
            },
            "required": ["symbol", "signal", "date"]
        },
        "ListResponseData": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"}
            },
            "required": ["items", "total"]
        },
        "SignalsResponse": {
            "type": "object",
            "properties": {
                "statusCode": {"type": "integer", "example": 200},
                "data": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"$ref": "#/components/schemas/Signal"}},
                        "total": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "offset": {"type": "integer"}
                    }
                },
                "data_freshness": {"$ref": "#/components/schemas/DataFreshness"}
            },
            "required": ["statusCode", "data"]
        },
        "KeyMetricsResponse": {
            "type": "object",
            "properties": {
                "statusCode": {"type": "integer", "example": 200},
                "data": {"$ref": "#/components/schemas/ListResponseData"},
                "data_freshness": {"$ref": "#/components/schemas/DataFreshness"}
            }
        },
    }


def _get_common_responses():
    """Generate common response definitions."""
    return {
        "BadRequest": {
            "description": "Bad request - invalid parameters",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "statusCode": 400,
                        "errorType": "bad_request",
                        "message": "Invalid symbol format",
                        "_error": "bad_request"
                    }
                }
            }
        },
        "Unauthorized": {
            "description": "Unauthorized - authentication required",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "statusCode": 401,
                        "errorType": "unauthorized",
                        "message": "Authentication required",
                        "_error": "unauthorized"
                    }
                }
            }
        },
        "NotFound": {
            "description": "Resource not found",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "statusCode": 404,
                        "errorType": "not_found",
                        "message": "Stock not found",
                        "_error": "not_found"
                    }
                }
            }
        },
        "ServiceUnavailable": {
            "description": "Service unavailable - database or external service error",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                    "example": {
                        "statusCode": 503,
                        "errorType": "connection_error",
                        "message": "Database connection failed",
                        "_error": "connection_error"
                    }
                }
            }
        }
    }
