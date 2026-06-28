"""Base rendering classes for dashboard modes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from rich.layout import Layout

from dashboard.core import DashboardContext


@dataclass
class RenderContext:
    """Rendering context passed to renderers."""

    compact: bool = False
    elapsed: float = 0.0
    frame: int = 0
    watch_interval: int | None = None
    last_load_time: float | None = None
    refreshing: bool = False
    data_source: str = "AWS"


class Renderer(ABC):
    """Base class for dashboard renderers."""

    @abstractmethod
    def render(self, ctx: DashboardContext, render_ctx: RenderContext) -> Layout:
        """Render dashboard layout."""
        pass


class NormalRenderer(Renderer):
    """Renders the normal (non-expanded) dashboard view."""

    def render(self, ctx: DashboardContext, render_ctx: RenderContext) -> Layout:
        """Render normal dashboard layout."""
        from dashboard.dashboard import render_dashboard

        return render_dashboard(
            ctx.data,
            compact=render_ctx.compact,
            elapsed=render_ctx.elapsed,
            frame=render_ctx.frame,
            watch_interval=render_ctx.watch_interval,
            last_load_time=render_ctx.last_load_time,
            refreshing=render_ctx.refreshing,
            view_mode="normal",
            data_source=render_ctx.data_source,
        )
