"""Stock composite/factor scores panel for dashboard (compact + expanded)."""

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dashboard.panel_registry import register_panel as register_panel
else:
    try:
        from dashboard.panel_registry import register_panel
    except ImportError:
        from collections.abc import Callable
        from typing import TypeVar

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


from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from ._helpers import _composite_score_color, _error_panel, _score_cell
from .data_extractors import safe_get_dict, safe_get_field, safe_get_list


def _build_scores_table(top_scores: list[Any], limit: int = 15) -> list[Text | Table]:
    """Build stock quality scores table.

    Validates input is list before accessing items.
    Logs all validation failures.
    """
    rows: list[Text | Table] = []
    if not isinstance(top_scores, list):
        logger.error(f"_build_scores_table: top_scores is not list, got {type(top_scores).__name__}")
        rows.append(Text.from_markup("[yellow]Invalid score data structure - check Data Health[/]"))
        return rows
    if not top_scores:
        logger.debug("_build_scores_table: top_scores is empty (no score data available)")
        rows.append(Text.from_markup("[yellow]No score data - check Data Health[/]"))
        return rows

    t: Table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=True,
        row_styles=["", "dim"],
    )
    t.add_column("Symbol", style="bold white", no_wrap=True, min_width=6)
    t.add_column("Composite", justify="right", no_wrap=True, min_width=7)
    t.add_column("Momentum", justify="right", no_wrap=True, min_width=8)
    t.add_column("Quality", justify="right", no_wrap=True, min_width=7)
    t.add_column("Value", justify="right", no_wrap=True, min_width=5)
    t.add_column("Growth", justify="right", no_wrap=True, min_width=7)
    t.add_column("Stability", justify="right", no_wrap=True, min_width=8)
    t.add_column("Positioning", justify="right", no_wrap=True, min_width=8)
    t.add_column("RS%", justify="right", no_wrap=True, min_width=5)
    t.add_column("Change%", justify="right", no_wrap=True, min_width=7)
    t.add_column("Sector", no_wrap=True, max_width=12)

    for sc in top_scores[:limit]:
        sym = safe_get_field(sc, "symbol", "--")
        comp = safe_get_field(sc, "composite_score")
        mom = safe_get_field(sc, "momentum_score")
        qual = safe_get_field(sc, "quality_score")
        val = safe_get_field(sc, "value_score")
        grwth = safe_get_field(sc, "growth_score")
        stab = safe_get_field(sc, "stability_score")
        pos = safe_get_field(sc, "positioning_score")
        rs_pct = safe_get_field(sc, "rs_percentile")
        chg = safe_get_field(sc, "change_percent")
        sector = (safe_get_field(sc, "sector", ""))[:12]
        comp_v: float | None = safe_float(comp)
        sc_c: str = _composite_score_color(comp_v) if comp_v is not None else "dim"
        chg_v: float | None = safe_float(chg)
        chg_c: str = "green" if chg_v is not None and chg_v > 0 else ("red" if chg_v is not None and chg_v < 0 else "dim")
        rs_v: float | None = safe_float(rs_pct)

        t.add_row(
            sym,
            Text(f"{comp_v:.0f}" if comp_v is not None else "--", style=sc_c),
            _score_cell(mom),
            _score_cell(qual),
            _score_cell(val),
            _score_cell(grwth),
            _score_cell(stab),
            _score_cell(pos),
            Text(
                f"{rs_v:.0f}" if rs_v is not None else "--",
                style="green" if rs_v is not None and rs_v >= 70 else "dim",
            ),
            Text(f"{chg_v:+.1f}%" if chg_v is not None else "--", style=chg_c),
            Text(sector, style="dim"),
        )
    rows.append(t)
    return rows


@register_panel(
    "scores",
    endpoint_deps=["scores"],
    optional=True,
    description="Top composite/factor stock scores",
)
def panel_scores_compact(scores: Any) -> Panel:
    """Compact scores panel - composite + 6-factor breakdown for top-ranked stocks."""
    err_panel = _error_panel("scores", scores, "SCORES", border="cyan")
    if err_panel:
        return err_panel

    top_scores_raw = safe_get_list(safe_get_dict(scores).get("top", []))
    top_scores: list[Any] = top_scores_raw if isinstance(top_scores_raw, list) else []
    if not top_scores:
        no_data_panel = _error_panel("scores", {"_error": "No top scores available"}, "SCORES", border="cyan")
        if no_data_panel is not None:
            return no_data_panel
        return Panel(Text("No score data", style="dim"), title="[bold cyan]SCORES[/]", border_style="cyan")

    rows: list[Text | Table] = [
        Text.from_markup(f"[cyan][bold]TOP STOCK SCORES[/][/] [dim]({len(top_scores)} ranked candidates)[/]"),
    ]
    rows.extend(_build_scores_table(top_scores, limit=15))

    return Panel(
        Group(*rows),
        title="[bold cyan]SCORES[/]  [dim][c] expand[/]",
        border_style="cyan",
        padding=(0, 1),
    )


def panel_scores_expanded(scores: Any) -> Panel:
    """Full-screen scores view - composite + 6-factor breakdown for a larger candidate set."""
    err_panel = _error_panel("scores", scores, "SCORES", border="cyan")
    if err_panel:
        return err_panel

    top_scores_raw = safe_get_list(safe_get_dict(scores).get("top", []))
    top_scores: list[Any] = top_scores_raw if isinstance(top_scores_raw, list) else []

    rows: list[Text | Table] = [
        Text.from_markup("[cyan][bold]SCORES - EXPANDED[/][/]"),
        Text.from_markup(
            f"[dim]{len(top_scores)} ranked candidates by composite score[/]  "
            "[dim]press [/][bold cyan]c[/][dim] to return[/]"
        ),
    ]
    if top_scores:
        rows.extend(_build_scores_table(top_scores, limit=50))
    else:
        rows.append(Text.from_markup("[yellow]No score data - check Data Health[/]"))

    return Panel(
        Group(*rows),
        title="[bold cyan]SCORES - EXPANDED[/]",
        border_style="cyan",
        padding=(0, 1),
    )


__all__ = [
    "panel_scores_compact",
    "panel_scores_expanded",
]
