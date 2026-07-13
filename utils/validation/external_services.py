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

        # Validate 'sub' (subject claim - user ID) - explicit presence check
        sub = jwt_claims.get("sub") if "sub" in jwt_claims else None
        if not sub or not isinstance(sub, str):
            errors.append(f"Invalid or missing 'sub' claim: {sub}")

        # Validate 'cognito:groups' (group membership) - explicit presence check
        groups = None  # Default to empty list only on explicit absence
        if "cognito:groups" in jwt_claims:
            groups = jwt_claims["cognito:groups"]
            if groups is not None and not isinstance(groups, list):
                errors.append(f"'cognito:groups' must be list, got {type(groups).__name__}")
                groups = None  # Mark as invalid, don't silently use empty list
            elif groups is None:
                groups = []
        else:
            groups = []  # Intentional default when field is completely absent

        # Validate 'email' (optional but should be string if present) - explicit presence check
        email = None  # Default to None when absent
        if "email" in jwt_claims:
            email = jwt_claims["email"]
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

        # Check for AWS error response - explicit presence check for error message
        if "Error" in response:
            error_msg = response["Error"].get("Message") if "Message" in response["Error"] else "Unknown"
            if error_msg is None:
                error_msg = "Unknown"  # Explicit fallback only when None
            errors.append(f"DynamoDB error: {error_msg}")

        # Validate response structure - explicit presence check
        item = response.get("Item") if "Item" in response else None
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

        # Check for AWS error response - explicit presence check for error message
        if "Error" in response:
            error_msg = response["Error"].get("Message") if "Message" in response["Error"] else None
            if error_msg is None:
                error_msg = "Unknown"  # Explicit fallback only when None
            errors.append(f"DynamoDB error: {error_msg}")

        # Check for HTTP status code - explicit presence check
        status_code = None
        if "ResponseMetadata" in response:
            response_metadata = response["ResponseMetadata"]
            if isinstance(response_metadata, dict) and "HTTPStatusCode" in response_metadata:
                status_code = response_metadata["HTTPStatusCode"]
                if status_code is not None and status_code not in (200, 201):
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

        # Check for AWS error response - explicit presence check for error message
        if "Error" in response:
            error_msg = response["Error"].get("Message") if "Message" in response["Error"] else None
            if error_msg is None:
                error_msg = "Unknown"  # Explicit fallback only when None
            errors.append(f"DynamoDB error: {error_msg}")

        # Validate attributes - explicit presence check
        attributes = response.get("Attributes") if "Attributes" in response else None
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

    @staticmethod
    def safe_get_float(
        row: dict[str, Any] | None, key: str, default: float | None = 0.0, strict: bool = False
    ) -> float | None:
        """Safely extract and convert float from database row.

        Args:
            row: Database row dict (from DictCursor)
            key: Column name
            default: Default value if missing or invalid (explicit fallback - log when used)
            strict: If True, raise exception on invalid value

        Returns:
            Float value or default
        """
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            # Explicit fallback - log when row is None
            logger.debug(f"Row is None, using default {default} for {key}")
            return default

        try:
            # Explicit key presence check
            if key not in row:
                logger.debug(f"Key {key} not in row, using default {default}")
                return default

            value = row[key]
            if value is None:
                logger.debug(f"Value for {key} is None, using default {default}")
                return default
            return float(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to float: {e}") from None
            # Explicit fallback on conversion error - log it
            logger.warning(f"Failed to convert {key}={row.get(key)} to float, using default {default}")
            return default

    @staticmethod
    def safe_get_int(row: dict[str, Any] | None, key: str, default: int | None = 0, strict: bool = False) -> int | None:
        """Safely extract and convert int from database row.

        Note: Uses default value when missing/invalid. Log when fallback is used.
        """
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            # Explicit fallback - log when row is None
            logger.debug(f"Row is None, using default {default} for {key}")
            return default

        try:
            # Explicit key presence check
            if key not in row:
                logger.debug(f"Key {key} not in row, using default {default}")
                return default

            value = row[key]
            if value is None:
                logger.debug(f"Value for {key} is None, using default {default}")
                return default
            return int(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to int: {e}") from None
            # Explicit fallback on conversion error - log it
            logger.warning(f"Failed to convert {key}={row.get(key)} to int, using default {default}")
            return default

    @staticmethod
    def safe_get_str(
        row: dict[str, Any] | None, key: str, default: str | None = "", strict: bool = False
    ) -> str | None:
        """Safely extract and convert string from database row.

        Note: Uses default value when missing/invalid. Log when fallback is used.
        """
        if row is None:
            if strict:
                raise ValueError("Database row is None")
            # Explicit fallback - log when row is None
            logger.debug(f"Row is None, using default '{default}' for {key}")
            return default

        try:
            # Explicit key presence check
            if key not in row:
                logger.debug(f"Key {key} not in row, using default '{default}'")
                return default

            value = row[key]
            if value is None:
                logger.debug(f"Value for {key} is None, using default '{default}'")
                return default
            return str(value)
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to str: {e}") from None
            # Explicit fallback on conversion error - log it
            logger.warning(f"Failed to convert {key}={row.get(key)} to str, using default '{default}'")
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
    def safe_get_first_row(rows: list[Any] | None, context: str = "database query") -> Any:
        """Safely get first row from query results. Returns marker dict if rows are empty or None.

        ALWAYS USE THIS instead of rows[0] to prevent IndexError.

        Args:
            rows: List from fetchall()
            context: Operation name for logging

        Returns:
            First row if available, or marker dict with data_unavailable=True
        """
        if rows is None:
            logger.warning(f"{context}: fetchall() returned None")
            return {"data_unavailable": True, "reason": "fetchall_returned_none", "context": context}
        if len(rows) == 0:
            logger.debug(f"{context}: fetchall() returned empty list")
            return {"data_unavailable": True, "reason": "fetchall_returned_empty_list", "context": context}
        return rows[0]


__all__ = [
    "CognitoValidator",
    "DatabaseResultValidator",
    "DynamoDBValidator",
]
