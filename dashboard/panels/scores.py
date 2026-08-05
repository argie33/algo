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
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from ..formatters import fmt_age
from ..utilities import CY, G, R, Y
from ._helpers import _composite_score_color, _error_panel, _score_cell
from .data_extractors import safe_get_dict, safe_get_field, safe_get_list


def _build_scores_summary(scores: dict[str, Any], shown: int) -> Text | None:
    """Build the summary line above the scores table: universe size, avg composite, A-D grades.

    Mirrors the SIGNALS panel's header line (count + grade breakdown) so both panels give the
    same at-a-glance context before their detail table. Returns None if the API didn't provide
    summary metrics (e.g. an older API version) - the panel still renders the table either way.
    """
    universe_total = safe_get_field(scores, "universe_total")
    avg_composite = safe_get_field(scores, "avg_composite")
    grades_field = safe_get_field(scores, "grades")
    grades = safe_get_dict(grades_field) if grades_field else {}

    if universe_total is None and avg_composite is None and not grades:
        return None

    parts = []
    if universe_total is not None:
        parts.append(f"[bold cyan]{universe_total}[/] candidates ranked [dim](showing top {shown})[/]")
    avg_v = safe_float(avg_composite)
    if avg_v is not None:
        parts.append(f"[dim]avg composite:[/][white]{avg_v:.1f}[/]")

    if grades:
        ga = safe_get_field(grades, "a")
        gb = safe_get_field(grades, "b")
        gc = safe_get_field(grades, "c")
        gd = safe_get_field(grades, "d")
        ga_s = f"{ga}" if ga is not None else "--"
        gb_s = f"{gb}" if gb is not None else "--"
        gc_s = f"{gc}" if gc is not None else "--"
        gd_s = f"{gd}" if gd is not None else "--"
        parts.append(f"[{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]")

    return Text.from_markup("  ".join(parts))


def _build_scores_table(top_scores: list[Any], limit: int = 15, show_company: bool = False) -> list[Text | Table]:
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
        # expand=True stretches every fixed-width column proportionally to fill the
        # console (Rich distributes leftover space across ALL columns, not just wide
        # ones), which reads as huge gaps once the Company column pushes the natural
        # table width close to the full terminal width - so let it size to content here.
        expand=not show_company,
        row_styles=["", "dim"],
    )
    if show_company:
        t.add_column("#", style="dim", justify="right", no_wrap=True, width=3)
    t.add_column("Symbol", style="bold white", no_wrap=True, width=6)
    t.add_column("Company", style="white", no_wrap=True, width=40)
    t.add_column("Comp", justify="right", no_wrap=True, width=5)
    t.add_column("Mom", justify="right", no_wrap=True, width=4)
    t.add_column("Qual", justify="right", no_wrap=True, width=5)
    t.add_column("Val", justify="right", no_wrap=True, width=4)
    t.add_column("Grow", justify="right", no_wrap=True, width=5)
    t.add_column("Stab", justify="right", no_wrap=True, width=5)
    t.add_column("Pos", justify="right", no_wrap=True, width=4)
    t.add_column("Sector", style="dim", no_wrap=True, width=16)

    for rank, sc in enumerate(top_scores[:limit], 1):
        sym = safe_get_field(sc, "symbol", "--")
        company = (safe_get_field(sc, "company_name") or "--")[:40]
        comp = safe_get_field(sc, "composite_score")
        mom = safe_get_field(sc, "momentum_score")
        qual = safe_get_field(sc, "quality_score")
        val = safe_get_field(sc, "value_score")
        grwth = safe_get_field(sc, "growth_score")
        stab = safe_get_field(sc, "stability_score")
        pos = safe_get_field(sc, "positioning_score")
        sector = safe_get_field(sc, "sector", "--")
        comp_v: float | None = safe_float(comp)
        sc_c: str = _composite_score_color(comp_v) if comp_v is not None else "dim"

        row_cells: list[str | Text] = []
        if show_company:
            row_cells.append(Text(str(rank), style="dim"))
        row_cells.extend([
            sym,
            Text(company, style="dim"),
        ])
        row_cells.extend(
            [
                Text(f"{comp_v:.0f}" if comp_v is not None else "--", style=sc_c),
                _score_cell(mom),
                _score_cell(qual),
                _score_cell(val),
                _score_cell(grwth),
                _score_cell(stab),
                _score_cell(pos),
                Text(str(sector), style="dim"),
            ]
        )
        t.add_row(*row_cells)
    rows.append(t)
    return rows


def _build_factor_top5_tables(top_scores: list[Any]) -> Layout:
    """Build 6 tables showing top 15 for each factor score, arranged in 2 rows x 3 columns.

    Creates a grid layout with one table per factor (Momentum, Quality, Value, Growth, Stability, Positioning).
    """
    if not isinstance(top_scores, list) or not top_scores:
        layout = Layout()
        layout.update(Text.from_markup("[dim]No score data[/]"))
        return layout

    # Define factors with their field names and colors
    factors = [
        ("Momentum", "momentum_score"),
        ("Quality", "quality_score"),
        ("Value", "value_score"),
        ("Growth", "growth_score"),
        ("Stability", "stability_score"),
        ("Positioning", "positioning_score"),
    ]

    # Build tables for each factor
    factor_panels = []
    for factor_name, field_name in factors:
        # Sort by this factor's score
        sorted_scores = []
        for sc in top_scores:
            score_val = safe_float(safe_get_field(sc, field_name))
            if score_val is not None:
                sorted_scores.append((score_val, sc))
        sorted_scores.sort(key=lambda x: x[0], reverse=True)

        # Build small table for top 15 with rank numbers
        t = Table(
            box=box.SIMPLE_HEAD,
            show_header=False,
            header_style="dim",
            padding=(0, 1),
            expand=False,
            row_styles=["", "dim"],
        )
        t.add_column("#", style="dim", justify="right", no_wrap=True, width=2)
        t.add_column("S", style="bold white", no_wrap=True, width=5)
        t.add_column(factor_name[:2], justify="right", no_wrap=True, width=4)

        for rank, (score_val, sc) in enumerate(sorted_scores[:15], 1):
            sym = safe_get_field(sc, "symbol", "--")
            t.add_row(
                Text(str(rank), style="dim"),
                sym,
                Text(f"{score_val:.0f}" if score_val is not None else "--", style=_composite_score_color(score_val)),
            )

        factor_panels.append(Panel(
            t,
            title=f"[bold dim]{factor_name}[/]",
            border_style="dim",
            padding=(0, 0),
        ))

    # Arrange in 2 rows x 3 columns layout
    layout = Layout()
    layout.split_row(
        Layout(name="col1", ratio=1),
        Layout(name="col2", ratio=1),
        Layout(name="col3", ratio=1),
    )
    layout["col1"].split_column(
        Layout(factor_panels[0], name="m", ratio=1),
        Layout(factor_panels[3], name="g", ratio=1),
    )
    layout["col2"].split_column(
        Layout(factor_panels[1], name="q", ratio=1),
        Layout(factor_panels[4], name="s", ratio=1),
    )
    layout["col3"].split_column(
        Layout(factor_panels[2], name="v", ratio=1),
        Layout(factor_panels[5], name="p", ratio=1),
    )

    return layout


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

    # has_error() only flags None or a dict with an error marker - a bare list (malformed/
    # legacy API response) passes through as "no error" and then crashes safe_get_dict()
    # with an unhandled TypeError instead of rendering a graceful error panel.
    if not isinstance(scores, dict):
        malformed_panel = _error_panel(
            "scores", {"_error": f"Expected scores dict, got {type(scores).__name__}"}, "SCORES", border="cyan"
        )
        if malformed_panel is not None:
            return malformed_panel
        return Panel(Text("Malformed score data", style="dim"), title="[bold cyan]SCORES[/]", border_style="cyan")

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
    summary = _build_scores_summary(safe_get_dict(scores), shown=min(len(top_scores), 15))
    if summary is not None:
        rows.append(summary)
    rows.extend(_build_scores_table(top_scores, limit=15))

    timestamp_val = safe_get_dict(scores).get("timestamp")
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    return Panel(
        Group(*rows),
        title=rf"[bold cyan]SCORES[/]{age_s}  [dim]\[c] expand[/]",
        border_style="cyan",
        padding=(0, 1),
    )


def panel_scores_expanded(scores: Any) -> Panel:
    """Full-screen scores view - composite + 6-factor breakdown for a larger candidate set.

    Layout: left side shows wider company/sector table (35 rows), right side shows top-5 for each factor.
    """
    err_panel = _error_panel("scores", scores, "SCORES", border="cyan")
    if err_panel:
        return err_panel

    # See panel_scores_compact above: has_error() doesn't flag a bare list, which would
    # otherwise crash safe_get_dict() with an unhandled TypeError.
    if not isinstance(scores, dict):
        malformed_panel = _error_panel(
            "scores", {"_error": f"Expected scores dict, got {type(scores).__name__}"}, "SCORES", border="cyan"
        )
        if malformed_panel is not None:
            return malformed_panel
        return Panel(Text("Malformed score data", style="dim"), title="[bold cyan]SCORES[/]", border_style="cyan")

    top_scores_raw = safe_get_list(safe_get_dict(scores).get("top", []))
    top_scores: list[Any] = top_scores_raw if isinstance(top_scores_raw, list) else []

    timestamp_val = safe_get_dict(scores).get("timestamp")
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""

    if not top_scores:
        return Panel(
            Text.from_markup("[yellow]No score data - check Data Health[/]"),
            title=f"[bold cyan]SCORES - EXPANDED[/]{age_s}",
            border_style="cyan",
            padding=(0, 1),
        )

    # Build left side: main table with company/sector info
    left_rows: list[Text | Table] = [
        Text.from_markup("[cyan][bold]TOP CANDIDATES[/][/]"),
    ]
    summary = _build_scores_summary(safe_get_dict(scores), shown=min(len(top_scores), 50))
    if summary is not None:
        left_rows.append(summary)
    left_rows.extend(_build_scores_table(top_scores, limit=50, show_company=True))

    # Build right side: top-5 for each factor (3 columns x 2 rows grid)
    factor_layout = _build_factor_top5_tables(top_scores)

    # Create side-by-side layout: main table on left (expanded), factor grid on right (narrow)
    main_layout = Layout()
    main_layout.split_row(
        Layout(Group(*left_rows), ratio=6, name="main"),
        Layout(factor_layout, ratio=3, name="factors"),
    )

    return Panel(
        main_layout,
        title=f"[bold cyan]SCORES - EXPANDED[/]{age_s}  [dim]press [/][bold cyan]c[/][dim] to return[/]",
        border_style="cyan",
        padding=(0, 0),
    )


__all__ = [
    "panel_scores_compact",
    "panel_scores_expanded",
]
