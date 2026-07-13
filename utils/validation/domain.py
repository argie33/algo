#!/usr/bin/env python3
"""
Domain-Specific Validators - Business Logic Validators Using Validation Framework

Provides validators for Alpaca orders, database schemas, phase results, and other
domain-specific data structures. These wrap business-logic validation into the
unified validation framework.

VALIDATORS:
1. AlpacaOrderValidator - Validates Alpaca order API responses
2. AlpacaOrderStatusValidator - Validates Alpaca order status responses
3. AlpacaAccountValidator - Validates Alpaca account responses
4. AlpacaPositionValidator - Validates Alpaca position responses
5. DatabaseSchemaValidator - Validates table schema and data
6. PhaseResultsValidator - Validates orchestrator phase results
7. TableDataValidator - Validates row data against type constraints
"""

import logging
from datetime import date
from typing import Any

from .framework import (
    PhaseValidator,
    ValidationResult,
    Validator,
    ValidatorRegistry,
)

logger = logging.getLogger(__name__)


class AlpacaOrderValidator(Validator):
    """Validates Alpaca order creation/status responses.

    Checks required fields, types, and value constraints.
    """

    def __init__(self) -> None:
        super().__init__("AlpacaOrderValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: order response expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned: dict[str, Any] = {}

        # Validate order_id
        order_id = data.get("id")
        if not order_id:
            all_errors.append(f"{context}: missing or empty order ID")
        elif not isinstance(order_id, str):
            all_errors.append(f"{context}: order ID must be string, got {type(order_id).__name__}")
        else:
            cleaned["id"] = order_id

        # Validate status
        status = data.get("status")
        valid_statuses = {
            "pending_new",
            "accepted",
            "accepted_for_bidding",
            "filled",
            "partially_filled",
            "pending_cancel",
            "cancelled",
            "rejected",
        }
        if not status:
            all_errors.append(f"{context}: missing status")
        elif status not in valid_statuses:
            all_errors.append(f"{context}: invalid status {status!r} (valid: {valid_statuses})")
        else:
            cleaned["status"] = status

        # Validate filled_avg_price
        filled_avg_price = data.get("filled_avg_price")
        if filled_avg_price is not None:
            try:
                price_float = float(filled_avg_price)
                if price_float < 0:
                    all_errors.append(f"{context}: filled_avg_price must be non-negative, got {price_float}")
                else:
                    cleaned["filled_avg_price"] = price_float
            except (ValueError, TypeError):
                all_errors.append(f"{context}: filled_avg_price not numeric: {filled_avg_price!r}")

        # Validate bracket order legs if present
        order_class = data.get("order_class", "simple")
        legs = data.get("legs")
        if order_class == "bracket":
            if not isinstance(legs, list):
                all_errors.append(f"{context}: legs must be list, got {type(legs).__name__}")
            elif len(legs) < 2:
                all_errors.append(f"{context}: bracket order requires 2+ legs, got {len(legs)}")
            else:
                cleaned["legs"] = legs
        else:
            if legs is not None:
                cleaned["legs"] = legs

        cleaned["order_class"] = order_class
        if data.get("cancel_reason"):
            cleaned["rejection_reason"] = data.get("cancel_reason")
        elif data.get("failed_reason"):
            cleaned["rejection_reason"] = data.get("failed_reason")
        elif data.get("reason"):
            cleaned["rejection_reason"] = data.get("reason")
        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class AlpacaOrderStatusValidator(Validator):
    """Validates Alpaca order status response (GET /v2/orders/{order_id})."""

    def __init__(self) -> None:
        super().__init__("AlpacaOrderStatusValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: order status response expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = {}

        # Validate status (required)
        status = data.get("status")
        if not status:
            all_errors.append(f"{context}: missing status")
        else:
            cleaned["status"] = str(status)

        # Validate filled_qty
        filled_qty = data.get("filled_qty")
        if filled_qty is not None:
            try:
                val = int(filled_qty)
                if val < 0:
                    all_errors.append(f"{context}: filled_qty must be non-negative, got {val}")
                else:
                    cleaned["filled_qty"] = val  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: filled_qty not integer: {filled_qty!r}")

        # Validate filled_avg_price
        filled_avg_price = data.get("filled_avg_price")
        if filled_avg_price is not None:
            try:
                val = float(filled_avg_price)  # type: ignore
                if val < 0:
                    all_errors.append(f"{context}: filled_avg_price must be non-negative, got {val}")
                else:
                    cleaned["filled_avg_price"] = val  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: filled_avg_price not numeric: {filled_avg_price!r}")

        # Validate qty
        qty = data.get("qty")
        if qty is not None:
            try:
                val = int(qty)
                if val < 0:
                    all_errors.append(f"{context}: qty must be non-negative, got {val}")
                else:
                    cleaned["qty"] = val  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: qty not integer: {qty!r}")

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class AlpacaAccountValidator(Validator):
    """Validates Alpaca account response."""

    def __init__(self) -> None:
        super().__init__("AlpacaAccountValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: account response expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = {}

        # Validate account_id
        account_id = data.get("id")
        if not account_id:
            all_errors.append(f"{context}: missing account ID")
        else:
            cleaned["id"] = str(account_id)

        # Validate portfolio_value
        portfolio_value = data.get("portfolio_value")
        if portfolio_value is not None:
            try:
                cleaned["portfolio_value"] = float(portfolio_value)  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: portfolio_value not numeric: {portfolio_value!r}")

        # Validate cash
        cash = data.get("cash")
        if cash is not None:
            try:
                cleaned["cash"] = float(cash)  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: cash not numeric: {cash!r}")

        # Validate status
        account_status = data.get("status")
        if account_status:
            cleaned["status"] = str(account_status)

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class AlpacaPositionValidator(Validator):
    """Validates Alpaca position response (GET /v2/positions/{symbol})."""

    def __init__(self) -> None:
        super().__init__("AlpacaPositionValidator")

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: position response expected dict, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = {}

        # Validate symbol (required)
        symbol = data.get("symbol")
        if not symbol:
            all_errors.append(f"{context}: missing symbol")
        else:
            cleaned["symbol"] = str(symbol)

        # Validate qty
        qty = data.get("qty")
        if qty is not None:
            try:
                cleaned["qty"] = int(qty)  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: qty not integer: {qty!r}")

        # Validate current_price
        current_price = data.get("current_price")
        if current_price is not None:
            try:
                val = float(current_price)
                if val < 0:
                    all_errors.append(f"{context}: price must be non-negative, got {val}")
                else:
                    cleaned["current_price"] = val  # type: ignore
            except (ValueError, TypeError):
                all_errors.append(f"{context}: price not numeric: {current_price!r}")

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class DatabaseSchemaValidator(Validator):
    """Validates database table schema and data presence.

    Checks:
    1. Table exists
    2. Required columns exist with correct types
    3. Table contains data (non-empty)
    """

    def __init__(
        self,
        table_name: str,
        required_columns: dict[str, str],
        severity: str = "critical",
    ):
        """Initialize with table name and required columns.

        Args:
            table_name: Name of table to validate
            required_columns: Dict of {column_name: expected_type}
                Expected types: 'numeric', 'temporal', 'text'
            severity: 'critical' (must exist), 'important' (must have data), 'supporting'
        """
        super().__init__(f"DatabaseSchemaValidator({table_name})")
        self.table_name = table_name
        self.required_columns = required_columns
        self.severity = severity

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        """Validate table schema information.

        Args:
            data: Dict with schema info {table_name, columns: {col_name: col_type}, row_count}

        Returns:
            ValidationResult with schema validity and errors
        """
        all_errors = []
        cleaned = {}

        # Handle deferred validation with cursor
        if not isinstance(data, dict):
            return ValidationResult(
                is_valid=False,
                errors=["DatabaseSchemaValidator expects dict schema info, got cursor (deferred validation)"],
                context=context,
                validator_name=self.name,
            )

        table_name = data.get("table_name", self.table_name)
        columns = data.get("columns")

        # FAIL-FAST: Validate row_count is present (do not default to 0)
        # Missing row_count data indicates incomplete schema validation, not an empty table
        if "row_count" not in data:
            all_errors.append(
                f"{context}: {table_name} missing 'row_count' in schema validation data. "
                f"Cannot validate table presence without row count metadata. "
                f"Check schema info source — data may be incomplete."
            )
            row_count = None
        else:
            row_count = data["row_count"]

        if not columns:
            all_errors.append(f"{context}: {table_name} missing columns info")
        else:
            # Check required columns exist
            missing_cols = [col for col in self.required_columns.keys() if col not in columns]
            if missing_cols:
                all_errors.append(f"{context}: {table_name} missing columns {missing_cols}")

            # Check column types match
            type_mismatches = []
            for col_name, expected_type in self.required_columns.items():
                if col_name in columns:
                    actual_type = columns[col_name].lower()
                    if not self._type_family_matches(actual_type, expected_type):
                        type_mismatches.append(f"{col_name} is {actual_type} (expected {expected_type})")

            if type_mismatches:
                all_errors.append(f"{context}: {table_name} type mismatches: {'; '.join(type_mismatches)}")

        # Check data presence (only if row_count is available)
        if self.severity in ("critical", "important"):
            if row_count is not None and row_count == 0:
                all_errors.append(f"{context}: {table_name} is empty (no data)")

        if len(all_errors) == 0:
            cleaned = {
                "table_name": table_name,
                "columns": columns,
                "row_count": row_count,
            }

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )

    def _type_family_matches(self, actual: str, expected: str) -> bool:
        if expected == "numeric":
            return any(
                t in actual
                for t in [
                    "int",
                    "numeric",
                    "decimal",
                    "float",
                    "real",
                    "double",
                    "bigint",
                    "smallint",
                ]
            )
        elif expected == "temporal":
            return any(t in actual for t in ["date", "timestamp", "time"])
        elif expected == "text":
            return any(t in actual for t in ["char", "text", "varchar"])
        return False


class TableDataValidator(Validator):
    """Validates row data against type constraints (can convert types).

    Used to validate data from database rows or CSV before processing.
    """

    def __init__(self, schema: dict[str, str]):
        """Initialize with column type schema.

        Args:
            schema: Dict of {column_name: type_name}
                Type names: 'float', 'int', 'date', 'text'
        """
        super().__init__("TableDataValidator")
        self.schema = schema

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, dict):
            errors = [f"{context}: expected dict row, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned: dict[str, Any] = {}

        for col_name, col_type in self.schema.items():
            if col_name not in data:
                all_errors.append(f"{context}: missing column {col_name!r}")
                continue

            value = data[col_name]

            # Convert based on type
            if col_type in ("float", "numeric"):
                if value is None:
                    cleaned[col_name] = None
                else:
                    try:
                        cleaned[col_name] = float(value)
                    except (ValueError, TypeError):
                        all_errors.append(f"{context}.{col_name}: cannot convert {value!r} to float")
            elif col_type in ("int", "integer"):
                if value is None:
                    cleaned[col_name] = None
                else:
                    try:
                        cleaned[col_name] = int(value)
                    except (ValueError, TypeError):
                        all_errors.append(f"{context}.{col_name}: cannot convert {value!r} to int")
            elif col_type in ("date", "temporal"):
                if value is None:
                    cleaned[col_name] = None
                else:
                    try:
                        if isinstance(value, (date, str)):
                            cleaned[col_name] = value
                        else:
                            all_errors.append(f"{context}.{col_name}: invalid date type {type(value).__name__}")
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        all_errors.append(f"{context}.{col_name}: date conversion failed: {e}")
            elif col_type in ("text", "string", "varchar"):
                cleaned[col_name] = str(value) if value is not None else None
            else:
                # Unknown type - pass through
                cleaned[col_name] = value

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


class PhaseResultsValidator(Validator):
    """Validates list of phase results with consistent structure.

    Each phase must have 'name'/'phase' and valid 'status'.
    """

    def __init__(self) -> None:
        super().__init__("PhaseResultsValidator")
        self.phase_validator = PhaseValidator()

    def validate(self, data: Any, context: str = "") -> ValidationResult:
        if not isinstance(data, list):
            errors = [f"{context}: expected list, got {type(data).__name__}"]
            return ValidationResult(is_valid=False, errors=errors, context=context)

        all_errors = []
        cleaned = []

        for i, phase_data in enumerate(data):
            phase_context = f"{context}[{i}]"
            result = self.phase_validator.validate(phase_data, context=phase_context)
            if not result.is_valid:
                all_errors.extend(result.errors)
            else:
                cleaned.append(result.data)

        # Log summary
        if len(cleaned) < len(data):
            logger.warning(f"PhaseResultsValidator: {len(cleaned)} valid, {len(data) - len(cleaned)} invalid phases")

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            data=cleaned if len(all_errors) == 0 else None,
            context=context,
            validator_name=self.name,
        )


def create_default_registry() -> ValidatorRegistry:
    """Create a registry with common validators pre-registered.

    Returns ValidatorRegistry with standard validators.
    """
    registry = ValidatorRegistry()

    # Register domain-specific validators
    registry.register(
        "alpaca_order",
        AlpacaOrderValidator(),
        "Alpaca order creation response",
    )
    registry.register(
        "alpaca_order_status",
        AlpacaOrderStatusValidator(),
        "Alpaca order status response",
    )
    registry.register(
        "alpaca_account",
        AlpacaAccountValidator(),
        "Alpaca account information response",
    )
    registry.register(
        "alpaca_position",
        AlpacaPositionValidator(),
        "Alpaca position response for single symbol",
    )
    registry.register(
        "phase_results",
        PhaseResultsValidator(),
        "List of orchestrator phase execution results",
    )

    logger.debug("Initialized default validator registry with domain validators")
    return registry
