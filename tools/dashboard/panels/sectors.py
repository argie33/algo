"""Sector analysis panel functions."""

import logging


logger = logging.getLogger(__name__)

try:
    from panel_registry import register_panel
except ImportError as e:
    logger.warning(f"Panel registry not available: {e} - panels will not auto-register")

    def register_panel(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn


from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from utils.safe_data_conversion import safe_float

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


def _rdelta(r, wk="rank_1w_ago", wk4=None):
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
def panel_sector_compact(srank, pos, port, sec_rot=None, irank=None):
    """Rotation + holdings (max 2) + sector leaders (1 pair) + industries (2 pairs) = 8 lines."""
    if _error_panel("srank", srank, "SECTORS"):
        return _error_panel("srank", srank, "SECTORS")
    if _error_panel("positions", pos, "SECTORS"):
        return _error_panel("positions", pos, "SECTORS")
    if _error_panel("portfolio", port, "SECTORS"):
        return _error_panel("portfolio", port, "SECTORS")

    rows = []

    # Row 1: Rotation signal
    if sec_rot and not _error_panel("sec_rot", sec_rot, "SECTORS") and safe_get_field(sec_rot, "signal"):
        sig_name = (safe_get_field(sec_rot, "signal") or "").replace("_", " ").title()
        wks = safe_get_field(sec_rot, "weeks") or 1
        def_s = safe_get_field(sec_rot, "def_score")
        cyc_s = safe_get_field(sec_rot, "cyc_score")
        strength = safe_get_field(sec_rot, "strength")
        def_f = float(def_s) if def_s is not None else None
        cyc_f = float(cyc_s) if cyc_s is not None else None
        strength_f = float(strength) if strength is not None else None
        sig_c = R if def_f is not None and def_f >= 60 else (Y if def_f is not None and def_f >= 40 else G)
        scores_s = f" [dim]def:{def_f:.0f} cyc:{cyc_f:.0f}[/]" if def_f is not None or cyc_f is not None else ""
        str_s = f" [dim]spread:{strength_f:.1f}[/]" if strength_f is not None else ""
        rows.append(
            Text.from_markup(f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name[:24]}[/] [dim]{wks}wk[/]{scores_s}{str_s}")
        )

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

        def fmt_sec_item(sec, dv):
            pct = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc = G if avg_pnl >= 0 else R
            bar_f = int(min(pct, 30) / 30 * 4)
            bar_s = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (4 - bar_f)}[/]"
            return f"[white]{sec[:13]:<13}[/]{bar_s}[dim]{pct:3.0f}%[/] [{pc}]{avg_pnl:+.1f}%[/]"

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
        return rows

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
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la = f"[{G}]#{a['current_rank']:<2}[/] [dim]{na}[/]{ms_a}{_rdelta(a, wk4='rank_4w_ago')}"
            if b:
                nb = (safe_get_field(b, "sector_name", ""))[:13]
                mmb = safe_get_field(b, "momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                lb = f"[{G}]#{b['current_rank']:<2}[/] [dim]{nb}[/]{ms_b}{_rdelta(b, wk4='rank_4w_ago')}"
            else:
                lb = ""
            srank_tbl.add_row(Text.from_markup(la), Text.from_markup(lb) if lb else Text(""))
        rows.append(srank_tbl)

    # Top industries (sub-sector groups)
    # Fail-fast: return early if API error detected
    if has_error(irank):
        return rows

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
            la = f"[{CY}]#{a['current_rank']:<2}[/] [white]{na}[/]{ms_a}{_rdelta(a)}"
            if b:
                nb = (safe_get_field(b, "industry", ""))[:14]
                mmb = safe_get_field(b, "momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                lb = f"[{CY}]#{b['current_rank']:<2}[/] [white]{nb}[/]{ms_b}{_rdelta(b)}"
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


def panel_sectors_expanded(srank, pos, port, sec_rot=None, irank=None):
    """Full-screen sectors - all sector and industry rankings, full portfolio breakdown."""
    if _error_panel("srank", srank, "SECTORS"):
        return _error_panel("srank", srank, "SECTORS")
    if _error_panel("positions", pos, "SECTORS"):
        return _error_panel("positions", pos, "SECTORS")
    if _error_panel("portfolio", port, "SECTORS"):
        return _error_panel("portfolio", port, "SECTORS")

    rows: list = [
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
            def_s = float(def_s_raw)
            cyc_s = float(cyc_s_raw)
            strength = float(strength_raw)
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
            logger.warning(f"Sector rotation missing required fields: def_score={def_s_raw}, cyc_score={cyc_s_raw}, strength={strength_raw}")

    # Full portfolio by sector
    # Issue 3.1 FIX: Use unified normalization function
    pos_list, _, _ = normalize_positions_data(pos)
    if pos_list:
        pv_raw = safe_get_field(port, "total_portfolio_value")
        if pv_raw is None:
            logger.warning("Total portfolio value unavailable for sector breakdown")
            pv = None
        else:
            pv = float(pv_raw)
        sd: dict = {}
        invalid_count = 0
        for p in pos_list:
            if not isinstance(p, dict):
                invalid_count += 1
                logger.error(f"panel_sectors_expanded: invalid position (not a dict): {type(p).__name__}")
                continue
            sec = safe_get_field(p, "sector", "Unknown")
            val = safe_float(safe_get_field(p, "position_value"), default=None)
            pnl = safe_float(safe_get_field(p, "unrealized_pnl_pct"), default=None)
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
                avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
                pc = G if avg_pnl >= 0 else R
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
    valid_irank = []
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

