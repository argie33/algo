#!/usr/bin/env python3
"""Unified dict access patterns - Standardize 556+ .get() calls.

Provides consistent, typed, and safe access to nested dicts across the platform.
Replaces inconsistent patterns:
- dict.get("key") → dict.get("key", {}).get("subkey")
- dict["key"] → KeyError (unhandled)
- dict.get("key", None) → None (ambiguous: missing vs None value)

STANDARD PATTERN:
    from utils.validation.dict_access import SafeDict

    # Type-safe access with defaults
    value = SafeDict(data).get("key1", "key2", "key3", default="N/A")

    # Explicitly typed access
    count = SafeDict(params).int_value("count", default=0, field_name="query param count")
    threshold = SafeDict(config).float_value("thresholds", "risk", default=0.5)

    # Validation built-in
    symbol = SafeDict(params).required_string("symbol")  # Raises if missing/empty
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SafeDict:
    """Unified dict access with automatic logging, type coercion, and validation.

    Replaces fragmented patterns across 556+ call sites:
    - params.get("key", {}).get("subkey")  # Fragile
    - dict["key"]  # Crashes on missing
    - dict.get("key", None)  # Ambiguous: missing vs explicit None

    Usage:
        # Simple access with default
        value = SafeDict(data).get("key", default="N/A")

        # Nested access
        symbol = SafeDict(params).get("symbol", default="unknown")

        # Typed access
        limit = SafeDict(params).int_value("limit", default=100, field_name="query param limit")
        threshold = SafeDict(config).float_value("thresholds", "risk", default=0.5)

        # Required access (raises if missing/empty)
        symbol = SafeDict(request).required_string("symbol")  # ValueError if missing
    """

    def __init__(self, data: Any, context: str = "", strict: bool = False) -> None:
        """Initialize with data dict.

        Args:
            data: The dict to access (or None, treated as empty dict)
            context: Context for logging (e.g., "query params", "request body")
            strict: If True, raise on missing keys instead of returning default
        """
        self._data = data if isinstance(data, dict) else {}
        self._context = context
        self._strict = strict

    # ──────────────────────────────────────────────────────────────────────────
    # GENERIC GET
    # ──────────────────────────────────────────────────────────────────────────

    def get(self, *keys: str, default: Any = None, field_name: str | None = None) -> Any:
        """Get nested value with fallback default.

        Supports arbitrary nesting depth via positional args.
        Logs warnings on missing keys (if context provided).

        Args:
            *keys: Path to value (e.g., "key", "subkey", "subsubkey")
            default: Value if key not found or value is None
            field_name: Field name for logging (preferred over extracting from keys)

        Returns:
            Value at path, or default if not found or value is None

        Examples:
            SafeDict(params).get("user", "profile", "name", default="Unknown")
            SafeDict(data).get("thresholds", "risk", default=0.5)
        """
        if not keys:
            return default

        current = self._data
        path = " → ".join(keys)

        for i, key in enumerate(keys):
            if not isinstance(current, dict):
                if self._strict:
                    raise KeyError(f"Cannot navigate path {path}: non-dict at {' → '.join(keys[:i])}")
                logger.debug(f"[DICT_ACCESS] Path {path} invalid (non-dict at level {i}) {self._context_str()}")
                return default

            if key not in current:
                if self._strict:
                    raise KeyError(f"Missing key '{key}' in path {path} {self._context_str()}")
                logger.debug(f"[DICT_ACCESS] Missing key '{key}' in path {path} {self._context_str()}")
                return default

            current = current[key]

        if current is None:
            logger.debug(f"[DICT_ACCESS] Path {path} is None, using default {self._context_str()}")
            return default

        return current

    # ──────────────────────────────────────────────────────────────────────────
    # TYPED ACCESS
    # ──────────────────────────────────────────────────────────────────────────

    def int_value(self, *keys: str, default: int | None = None, field_name: str | None = None) -> int | None:
        """Get value as int with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing or conversion fails
            field_name: Field name for logging

        Returns:
            Int value or default

        Example:
            limit = SafeDict(params).int_value("limit", default=100)
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default

        try:
            return int(value)
        except (ValueError, TypeError):
            path = " → ".join(keys)
            logger.warning(
                f"[DICT_ACCESS] Cannot convert {path}={value!r} to int (returning {default}) {self._context_str()}"
            )
            return default

    def float_value(self, *keys: str, default: float | None = None, field_name: str | None = None) -> float | None:
        """Get value as float with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing or conversion fails
            field_name: Field name for logging

        Returns:
            Float value or default

        Example:
            threshold = SafeDict(config).float_value("thresholds", "risk", default=0.5)
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default

        try:
            return float(value)
        except (ValueError, TypeError):
            path = " → ".join(keys)
            logger.warning(
                f"[DICT_ACCESS] Cannot convert {path}={value!r} to float (returning {default}) {self._context_str()}"
            )
            return default

    def str_value(self, *keys: str, default: str | None = None, field_name: str | None = None) -> str | None:
        """Get value as string with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing
            field_name: Field name for logging

        Returns:
            String value or default

        Example:
            symbol = SafeDict(params).string("symbol", default="SPY")
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default
        return str(value)

    def bool_value(self, *keys: str, default: bool | None = None, field_name: str | None = None) -> bool | None:
        """Get value as bool with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing
            field_name: Field name for logging

        Returns:
            Bool value or default

        Example:
            enabled = SafeDict(config).bool("features", "trading", default=False)
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    def dict_value(
        self, *keys: str, default: dict[str, Any] | None = None, field_name: str | None = None
    ) -> dict[str, Any] | None:
        """Get value as dict with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing or not a dict
            field_name: Field name for logging

        Returns:
            Dict value or default

        Example:
            config = SafeDict(params).dict("config", default={})
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default if default is not None else {}
        if isinstance(value, dict):
            return value
        logger.warning(
            f"[DICT_ACCESS] Expected dict at {' → '.join(keys)}, got {type(value).__name__} {self._context_str()}"
        )
        return default if default is not None else {}

    def list_value(
        self, *keys: str, default: list[Any] | None = None, field_name: str | None = None
    ) -> list[Any] | None:
        """Get value as list with fallback default.

        Args:
            *keys: Path to value
            default: Default if missing or not a list
            field_name: Field name for logging

        Returns:
            List value or default

        Example:
            items = SafeDict(response).list("data", "items", default=[])
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            return default if default is not None else []
        if isinstance(value, list):
            return value
        logger.warning(
            f"[DICT_ACCESS] Expected list at {' → '.join(keys)}, got {type(value).__name__} {self._context_str()}"
        )
        return default if default is not None else []

    # ──────────────────────────────────────────────────────────────────────────
    # REQUIRED ACCESS (raises if missing)
    # ──────────────────────────────────────────────────────────────────────────

    def required_string(self, *keys: str, field_name: str | None = None) -> str:
        """Get required string value (raises ValueError if missing/empty).

        Args:
            *keys: Path to value
            field_name: Field name for error message

        Returns:
            String value

        Raises:
            ValueError: If key missing, value is None, or value is empty string

        Example:
            symbol = SafeDict(request).required_string("symbol")  # Raises if missing
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            path = " → ".join(keys)
            raise ValueError(f"Required field missing or empty: {field_name or path} {self._context_str()}")
        return str(value)

    def required_int(self, *keys: str, field_name: str | None = None) -> int:
        """Get required int value (raises ValueError if missing or invalid).

        Args:
            *keys: Path to value
            field_name: Field name for error message

        Returns:
            Int value

        Raises:
            ValueError: If key missing or conversion fails

        Example:
            limit = SafeDict(request).required_int("limit")  # Raises if missing
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            path = " → ".join(keys)
            raise ValueError(f"Required field missing: {field_name or path} {self._context_str()}")
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            path = " → ".join(keys)
            raise ValueError(f"Cannot convert {field_name or path}={value!r} to int {self._context_str()}") from e

    def required_float(self, *keys: str, field_name: str | None = None) -> float:
        """Get required float value (raises ValueError if missing or invalid).

        Args:
            *keys: Path to value
            field_name: Field name for error message

        Returns:
            Float value

        Raises:
            ValueError: If key missing or conversion fails

        Example:
            threshold = SafeDict(request).required_float("threshold")  # Raises if missing
        """
        value = self.get(*keys, default=None, field_name=field_name)
        if value is None:
            path = " → ".join(keys)
            raise ValueError(f"Required field missing: {field_name or path} {self._context_str()}")
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            path = " → ".join(keys)
            raise ValueError(f"Cannot convert {field_name or path}={value!r} to float {self._context_str()}") from e

    # ──────────────────────────────────────────────────────────────────────────
    # UTILITY
    # ──────────────────────────────────────────────────────────────────────────

    def _context_str(self) -> str:
        return f"[{self._context}]" if self._context else ""

    def keys(self) -> list[str]:
        return list(self._data.keys()) if isinstance(self._data, dict) else []

    def has(self, *keys: str) -> bool:
        """Check if path exists and is not None.

        Args:
            *keys: Path to value

        Returns:
            True if path exists and value is not None
        """
        current = self._data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        return current is not None

    def raw(self) -> dict[str, Any]:
        return self._data if isinstance(self._data, dict) else {}
