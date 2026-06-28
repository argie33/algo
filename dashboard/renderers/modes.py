"""Mode-specific rendering orchestration."""


from rich.layout import Layout

from dashboard.core import DashboardContext, ViewMode
from dashboard.renderers.base import RenderContext, Renderer


class ModeRenderer(Renderer):
    """Orchestrates rendering for different view modes."""

    def __init__(self, view_mode: str = "normal") -> None:
        self.view_mode = view_mode

    def render(self, ctx: DashboardContext, render_ctx: RenderContext) -> Layout:
        """Render layout for current view mode."""
        from dashboard.dashboard import render_dashboard

        if not ViewMode.is_valid(self.view_mode):
            self.view_mode = "normal"

        return render_dashboard(
            ctx.data,
            compact=render_ctx.compact,
            elapsed=render_ctx.elapsed,
            frame=render_ctx.frame,
            watch_interval=render_ctx.watch_interval,
            last_load_time=render_ctx.last_load_time,
            refreshing=render_ctx.refreshing,
            view_mode=self.view_mode,
            data_source=render_ctx.data_source,
        )

    def set_mode(self, mode: str) -> None:
        """Set the view mode."""
        if ViewMode.is_valid(mode):
            self.view_mode = mode

    def toggle_mode(self, target: str) -> str:
        """Toggle to target mode, returning new mode."""
        if self.view_mode == target:
            self.view_mode = "normal"
        else:
            self.set_mode(target)
        return self.view_mode
