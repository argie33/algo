#!/usr/bin/env python3
"""
Configuration Protocol - Type definition for dependency injection.

This module defines the interface that all classes expect from a configuration object.
It supports both AlgoConfig instances and plain dicts for maximum flexibility during
the transition to dependency injection.
"""

from typing import Protocol, Any, Union, runtime_checkable


@runtime_checkable
class ConfigProtocol(Protocol):
    """Allows both AlgoConfig and plain dicts for maximum flexibility during DI transition."""

    def get(self, key: str, default: Any = None) -> Any:
        ...

    def override(self, key: str, value: Any) -> None:
        """Apply in-memory-only override (for testing and CLI args)."""
        ...

    def to_dict(self) -> dict:
        ...


ConfigType = Union[ConfigProtocol, dict]
"""Type alias for configuration objects accepted in dependency injection."""
