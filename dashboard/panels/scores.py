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
    t.add_column("Symbol", style="bold white", no_wrap=True, width=6)
    t.add_column("Comp", justify="right", no_wrap=True, width=5)
    t.add_column("Mom", justify="right", no_wrap=True, width=4)
    t.add_column("Qual", justify="right", no_wrap=True, width=5)
    t.add_column("Val", justify="right", no_wrap=True, width=4)
    t.add_column("Grow", justify="right", no_wrap=True, width=5)
    t.add_column("Stab", justify="right", no_wrap=True, width=5)
    t.add_column("Pos", justify="right", no_wrap=True, width=4)
    t.add_column("Chg%", justify="right", no_wrap=True, width=5)
    t.add_column("Sector", no_wrap=True, width=10)

    for sc in top_scores[:limit]:
        sym = safe_get_field(sc, "symbol", "--")
        comp = safe_get_field(sc, "composite_score")
        mom = safe_get_field(sc, "momentum_score")
        qual = safe_get_field(sc, "quality_score")
        val = safe_get_field(sc, "value_score")
        grwth = safe_get_field(sc, "growth_score")
        stab = safe_get_field(sc, "stability_score")
        pos = safe_get_field(sc, "positioning_score")
        chg = safe_get_field(sc, "change_percent")
        sector = (safe_get_field(sc, "sector") or "")[:12]
        comp_v: float | None = safe_float(comp)
        sc_c: str = _composite_score_color(comp_v) if comp_v is not None else "dim"
        chg_v: float | None = safe_float(chg)
        chg_c: str = "green" if chg_v is not None and chg_v > 0 else ("red" if chg_v is not None and chg_v < 0 else "dim")

        t.add_row(
            sym,
            Text(f"{comp_v:.0f}" if comp_v is not None else "--", style=sc_c),
            _score_cell(mom),
            _score_cell(qual),
            _score_cell(val),
            _score_cell(grwth),
            _score_cell(stab),
            _score_cell(pos),
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
    """Full-screen scores view - composite + 6-factor breakdown for a larger candidate set."""
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

    rows: list[Text | Table] = [
        Text.from_markup("[cyan][bold]SCORES - EXPANDED[/][/]"),
        Text.from_markup(
            f"[dim]{len(top_scores)} ranked candidates by composite score[/]  "
            "[dim]press [/][bold cyan]c[/][dim] to return[/]"
        ),
    ]
    summary = _build_scores_summary(safe_get_dict(scores), shown=min(len(top_scores), 50))
    if summary is not None:
        rows.append(summary)
    if top_scores:
        rows.extend(_build_scores_table(top_scores, limit=50))
    else:
        rows.append(Text.from_markup("[yellow]No score data - check Data Health[/]"))

    timestamp_val = safe_get_dict(scores).get("timestamp")
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    return Panel(
        Group(*rows),
        title=f"[bold cyan]SCORES - EXPANDED[/]{age_s}",
        border_style="cyan",
        padding=(0, 1),
    )


__all__ = [
    "panel_scores_compact",
    "panel_scores_expanded",
]
