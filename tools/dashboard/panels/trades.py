"""Recent trades and expanded trades panel functions."""

import logging
from typing import Any


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


def _extract_items(data: Any) -> list:
    """Extract items list from various data structure formats."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("trades", [])
    return []


@register_panel(
    "trades",
    endpoint_deps=["trades"],
    optional=True,
    description="Recent Trades",
)
def panel_recent_trades(trades):
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
        trades_timestamp = trades.get("timestamp")
        trades_list = trades.get("items", [])
    else:
        trades_list = trades if isinstance(trades, list) else []

    # Filter to closed trades only — open/pending are in the positions panel
    closed_trades = [tr for tr in trades_list if isinstance(tr, dict) and (tr.get("status", "")).lower() == "closed"]

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

    def _fmt_date(d):
        if hasattr(d, "strftime"):
            return d.strftime("%b%d")
        if isinstance(d, str) and len(d) >= 7:
            try:
                from datetime import datetime as _dt

                return _dt.fromisoformat(d.replace("Z", "+00:00")).strftime("%b%d")
            except (ValueError, TypeError):
                return d[5:10]
        return str(d or "--")[:5]

    for tr in closed_trades[:12]:
        sym = tr.get("symbol", "--")
        pnl_d_raw = tr.get("profit_loss_dollars")
        pnl_p_raw = tr.get("profit_loss_pct")
        pnl_d = float(pnl_d_raw) if pnl_d_raw is not None else None
        pnl_p = float(pnl_p_raw) if pnl_p_raw is not None else None
        rmul_raw = tr.get("exit_r_multiple")
        rmul = float(rmul_raw) if rmul_raw is not None else None
        entry_raw = tr.get("entry_price")
        exit_raw = tr.get("exit_price")
        entry_p = float(entry_raw) if entry_raw is not None else None
        exit_p = float(exit_raw) if exit_raw is not None else None
        dur_raw = tr.get("trade_duration_days")
        dur = int(dur_raw) if dur_raw is not None else None
        exit_date = tr.get("exit_date") or tr.get("trade_date")

        has_pnl = pnl_p is not None
        pc = G if (pnl_d or pnl_p or 0) > 0 else R
        si = f"[{G}]▲[/]" if (pnl_p or 0) > 0 else f"[{R}]▼[/]"
        grade = tr.get("swing_grade", "--")
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


def panel_trades_expanded(trades):
    """Full-screen closed trade history with all columns."""
    trades_timestamp = None
    if isinstance(trades, dict):
        trades_timestamp = trades.get("timestamp")
        trades_list = trades.get("items", [])
    else:
        trades_list = trades if isinstance(trades, list) else []

    closed = [tr for tr in trades_list if isinstance(tr, dict) and (tr.get("status", "")).lower() == "closed"]

    rows = [
        Text.from_markup("[dim]press [/][bold cyan]t[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    if not closed:
        rows.append(Text("no closed trades yet", style="dim"))
        return Panel(
            Group(*rows),
            title="[bold cyan]TRADE HISTORY - EXPANDED[/]  [dim][t] return[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    # Summary stats (from displayed trades; see Performance panel for all-time stats)
    total = len(closed)
    wins = sum(1 for t in closed if (t.get("profit_loss_pct", 0)) > 0)
    losses = total - wins
    wr = wins / total * 100 if total else 0
    total_pnl = sum(float(t.get("profit_loss_dollars", 0)) for t in closed)
    avg_r_list = [float(t["exit_r_multiple"]) for t in closed if t.get("exit_r_multiple") is not None]
    avg_r = sum(avg_r_list) / len(avg_r_list) if avg_r_list else None
    wc = G if wr >= 45 else (Y if wr >= 40 else R)
    pnl_c = G if total_pnl >= 0 else R
    rows.append(
        Text.from_markup(
            f"[dim]Showing {total} trades:[/]  [{G}]{wins}W[/][dim]/[/][{R}]{losses}L[/]  "
            f"[dim]Win Rate:[/][{wc}]{wr:.0f}%[/]  "
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

    def _fd(d):
        if hasattr(d, "strftime"):
            return d.strftime("%b%d")
        if isinstance(d, str) and len(d) >= 7:
            try:
                from datetime import datetime as _dt

                return _dt.fromisoformat(d.replace("Z", "+00:00")).strftime("%b%d")
            except (ValueError, TypeError):
                return d[5:10]
        return str(d or "--")[:6]

    for tr in closed[:50]:
        sym = tr.get("symbol", "--")
        pnl_d_raw = tr.get("profit_loss_dollars")
        pnl_p_raw = tr.get("profit_loss_pct")
        pnl_d = float(pnl_d_raw) if pnl_d_raw is not None else None
        pnl_p = float(pnl_p_raw) if pnl_p_raw is not None else None
        rmul_raw = tr.get("exit_r_multiple")
        rmul = float(rmul_raw) if rmul_raw is not None else None
        entry_raw = tr.get("entry_price")
        exit_raw = tr.get("exit_price")
        entry_p = float(entry_raw) if entry_raw is not None else None
        exit_p = float(exit_raw) if exit_raw is not None else None
        dur_raw = tr.get("trade_duration_days")
        dur = int(dur_raw) if dur_raw is not None else None
        grade = tr.get("swing_grade", "--")
        mfe_raw = tr.get("mfe_pct")
        mae_raw = tr.get("mae_pct")
        mfe = float(mfe_raw) if mfe_raw is not None else None
        mae = float(mae_raw) if mae_raw is not None else None
        trade_date = tr.get("trade_date") or tr.get("signal_date")
        exit_date = tr.get("exit_date")
        exit_rsn_raw = (tr.get("exit_reason", "")).lower().strip()
        exit_rsn = exit_short.get(exit_rsn_raw, exit_rsn_raw[:4] if exit_rsn_raw else "--")
        exit_rsn_c = R if exit_rsn == "stop" else (G if exit_rsn in ("T1", "T2") else (Y if exit_rsn == "man" else DIM))

        pc = G if (pnl_p or 0) > 0 else R
        si = f"[{G}]▲[/]" if (pnl_p or 0) > 0 else f"[{R}]▼[/]"
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
            Text(f"{sign(pnl_d)}${abs(pnl_d):.0f}" if pnl_d is not None else "--", style=pc),
            Text(f"{sign(pnl_p)}{pnl_p:.1f}%" if pnl_p is not None else "--", style=pc),
            Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=pc),
            Text(f"{dur}d" if dur is not None else "--", style="dim"),
            Text(grade, style=grade_c),
            Text(exit_rsn, style=exit_rsn_c),
            Text(f"{mfe:.1f}%" if mfe is not None else "--", style=G if (mfe or 0) > 0 else DIM),
            Text(f"{mae:.1f}%" if mae is not None else "--", style=R if (mae or 0) < 0 else DIM),
        )

    rows.append(tbl)

    age_s = f"  [dim]{fmt_age(trades_timestamp)}[/]" if trades_timestamp is not None else ""
    return Panel(
        Group(*rows),
        title=f"[bold cyan]TRADE HISTORY ({total} closed)[/]{age_s}  [dim][t] return[/]",
        border_style="cyan",
        padding=(0, 1),
    )


__all__ = [
    "_extract_items",
    "panel_recent_trades",
    "panel_trades_expanded",
]

