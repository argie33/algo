"""Options CSP/covered-call candidate screener panel (goal session 2026-09-12 POC).

Registered optional=True: this is a manual/periodic-sample data source (scripts/
options_data_loader.py), not a continuously-refreshed loader - missing/stale data here
must never block the rest of the dashboard from rendering.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dashboard.panel_registry import register_panel as register_panel
else:
    try:
        from dashboard.panel_registry import register_panel
    except ImportError as e:
        logger.warning(f"Panel registry not available: {e} - panels will not auto-register")
        from typing import TypeVar, overload

        _F = TypeVar("_F", bound=Callable[..., Any])

        @overload
        def register_panel(
            name: str,
            endpoint_deps: list[str],
            render_fn: None = None,
            optional: bool = False,
            description: str = "",
        ) -> Callable[[_F], _F]: ...

        @overload
        def register_panel(
            name: str,
            endpoint_deps: list[str],
            render_fn: _F,
            optional: bool = False,
            description: str = "",
        ) -> _F: ...

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
from rich.text import Text

from ..data_validation import safe_float
from ._helpers import _error_panel

_MAX_ROWS_PER_SIDE = 5


def _fmt(value: Any, field_name: str, decimals: int) -> str:
    parsed = safe_float(value, field_name=field_name)
    return "[dim]?[/]" if parsed is None else f"{parsed:.{decimals}f}"


@register_panel(
    "options",
    endpoint_deps=["options"],
    optional=True,
    description="CSP/covered-call candidate screener (0.15-0.30 delta zone)",
)
def panel_options(options: Any) -> Panel:
    """CSP (put) and covered-call (call) candidates, 0.15-0.30 |delta| zone.

    Data is filtered server-side (lambda/api/routes/options.py) - this panel just renders
    whatever comes back, split into the two sides already provided by fetch_options().
    """
    err_panel = _error_panel("options candidates", options, "OPTIONS SCREENER", border="cyan")
    if err_panel:
        return err_panel

    if not isinstance(options, dict):
        logger.error("[OPTIONS] Options data is not a dict: got %s", type(options).__name__)
        return Panel(
            Text("Options data is invalid", style="dim"),
            title="[bold cyan]OPTIONS SCREENER[/]",
            border_style="red",
            padding=(0, 1),
        )

    csp = options.get("csp_candidates")
    cc = options.get("covered_call_candidates")
    if csp is None or cc is None:
        logger.error("[OPTIONS] Missing csp_candidates/covered_call_candidates field")
        return Panel(
            Text("Options candidates missing (data_unavailable)", style="dim"),
            title="[bold cyan]OPTIONS SCREENER[/]",
            border_style="red",
            padding=(0, 1),
        )

    stale_warning = ""
    freshness = options.get("data_freshness")
    if isinstance(freshness, dict) and freshness.get("is_stale"):
        age_days = freshness.get("data_age_days", "?")
        stale_warning = f" ⚠ STALE (data {age_days}d old)"

    def _fmt_row(tbl: Table, item: dict[str, Any]) -> None:
        # Nested rather than top-level: it only ever runs on items from csp/cc, which are
        # already validated above (has_error/_error_panel check at the top of
        # panel_options) - same indirection pattern as panel_circuit's fmt_b.
        symbol = str(item.get("symbol", "?"))
        strike_s = _fmt(item.get("strike_price"), "strike_price", 2)
        delta_s = _fmt(item.get("delta"), "delta", 3)
        bid_s = _fmt(item.get("bid"), "bid", 2)
        ask_s = _fmt(item.get("ask"), "ask", 2)
        exp = str(item.get("expiration_date", "?"))
        tbl.add_row(symbol, strike_s, delta_s, f"{bid_s}/{ask_s}", exp)

    tbl = Table.grid(padding=(0, 1), expand=True)
    tbl.add_column("Symbol")
    tbl.add_column("Strike", justify="right")
    tbl.add_column("Delta", justify="right")
    tbl.add_column("Bid/Ask", justify="right")
    tbl.add_column("Exp")

    if not csp and not cc:
        body: Any = Text("No candidates in the 0.15-0.30 delta zone right now", style="dim")
    else:
        tbl.add_row("[bold]CSP (puts)[/]", "", "", "", "")
        for item in csp[:_MAX_ROWS_PER_SIDE]:
            _fmt_row(tbl, item)
        tbl.add_row("", "", "", "", "")
        tbl.add_row("[bold]Covered calls[/]", "", "", "", "")
        for item in cc[:_MAX_ROWS_PER_SIDE]:
            _fmt_row(tbl, item)
        body = tbl

    return Panel(
        body,
        title=f"[bold cyan]OPTIONS SCREENER{stale_warning}[/]",
        border_style="cyan",
        padding=(0, 1),
    )
