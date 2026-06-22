"""Portfolio performance and analysis panel functions."""

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

from ..formatters import (
    fmt_age,
    fmt_money,
    fmt_money_short,
    mini_bar,
    sign,
    sparkline,
)
from ..utilities import (
    G,
    R,
    Y,
    normalize_positions_data,
)
from ._helpers import _error_panel


def _calculate_adjusted_win_rate(perf, pos):
    """E10 Fix: Include losing open positions in win rate calculation.

    Win rate should reflect all active positions (closed + open losses), not just closed trades.
    Counts open positions with unrealized_pnl_pct < 0 as losses.
    """
    if not perf or perf.get("_error"):
        return perf.get("wr") or 0, perf.get("w") or 0, perf.get("l") or 0

    closed_wins = perf.get("w") or 0
    closed_losses = perf.get("l") or 0
    losing_open = 0

    if pos and not pos.get("_error"):
        pos_items, _, _ = normalize_positions_data(pos)
        for p in pos_items:
            if isinstance(p, dict):
                pnl_val = p.get("unrealized_pnl_pct")
                if pnl_val is not None:
                    pnl = float(pnl_val)
                    if pnl < 0:
                        losing_open += 1

    total_trades = closed_wins + closed_losses + losing_open
    if total_trades == 0:
        return 0, closed_wins, closed_losses + losing_open

    adjusted_wr = (closed_wins / total_trades) * 100
    return adjusted_wr, closed_wins, closed_losses + losing_open


@register_panel(
    "portfolio",
    endpoint_deps=["port", "cfg", "risk", "perf"],
    optional=False,
    description="Portfolio",
)
def panel_portfolio(port, cfg, risk=None, perf=None):
    err_panel = _error_panel("portfolio", port, "PORTFOLIO", border="green")
    if err_panel:
        return err_panel

    pv = float(port["total_portfolio_value"])
    cash = float(port["total_cash"])
    npos = int(port["position_count"])
    dr = float(port.get("daily_return_pct")) if port.get("daily_return_pct") is not None else None
    urp = float(port.get("unrealized_pnl_pct")) if port.get("unrealized_pnl_pct") is not None else None
    cum = port.get("cumulative_return_pct")
    mxdd = port.get("max_drawdown_pct")
    lgpos = port.get("largest_position_pct")
    snap = port.get("snapshot_date")
    max_n = int(cfg.get("max_pos_n") or 0) if cfg else 0
    snap_s = f"  [dim]{fmt_age(snap)}[/]" if snap is not None else ""

    # Header: portfolio value + age
    header = Text.from_markup(f"[bold white]{fmt_money(pv)}[/]{snap_s}")

    # 2-column grid — keeps labels from wrapping
    def cell(label, value_markup):
        return Text.from_markup(f"[dim]{label}[/] {value_markup}")

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("left", ratio=1)
    tbl.add_column("right", ratio=1)

    # Cash / Positions
    if npos is not None:
        if max_n:
            _sb = mini_bar(npos, max_n, w=4)
            pos_val = f"{_sb}[dim]{npos}/{max_n}[/]"
        else:
            pos_val = f"[white]{npos}[/]"
    else:
        pos_val = "[dim]--[/]"
    tbl.add_row(
        cell("Cash:", f"[white]{fmt_money(cash)}[/]"),
        cell("Positions:", pos_val),
    )

    # Daily return / Unrealized P&L
    dr_s = f"[{G if (dr or 0) >= 0 else R}]{sign(dr or 0)}{(dr or 0):.2f}%[/]" if dr is not None else "[dim]--[/]"
    urp_s = f"[{G if (urp or 0) >= 0 else R}]{sign(urp or 0)}{(urp or 0):.2f}%[/]" if urp is not None else "[dim]--[/]"
    tbl.add_row(cell("Daily Return:", dr_s), cell("Unrealized P&L:", urp_s))

    # Total return / Max drawdown
    cum_v = float(cum) if cum is not None else None
    mxdd_v = float(mxdd) if mxdd is not None else None
    cc = G if (cum_v or 0) >= 0 else R
    cum_val = f"[{cc}]{sign(cum_v or 0)}{(cum_v or 0):.2f}%[/]" if cum_v is not None else "[dim]--[/]"
    dd_v = abs(mxdd_v) if mxdd_v is not None else None
    dd_c = R if (dd_v or 0) >= 15 else (Y if (dd_v or 0) >= 5 else G)
    dd_val = f"[{dd_c}]-{dd_v:.1f}%[/]" if dd_v is not None else "[dim]--[/]"
    tbl.add_row(cell("Total Return:", cum_val), cell("Max Drawdown:", dd_val))

    # Largest position
    if lgpos is not None:
        lp_c = R if float(lgpos) >= 20 else (Y if float(lgpos) >= 15 else "white")
        tbl.add_row(
            cell("Largest Position:", f"[{lp_c}]{float(lgpos):.1f}%[/]"),
            Text(""),
        )

    # Risk metrics (VaR, CVaR, Beta, concentration, Stressed VaR)
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        var_v = risk.get("var95") or 0
        cvar_v = risk.get("cvar95") or 0
        beta_v = risk.get("beta") or 0
        conc5_v = risk.get("conc5") or 0
        svar_v = risk.get("svar")
        conc_c = R if conc5_v >= 35 else (Y if conc5_v >= 25 else "white")
        var_c = R if var_v >= 4 else (Y if var_v >= 2 else "white")
        beta_c = R if beta_v >= 1.2 else (Y if beta_v >= 0.8 else G)
        tbl.add_row(
            cell("Value at Risk (95%):", f"[{var_c}]{var_v:.2f}%[/]"),
            cell("Cond. VaR (95%):", f"[{var_c}]{cvar_v:.2f}%[/]"),
        )
        tbl.add_row(
            cell("Portfolio Beta:", f"[{beta_c}]{beta_v:.2f}[/]"),
            cell("Top 5 Concentration:", f"[{conc_c}]{conc5_v:.0f}%[/]"),
        )
        if svar_v and float(svar_v) > 0:
            tbl.add_row(
                cell("Stressed VaR:", f"[{R}]{float(svar_v):.2f}%[/]"),
                Text(""),
            )

    return Panel(
        Group(header, tbl),
        title="[bold green]PORTFOLIO[/]  [dim][f] expand[/]",
        border_style="green",
        padding=(0, 1),
    )


@register_panel(
    "performance",
    endpoint_deps=["per", "trades", "perf_anl"],
    optional=True,
    description="Performance",
)
def panel_performance_spark(perf, rec, perf_anl=None, pos=None):
    """Performance metrics + equity sparkline + rolling analytics."""
    err_panel = _error_panel("performance", perf, "PERFORMANCE", border="green")
    if err_panel:
        return err_panel

    streak = perf.get("streak") if perf.get("streak") is not None else 0
    str_s = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
    str_c = G if streak >= 0 else R
    unrlzd = perf.get("unrealized_pnl")
    pnl_val = perf.get("pnl")
    pnl_c = G if pnl_val is not None and pnl_val >= 0 else R
    pf = perf.get("profit_factor")
    pf_s = f"{pf:.2f}" if pf is not None else "--"
    pf_c = G if pf is not None and pf >= 1.5 else (Y if pf is not None and pf >= 1.0 else R)
    exp = perf.get("expectancy")
    exp_c = G if (exp is None or exp >= 0) else R
    exp_s = f"{exp:.2f}R" if exp is not None else "--"
    sharpe_v = perf.get("sharpe")
    sharpe_s = f"{sharpe_v:.2f}" if sharpe_v is not None else "--"

    wr_v, _adj_w, adj_l = _calculate_adjusted_win_rate(perf, pos)
    closed_wins = perf.get("w") or 0
    closed_losses = perf.get("l") or 0
    losing_open = (adj_l or 0) - (closed_losses or 0)
    avg_win_v = perf.get("avg_win")
    avg_loss_v = perf.get("avg_loss")
    avg_win_s = f"{avg_win_v:.1f}%" if avg_win_v is not None else "--"
    avg_loss_s = f"{avg_loss_v:.1f}%" if avg_loss_v is not None else "--"
    wrc = G if wr_v >= 45 else (Y if wr_v >= 40 else R)
    open_l_s = f" [dim](+{losing_open} open L)[/]" if losing_open > 0 else ""

    # Header line: trade summary
    header = Text.from_markup(
        f"[bold white]{closed_wins + closed_losses + losing_open} Trades[/]  "
        f"[{G}]{closed_wins}W[/][dim]/[/][{R}]{adj_l}L[/]  "
        f"[dim]Win Rate:[/][{wrc}]{wr_v:.1f}%[/]{open_l_s}  "
        f"[{str_c}]{str_s} streak[/]"
    )

    # 2-column grid for metrics so labels don't wrap
    def cell(label, value_markup):
        return Text.from_markup(f"[dim]{label}[/] {value_markup}")

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("left", ratio=1)
    tbl.add_column("right", ratio=1)

    grid_rows = []

    # P&L row
    pnl_s = f"[{pnl_c}]{fmt_money(perf.get('pnl'))}[/]"
    if unrlzd is not None:
        unrlzd_s = f"[{G if (unrlzd or 0) >= 0 else R}]{fmt_money(unrlzd)}[/]"
        grid_rows.append((cell("Realized P&L:", pnl_s), cell("Unrealized P&L:", unrlzd_s)))
    else:
        grid_rows.append((cell("Realized P&L:", pnl_s), Text("")))

    # Ratios row
    grid_rows.append(
        (
            cell("Profit Factor:", f"[{pf_c}]{pf_s}[/]"),
            cell("Sharpe Ratio:", f"[white]{sharpe_s}[/]"),
        )
    )

    # Expectancy + avg win/loss row
    grid_rows.append(
        (
            cell("Expectancy (R):", f"[{exp_c}]{exp_s}[/]"),
            cell("Avg Win / Loss:", f"[{G}]{avg_win_s}[/][dim]/[/][{R}]{avg_loss_s}[/]"),
        )
    )

    # Rolling analytics
    if perf_anl and not perf_anl.get("_error"):
        sharpe252 = perf_anl.get("sharpe252")
        sortino = perf_anl.get("sortino")
        calmar = perf_anl.get("calmar")
        wr50 = perf_anl.get("wr50")
        avg_w_r = perf_anl.get("avg_w_r")
        avg_l_r = perf_anl.get("avg_l_r")

        if sharpe252 is not None and sharpe252 != 0.0 and sortino is not None and sortino != 0.0:
            sc1 = G if sharpe252 >= 1.0 else (Y if sharpe252 >= 0 else R)
            sc2 = G if sortino >= 1.5 else (Y if sortino >= 0 else R)
            grid_rows.append(
                (
                    cell("Sharpe (1-Year):", f"[{sc1}]{sharpe252:.2f}[/]"),
                    cell("Sortino Ratio:", f"[{sc2}]{sortino:.2f}[/]"),
                )
            )
        elif sharpe252 is not None and sharpe252 != 0.0:
            sc1 = G if sharpe252 >= 1.0 else (Y if sharpe252 >= 0 else R)
            grid_rows.append((cell("Sharpe (1-Year):", f"[{sc1}]{sharpe252:.2f}[/]"), Text("")))

        total_trades = perf.get("n", 0) if perf else 0
        calmar_cell = None
        wr50_cell = None
        if calmar is not None and calmar != 0.0:
            cc = G if calmar >= 0.5 else (Y if calmar >= 0 else R)
            calmar_cell = cell("Calmar Ratio:", f"[{cc}]{calmar:.2f}[/]")
        if wr50 is not None and wr50 != 0.0 and (total_trades >= 10 or wr50 > 0):
            wc = G if wr50 >= 50 else (Y if wr50 >= 42 else R)
            wr50_cell = cell("Win Rate (50 trades):", f"[{wc}]{wr50:.0f}%[/]")
        if calmar_cell is not None or wr50_cell is not None:
            grid_rows.append((calmar_cell or Text(""), wr50_cell or Text("")))

        if avg_w_r is not None or avg_l_r is not None:
            aw = cell("Avg Win (R-mult):", f"[{G}]{avg_w_r:.2f}R[/]") if avg_w_r is not None else Text("")
            al = cell("Avg Loss (R-mult):", f"[{R}]{avg_l_r:.2f}R[/]") if avg_l_r is not None else Text("")
            grid_rows.append((aw, al))

    for left, right in grid_rows:
        tbl.add_row(left, right)

    rows = [header, tbl]

    # Equity curve sparkline
    equity_vals = perf.get("equity_vals") or []
    if len(equity_vals) >= 3:
        sp = sparkline(equity_vals, width=28)
        rows.append(Text.from_markup(f"[dim]Equity curve:[/] {sp}"))

    # Recent daily returns (last 5 snapshots)
    recent_rets = perf.get("recent_rets") or []
    if recent_rets:
        parts = []
        for item in recent_rets[-5:]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                dt, ret = item[0], item[1]
            else:
                continue
            ret = ret or 0
            rc = G if ret >= 0 else R
            if hasattr(dt, "strftime"):
                d_s = dt.strftime("%a")
            elif isinstance(dt, str):
                try:
                    from datetime import datetime

                    dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                    d_s = dt_obj.strftime("%a")
                except (ValueError, AttributeError, TypeError) as e:
                    logger.debug(f"Failed to parse datetime {dt}: {e}")
                    d_s = str(dt)[:3]
            else:
                d_s = str(dt)[:3]
            parts.append(f"[dim]{d_s}[/][{rc}]{sign(ret)}{ret:.1f}%[/]")
        if parts:
            rows.append(Text.from_markup("  ".join(parts)))

    return Panel(
        Group(*rows),
        title="[bold green]PERFORMANCE[/]  [dim][f] expand[/]",
        border_style="green",
        padding=(0, 1),
    )


@register_panel(
    "portfolio_expanded",
    endpoint_deps=["port", "cfg", "risk", "perf", "perf_anl", "pos"],
    optional=True,
    description="Portfolio & Performance Expanded",
)
def panel_portfolio_perf_expanded(port, cfg, risk=None, perf=None, perf_anl=None, pos=None):
    """Full-screen portfolio + performance deep dive — all metrics, risk, concentration."""
    rows = [
        Text.from_markup("[dim]press [/][bold green]f[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    # ── Portfolio snapshot ────────────────────────────────────────────────────
    if port and not port.get("_error"):
        pv = float(port["total_portfolio_value"])
        cash = float(port["total_cash"])
        npos = int(port["position_count"])
        dr = float(port.get("daily_return_pct")) if port.get("daily_return_pct") is not None else None
        urp = float(port.get("unrealized_pnl_pct")) if port.get("unrealized_pnl_pct") is not None else None
        cum = float(port.get("cumulative_return_pct")) if port.get("cumulative_return_pct") is not None else None
        mxdd = float(port.get("max_drawdown_pct")) if port.get("max_drawdown_pct") is not None else None
        lgpos = float(port.get("largest_position_pct")) if port.get("largest_position_pct") is not None else None
        snap = port.get("snapshot_date")

        rows.append(Text.from_markup("[dim bold]PORTFOLIO SNAPSHOT[/]"))
        ptbl = Table.grid(padding=(0, 3), expand=False)
        ptbl.add_column("label", style="dim")
        ptbl.add_column("val", style="white")
        ptbl.add_column("label2", style="dim")
        ptbl.add_column("val2", style="white")
        ptbl.add_row(
            "Total Value:",
            f"{fmt_money(pv)}",
            "Cash:",
            fmt_money(cash),
        )
        max_n = int(cfg.get("max_pos_n") or 0) if cfg else 0
        slots_s = f"{npos}/{max_n}" if (npos is not None and max_n) else (str(npos) if npos is not None else "--")
        dr_s = f"{dr:+.2f}%" if dr is not None else "--"
        ptbl.add_row("Open Positions:", slots_s, "Day Return:", dr_s)
        urp_s = f"{urp:+.2f}%" if urp is not None else "--"
        cum_s = f"{cum:+.2f}%" if cum is not None else "--"
        ptbl.add_row("Unrealized P&L:", urp_s, "Total Return:", cum_s)
        dd_v = abs(mxdd) if mxdd is not None else None
        dd_s = f"-{dd_v:.1f}%" if dd_v is not None else "--"
        lp_s = f"{lgpos:.1f}%" if lgpos is not None else "--"
        ptbl.add_row("Max Drawdown:", dd_s, "Largest Position:", lp_s)
        if snap:
            ptbl.add_row("Snapshot Date:", str(snap)[:10], "", "")
        rows.append(ptbl)
    else:
        rows.append(Text("[dim]No portfolio data[/]"))

    rows.append(Rule(style="dim"))

    # ── Performance metrics ────────────────────────────────────────────────────
    if perf and not perf.get("_error") and not perf.get("_no_data"):
        rows.append(Text.from_markup("[dim bold]PERFORMANCE METRICS[/]"))
        n = perf.get("n") or 0
        w = perf.get("w") or 0
        closed_losses = perf.get("l") or 0
        streak = perf.get("streak") or 0
        pnl_val = perf.get("pnl")
        unrlzd_pnl = perf.get("unrealized_pnl")
        open_cnt = perf.get("open_count")
        pf = perf.get("profit_factor")
        sharpe_v = perf.get("sharpe")
        exp = perf.get("expectancy")
        dd_v = perf.get("maxdd") or 0
        avg_win = perf.get("avg_win")
        avg_loss = perf.get("avg_loss")

        wr_v, _adj_w, adj_l = _calculate_adjusted_win_rate(perf, pos)
        losing_open = (adj_l or 0) - (closed_losses or 0)
        wr_label = "Win Rate (adj.):" if losing_open > 0 else "Win Rate:"

        wrc = G if wr_v >= 45 else (Y if wr_v >= 40 else R)
        pf_c = G if pf is not None and pf >= 1.5 else (Y if pf is not None and pf >= 1.0 else R)
        exp_c = G if (exp is None or exp >= 0) else R
        str_c = G if streak >= 0 else R
        str_s = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
        dd_c = R if dd_v >= 15 else (Y if dd_v >= 5 else G)

        perfblk = Table.grid(padding=(0, 3), expand=False)
        perfblk.add_column("label", style="dim")
        perfblk.add_column("val")
        perfblk.add_column("label2", style="dim")
        perfblk.add_column("val2")
        perfblk.add_row(
            "Total Trades:",
            Text(str(n), style="white"),
            "Win/Loss:",
            Text.from_markup(f"[{G}]{w}W[/][dim]/[/][{R}]{closed_losses}L[/]"),
        )
        perfblk.add_row(
            wr_label,
            Text(f"{wr_v:.1f}%", style=wrc),
            "Streak:",
            Text(str_s, style=str_c),
        )
        perfblk.add_row(
            "Total P&L:",
            Text(fmt_money(pnl_val), style=G if (pnl_val or 0) >= 0 else R),
            "Profit Factor:",
            Text(f"{pf:.2f}" if pf else "--", style=pf_c),
        )
        perfblk.add_row(
            "Unrealized P&L:",
            Text(
                fmt_money(unrlzd_pnl) if unrlzd_pnl is not None else "--",
                style=G if (unrlzd_pnl or 0) >= 0 else R,
            ),
            "Open Positions:",
            Text(str(open_cnt) if open_cnt is not None else "--", style="white"),
        )
        perfblk.add_row(
            "Max Drawdown:",
            Text(f"-{dd_v:.1f}%" if dd_v else "--", style=dd_c),
            "Sharpe (annl.):",
            Text(f"{sharpe_v:.2f}" if sharpe_v is not None else "--", style="white"),
        )
        perfblk.add_row(
            "Expectancy:",
            Text(f"{exp:.2f}R" if exp is not None else "--", style=exp_c),
            "",
            Text(""),
        )
        perfblk.add_row(
            "Avg Win:",
            Text(f"{avg_win:.1f}%" if avg_win else "--", style=G),
            "Avg Loss:",
            Text(f"{avg_loss:.1f}%" if avg_loss else "--", style=R),
        )
        rows.append(perfblk)

        # Equity sparkline
        equity_vals = perf.get("equity_vals") or []
        if len(equity_vals) >= 3:
            sp = sparkline(equity_vals, width=50)
            rows.append(Text.from_markup(f"[dim]Equity curve:[/] {sp}"))

        # Recent daily returns
        recent_rets = perf.get("recent_rets") or []
        if recent_rets:
            from datetime import datetime

            parts = []
            for item in recent_rets[-10:]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    dt, ret = item[0], item[1]
                else:
                    continue
                ret = ret or 0
                rc = G if ret >= 0 else R
                try:
                    if hasattr(dt, "strftime"):
                        d_s = dt.strftime("%m/%d")
                    elif isinstance(dt, str):
                        d_s = datetime.fromisoformat(dt.replace("Z", "+00:00")).strftime("%m/%d")
                    else:
                        d_s = str(dt)[:5]
                except (ValueError, AttributeError, TypeError):
                    d_s = str(dt)[:5]
                parts.append(f"[dim]{d_s}[/][{rc}]{ret:+.1f}%[/]")
            if parts:
                rows.append(Text.from_markup("[dim]Daily returns:[/] " + "  ".join(parts)))

    rows.append(Rule(style="dim"))

    # ── Performance Analytics (rolling) ──────────────────────────────────────
    if perf_anl and not perf_anl.get("_error"):
        rows.append(Text.from_markup("[dim bold]ROLLING ANALYTICS[/]"))
        anl = Table.grid(padding=(0, 3), expand=False)
        anl.add_column("label", style="dim")
        anl.add_column("val")
        anl.add_column("label2", style="dim")
        anl.add_column("val2")
        sharpe252 = perf_anl.get("sharpe252")
        sortino = perf_anl.get("sortino")
        calmar = perf_anl.get("calmar")
        wr50 = perf_anl.get("wr50")
        avg_w_r = perf_anl.get("avg_w_r")
        avg_l_r = perf_anl.get("avg_l_r")
        exp2 = perf_anl.get("expectancy")
        maxdd2 = perf_anl.get("maxdd")
        anl.add_row(
            "Sharpe (252d):",
            Text(
                f"{sharpe252:.2f}" if sharpe252 is not None else "--",
                style=(G if (sharpe252 or 0) >= 1 else (Y if (sharpe252 or 0) >= 0 else R)),
            ),
            "Sortino:",
            Text(
                f"{sortino:.2f}" if sortino is not None else "--",
                style=G if (sortino or 0) >= 1.5 else (Y if (sortino or 0) >= 0 else R),
            ),
        )
        anl.add_row(
            "Calmar:",
            Text(
                f"{calmar:.2f}" if calmar else "--",
                style=G if (calmar or 0) >= 0.5 else (Y if (calmar or 0) >= 0 else R),
            ),
            "Win Rate (50T):",
            Text(
                f"{wr50:.0f}%" if wr50 else "--",
                style=G if (wr50 or 0) >= 50 else (Y if (wr50 or 0) >= 42 else R),
            ),
        )
        anl.add_row(
            "Avg Win R (50T):",
            Text(f"{avg_w_r:.2f}R" if avg_w_r else "--", style=G),
            "Avg Loss R (50T):",
            Text(f"{avg_l_r:.2f}R" if avg_l_r else "--", style=R),
        )
        if exp2 is not None or maxdd2 is not None:
            anl.add_row(
                "Expectancy:",
                Text(f"{exp2:.2f}R" if exp2 else "--", style=G if (exp2 or 0) >= 0 else R),
                "Max Drawdown:",
                Text(
                    f"-{abs(maxdd2):.1f}%" if maxdd2 else "--",
                    style=(R if abs(maxdd2 or 0) >= 15 else (Y if abs(maxdd2 or 0) >= 5 else G)),
                ),
            )
        rows.append(anl)
        rows.append(Rule(style="dim"))

    # ── Risk metrics ──────────────────────────────────────────────────────────
    if risk and not risk.get("_error") and risk.get("var95") and float(risk.get("var95") or 0) > 0:
        rows.append(Text.from_markup("[dim bold]RISK METRICS[/]"))
        rtbl = Table.grid(padding=(0, 3), expand=False)
        rtbl.add_column("label", style="dim")
        rtbl.add_column("val")
        rtbl.add_column("label2", style="dim")
        rtbl.add_column("val2")
        beta_c = R if (risk.get("beta") or 0) >= 1.2 else (Y if (risk.get("beta") or 0) >= 0.8 else G)
        conc_c = R if (risk.get("conc5") or 0) >= 35 else (Y if (risk.get("conc5") or 0) >= 25 else "white")
        var_c = R if (risk.get("var95") or 0) >= 4 else (Y if (risk.get("var95") or 0) >= 2 else "white")
        rtbl.add_row(
            "VaR (95%):",
            Text(f"{(risk.get('var95') or 0):.2f}%", style=var_c),
            "CVaR (95%):",
            Text(f"{(risk.get('cvar95') or 0):.2f}%", style=var_c),
        )
        rtbl.add_row(
            "Portfolio Beta:",
            Text(f"{(risk.get('beta') or 0):.2f}", style=beta_c),
            "Top-5 Concentration:",
            Text(f"{(risk.get('conc5') or 0):.0f}%", style=conc_c),
        )
        if risk.get("svar") and float(risk.get("svar") or 0) > 0:
            rtbl.add_row(
                "Stressed VaR:",
                Text(f"{(risk.get('svar') or 0):.2f}%", style=R),
                "Risk Date:",
                Text(str(risk.get("date") or "--")[:10], style="dim"),
            )
        rows.append(rtbl)

    # ── Position concentration ─────────────────────────────────────────────────
    if pos:
        pos_items, _, _ = normalize_positions_data(pos)
        if pos_items:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim bold]POSITION CONCENTRATION[/]"))
            pv_total = float(port["total_portfolio_value"]) if port and not port.get("_error") else 0
            conc_rows = []
            for p in pos_items:
                if not isinstance(p, dict):
                    continue
                sym = p.get("symbol") or "--"
                val_raw = p.get("position_value")
                val = float(val_raw) if val_raw is not None else None
                pnl_raw = p.get("unrealized_pnl_pct")
                pnl = float(pnl_raw) if pnl_raw is not None else None
                pct = val / pv_total * 100 if (val and pv_total) else 0
                conc_rows.append((pct, sym, val, pnl))
            conc_rows.sort(reverse=True)
            ctbl2 = Table.grid(padding=(0, 2), expand=True)
            ctbl2.add_column("sym", min_width=7)
            ctbl2.add_column("bar")
            ctbl2.add_column("pct", justify="right", min_width=6)
            ctbl2.add_column("val", justify="right", min_width=8)
            ctbl2.add_column("pnl", justify="right", min_width=7)
            for pct, sym, val, pnl in conc_rows[:15]:
                bar_f = int(min(pct, 25) / 25 * 12)
                pc = G if (pnl or 0) >= 0 else R
                bar_s = Text.from_markup(f"[{pc}]{'█' * bar_f}[/][dim]{'░' * (12 - bar_f)}[/]")
                conc_c = R if pct >= 20 else (Y if pct >= 15 else "white")
                ctbl2.add_row(
                    Text(sym, style="bold white"),
                    bar_s,
                    Text(f"{pct:.1f}%", style=conc_c),
                    Text(fmt_money_short(val) if val else "--", style="dim"),
                    Text(f"{pnl:+.1f}%" if pnl is not None else "--", style=pc),
                )
            rows.append(ctbl2)

    return Panel(
        Group(*rows),
        title="[bold green]PORTFOLIO & PERFORMANCE - EXPANDED[/]  [dim][f] return[/]",
        border_style="green",
        padding=(0, 1),
    )


__all__ = [
    "_calculate_adjusted_win_rate",
    "panel_performance_spark",
    "panel_portfolio",
    "panel_portfolio_perf_expanded",
]
