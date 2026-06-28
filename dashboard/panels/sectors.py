"""Sector analysis panel functions."""

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


from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from ..error_boundary import has_error
from ..formatters import sign
from ..utilities import (
    CY,
    G,
    R,
    Y,
    compute_sector_agg,
    normalize_positions_data,
)
from ._helpers import _error_panel
from .data_extractors import safe_get_field


def _rdelta(r: Any, wk: str = "rank_1w_ago", wk4: str | None = None) -> str:
    """Format rank delta: show change and direction arrow."""
    cur = safe_get_field(r, "rank")
    prev = safe_get_field(r, wk)
    if cur is None or prev is None:
        return "--"
    delta = prev - cur
    if delta == 0:
        return "→"
    arrow = "↑" if delta > 0 else "↓"
    return f"{arrow}{abs(delta)}"


@register_panel(
    "sectors",
    endpoint_deps=["srank", "pos", "port"],
    optional=True,
    description="Sectors",
)
def panel_sector_compact(srank: Any, pos: Any, port: Any, sec_rot: Any = None, irank: Any = None) -> Panel:  # noqa: C901
    """Rotation + holdings (max 2) + sector leaders (1 pair) + industries (2 pairs) = 8 lines."""
    err = _error_panel("srank", srank, "SECTORS")
    if err is not None:
        return err
    err = _error_panel("positions", pos, "SECTORS")
    if err is not None:
        return err
    err = _error_panel("portfolio", port, "SECTORS")
    if err is not None:
        return err

    rows: list[Text | Rule | Table] = []

    # Row 1: Rotation signal
    if sec_rot and not _error_panel("sec_rot", sec_rot, "SECTORS") and safe_get_field(sec_rot, "signal"):
        sig_name = (safe_get_field(sec_rot, "signal") or "").replace("_", " ").title()
        wks = safe_get_field(sec_rot, "weeks")
        if wks is None:
            logger.warning("Sector rotation missing 'weeks' field — cannot display rotation window")
            wks = None
        def_s = safe_get_field(sec_rot, "def_score")
        cyc_s = safe_get_field(sec_rot, "cyc_score")
        strength = safe_get_field(sec_rot, "strength")
        def_f = safe_float(def_s)
        cyc_f = safe_float(cyc_s)
        strength_f = safe_float(strength)
        sig_c = R if def_f is not None and def_f >= 60 else (Y if def_f is not None and def_f >= 40 else G)
        scores_s = f" [dim]def:{def_f:.0f} cyc:{cyc_f:.0f}[/]" if def_f is not None or cyc_f is not None else ""
        str_s = f" [dim]spread:{strength_f:.1f}[/]" if strength_f is not None else ""
        wks_s = f" [dim]{wks}wk[/]" if wks is not None else " [dim]--wk[/]"
        rows.append(Text.from_markup(f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name[:24]}[/]{wks_s}{scores_s}{str_s}"))

    # Holdings by sector: 2-col pairs, up to 6 sectors
    try:
        sorted_secs, total_secs, pv = compute_sector_agg(pos, port)
    except ValueError as e:
        logger.warning(f"Cannot compute sector aggregation: {e}")
        sorted_secs = None
    if sorted_secs:
        show_secs = sorted_secs[:6]
        hdr_more = f" [dim](top 6 of {total_secs})[/]" if total_secs > 6 else ""
        rows.append(Text.from_markup(f"[dim]Holdings by sector:{hdr_more}[/]"))

        def fmt_sec_item(sec: str, dv: dict[str, Any]) -> str:
            if pv is None or pv == 0:
                raise ValueError("Cannot format sector item: portfolio value missing or zero")
            pct = dv["val"] / pv * 100
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else None
            pc = G if (avg_pnl is not None and avg_pnl >= 0) else R
            bar_f = int(min(pct, 30) / 30 * 4)
            bar_s = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (4 - bar_f)}[/]"
            pnl_str = f"{avg_pnl:+.1f}%" if avg_pnl is not None else "N/A"
            return f"[white]{sec[:13]:<13}[/]{bar_s}[dim]{pct:3.0f}%[/] [{pc}]{pnl_str}[/]"

        sec_tbl = Table.grid(padding=(0, 2), expand=True)
        sec_tbl.add_column("a", ratio=1)
        sec_tbl.add_column("b", ratio=1)
        for a, b in zip(show_secs[::2], [*show_secs[1::2], None], strict=False):
            sec_tbl.add_row(
                Text.from_markup(fmt_sec_item(*a)),
                Text.from_markup(fmt_sec_item(*b)) if b else Text(""),
            )
        rows.append(sec_tbl)

    # Top sector rankings with 1-week and 4-week rank changes
    # Fail-fast: return early if API error detected
    if has_error(srank):
        return Panel(
            Group(*rows) if rows else Text("no data", style="dim"),
            title="[bold cyan]SECTORS & INDUSTRIES[/]  [dim][r] expand[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    srank_items = None
    if isinstance(srank, dict) and "items" in srank:
        srank_items = safe_get_field(srank, "items")
        if not isinstance(srank_items, list):
            srank_items = None
    elif isinstance(srank, list):
        srank_items = srank
    if srank_items is None:
        srank_items = []
    valid_srank = srank_items[:6]
    if valid_srank:
        if rows:
            rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Sector rankings by momentum  ↑↓= rank change vs 1wk/4wk:[/]"))
        srank_tbl = Table.grid(padding=(0, 2), expand=True)
        srank_tbl.add_column("a", ratio=1)
        srank_tbl.add_column("b", ratio=1)
        for a, b in zip(valid_srank[::2], [*valid_srank[1::2], None], strict=False):
            na = (safe_get_field(a, "sector_name", ""))[:13]
            mma = safe_get_field(a, "momentum_score")
            mma_f = safe_float(mma)
            ms_a = f"[dim] mom:{mma_f:.0f}[/]" if mma_f is not None else ""
            rank_a = safe_get_field(a, "current_rank", "--")
            la = f"[{G}]#{rank_a:<2}[/] [dim]{na}[/]{ms_a}{_rdelta(a, wk4='rank_4w_ago')}"
            if b:
                nb = (safe_get_field(b, "sector_name", ""))[:13]
                mmb = safe_get_field(b, "momentum_score")
                mmb_f = safe_float(mmb)
                ms_b = f"[dim] mom:{mmb_f:.0f}[/]" if mmb_f is not None else ""
                rank_b = safe_get_field(b, "current_rank", "--")
                lb = f"[{G}]#{rank_b:<2}[/] [dim]{nb}[/]{ms_b}{_rdelta(b, wk4='rank_4w_ago')}"
            else:
                lb = ""
            srank_tbl.add_row(Text.from_markup(la), Text.from_markup(lb) if lb else Text(""))
        rows.append(srank_tbl)

    # Top industries (sub-sector groups)
    # Fail-fast: return early if API error detected
    if has_error(irank):
        return Panel(
            Group(*rows) if rows else Text("no data", style="dim"),
            title="[bold cyan]SECTORS & INDUSTRIES[/]  [dim][r] expand[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    irank_items = None
    if isinstance(irank, dict) and "items" in irank:
        irank_items = safe_get_field(irank, "items")
        if not isinstance(irank_items, list):
            irank_items = None
    elif isinstance(irank, list):
        irank_items = irank
    if irank_items is None:
        irank_items = []
    valid_irank = irank_items if irank_items else []
    if valid_irank:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim]Top industries by momentum  ↑↓= vs 1wk:[/]"))
        irank_tbl = Table.grid(padding=(0, 2), expand=True)
        irank_tbl.add_column("a", ratio=1)
        irank_tbl.add_column("b", ratio=1)
        for a, b in zip(valid_irank[:4][::2], [*valid_irank[:4][1::2], None], strict=False):
            na = (safe_get_field(a, "industry", ""))[:14]
            mma = safe_get_field(a, "momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            rank_a = safe_get_field(a, "current_rank", "--")
            la = f"[{CY}]#{rank_a:<2}[/] [white]{na}[/]{ms_a}{_rdelta(a)}"
            if b:
                nb = (safe_get_field(b, "industry", ""))[:14]
                mmb = safe_get_field(b, "momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                rank_b = safe_get_field(b, "current_rank", "--")
                lb = f"[{CY}]#{rank_b:<2}[/] [white]{nb}[/]{ms_b}{_rdelta(b)}"
            else:
                lb = ""
            irank_tbl.add_row(Text.from_markup(la), Text.from_markup(lb) if lb else Text(""))
        rows.append(irank_tbl)

    if not rows:
        return Panel(
            Text("no data", style="dim"),
            title="[bold]SECTORS & INDUSTRIES[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    return Panel(
        Group(*rows),
        title="[bold cyan]SECTORS & INDUSTRIES[/]  [dim][r] expand[/]",
        border_style="cyan",
        padding=(0, 1),
    )


def panel_sectors_expanded(srank: Any, pos: Any, port: Any, sec_rot: Any = None, irank: Any = None) -> Panel:  # noqa: C901
    """Full-screen sectors - all sector and industry rankings, full portfolio breakdown."""
    err = _error_panel("srank", srank, "SECTORS")
    if err is not None:
        return err
    err = _error_panel("positions", pos, "SECTORS")
    if err is not None:
        return err
    err = _error_panel("portfolio", port, "SECTORS")
    if err is not None:
        return err

    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold cyan]r[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    if sec_rot and not _error_panel("sec_rot", sec_rot, "SECTORS") and safe_get_field(sec_rot, "signal"):
        sig_name = (safe_get_field(sec_rot, "signal") or "").replace("_", " ").title()
        wks = safe_get_field(sec_rot, "weeks")
        if wks is None:
            wks = 1
        def_s_raw = safe_get_field(sec_rot, "def_score")
        cyc_s_raw = safe_get_field(sec_rot, "cyc_score")
        strength_raw = safe_get_field(sec_rot, "strength")
        if def_s_raw is not None and cyc_s_raw is not None and strength_raw is not None:
            def_s = safe_float(def_s_raw)
            cyc_s = safe_float(cyc_s_raw)
            strength = safe_float(strength_raw)
            if def_s is not None and cyc_s is not None and strength is not None:
                sig_c = R if def_s >= 60 else (Y if def_s >= 40 else G)
                rot_date = safe_get_field(sec_rot, "date")
                date_s = f"  [dim]as of {str(rot_date)[:10]}[/]" if rot_date else ""
                rows.append(
                    Text.from_markup(
                        f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name}[/]  [dim]{wks}wk  "
                        f"defensive:{def_s:.0f}  cyclical:{cyc_s:.0f}  spread:{strength:.1f}[/]{date_s}"
                    )
                )
                rows.append(Rule(style="dim"))
            else:
                logger.warning(
                    f"Sector rotation missing required fields: def_score={def_s_raw}, cyc_score={cyc_s_raw}, strength={strength_raw}"
                )
        else:
            logger.warning(
                f"Sector rotation missing required fields: def_score={def_s_raw}, cyc_score={cyc_s_raw}, strength={strength_raw}"
            )

    # Full portfolio by sector
    # Issue 3.1 FIX: Use unified normalization function
    pos_list, _, _ = normalize_positions_data(pos)
    if pos_list:
        pv_raw = safe_get_field(port, "total_portfolio_value")
        if pv_raw is None:
            logger.warning("Total portfolio value unavailable for sector breakdown")
            pv = None
        else:
            pv = safe_float(pv_raw)
        sd: dict[str, dict[str, Any]] = {}
        invalid_count = 0
        missing_sector_count = 0
        for p in pos_list:
            if not isinstance(p, dict):
                invalid_count += 1
                logger.error(f"panel_sectors_expanded: invalid position (not a dict): {type(p).__name__}")
                continue
            sec = safe_get_field(p, "sector")
            # CRITICAL: Skip positions without sector (don't default to "Unknown" which masks enrichment gaps)
            if sec is None:
                sym = p.get("symbol", "unknown")
                missing_sector_count += 1
                logger.warning(f"Position {sym} missing sector enrichment — skipping from sector breakdown")
                continue
            val = safe_float(safe_get_field(p, "position_value"))
            pnl = safe_float(safe_get_field(p, "unrealized_pnl_pct"))
            if sec not in sd:
                sd[sec] = {"val": 0.0, "n": 0, "pnls": []}
            if val is not None:
                sd[sec]["val"] += val
            sd[sec]["n"] += 1
            if pnl is not None:
                sd[sec]["pnls"].append(pnl)

        if invalid_count > 0:
            logger.error(
                f"panel_sectors_expanded: encountered {invalid_count} invalid position(s); sector totals may be incomplete"
            )

        # Only show sector breakdown if we have portfolio value (required for percentage calculations)
        if pv is not None and pv > 0:
            sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
            rows.append(Text.from_markup("[dim]Portfolio by sector:[/]"))
            for sec, dv in sorted_secs:
                pct = dv["val"] / pv * 100
                avg_pnl = (sum(dv["pnls"]) / len(dv["pnls"])) if dv["pnls"] else None
                pc = G if (avg_pnl is not None and avg_pnl >= 0) else R
                bar_f = int(min(pct, 25) / 25 * 8)
                bar_s = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (8 - bar_f)}[/]"
                rows.append(
                    Text.from_markup(
                        f"  [white]{sec!s:<24}[/]{bar_s} [dim]{pct:.1f}%  {dv['n']} pos[/]  [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}% avg P&L[/]"
                    )
                )
            rows.append(Rule(style="dim"))
        elif pv is not None:
            rows.append(Text.from_markup("[dim]Portfolio value is zero - no sector breakdown[/]"))
            rows.append(Rule(style="dim"))

    # All sector rankings — one per row, full names, 1wk and 4wk changes
    # Fail-fast: skip section if API error detected
    valid_srank: list[Any] = []
    if not has_error(srank):
        srank_items_exp = None
        if isinstance(srank, dict) and "items" in srank:
            srank_items_exp = safe_get_field(srank, "items")
            if not isinstance(srank_items_exp, list):
                srank_items_exp = None
        elif isinstance(srank, list):
            srank_items_exp = srank
        if srank_items_exp is None:
            srank_items_exp = []
        valid_srank = srank_items_exp
    if valid_srank:
        rows.append(Text.from_markup("[dim]All sectors  (rank  mom  ↑↓1wk/4wk):[/]"))
        for r in valid_srank:
            nm = str(safe_get_field(r, "sector_name", ""))
            mm = safe_get_field(r, "momentum_score")
            ms = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rank_str = str(safe_get_field(r, "current_rank", ""))
            rows.append(
                Text.from_markup(f"  [{G}]#{rank_str:<2}[/]  [white]{nm:<28}[/]{ms}  {_rdelta(r, wk4='rank_4w_ago')}")
            )
        rows.append(Rule(style="dim"))

    # All industries — full names, 1wk change
    # Fail-fast: skip section if API error detected
    valid_irank: list[Any] = []
    if not has_error(irank):
        irank_items_exp = None
        if isinstance(irank, dict) and "items" in irank:
            irank_items_exp = safe_get_field(irank, "items")
            if not isinstance(irank_items_exp, list):
                irank_items_exp = None
        elif isinstance(irank, list):
            irank_items_exp = irank
        if irank_items_exp is None:
            irank_items_exp = []
        valid_irank = irank_items_exp if irank_items_exp else []
    if valid_irank:
        rows.append(Text.from_markup("[dim]All industries  (rank  mom  ↑↓1wk):[/]"))
        for r in valid_irank:
            nm = str(safe_get_field(r, "industry", ""))
            mm = safe_get_field(r, "momentum_score")
            ms = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rank_str = str(safe_get_field(r, "current_rank", ""))
            rows.append(Text.from_markup(f"  [{CY}]#{rank_str:<2}[/]  [white]{nm:<32}[/]{ms}  {_rdelta(r)}"))

    if not rows:
        return Panel(
            Text("no data", style="dim"),
            title="[bold]SECTORS[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    return Panel(
        Group(*rows),
        title="[bold cyan]SECTORS & INDUSTRIES - EXPANDED[/]  [dim][r] return[/]",
        border_style="cyan",
        padding=(0, 1),
    )


__all__ = [
    "_rdelta",
    "panel_sector_compact",
    "panel_sectors_expanded",
]
