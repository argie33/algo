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

FILE-SIZE-RATCHET DECOMPOSITION (2026-09-05): the declarative endpoint/panel data
that used to live here in one ~1,150-line block now lives in sibling data-only
modules, grouped by dashboard/API area:
- dashboard_api_contract_models.py: ResponseSchema/EndpointDefinition/PanelDefinition
  (moved out only to avoid a circular import with the data files below; re-exported
  here so every existing import path is unaffected)
- dashboard_api_contract_endpoints_core.py: core algo/dashboard operational endpoints
  (run, config, portfolio, performance, health, audit, execution history, etc.)
- dashboard_api_contract_endpoints_market.py: market/economic/risk endpoints
  (sector rankings, economic calendar, sentiment, risk metrics, performance
  analytics, market status)
- dashboard_api_contract_endpoints_scores.py: scores/industries/stocks endpoints
- dashboard_api_contract_endpoints_financials.py: per-symbol financials + batch
  price history endpoints
- dashboard_api_contract_panels.py: dashboard panel definitions

This file keeps the "engine": the model classes (re-exported from
dashboard_api_contract_models), the merged DASHBOARD_ENDPOINTS/DASHBOARD_PANELS
dicts, and the EndpointRegistry/PanelRegistry classes that consume them. No
behavior change - every endpoint/panel entry moved verbatim.
"""

from typing import Any, cast

from .dashboard_api_contract_endpoints_core import CORE_ENDPOINTS
from .dashboard_api_contract_endpoints_financials import FINANCIALS_PRICES_ENDPOINTS
from .dashboard_api_contract_endpoints_market import MARKET_ECONOMIC_ENDPOINTS
from .dashboard_api_contract_endpoints_scores import SCORES_INDUSTRIES_ENDPOINTS
from .dashboard_api_contract_models import (
    EndpointDefinition,
    PanelDefinition,
    ResponseSchema,
)
from .dashboard_api_contract_panels import DASHBOARD_PANELS

__all__ = [
    "DASHBOARD_ENDPOINTS",
    "DASHBOARD_PANELS",
    "EndpointDefinition",
    "EndpointRegistry",
    "PanelDefinition",
    "PanelRegistry",
    "ResponseSchema",
]

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
#
# The actual entries live in the sibling dashboard_api_contract_endpoints_*.py
# modules (grouped by dashboard/API area) and are merged back together here,
# in the same order as the original single dict, so DASHBOARD_ENDPOINTS is
# identical to what it was before the split.
# ============================================================================

DASHBOARD_ENDPOINTS: dict[str, dict[str, Any]] = {
    **CORE_ENDPOINTS,
    **MARKET_ECONOMIC_ENDPOINTS,
    **SCORES_INDUSTRIES_ENDPOINTS,
    **FINANCIALS_PRICES_ENDPOINTS,
}

# ============================================================================
# DASHBOARD PANEL DEFINITIONS
# ============================================================================
# Each panel defines:
# - endpoint_deps: Which endpoints it requires
# - data_shape: Expected data structure
# - optional: If true, dashboard still renders if missing
#
# The actual entries live in dashboard_api_contract_panels.py.
# ============================================================================


class EndpointRegistry:
    """Registry for querying endpoint definitions dynamically."""

    @staticmethod
    def get_endpoint(name: str) -> dict[str, Any] | None:
        return DASHBOARD_ENDPOINTS.get(name)

    @staticmethod
    def get_all_endpoints() -> dict[str, dict[str, Any]]:
        return DASHBOARD_ENDPOINTS.copy()

    @staticmethod
    def get_endpoint_path(name: str) -> str | None:
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
        return name in DASHBOARD_ENDPOINTS

    @staticmethod
    def get_endpoint_freshness(name: str) -> int | None:
        endpoint = DASHBOARD_ENDPOINTS.get(name)
        return cast(int | None, endpoint.get("freshness_max_age_seconds") if endpoint else None)


class PanelRegistry:
    """Registry for querying panel definitions."""

    @staticmethod
    def get_panel(name: str) -> dict[str, Any] | None:
        return DASHBOARD_PANELS.get(name)

    @staticmethod
    def get_all_panels() -> dict[str, dict[str, Any]]:
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
