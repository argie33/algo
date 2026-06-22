#!/usr/bin/env python3
"""Lazy Class Consolidation - Eliminate overly simple utility classes."""


class ConfigMetadata:
    """Consolidated metadata store for configuration and constants."""

    # Consolidated from error_types.py
    ERROR_TYPES = {
        "CONFIG_MISSING": "Required configuration not found",
        "VALIDATION_FAILED": "Validation check failed",
        "DATA_UNAVAILABLE": "Required data not available",
    }

    # Consolidated from colors.py
    COLORS = {
        "GREEN": "\033[92m",
        "RED": "\033[91m",
        "YELLOW": "\033[93m",
        "RESET": "\033[0m",
    }

    @staticmethod
    def get_error(error_type: str) -> str:
        """Get error message."""
        return ConfigMetadata.ERROR_TYPES.get(error_type, "Unknown error")

    @staticmethod
    def colorize(text: str, color: str) -> str:
        """Add color to text."""
        color_code = ConfigMetadata.COLORS.get(color, "")
        return f"{color_code}{text}{ConfigMetadata.COLORS.get('RESET', '')}"
