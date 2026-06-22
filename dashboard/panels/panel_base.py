#!/usr/bin/env python3
"""PanelBase - abstract base class for all dashboard panels.

This module provides a common interface and boilerplate for dashboard panels,
eliminating code duplication across market, portfolio, health, signals, sectors,
economic, circuit, and exposure panels.

Pattern:
    Before: Each panel function re-implemented error handling, data extraction,
            and formatting logic separately
    After:  Panel classes inherit from PanelBase and implement only panel-specific logic
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from rich.panel import Panel
from rich.text import Text

from ._helpers import _error_panel

logger = logging.getLogger(__name__)


class PanelBase(ABC):
    """Abstract base class for dashboard panels.

    All panels follow the same pattern:
    1. Validate input data (check for errors)
    2. Extract relevant fields
    3. Format the output
    4. Return Rich Panel object

    Subclasses implement only the panel-specific logic.
    """

    def __init__(self, name: str, title: str, border_style: str = "blue") -> None:
        """Initialize panel base.

        Args:
            name: Panel identifier (used for error handling)
            title: Panel display title
            border_style: Border style for Rich Panel (blue, red, green, etc)

        """
        self.name = name
        self.title = title
        self.border_style = border_style
        self.logger = logging.getLogger(f"{__name__}.{name}")

    def render(self, **kwargs) -> Panel:
        """Render the panel with error handling.

        Args:
            **kwargs: Data dict(s) to render

        Returns:
            Rich Panel object (possibly error panel if validation failed)

        """
        # Step 1: Validate inputs
        validation_error = self.validate_inputs(**kwargs)  # pylint: disable=assignment-from-no-return
        if validation_error:
            return self._error_panel(validation_error)

        try:
            # Step 2: Extract and format data
            content = self.format_content(**kwargs)
            return content

        except Exception as e:
            self.logger.error(f"Panel rendering failed: {e}")
            return self._error_panel(f"Rendering error: {e!s}")

    def validate_inputs(self, **kwargs) -> str | None:
        """Validate input data before rendering.

        Should return None if valid, or error message string if invalid.
        Override in subclasses to add custom validation.

        Args:
            **kwargs: Input data dicts

        Returns:
            None if valid, error message if invalid

        """
        return None

    @abstractmethod
    def format_content(self, **kwargs) -> Panel:
        """Format the panel content.

        Subclasses must implement this to provide panel-specific formatting.

        Args:
            **kwargs: Input data dicts

        Returns:
            Formatted Rich Panel object

        """
        ...

    def _error_panel(self, message: str) -> Panel:
        """Create an error panel (common error handling).

        Args:
            message: Error message to display

        Returns:
            Red error Panel

        """
        return Panel(
            Text.from_markup(f"[dim]{message}[/]"),
            title=f"[bold {self.border_style}]{self.title} (ERROR)[/]",
            border_style="red",
            padding=(0, 1),
        )

    def check_error(self, key: str, data: Any, panel_name: str | None = None) -> Panel | None:
        """Check if data has error (common pattern across panels).

        Args:
            key: Data key to check
            data: Data dict to check
            panel_name: Panel name for error reporting (defaults to self.name)

        Returns:
            Error panel if error detected, None otherwise

        """
        if panel_name is None:
            panel_name = self.name
        return _error_panel(key, data, panel_name)


class CompactPanelBase(PanelBase):
    """Base class for compact panel views.

    Compact panels show minimal information, suitable for dashboard summaries.
    """

    def __init__(self, name: str, title: str, border_style: str = "blue") -> None:
        """Initialize compact panel."""
        super().__init__(name, title, border_style)
        self.compact = True


class ExpandedPanelBase(PanelBase):
    """Base class for expanded panel views.

    Expanded panels show detailed information, suitable for focused analysis.
    """

    def __init__(self, name: str, title: str, border_style: str = "blue") -> None:
        """Initialize expanded panel."""
        super().__init__(name, title, border_style)
        self.compact = False


class MultiViewPanelBase(ABC):
    """Base class for panels with multiple views (compact + expanded).

    Some panels provide both compact and expanded representations.
    This base manages both views with shared data extraction.
    """

    def __init__(self, name: str, base_title: str, border_style: str = "blue") -> None:
        """Initialize multi-view panel.

        Args:
            name: Panel identifier
            base_title: Base title for panel
            border_style: Border style for Rich Panels

        """
        self.name = name
        self.base_title = base_title
        self.border_style = border_style
        self.logger = logging.getLogger(f"{__name__}.{name}")

    def render_compact(self, **kwargs) -> Panel:
        """Render compact view of panel."""
        return self._render_with_error_handling(**kwargs, expanded=False)

    def render_expanded(self, **kwargs) -> Panel:
        """Render expanded view of panel."""
        return self._render_with_error_handling(**kwargs, expanded=True)

    def _render_with_error_handling(self, expanded: bool = False, **kwargs) -> Panel:
        """Render with error handling."""
        validation_error = self.validate_inputs(**kwargs)  # pylint: disable=assignment-from-no-return
        if validation_error:
            return self._error_panel(validation_error)

        try:
            content = self.format_expanded_content(**kwargs) if expanded else self.format_compact_content(**kwargs)
            return content
        except Exception as e:
            self.logger.error(f"Panel rendering failed: {e}")
            return self._error_panel(f"Rendering error: {e!s}")

    def validate_inputs(self, **kwargs) -> str | None:
        """Validate inputs. Override in subclasses."""
        return None

    @abstractmethod
    def format_compact_content(self, **kwargs) -> Panel:
        """Format compact panel content."""
        ...

    @abstractmethod
    def format_expanded_content(self, **kwargs) -> Panel:
        """Format expanded panel content."""
        ...

    def _error_panel(self, message: str) -> Panel:
        """Create error panel."""
        return Panel(
            Text.from_markup(f"[dim]{message}[/]"),
            title=f"[bold {self.border_style}]{self.base_title} (ERROR)[/]",
            border_style="red",
            padding=(0, 1),
        )
