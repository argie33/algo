"""Dashboard rendering system with mode-specific renderers."""

from dashboard.renderers.base import RenderContext, Renderer
from dashboard.renderers.modes import ModeRenderer
from dashboard.renderers.pipeline import (
    check_auth_lost,
    render_dashboard_body,
    render_error_panel,
    render_expanded_view,
    render_header_components,
)

__all__ = [
    "ModeRenderer",
    "RenderContext",
    "Renderer",
    "check_auth_lost",
    "render_dashboard_body",
    "render_error_panel",
    "render_expanded_view",
    "render_header_components",
]
