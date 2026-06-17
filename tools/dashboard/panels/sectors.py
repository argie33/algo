"""Sector analysis panel functions."""

import json
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

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from data_validation import safe_float
from utilities import (
    compute_sector_agg,
    normalize_positions_data,
    G,
    R,
    Y,
    CY,
    DIM,
)
from formatters import (
    hbar,
    mini_bar,
)

from ._helpers import _error_panel


def _rdelta(r, wk="rank_1w_ago", wk4=None):
    """Format rank delta: show change and direction arrow."""
    cur = r.get("rank")
    prev = r.get(wk)
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
    rows = []

    # Row 1: Rotation signal
    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = (sec_rot.get("signal") or "").replace("_", " ").title()
        wks = sec_rot.get("weeks", 1)
        def_s = float(sec_rot.get("def_score") or 0)
        cyc_s = float(sec_rot.get("cyc_score") or 0)
        strength = float(sec_rot.get("strength") or 0)
        sig_c = R if def_s >= 60 else (Y if def_s >= 40 else G)
        scores_s = (
            f" [dim]def:{def_s:.0f} cyc:{cyc_s:.0f}[/]"
            if def_s or cyc_s
            else ""
        )
        str_s = f" [dim]spread:{strength:.1f}[/]" if strength else ""
        rows.append(
            Text.from_markup(
                f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name[:24]}[/] [dim]{wks}wk[/]{scores_s}{str_s}"
            )
        )

    # Holdings by sector: 2-col pairs, up to 6 sectors
    sorted_secs, total_secs, pv = compute_sector_agg(pos, port)
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
            return (
                f"[white]{sec[:13]:<13}[/]{bar_s}"
                f"[dim]{pct:3.0f}%[/] [{pc}]{avg_pnl:+.1f}%[/]"
            )

        sec_tbl = Table.grid(padding=(0, 2), expand=True)
        sec_tbl.add_column("a", ratio=1)
        sec_tbl.add_column("b", ratio=1)
        for a, b in zip(show_secs[::2], show_secs[1::2] + [None]):
            sec_tbl.add_row(
                Text.from_markup(fmt_sec_item(*a)),
                Text.from_markup(fmt_sec_item(*b)) if b else Text(""),
            )
        rows.append(sec_tbl)

    # Top sector rankings with 1-week and 4-week rank changes
    srank_items = (
        srank.get("items", [])
        if isinstance(srank, dict) and "items" in srank
        else (srank if isinstance(srank, list) else [])
    )
    srank_error = srank.get("_error") if isinstance(srank, dict) else None
    valid_srank = [r for r in srank_items if not srank_error][:6]
    if valid_srank:
        if rows:
            rows.append(Rule(style="dim"))
        rows.append(
            Text.from_markup("[dim]Sector rankings by momentum  ↑↓= rank change vs 1wk/4wk:[/]")
        )
        srank_tbl = Table.grid(padding=(0, 2), expand=True)
        srank_tbl.add_column("a", ratio=1)
        srank_tbl.add_column("b", ratio=1)
        for a, b in zip(valid_srank[::2], valid_srank[1::2] + [None]):
            na = (a.get("sector_name") or "")[:13]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la = f"[{G}]#{a['current_rank']:<2}[/] [dim]{na}[/]{ms_a}{_rdelta(a, wk4='rank_4w_ago')}"
            if b:
                nb = (b.get("sector_name") or "")[:13]
                mmb = b.get("momentum_score")
                ms_b = f"[dim] mom:{float(mmb):.0f}[/]" if mmb is not None else ""
                lb = f"[{G}]#{b['current_rank']:<2}[/] [dim]{nb}[/]{ms_b}{_rdelta(b, wk4='rank_4w_ago')}"
            else:
                lb = ""
            srank_tbl.add_row(Text.from_markup(la), Text.from_markup(lb) if lb else Text(""))
        rows.append(srank_tbl)

    # Top industries (sub-sector groups)
    irank_items = (
        irank.get("items", [])
        if isinstance(irank, dict) and "items" in irank
        else (irank if isinstance(irank, list) else [])
    )
    irank_error = irank.get("_error") if isinstance(irank, dict) else None
    valid_irank = irank_items if irank_items and not irank_error else []
    if valid_irank:
        rows.append(Rule(style="dim"))
        rows.append(
            Text.from_markup("[dim]Top industries by momentum  ↑↓= vs 1wk:[/]")
        )
        irank_tbl = Table.grid(padding=(0, 2), expand=True)
        irank_tbl.add_column("a", ratio=1)
        irank_tbl.add_column("b", ratio=1)
        for a, b in zip(valid_irank[:4][::2], valid_irank[:4][1::2] + [None]):
            na = (a.get("industry") or "")[:14]
            mma = a.get("momentum_score")
            ms_a = f"[dim] mom:{float(mma):.0f}[/]" if mma is not None else ""
            la = f"[{CY}]#{a['current_rank']:<2}[/] [white]{na}[/]{ms_a}{_rdelta(a)}"
            if b:
                nb = (b.get("industry") or "")[:14]
                mmb = b.get("momentum_score")
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
    rows: list = [
        Text.from_markup(
            "[dim]press [/][bold cyan]r[/][dim] to return to dashboard[/]"
        ),
        Rule(style="dim"),
    ]

    if sec_rot and not sec_rot.get("_error") and sec_rot.get("signal"):
        sig_name = (sec_rot.get("signal") or "").replace("_", " ").title()
        wks = sec_rot.get("weeks", 1)
        def_s = float(sec_rot.get("def_score") or 0)
        cyc_s = float(sec_rot.get("cyc_score") or 0)
        strength = float(sec_rot.get("strength") or 0)
        sig_c = R if def_s >= 60 else (Y if def_s >= 40 else G)
        rot_date = sec_rot.get("date")
        date_s = f"  [dim]as of {str(rot_date)[:10]}[/]" if rot_date else ""
        rows.append(
            Text.from_markup(
                f"[dim]Sector Rotation:[/] [{sig_c}]{sig_name}[/]  [dim]{wks}wk  "
                f"defensive:{def_s:.0f}  cyclical:{cyc_s:.0f}  spread:{strength:.1f}[/]{date_s}"
            )
        )
        rows.append(Rule(style="dim"))

    # Full portfolio by sector
    # Issue 3.1 FIX: Use unified normalization function
    pos_list, _, _ = normalize_positions_data(pos)
    if pos_list:
        pv = float(port.get("total_portfolio_value") or 0)
        sd: dict = {}
        invalid_count = 0
        for p in pos_list:
            if not isinstance(p, dict):
                invalid_count += 1
                logger.error(
                    f"panel_sectors_expanded: invalid position (not a dict): {type(p).__name__}"
                )
                continue
            sec = p.get("sector") or "Unknown"
            val = safe_float(p.get("position_value"), default=None)
            pnl = safe_float(p.get("unrealized_pnl_pct"), default=None)
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
        sorted_secs = sorted(sd.items(), key=lambda x: -x[1]["val"])
        rows.append(Text.from_markup("[dim]Portfolio by sector:[/]"))
        for sec, dv in sorted_secs:
            pct = dv["val"] / pv * 100 if pv else 0
            avg_pnl = sum(dv["pnls"]) / len(dv["pnls"]) if dv["pnls"] else 0
            pc = G if avg_pnl >= 0 else R
            bar_f = int(min(pct, 25) / 25 * 8)
            bar_s = f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (8 - bar_f)}[/]"
            rows.append(
                Text.from_markup(
                    f"  [white]{str(sec):<24}[/]{bar_s} [dim]{pct:.1f}%  {dv['n']} pos[/]  [{pc}]{sign(avg_pnl)}{avg_pnl:.1f}% avg P&L[/]"
                )
            )
        rows.append(Rule(style="dim"))

    # All sector rankings — one per row, full names, 1wk and 4wk changes
    srank_items_exp = (
        srank.get("items", [])
        if isinstance(srank, dict) and "items" in srank
        else (srank if isinstance(srank, list) else [])
    )
    srank_error_exp = srank.get("_error") if isinstance(srank, dict) else None
    valid_srank = [r for r in srank_items_exp if not srank_error_exp]
    if valid_srank:
        rows.append(
            Text.from_markup("[dim]All sectors  (rank  mom  ↑↓1wk/4wk):[/]")
        )
        for r in valid_srank:
            nm = str(r.get("sector_name") or "")
            mm = r.get("momentum_score")
            ms = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rank_str = str(r.get("current_rank") or "")
            rows.append(
                Text.from_markup(
                    f"  [{G}]#{rank_str:<2}[/]  [white]{nm:<28}[/]{ms}  {_rdelta(r, wk4='rank_4w_ago')}"
                )
            )
        rows.append(Rule(style="dim"))

    # All industries — full names, 1wk change
    irank_items_exp = (
        irank.get("items", [])
        if isinstance(irank, dict) and "items" in irank
        else (irank if isinstance(irank, list) else [])
    )
    irank_error_exp = irank.get("_error") if isinstance(irank, dict) else None
    valid_irank = irank_items_exp if irank_items_exp and not irank_error_exp else []
    if valid_irank:
        rows.append(
            Text.from_markup("[dim]All industries  (rank  mom  ↑↓1wk):[/]")
        )
        for r in valid_irank:
            nm = str(r.get("industry") or "")
            mm = r.get("momentum_score")
            ms = f"[dim]  mom:{float(mm):.0f}[/]" if mm is not None else ""
            rank_str = str(r.get("current_rank") or "")
            rows.append(
                Text.from_markup(
                    f"  [{CY}]#{rank_str:<2}[/]  [white]{nm:<32}[/]{ms}  {_rdelta(r)}"
                )
            )

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
    "panel_sector_compact",
    "panel_sectors_expanded",
    "_rdelta",
]
