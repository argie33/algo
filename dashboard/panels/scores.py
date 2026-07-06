"""Growth Scores panel for dashboard."""

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dashboard.panel_registry import register_panel as register_panel
else:
    try:
        from dashboard.panel_registry import register_panel
    except ImportError:
        from typing import Callable, TypeVar

        _F = TypeVar("_F", bound=Callable[..., Any])

        def register_panel(  # type: ignore[misc]
            name: str,
            endpoint_deps: list[str],
            render_fn: _F | None = None,
            optional: bool = False,
            description: str = "",
        ) -> Callable[[_F], _F] | _F:
            if render_fn is not None:
                return render_fn

            def passthrough_decorator(fn: _F) -> _F:
                return fn

            return passthrough_decorator


from rich.panel import Panel
from rich.table import Table

from dashboard.data_validation import safe_float
from dashboard.utilities import DIM, G, R, Y

from ._helpers import _composite_score_color, _error_panel, _score_cell
from .data_extractors import safe_get_dict, safe_get_field, safe_get_list


@register_panel(
    name="top_growth_scores",
    endpoint_deps=["scores"],
    description="Top stocks by composite growth score",
)
def render_scores(data: dict[str, Any]) -> Panel | None:
    """Render top growth scores panel."""
    try:
        scores_data = safe_get_dict(data.get("scores"))
        if not scores_data:
            return _error_panel("scores", scores_data, "TOP GROWTH SCORES", border="cyan")

        top_scores_raw = safe_get_list(scores_data.get("items", []))
        top_scores: list[Any] = top_scores_raw if isinstance(top_scores_raw, list) else []
        if not top_scores:
            return _error_panel("scores", {"_error": "No top scores available"}, "TOP GROWTH SCORES", border="cyan")

        table = Table(
            title="Top Growth Scores",
            box=None,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
        )

        table.add_column("Symbol", width=8, style="bold white")
        table.add_column("Company", width=20, style="dim white")
        table.add_column("Composite", width=10, justify="right")
        table.add_column("Growth", width=10, justify="right")
        table.add_column("Quality", width=10, justify="right")
        table.add_column("Momentum", width=10, justify="right")
        table.add_column("Complete", width=10, justify="right")

        for score_row in top_scores[:20]:  # Show top 20
            score_dict = safe_get_dict(score_row)
            if not score_dict:
                continue

            symbol = safe_get_field(score_dict, "symbol", "--")
            company = safe_get_field(score_dict, "company_name", "--")
            if isinstance(company, str):
                company = company[:20]
            else:
                company = "--"
            composite = safe_float(safe_get_field(score_dict, "composite_score"))
            growth = safe_float(safe_get_field(score_dict, "growth_score"))
            quality = safe_float(safe_get_field(score_dict, "quality_score"))
            momentum = safe_float(safe_get_field(score_dict, "momentum_score"))
            completeness = safe_float(safe_get_field(score_dict, "data_completeness"))

            comp_color = _composite_score_color(composite)

            # Format completeness percentage manually instead of using decimal_places param
            completeness_str = f"{completeness:.0f}" if completeness is not None else "--"

            table.add_row(
                str(symbol),
                str(company),
                f"[{comp_color}]{_score_cell(composite)}[/]",
                f"[{_composite_score_color(growth)}]{_score_cell(growth)}[/]",
                f"[{_composite_score_color(quality)}]{_score_cell(quality)}[/]",
                f"[{_composite_score_color(momentum)}]{_score_cell(momentum)}[/]",
                f"[dim]{completeness_str}%[/]",
            )

        return Panel(
            table,
            title="[bold cyan]Growth Scores[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    except (TypeError, ValueError, KeyError) as e:
        logger.error(f"Error rendering scores panel: {e}")
        return _error_panel("scores", {"_error": str(e)}, "GROWTH SCORES ERROR", border="cyan")
