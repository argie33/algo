"""Recent trades and expanded trades panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from rich.console import ConsoleRenderable, RichCast

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
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from .. import error_boundary
from ..formatters import (
    fmt_age,
    sign,
)
from ..utilities import (
    CY,
    DIM,
    G,
    R,
    Y,
)
from .data_extractors import safe_get_field


def _extract_items(data: Any) -> list[Any] | dict[str, Any]:
    """Extract items list from various data structure formats.

    Propagates error dicts instead of silently returning empty list.
    Returns error dict if present, otherwise returns items list.
    Raises on malformed data to prevent silent data loss.
    """
    # Handle None explicitly — data not available yet (common on first load)
    if data is None:
        return {
            "_data_unavailable": True,
            "reason": "data_not_ready",
            "_message": "Trades data is still loading. Check network and API status.",
        }

    # Propagate error dicts (contains _error field)
    if isinstance(data, dict) and "_error" in data:
        return data
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return data["items"]
        if "trades" in data and isinstance(data["trades"], list):
            return data["trades"]
        # Dict exists but doesn't have expected structure — fail fast
        raise ValueError(
            f"Data dict missing 'items' or 'trades' field. "
            f"Got keys: {list(data.keys())}. "
            f"This indicates data structure mismatch or corruption."
        )

    # Unexpected data type — fail fast instead of silent empty list
    raise TypeError(
        f"Data must be None, list, or dict, got {type(data).__name__}. "
        f"This indicates a data validation or API response issue."
    )


@register_panel(
    "trades",
    endpoint_deps=["trades"],
    optional=True,
    description="Recent Trades",
)
def panel_recent_trades(trades: Any) -> Any:
    """Closed trade history (open positions are in the POSITIONS panel)."""
    if error_boundary.has_error(trades):
        error_msg = error_boundary.get_error_message(trades)
        return Panel(
            Text(error_msg or "Data unavailable", style="red"),
            title="[bold cyan]RECENT TRADES[/]  [dim][t] expand[/]",
            border_style="red",
            padding=(0, 1),
        )

    trades_timestamp = None
    if isinstance(trades, dict):
        trades_timestamp = safe_get_field(trades, "timestamp")
        trades_list = safe_get_field(trades, "items")
    else:
        trades_list = trades if isinstance(trades, list) else []

    # Filter to closed trades only — open/pending are in the positions panel
    closed_trades = [
        tr for tr in trades_list if isinstance(tr, dict) and (safe_get_field(tr, "status", "")).lower() == "closed"
    ]

    if not closed_trades:
        age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
        return Panel(
            Text("no closed trades yet", style="dim"),
            title=f"[bold cyan]RECENT TRADES[/]{age_s}  [dim][t] expand[/]",
            border_style="cyan",
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
    t.add_column("Sym", style="bold white", no_wrap=True, min_width=6)
    t.add_column("Exit", style="dim", no_wrap=True, min_width=5)
    t.add_column("Entry$", justify="right", no_wrap=True, min_width=6)
    t.add_column("Exit$", justify="right", no_wrap=True, min_width=6)
    t.add_column("P&L%", justify="right", no_wrap=True, min_width=6)
    t.add_column("R", justify="right", no_wrap=True, min_width=5)
    t.add_column("Days", justify="right", no_wrap=True, min_width=4)
    t.add_column("Grade", justify="center", no_wrap=True, min_width=5)

    def _fmt_date(d: Any) -> str:
        if hasattr(d, "strftime"):
            return d.strftime("%b%d")  # type: ignore[no-any-return]
        if isinstance(d, str) and len(d) >= 7:
            try:
                from datetime import datetime as _dt

                return _dt.fromisoformat(d.replace("Z", "+00:00")).strftime("%b%d")
            except (ValueError, TypeError):
                return d[5:10]
        return str(d or "--")[:5]

    for tr in closed_trades[:12]:
        # Extract trade fields once, then convert to typed values
        sym = safe_get_field(tr, "symbol", "--")
        pnl_d_raw = safe_get_field(tr, "profit_loss_dollars")
        pnl_p_raw = safe_get_field(tr, "profit_loss_pct")
        rmul_raw = safe_get_field(tr, "exit_r_multiple")
        entry_raw = safe_get_field(tr, "entry_price")
        exit_raw = safe_get_field(tr, "exit_price")
        dur_raw = safe_get_field(tr, "trade_duration_days")

        # Convert to typed values
        pnl_d = safe_float(pnl_d_raw)
        pnl_p = safe_float(pnl_p_raw)
        rmul = safe_float(rmul_raw)
        entry_p = safe_float(entry_raw)
        exit_p = safe_float(exit_raw)
        dur = int(dur_raw) if dur_raw is not None else None
        exit_date = safe_get_field(tr, "exit_date") or safe_get_field(tr, "trade_date")

        has_pnl = pnl_p is not None
        pnl_for_color = pnl_d if pnl_d is not None else pnl_p
        pc = G if (pnl_for_color is not None and pnl_for_color > 0) else R
        si = f"[{G}]▲[/]" if (pnl_p is not None and pnl_p > 0) else f"[{R}]▼[/]"
        grade = safe_get_field(tr, "swing_grade") or "--"
        grade_c = (
            G
            if grade in ("A", "A+", "A-")
            else (CY if grade in ("B", "B+", "B-") else (Y if grade in ("C", "C+", "C-") else DIM))
        )

        t.add_row(
            Text.from_markup(f"{si} {sym}"),
            _fmt_date(exit_date),
            Text(f"${entry_p:.2f}" if entry_p is not None else "--", style="dim"),
            Text(f"${exit_p:.2f}" if exit_p is not None else "--", style="dim"),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if has_pnl else "--", style=pc),
            Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=pc),
            Text(f"{dur}d" if dur is not None else "--", style="dim"),
            Text(grade, style=grade_c),
        )

    age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
    return Panel(
        t,
        title=f"[bold cyan]RECENT TRADES ({len(closed_trades)})[/]{age_s}  [dim][t] expand[/]",
        border_style="cyan",
        padding=(0, 0),
    )


def panel_trades_expanded(trades: Any) -> Any:
    """Full-screen closed trade history with all columns."""
    if error_boundary.has_error(trades):
        error_msg = error_boundary.get_error_message(trades)
        return Panel(
            Text(error_msg or "Data unavailable", style="red"),
            title="[bold cyan]TRADE HISTORY - EXPANDED[/]  [dim][t] return[/]",
            border_style="red",
            padding=(0, 1),
        )

    trades_timestamp = None
    if isinstance(trades, dict):
        trades_timestamp = safe_get_field(trades, "timestamp")
        trades_list = safe_get_field(trades, "items")
    else:
        trades_list = trades if isinstance(trades, list) else []

    closed = [
        tr for tr in trades_list if isinstance(tr, dict) and (safe_get_field(tr, "status", "")).lower() == "closed"
    ]

    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold cyan]t[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    if not closed:
        rows.append(Text("no closed trades yet", style="dim"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title="[bold cyan]TRADE HISTORY - EXPANDED[/]  [dim][t] return[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    # Summary stats (from displayed trades; see Performance panel for all-time stats)
    total = len(closed)
    # Count wins: only trades with profit_loss_pct data
    wins = sum(1 for t in closed if (pnl := safe_get_field(t, "profit_loss_pct")) is not None and float(pnl) > 0)
    losses = total - wins
    wr = wins / total * 100 if total else None
    # Sum P&L only from trades with profit_loss_dollars data
    total_pnl = sum(float(pnl_d) for t in closed if (pnl_d := safe_get_field(t, "profit_loss_dollars")) is not None)
    avg_r_list = [float(r) for t in closed if (r := safe_get_field(t, "exit_r_multiple")) is not None]
    avg_r = sum(avg_r_list) / len(avg_r_list) if avg_r_list else None
    wc = G if (wr is not None and wr >= 45) else (Y if (wr is not None and wr >= 40) else R)
    pnl_c = G if total_pnl >= 0 else R
    wr_str = f"{wr:.0f}%" if wr is not None else "N/A"
    rows.append(
        Text.from_markup(
            f"[dim]Showing {total} trades:[/]  [{G}]{wins}W[/][dim]/[/][{R}]{losses}L[/]  "
            f"[dim]Win Rate:[/][{wc}]{wr_str}[/]  "
            f"[dim]P&L:[/][{pnl_c}]{sign(total_pnl)}${abs(total_pnl):.0f}[/]"
            + (f"  [dim]Avg R:[/][white]{avg_r:.2f}R[/]" if avg_r is not None else "")
        )
    )
    rows.append(Rule(style="dim"))

    exit_short = {
        "stop_loss": "stop",
        "stop": "stop",
        "t1_target": "T1",
        "t1_hit": "T1",
        "t1": "T1",
        "t2_target": "T2",
        "t2_hit": "T2",
        "t2": "T2",
        "manual": "man",
        "time_exit": "time",
        "time": "time",
    }

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        padding=(0, 1),
        row_styles=["", "dim"],
        expand=True,
    )
    tbl.add_column("Sym", style="bold white", no_wrap=True, min_width=6)
    tbl.add_column("Entry Date", style="dim", no_wrap=True, min_width=6)
    tbl.add_column("Exit Date", style="dim", no_wrap=True, min_width=6)
    tbl.add_column("Entry$", justify="right", no_wrap=True, min_width=7)
    tbl.add_column("Exit$", justify="right", no_wrap=True, min_width=7)
    tbl.add_column("P&L$", justify="right", no_wrap=True, min_width=7)
    tbl.add_column("P&L%", justify="right", no_wrap=True, min_width=6)
    tbl.add_column("R", justify="right", no_wrap=True, min_width=5)
    tbl.add_column("Days", justify="right", no_wrap=True, min_width=4)
    tbl.add_column("Grade", justify="center", no_wrap=True, min_width=5)
    tbl.add_column("Exit", justify="center", no_wrap=True, min_width=4)
    tbl.add_column("MFE%", justify="right", no_wrap=True, min_width=5)
    tbl.add_column("MAE%", justify="right", no_wrap=True, min_width=5)

    def _fd(d: Any) -> str:
        if hasattr(d, "strftime"):
            return cast(str, cast(Any, d).strftime("%b%d"))
        if isinstance(d, str) and len(d) >= 7:
            try:
                from datetime import datetime as _dt

                return _dt.fromisoformat(d.replace("Z", "+00:00")).strftime("%b%d")
            except (ValueError, TypeError):
                return d[5:10]
        return str(d or "--")[:6]

    for tr in closed[:50]:
        sym = safe_get_field(tr, "symbol", "--")
        pnl_d_raw = safe_get_field(tr, "profit_loss_dollars")
        pnl_p_raw = safe_get_field(tr, "profit_loss_pct")
        pnl_d = float(pnl_d_raw) if pnl_d_raw is not None else None
        pnl_p = float(pnl_p_raw) if pnl_p_raw is not None else None
        rmul_raw = safe_get_field(tr, "exit_r_multiple")
        rmul = float(rmul_raw) if rmul_raw is not None else None
        entry_raw = safe_get_field(tr, "entry_price")
        exit_raw = safe_get_field(tr, "exit_price")
        entry_p = float(entry_raw) if entry_raw is not None else None
        exit_p = float(exit_raw) if exit_raw is not None else None
        dur_raw = safe_get_field(tr, "trade_duration_days")
        dur = int(dur_raw) if dur_raw is not None else None
        grade = safe_get_field(tr, "swing_grade") or "--"
        mfe_raw = safe_get_field(tr, "mfe_pct")
        mae_raw = safe_get_field(tr, "mae_pct")
        mfe = float(mfe_raw) if mfe_raw is not None else None
        mae = float(mae_raw) if mae_raw is not None else None
        trade_date = safe_get_field(tr, "trade_date") or safe_get_field(tr, "signal_date")
        exit_date = safe_get_field(tr, "exit_date")
        exit_rsn_raw = (safe_get_field(tr, "exit_reason", "")).lower().strip()
        exit_rsn = exit_short.get(exit_rsn_raw, exit_rsn_raw[:4] if exit_rsn_raw else "--")
        exit_rsn_c = R if exit_rsn == "stop" else (G if exit_rsn in ("T1", "T2") else (Y if exit_rsn == "man" else DIM))

        pc = G if (pnl_p is not None and pnl_p > 0) else R
        si = f"[{G}]▲[/]" if (pnl_p is not None and pnl_p > 0) else f"[{R}]▼[/]"
        grade_c = (
            G
            if grade in ("A", "A+", "A-")
            else (CY if grade in ("B", "B+", "B-") else (Y if grade in ("C", "C+", "C-") else DIM))
        )

        tbl.add_row(
            Text.from_markup(f"{si} {sym}"),
            _fd(trade_date),
            _fd(exit_date),
            Text(f"${entry_p:.2f}" if entry_p is not None else "--", style="dim"),
            Text(f"${exit_p:.2f}" if exit_p is not None else "--", style="dim"),
            Text(
                f"{sign(pnl_d)}${abs(pnl_d):.0f}" if pnl_d is not None else "--",
                style=pc,
            ),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if pnl_p is not None else "--", style=pc),
            Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=pc),
            Text(f"{dur}d" if dur is not None else "--", style="dim"),
            Text(grade, style=grade_c),
            Text(exit_rsn, style=exit_rsn_c),
            Text(
                f"{mfe:.1f}%" if mfe is not None else "--",
                style=G if (mfe is not None and mfe > 0) else DIM,
            ),
            Text(
                f"{mae:.1f}%" if mae is not None else "--",
                style=R if (mae is not None and mae < 0) else DIM,
            ),
        )

    rows.append(tbl)

    age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title=f"[bold cyan]TRADE HISTORY ({total} closed)[/]{age_s}  [dim][t] return[/]",
        border_style="cyan",
        padding=(0, 1),
    )


__all__ = [
    "_extract_items",
    "panel_recent_trades",
    "panel_trades_expanded",
]
