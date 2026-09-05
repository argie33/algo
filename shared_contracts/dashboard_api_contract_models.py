"""Dashboard-API shared contract model classes.

Split out of dashboard_api_contract.py (file-size ratchet decomposition, 2026-09-05)
so that the sibling data files (dashboard_api_contract_endpoints_*.py,
dashboard_api_contract_panels.py) can construct ResponseSchema/EndpointDefinition/
PanelDefinition instances without a circular import against
dashboard_api_contract.py itself (which imports the data files back in).

dashboard_api_contract.py re-exports these three classes, so all existing callers
importing them from `shared_contracts.dashboard_api_contract` or `shared_contracts`
are unaffected.
"""

from typing import Any

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
