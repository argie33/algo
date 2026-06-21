#!/usr/bin/env python3
"""
External Service Response Validation

Provides defensive validation for responses from external services:
- Cognito token claims and responses
- DynamoDB operations
- AWS service responses

Pattern: Call validate() after every external service call to catch errors early.
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class CognitoValidator:
    """Validates Cognito JWT claims and API responses."""

    @staticmethod
    def validate_jwt_claims(jwt_claims: dict[str, Any] | None) -> dict[str, Any]:
        """Validate Cognito JWT claims structure.

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'sub': str or None,
            'cognito_groups': list or [],
            'email': str or None,
        }
        """
        if jwt_claims is None:
            return {
                "valid": False,
                "errors": ["JWT claims are None"],
                "sub": None,
                "cognito_groups": [],
                "email": None,
            }

        if not isinstance(jwt_claims, dict):
            return {
                "valid": False,
                "errors": [f"JWT claims must be dict, got {type(jwt_claims).__name__}"],
                "sub": None,
                "cognito_groups": [],
                "email": None,
            }

        errors = []

        # Validate 'sub' (subject claim - user ID)
        sub = jwt_claims.get("sub")
        if not sub or not isinstance(sub, str):
            errors.append(f"Invalid or missing 'sub' claim: {sub}")

        # Validate 'cognito:groups' (group membership)
        groups = jwt_claims.get("cognito:groups")
        if groups is not None and not isinstance(groups, list):
            errors.append(f"'cognito:groups' must be list, got {type(groups).__name__}")
            groups = []
        elif groups is None:
            groups = []

        # Validate 'email' (optional but should be string if present)
        email = jwt_claims.get("email")
        if email is not None and not isinstance(email, str):
            errors.append(f"'email' claim must be string, got {type(email).__name__}")
            email = None

        return {
            "valid": len(errors) == 0 and sub is not None,
            "errors": errors,
            "sub": sub,
            "cognito_groups": groups,
            "email": email,
        }

    @staticmethod
    def validate_admin_access(jwt_claims: dict[str, Any] | None) -> bool:
        """Check if user has admin access.

        Properly validates JWT claims before checking group membership.
        Returns False if claims are invalid or user not in admin group.
        """
        validation = CognitoValidator.validate_jwt_claims(jwt_claims)
        if not validation["valid"]:
            logger.warning(f"JWT validation failed: {validation['errors']}")
            return False
        return "admin" in validation["cognito_groups"]

    @staticmethod
    def log_validation_errors(errors: list[str], context: str = "") -> None:
        """Log Cognito validation errors for debugging."""
        for error in errors:
            logger.error(f"[Cognito Validation] {error} {context}")


class DynamoDBValidator:
    """Validates DynamoDB operation responses."""

    @staticmethod
    def validate_get_item_response(response: dict[str, Any]) -> dict[str, Any]:
        """Validate response from table.get_item().

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'item': dict or None,
            'found': bool,
        }
        """
        if not isinstance(response, dict):
            return {
                "valid": False,
                "errors": [f"Response must be dict, got {type(response).__name__}"],
                "item": None,
                "found": False,
            }

        errors = []

        # Check for AWS error response
        if "Error" in response:
            errors.append(f"DynamoDB error: {response['Error'].get('Message', 'Unknown')}")

        # Validate response structure
        item = response.get("Item")
        found = item is not None

        if item is not None and not isinstance(item, dict):
            errors.append(f"Item must be dict, got {type(item).__name__}")
            item = None
            found = False

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "item": item,
            "found": found,
        }

    @staticmethod
    def validate_put_item_response(response: dict[str, Any]) -> dict[str, Any]:
        """Validate response from table.put_item().

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'status_code': int or None,
        }
        """
        if not isinstance(response, dict):
            return {
                "valid": False,
                "errors": [f"Response must be dict, got {type(response).__name__}"],
                "status_code": None,
            }

        errors = []

        # Check for AWS error response
        if "Error" in response:
            errors.append(f"DynamoDB error: {response['Error'].get('Message', 'Unknown')}")

        # Check for HTTP status code
        response_metadata = response.get("ResponseMetadata")
        status_code = response_metadata.get("HTTPStatusCode") if response_metadata else None
        if status_code is not None:
            if status_code not in (200, 201):
                errors.append(f"DynamoDB returned status code {status_code}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "status_code": status_code,
        }

    @staticmethod
    def validate_update_item_response(response: dict[str, Any]) -> dict[str, Any]:
        """Validate response from table.update_item().

        Returns: {
            'valid': bool,
            'errors': [str] or [],
            'attributes': dict or None,
        }
        """
        if not isinstance(response, dict):
            return {
                "valid": False,
                "errors": [f"Response must be dict, got {type(response).__name__}"],
                "attributes": None,
            }

        errors = []

        # Check for AWS error response
        if "Error" in response:
            errors.append(f"DynamoDB error: {response['Error'].get('Message', 'Unknown')}")

        attributes = response.get("Attributes")
        if attributes is not None and not isinstance(attributes, dict):
            errors.append(f"Attributes must be dict, got {type(attributes).__name__}")
            attributes = None

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "attributes": attributes,
        }

    @staticmethod
    def log_validation_errors(errors: list[str], context: str = "") -> None:
        """Log DynamoDB validation errors for debugging."""
        for error in errors:
            logger.error(f"[DynamoDB Validation] {error} {context}")


class DatabaseResultValidator:
    """Validates database query results for type safety."""

    @staticmethod
    def safe_get_float(row: dict[str, Any] | None, key: str, default: float = 0.0, strict: bool = False) -> float:
        """Safely extract and convert float from database row.

        Args:
            row: Database row dict (from DictCursor)
            key: Column name
            default: Default value if missing or invalid
            strict: If True, raise exception on invalid value

        Returns:
            Float value or default
        """
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            return default

        try:
            value = row.get(key)
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to float: {e}") from None
            logger.warning(f"Failed to convert {key}={row.get(key)} to float, using default")
            return default

    @staticmethod
    def safe_get_int(row: dict[str, Any] | None, key: str, default: int = 0, strict: bool = False) -> int:
        """Safely extract and convert int from database row."""
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            return default

        try:
            value = row.get(key)
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to int: {e}") from None
            logger.warning(f"Failed to convert {key}={row.get(key)} to int, using default")
            return default

    @staticmethod
    def safe_get_str(row: dict[str, Any] | None, key: str, default: str = "", strict: bool = False) -> str:
        """Safely extract and convert string from database row."""
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            return default

        try:
            value = row.get(key)
            if value is None:
                return default
            return str(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to str: {e}") from None
            logger.warning(f"Failed to convert {key}={row.get(key)} to str, using default")
            return default

    @staticmethod
    def validate_row_not_none(row: Any, context: str = "database query") -> bool:
        """Validate that database row is not None.

        Args:
            row: Row from fetchone() or similar
            context: Operation name for logging

        Returns:
            True if row is not None, False otherwise
        """
        if row is None:
            logger.warning(f"{context}: fetchone() returned None (no rows found)")
            return False
        return True

    @staticmethod
    def validate_rows_not_empty(rows: list[Any] | None, context: str = "database query") -> bool:
        """Validate that database rows list is not empty.

        Args:
            rows: List from fetchall()
            context: Operation name for logging

        Returns:
            True if rows is not None and not empty
        """
        if rows is None:
            logger.warning(f"{context}: fetchall() returned None")
            return False
        if len(rows) == 0:
            logger.debug(f"{context}: fetchall() returned empty list")
            return False
        return True

    @staticmethod
    def safe_get_first_row(rows: list[Any] | None, context: str = "database query") -> Any | None:
        """Safely get first row from query results. Returns None if rows are empty or None.

        ALWAYS USE THIS instead of rows[0] to prevent IndexError.

        Args:
            rows: List from fetchall()
            context: Operation name for logging

        Returns:
            First row or None if empty/unavailable
        """
        if rows is None:
            logger.warning(f"{context}: fetchall() returned None")
            return None
        if len(rows) == 0:
            logger.debug(f"{context}: fetchall() returned empty list")
            return None
        return rows[0]


__all__ = [
    "CognitoValidator",
    "DatabaseResultValidator",
    "DynamoDBValidator",
]
