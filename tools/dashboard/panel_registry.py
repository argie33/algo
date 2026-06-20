"""Dashboard Panel Registry - enables pluggable, extensible panel system.

This module provides a registration mechanism for dashboard panels that:
1. Decouples panels from hard-coded imports in dashboard.py
2. Enables new panels to be added without modifying dashboard.py or fetchers.py
3. Tracks endpoint dependencies for each panel
4. Validates that all required endpoints are available before rendering
5. Provides panel lifecycle management (validation, rendering, error handling)

Instead of importing each panel function explicitly in dashboard.py:
    from panels import (
        panel_header_market, panel_portfolio, panel_circuit,
        panel_algo_health, panel_portfolio, panel_performance_spark,
        ...
    )

Panels self-register with their dependencies:
    @panel_registry.register_panel("header", endpoint_deps=["mkt", "sentiment"])
    def panel_header_market(mkt, sentiment, ts, mkt_s, elapsed, ...):
        ...

    # Dashboard gets panels dynamically
    panels = panel_registry.get_panels()
    for panel_name in panels:
        panel_def = panel_registry.get_panel(panel_name)
        if panel_def.can_render(data):
            layout = panel_def.render(data)
"""

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from shared_contracts import EndpointRegistry
except ImportError:
    EndpointRegistry = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class PanelDefinition:
    """Definition of a dashboard panel."""

    name: str
    endpoint_deps: list[str]  # Endpoint names this panel depends on
    render_fn: Callable | None = None  # Function to call to render panel
    optional: bool = False  # If True, dashboard renders without this panel
    description: str = ""  # Human-readable description


class PanelRegistry:
    """Central registry for dashboard panels.

    Maintains registrations of all panels and their dependencies,
    validates dependencies exist, and provides panel lookup methods.
    """

    def __init__(self):
        """Initialize the panel registry."""
        self._panels: dict[str, PanelDefinition] = {}
        self._render_functions: dict[str, Callable] = {}

    def register_panel(
        self,
        name: str,
        endpoint_deps: list[str],
        render_fn: Callable | None = None,
        optional: bool = False,
        description: str = "",
    ) -> None:
        """Register a new panel with its dependencies.

        Args:
            name: Unique panel identifier
            endpoint_deps: List of endpoint names required by this panel
            render_fn: Optional rendering function (can be added later)
            optional: If True, dashboard renders even if endpoint missing
            description: Human-readable panel description

        Raises:
            ValueError: If render_fn is not callable, or if required endpoints are missing/undefined
        """
        if name in self._panels:
            logger.warning(f"Panel {name} already registered, replacing")

        # Validate render function is callable
        if render_fn is not None and not callable(render_fn):
            raise ValueError(f"Panel {name}: render_fn is not callable")

        # Validate endpoints exist in contract
        if EndpointRegistry is not None:
            missing = []
            for endpoint in endpoint_deps:
                if not EndpointRegistry.validate_endpoint_exists(endpoint):
                    missing.append(endpoint)
            if missing:
                logger.warning(f"Panel {name} requires undefined endpoints: {missing} (optional={optional})")

        panel_def = PanelDefinition(
            name=name,
            endpoint_deps=endpoint_deps,
            render_fn=render_fn,
            optional=optional,
            description=description,
        )
        self._panels[name] = panel_def
        if render_fn:
            self._render_functions[name] = render_fn
        logger.debug(f"Registered panel: {name} (deps: {endpoint_deps})")

    def register_render_function(self, name: str, render_fn: Callable) -> None:
        """Register or update the rendering function for a panel.

        Args:
            name: Panel name
            render_fn: Rendering function

        Raises:
            ValueError: If render_fn is not callable
        """
        if not callable(render_fn):
            raise ValueError(f"Panel {name}: render_fn is not callable")
        if name not in self._panels:
            logger.warning(f"Registering render function for unregistered panel {name}")
        self._render_functions[name] = render_fn

    def get_panel(self, name: str) -> PanelDefinition | None:
        """Get a panel definition by name."""
        return self._panels.get(name)

    def get_all_panels(self) -> dict[str, PanelDefinition]:
        """Get all registered panels."""
        return self._panels.copy()

    def get_panel_names(self) -> list[str]:
        """Get all registered panel names."""
        return list(self._panels.keys())

    def get_render_function(self, name: str) -> Callable | None:
        """Get the rendering function for a panel."""
        return self._render_functions.get(name)

    def get_panel_dependencies(self, name: str) -> list[str]:
        """Get list of endpoint dependencies for a panel."""
        panel = self._panels.get(name)
        return panel.endpoint_deps if panel else []

    def is_panel_optional(self, name: str) -> bool:
        """Check if a panel is optional (ok to skip if endpoint missing)."""
        panel = self._panels.get(name)
        return panel.optional if panel else True

    def validate_panel_dependencies(self, name: str) -> tuple[bool, list[str]]:
        """Check if all required endpoints for a panel are defined in contract.

        Returns:
            (is_valid, missing_endpoints) tuple
        """
        panel = self._panels.get(name)
        if not panel:
            return False, [name]

        if EndpointRegistry is None:
            return True, []  # Can't validate without contract

        missing = []
        for endpoint in panel.endpoint_deps:
            if not EndpointRegistry.validate_endpoint_exists(endpoint):
                missing.append(endpoint)

        return len(missing) == 0, missing

    def can_render_panel(self, name: str, data: dict[str, Any]) -> tuple[bool, str | None]:
        """Check if a panel can be rendered with the given data.

        Returns:
            (can_render, error_reason) tuple
            - (True, None) if panel has all required data
            - (False, reason) if data is missing or invalid
        """
        panel = self._panels.get(name)
        if not panel:
            return False, f"Panel {name} not registered"

        # Check if all required endpoints have data
        missing_endpoints = []
        for endpoint in panel.endpoint_deps:
            if endpoint not in data:
                missing_endpoints.append(endpoint)
            elif data[endpoint].get("_error"):
                missing_endpoints.append(f"{endpoint} (error)")

        if missing_endpoints:
            if panel.optional:
                return True, None  # Optional panels render anyway
            return False, f"Missing data for: {missing_endpoints}"

        return True, None

    def get_panels_for_view_mode(self, view_mode: str) -> list[str]:
        """Get panels to display for a given view mode.

        view_mode can be: 'normal', 'positions', 'signals', 'health', 'sectors'

        Returns list of panel names to render.
        """
        # Map view modes to panels (can be customized)
        view_panels = {
            "normal": [
                "header",
                "exposure",
                "circuit",
                "health",
                "portfolio",
                "performance",
                "economic",
                "signals",
                "sectors",
                "positions",
            ],
            "positions": ["header", "exposure", "positions"],
            "signals": ["header", "exposure", "signals"],
            "health": ["header", "exposure", "health"],
            "sectors": ["header", "exposure", "sectors"],
        }
        return view_panels.get(view_mode, [])

    def get_critical_panels(self) -> list[str]:
        """Get panels that are not optional (dashboard won't fully render without them)."""
        return [name for name, panel in self._panels.items() if not panel.optional]

    def get_optional_panels(self) -> list[str]:
        """Get optional panels (dashboard can render without them)."""
        return [name for name, panel in self._panels.items() if panel.optional]


# Global singleton instance
_registry = PanelRegistry()


def get_panel_registry() -> PanelRegistry:
    """Get the global panel registry instance."""
    return _registry


def register_panel(
    name: str,
    endpoint_deps: list[str],
    render_fn: Callable | None = None,
    optional: bool = False,
    description: str = "",
) -> Callable:
    """Decorator to register a panel function.

    Usage:
        @register_panel("header", endpoint_deps=["mkt", "sentiment"])
        def panel_header_market(data, ...):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        _registry.register_panel(
            name=name,
            endpoint_deps=endpoint_deps,
            render_fn=fn,
            optional=optional,
            description=description,
        )
        return fn

    if render_fn is None:
        return decorator
    else:
        # Called as @register_panel(...) with render_fn
        _registry.register_panel(name, endpoint_deps, render_fn, optional, description)
        return render_fn
