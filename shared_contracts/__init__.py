"""Shared API Contract Package.

Provides single source of truth for dashboard-API integration:
- DASHBOARD_ENDPOINTS: All endpoint definitions with schemas
- DASHBOARD_PANELS: Panel definitions and dependencies
- EndpointRegistry: Query endpoints dynamically
- PanelRegistry: Query panels dynamically
- ResponseValidator: Validate API responses against schemas
"""

from .dashboard_api_contract import (
    DASHBOARD_ENDPOINTS,
    DASHBOARD_PANELS,
    EndpointRegistry,
    PanelRegistry,
    ResponseSchema,
)

__all__ = [
    "DASHBOARD_ENDPOINTS",
    "DASHBOARD_PANELS",
    "EndpointRegistry",
    "PanelRegistry",
    "ResponseSchema",
]
