"""Position panel functions."""

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


from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from ..formatters import (
    fmt_age,
    fmt_money_short,
    sign,
)
from ..utilities import (
    G,
    R,
    Y,
    normalize_positions_data,
)


@register_panel(
    "positions",
    endpoint_deps=["pos", "trades"],
    optional=True,
    description="Positions",
)
def panel_positions(pos: Any, compact: bool = False, trades: Any = None, extended: bool = False) -> Any:
    """Display open positions table. Normalizes input from {"items": [...]} format.

    Data Contract:
    - Expects pos as dict with {"items": [position_dicts]} or list of positions
    - Error handling via "_error" field (hard errors)
    - Optional data unavailability via "_data_unavailable" flag (graceful degradation)
    - Each position dict requires: symbol, current_price, avg_entry_price, position_value
    - Optional fields: weinstein_stage, swing_score, sector, company_name/name
    """
    # Issue 3.1 FIX: Use unified normalization function
    pos_items, pos_timestamp, has_err = normalize_positions_data(pos)
    if has_err:
        # Hard error: data layer returned explicit error marker
        err_msg = pos.get("_error") if isinstance(pos, dict) else None
        if err_msg is None:
            raise RuntimeError(
                "Positions panel received error flag but no error message. "
                "Cannot display positions without error context. "
                "Check normalize_positions_data output and _error field."
            )
        return Panel(
            Text(f"  Error: {err_msg}", style="red"),
            title="[bold red]POSITIONS[/]",
            border_style="red",
            padding=(0, 1),
        )

    if not pos_items:
        return Panel(
            Text("  No open positions - algo is flat", style="dim"),
            title="[bold]POSITIONS[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    # Check for graceful degradation: optional data unavailability marker
    is_data_unavailable = isinstance(pos, dict) and pos.get("_data_unavailable", False)
    if is_data_unavailable:
        # Optional data marked unavailable by loader (e.g., missing enrichment)
        reason = pos.get("reason", "unknown reason")
        logger.warning(f"Positions data marked unavailable: {reason}")
        return Panel(
            Text.from_markup("[red]✗ POSITIONS DATA UNAVAILABLE[/]\nOptional position enrichment unavailable. Check logs for details."),
            title="[bold red]POSITIONS (DATA UNAVAILABLE)[/]",
            border_style="red",
            padding=(0, 1),
        )

    t = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        padding=(0, 1),
        row_styles=["", "dim"],
        expand=True,
    )
    t.add_column("Symbol", style="bold white", no_wrap=True, min_width=6)
    t.add_column("Name", style="dim", no_wrap=True, max_width=16)
    t.add_column("Val", justify="right", no_wrap=True, min_width=5)
    t.add_column("Entry", justify="right", no_wrap=True)
    t.add_column("Price", justify="right", no_wrap=True)
    t.add_column("P&L%", justify="right", no_wrap=True, min_width=7)
    if extended:
        t.add_column("R-Mult", justify="right", no_wrap=True, min_width=6)
    t.add_column("Stop", justify="right", no_wrap=True)
    t.add_column("Dist%", justify="right", no_wrap=True)
    if not compact:
        t.add_column("T1->", justify="right", no_wrap=True)
        t.add_column("Days", justify="right", no_wrap=True, min_width=4)
        t.add_column("Stage", justify="center", no_wrap=True, min_width=3)
        t.add_column("Swing", justify="right", no_wrap=True, min_width=4)
        t.add_column("Sector", style="dim", no_wrap=True, max_width=12)
    invalid_count = 0
    for p in pos_items:
        # Validate position dict structure
        if not isinstance(p, dict):
            invalid_count += 1
            logger.error(f"panel_positions: invalid position (not a dict): {type(p).__name__}")
            continue

        # Extract and validate critical fields (required for display)
        symbol = p.get("symbol")
        if not symbol:
            invalid_count += 1
            logger.error("panel_positions: position missing required 'symbol' field")
            continue

        # Extract numeric fields (high-priority data)
        entry = safe_float(p.get("avg_entry_price"), default=None)
        price = safe_float(p.get("current_price"), default=None)
        pval = safe_float(p.get("position_value"), default=None)
        stop = safe_float(p.get("stop_loss_price"), default=None)
        pnl = safe_float(p.get("unrealized_pnl_pct"), default=None)

        # Log if critical numeric fields are missing
        if entry is None:
            logger.debug(f"panel_positions[{symbol}]: missing avg_entry_price")
        if price is None:
            logger.debug(f"panel_positions[{symbol}]: missing current_price")
        if pval is None:
            logger.debug(f"panel_positions[{symbol}]: missing position_value")

        # Extract optional enrichment fields (low-priority data)
        days = p.get("days_since_entry", "--")
        stg = p.get("weinstein_stage")  # Optional: Weinstein stage (may be unavailable)
        swg = p.get("swing_score")  # Optional: swing score (may be unavailable)
        sec = (p.get("sector") or "--")[:12]  # Optional: sector enrichment
        rmul = safe_float(p.get("r_multiple"), default=None)  # Optional: risk multiple
        dist = safe_float(p.get("distance_to_stop_pct"), default=None)  # Optional: distance metric
        t1pct = safe_float(p.get("distance_to_t1_pct"), default=None)  # Optional: target distance

        # Extract display name (either company_name or generic name field)
        company_name_val = p.get("company_name", "")
        name_val = p.get("name", "")
        if company_name_val:
            name = company_name_val
        elif name_val:
            name = name_val
        else:
            name = ""
        name = name[:16]

        # Determine row styling based on metrics
        pc = G if (pnl is not None and pnl >= 0) else R
        rc = G if (rmul is not None and rmul >= 0) else R
        dc = R if (dist is not None and dist < 3) else (Y if (dist is not None and dist < 5) else "white")

        # Build table row
        row = [
            symbol,
            Text(name, style="dim"),
            fmt_money_short(pval) if pval is not None else "--",
            f"${entry:.2f}" if entry is not None else "--",
            f"${price:.2f}" if price is not None else "--",
            Text(f"{sign(pnl)}{pnl:.2f}%" if pnl is not None else "--", style=pc),
        ]
        if extended:
            row.append(Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=rc))
        row += [
            f"${stop:.2f}" if stop is not None else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            swg_s = float(swg) if swg is not None else None
            swg_c = (
                G if (swg_s is not None and swg_s >= 80) else (Y if (swg_s is not None and swg_s >= 60) else "white")
            )
            row += [
                f"+{t1pct:.1f}%" if t1pct is not None else "--",
                str(days),
                f"S{stg}" if stg else "--",
                Text(f"{swg_s:.0f}" if swg_s is not None else "--", style=swg_c),
                sec,
            ]
        t.add_row(*row)

    content = t
    age_s = f"  [dim]{fmt_age(pos_timestamp)}[/]" if pos_timestamp is not None else ""
    if invalid_count > 0:
        logger.error(f"panel_positions: encountered {invalid_count} invalid position(s); display may be incomplete")
        border = "red"
        title_str = f"[bold red]POSITIONS ⚠ DATA ERROR ({invalid_count} invalid)[/]"
    else:
        border = "cyan"
        title_str = f"[bold cyan]POSITIONS ({len(pos_items)})[/]"
    return Panel(
        content,
        title=f"{title_str}{age_s}  [dim][p] expand[/]",
        border_style=border,
        padding=(0, 0),
    )


__all__ = [
    "panel_positions",
]
