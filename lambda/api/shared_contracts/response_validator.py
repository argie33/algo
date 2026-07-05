"""Response validator for API contracts - validates API responses against expected schemas."""

from __future__ import annotations

from typing import Any


class ResponseValidator:
    """Validates API responses match expected contract schemas."""

    # Define schemas for each endpoint - non-strict validation mode
    # Each schema just checks for required fields; all other validation is done by type coercion
    SCHEMAS = {
        "run": {"required": []},
        "port": {"required": []},
        "cfg": {"required": []},
        "mkt": {"required": []},
        "pos": {"required": []},
        "trades": {"required": []},
        "cb": {"required": []},
        "sig": {"required": []},
        "econ_cal": {"required": []},
        "sentiment": {"required": []},
        "health": {"required": []},
        "perf": {"required": []},
        "perf_anl": {"required": []},
        "risk": {"required": []},
        "audit": {"required": []},
        "notifs": {"required": []},
        "scores": {"required": []},
        "sec_rot": {"required": []},
        "srank": {"required": []},
        "sig_eval": {"required": []},
        "industries/list": {"required": ["items", "total"]},
        "industries/detail": {"required": []},
    }

    @staticmethod
    def validate_endpoint_response(endpoint_name: str, response_data: Any) -> tuple[bool, str]:
        """Validate response against schema for endpoint.

        Args:
            endpoint_name: Name of endpoint (e.g., 'cfg', 'run', 'port')
            response_data: Response data to validate

        Returns:
            (is_valid, error_message) tuple
        """
        # If no schema defined for endpoint, allow it (non-strict mode)
        schema = ResponseValidator.SCHEMAS.get(endpoint_name)
        if schema is None:
            return True, ""

        # If response_data is not a dict, validation fails
        if not isinstance(response_data, dict):
            return False, f"Expected dict, got {type(response_data).__name__}"

        # Check required fields
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in response_data:
                return False, f"Missing required field: {field}"

        return True, ""
