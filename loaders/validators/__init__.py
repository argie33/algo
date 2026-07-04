"""Unified validation framework for all loaders.

Consolidates validation logic that was previously scattered across 24+ loader methods.

Patterns:
- DataValidator: Base class for all validators
- CompletenessValidator: Check required data is present
- NumericValidator: Check numeric fields are valid (not NaN, Infinity, out of range)
- SchemaValidator: Check row schema matches expected columns

Usage:
    from loaders.validators import CompletenessValidator

    validator = CompletenessValidator(required_fields=['symbol', 'price', 'volume'])
    validator.check(row)  # Raises ValueError if missing required fields
"""

from .base import DataValidator
from .completeness import CompletenessValidator
from .numeric import NumericValidator
from .schema import SchemaValidator

__all__ = [
    "CompletenessValidator",
    "DataValidator",
    "NumericValidator",
    "SchemaValidator",
]
