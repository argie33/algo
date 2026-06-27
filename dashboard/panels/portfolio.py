"""Portfolio performance and analysis panel functions."""

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

from dashboard.data_validation import StrictValidationError, safe_float, safe_int

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


def _calculate_adjusted_win_rate(perf: dict[str, Any] | None, pos: dict[str, Any] | None) -> tuple[float, int, int]:
    """E10 Fix: Include losing open positions in win rate calculation.

    Win rate should reflect all active positions (closed + open losses), not just closed trades.
    Counts open positions with unrealized_pnl_pct < 0 as losses.
    """
    if perf is None or perf.get("_error"):
        return 0.0, 0, 0

    wr_val = perf.get("wr")
    w_val = perf.get("w")
    l_val = perf.get("l")
    if wr_val is None or w_val is None or l_val is None:
        return 0.0, 0, 0

    w_i = safe_int(w_val, 0, strict=True, field_name="closed_wins")
    l_i = safe_int(l_val, 0, strict=True, field_name="closed_losses")

    closed_wins = w_i
    closed_losses = l_i
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
        return 0.0, closed_wins, closed_losses + losing_open

    adjusted_wr = (closed_wins / total_trades) * 100
    return adjusted_wr, closed_wins, closed_losses + losing_open


@register_panel(
    "portfolio",
    endpoint_deps=["port", "cfg", "risk", "perf"],
    optional=False,
    description="Portfolio",
)
def panel_portfolio(
    port: dict[str, Any],
    cfg: dict[str, Any] | None,
    risk: dict[str, Any] | None = None,
    perf: dict[str, Any] | None = None,
) -> Panel:
    err_panel = _error_panel("portfolio", port, "PORTFOLIO", border="green")
    if err_panel:
        return err_panel

    pv = safe_float(port["total_portfolio_value"], strict=True, field_name="total_portfolio_value")
    cash = safe_float(port["total_cash"], strict=True, field_name="total_cash")
    npos = safe_int(port["position_count"], strict=True, field_name="position_count")
    dr = safe_float(port.get("daily_return_pct"), default=None)
    urp = safe_float(port.get("unrealized_pnl_pct"), default=None)
    cum = safe_float(port.get("cumulative_return_pct"), default=None)
    mxdd = safe_float(port.get("max_drawdown_pct"), default=None)
    lgpos = safe_float(port.get("largest_position_pct"), default=None)
    snap = port.get("snapshot_date")
    max_n_val = cfg.get("max_pos_n") if cfg else None
    if max_n_val is None:
        raise ValueError("max_pos_n config missing — cannot render portfolio position limits")
    max_n = safe_int(max_n_val, strict=True)
    snap_s = f"  [dim]{fmt_age(snap)}[/]" if snap is not None else ""
    # Header: portfolio value + age
    header = Text.from_markup(f"[bold white]{fmt_money(pv)}[/]{snap_s}")

    # 2-column grid — keeps labels from wrapping
    def cell(label: str, value_markup: str) -> Text:
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
    dr_s = f"[{G if dr >= 0 else R}]{sign(dr)}{dr:.2f}%[/]" if dr is not None else "[dim]--[/]"
    urp_s = f"[{G if urp >= 0 else R}]{sign(urp)}{urp:.2f}%[/]" if urp is not None else "[dim]--[/]"
    tbl.add_row(cell("Daily Return:", dr_s), cell("Unrealized P&L:", urp_s))

    # Total return / Max drawdown
    cum_v = float(cum) if cum is not None else None
    mxdd_v = float(mxdd) if mxdd is not None else None
    cc = G if cum_v is not None and cum_v >= 0 else R
    cum_val = f"[{cc}]{sign(cum_v)}{cum_v:.2f}%[/]" if cum_v is not None else "[dim]--[/]"
    dd_v: float | None = abs(mxdd_v) if mxdd_v is not None else None
    dd_c = R if dd_v is not None and dd_v >= 15 else (Y if dd_v is not None and dd_v >= 5 else G)
    dd_val = f"[{dd_c}]-{dd_v:.1f}%[/]" if dd_v is not None else "[dim]--[/]"
    tbl.add_row(cell("Total Return:", cum_val), cell("Max Drawdown:", dd_val))

    # Largest position
    if lgpos is not None:
        try:
            lgpos_f = safe_float(lgpos, 0.0, strict=True, field_name="largest_position_pct")
            lp_c = R if lgpos_f >= 20 else (Y if lgpos_f >= 15 else "white")
            tbl.add_row(
                cell("Largest Position:", f"[{lp_c}]{lgpos_f:.1f}%[/]"),
                Text(""),
            )
        except StrictValidationError:
            logger.warning("Largest position value conversion failed")

    # Risk metrics (VaR, CVaR, Beta, concentration, Stressed VaR)
    # CRITICAL: Fail-fast on missing risk metrics — don't silently hide them!
    if risk and not risk.get("_error"):
        var_v = safe_float(risk["var95"], strict=True, field_name="var95")
        cvar_v = safe_float(risk["cvar95"], strict=True, field_name="cvar95")
        beta_v = safe_float(risk["beta"], strict=True, field_name="beta")
        conc5_v = safe_float(risk["conc5"], strict=True, field_name="conc5")
        svar_v = safe_float(risk.get("svar"), strict=False, field_name="svar", default=None)

        # All critical fields available — render
        if var_v is not None and var_v > 0 and cvar_v is not None and beta_v is not None and conc5_v is not None:
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
            if svar_v is not None and svar_v > 0:
                tbl.add_row(
                    cell("Stressed VaR:", f"[{R}]{svar_v:.2f}%[/]"),
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
def panel_performance_spark(  # noqa: C901
    perf: dict[str, Any], rec: Any, perf_anl: dict[str, Any] | None = None, pos: dict[str, Any] | None = None
) -> Panel:
    """Performance metrics + equity sparkline + rolling analytics."""
    err_panel = _error_panel("performance", perf, "PERFORMANCE", border="green")
    if err_panel:
        return err_panel

    streak_val: int | Any = perf.get("streak") if perf.get("streak") is not None else 0
    streak = int(streak_val) if isinstance(streak_val, (int, float)) else 0
    str_s = f"+{streak}W" if streak >= 0 else f"{abs(streak)}L"
    str_c = G if streak >= 0 else R
    unrlzd = perf.get("unrealized_pnl")
    pnl_val_raw = perf.get("pnl")
    pnl_val = safe_float(pnl_val_raw, default=None)
    pnl_c = G if pnl_val is not None and pnl_val >= 0 else R
    pf = safe_float(perf.get("profit_factor"), default=None)
    pf_s = f"{pf:.2f}" if pf is not None else "--"
    pf_c = G if pf is not None and pf >= 1.5 else (Y if pf is not None and pf >= 1.0 else R)
    exp = safe_float(perf.get("expectancy"), default=None)
    exp_c = G if (exp is None or exp >= 0) else R
    exp_s = f"{exp:.2f}R" if exp is not None else "--"
    sharpe_v = perf.get("sharpe")
    sharpe_s = f"{sharpe_v:.2f}" if sharpe_v is not None else "--"

    wr_v, closed_wins, adj_l = _calculate_adjusted_win_rate(perf, pos)
    # closed_wins and adj_l are already validated by _calculate_adjusted_win_rate
    l_val = perf.get("l")
    closed_losses = int(l_val) if l_val is not None and isinstance(l_val, (int, float)) else 0
    losing_open = adj_l - closed_losses
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
    def cell(label: str, value_markup: str) -> Text:
        return Text.from_markup(f"[dim]{label}[/] {value_markup}")

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("left", ratio=1)
    tbl.add_column("right", ratio=1)

    grid_rows: list[tuple[Text, Text]] = []

    # P&L row
    pnl_s = f"[{pnl_c}]{fmt_money(perf.get('pnl'))}[/]"
    unrlzd_f = safe_float(unrlzd, default=None)
    if unrlzd_f is not None:
        unrlzd_s = f"[{G if unrlzd_f >= 0 else R}]{fmt_money(unrlzd)}[/]"
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

        # Explicit validation: total trade count required for display decisions
        if perf is None:
            total_trades = None
        else:
            total_trades = perf.get("n")
            if total_trades is None:
                logger.warning("Performance data missing 'n' (total trade count)")
                total_trades = None
            else:
                try:
                    total_trades = int(total_trades)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid total trade count in performance data: {total_trades}")
                    total_trades = None

        calmar_cell: Text | None = None
        wr50_cell: Text | None = None
        if calmar is not None and calmar != 0.0:
            cc = G if calmar >= 0.5 else (Y if calmar >= 0 else R)
            calmar_cell = cell("Calmar Ratio:", f"[{cc}]{calmar:.2f}[/]")
        if wr50 is not None and wr50 != 0.0 and ((total_trades is not None and total_trades >= 10) or wr50 > 0):
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

    rows: list[Any] = [header, tbl]

    # Equity curve sparkline
    equity_vals_val = perf.get("equity_vals")
    equity_vals = equity_vals_val if equity_vals_val is not None else []
    if len(equity_vals) >= 3:
        sp = sparkline(equity_vals, width=28)
        rows.append(Text.from_markup(f"[dim]Equity curve:[/] {sp}"))

    # Recent daily returns (last 5 snapshots)
    recent_rets_val = perf.get("recent_rets")
    recent_rets = recent_rets_val if recent_rets_val is not None else []
    if recent_rets:
        parts: list[str] = []
        for item in recent_rets[-5:]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                dt, ret = item[0], item[1]
            else:
                continue
            if ret is None:
                logger.debug("Return value is None in recent_rets, skipping display")
                continue
            ret = float(ret)
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
def panel_portfolio_perf_expanded(  # noqa: C901
    port: dict[str, Any],
    cfg: dict[str, Any] | None,
    risk: dict[str, Any] | None = None,
    perf: dict[str, Any] | None = None,
    perf_anl: dict[str, Any] | None = None,
    pos: dict[str, Any] | None = None,
) -> Panel:
    """Full-screen portfolio + performance deep dive — all metrics, risk, concentration."""
    rows: list[Any] = [
        Text.from_markup("[dim]press [/][bold green]f[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    # ── Portfolio snapshot ────────────────────────────────────────────────────
    if port and not port.get("_error"):
        pv_val: Any = port["total_portfolio_value"]
        cash_val: Any = port["total_cash"]
        npos_val: Any = port["position_count"]
        if pv_val is None:
            raise ValueError("Portfolio total_portfolio_value missing - cannot render snapshot")
        if cash_val is None:
            raise ValueError("Portfolio total_cash missing - cannot render snapshot")
        if npos_val is None:
            raise ValueError("Portfolio position_count missing - cannot render snapshot")
        pv = float(pv_val)
        cash = float(cash_val)
        npos = int(npos_val)
        dr_val: Any = port.get("daily_return_pct")
        urp_val: Any = port.get("unrealized_pnl_pct")
        cum_val: Any = port.get("cumulative_return_pct")
        mxdd_val: Any = port.get("max_drawdown_pct")
        lgpos_val: Any = port.get("largest_position_pct")
        dr = float(dr_val) if dr_val is not None else None
        urp = float(urp_val) if urp_val is not None else None
        cum = float(cum_val) if cum_val is not None else None
        mxdd = float(mxdd_val) if mxdd_val is not None else None
        lgpos = float(lgpos_val) if lgpos_val is not None else None
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
        max_n_val = cfg.get("max_pos_n") if cfg else None
        if max_n_val is None:
            slots_s = str(npos) if npos is not None else "--"
        else:
            max_n = int(max_n_val) if isinstance(max_n_val, (int, float)) else None
            if max_n is None:
                raise ValueError(f"max_pos_n config invalid type: {type(max_n_val).__name__}")
            slots_s = f"{npos}/{max_n}" if npos is not None else "--"
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
        n_val = perf.get("n")
        n = safe_int(n_val, strict=True, field_name="total_trades_n")
        w_val = perf.get("w")
        w = safe_int(w_val, strict=True, field_name="closed_wins_w")
        l_val = perf.get("l")
        closed_losses = safe_int(l_val, strict=True, field_name="closed_losses_l")
        streak_val = perf.get("streak")
        streak = safe_int(streak_val, 0, strict=True, field_name="win_streak")
        pnl_val = safe_float(perf.get("pnl"), default=None)
        unrlzd_pnl = safe_float(perf.get("unrealized_pnl"), default=None)
        open_cnt = safe_int(perf.get("open_count"), default=None)
        pf = safe_float(perf.get("profit_factor"), default=None)
        sharpe_v = safe_float(perf.get("sharpe"), default=None)
        exp = safe_float(perf.get("expectancy"), default=None)
        dd_val = perf.get("maxdd")
        if dd_val is None or not isinstance(dd_val, (int, float)):
            raise ValueError(f"Max drawdown value missing or invalid: {dd_val}")
        dd_v = float(dd_val)
        avg_win = perf.get("avg_win")
        avg_loss = perf.get("avg_loss")

        try:
            wr_v, _adj_w, adj_l = _calculate_adjusted_win_rate(perf, pos)
            if adj_l is None:
                raise ValueError("Adjusted loss count is None — cannot calculate open losing positions")
            if closed_losses is None:
                raise ValueError("Closed losses count is None — cannot calculate open losing positions")
            losing_open = adj_l - closed_losses
        except ValueError as e:
            logger.error(f"Win rate calculation failed: {e}")
            raise
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
        pnl_val_safe = pnl_val if pnl_val is not None else 0
        unrlzd_pnl_safe = unrlzd_pnl if unrlzd_pnl is not None else 0
        perfblk.add_row(
            "Total P&L:",
            Text(fmt_money(pnl_val), style=G if pnl_val_safe >= 0 else R),
            "Profit Factor:",
            Text(f"{pf:.2f}" if pf else "--", style=pf_c),
        )
        perfblk.add_row(
            "Unrealized P&L:",
            Text(
                fmt_money(unrlzd_pnl) if unrlzd_pnl is not None else "--",
                style=G if unrlzd_pnl_safe >= 0 else R,
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
        equity_vals_val = perf.get("equity_vals")
        equity_vals = equity_vals_val if equity_vals_val is not None else []
        if len(equity_vals) >= 3:
            sp = sparkline(equity_vals, width=50)
            rows.append(Text.from_markup(f"[dim]Equity curve:[/] {sp}"))

        # Recent daily returns
        recent_rets_val = perf.get("recent_rets")
        recent_rets = recent_rets_val if recent_rets_val is not None else []
        if recent_rets:
            from datetime import datetime

            parts: list[str] = []
            for item in recent_rets[-10:]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    dt, ret = item[0], item[1]
                else:
                    continue
                if ret is None:
                    logger.debug("Return value is None in recent_rets, skipping display")
                    continue
                ret = float(ret)
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
        sharpe252 = safe_float(perf_anl.get("sharpe252"), default=None)
        sortino = safe_float(perf_anl.get("sortino"), default=None)
        calmar = safe_float(perf_anl.get("calmar"), default=None)
        wr50 = safe_float(perf_anl.get("wr50"), default=None)
        avg_w_r = safe_float(perf_anl.get("avg_w_r"), default=None)
        avg_l_r = safe_float(perf_anl.get("avg_l_r"), default=None)
        exp2 = safe_float(perf_anl.get("expectancy"), default=None)
        maxdd2 = safe_float(perf_anl.get("maxdd"), default=None)
        anl.add_row(
            "Sharpe (252d):",
            Text(
                f"{sharpe252:.2f}" if sharpe252 is not None else "--",
                style=(G if (sharpe252 is not None and sharpe252 >= 1) else (Y if (sharpe252 is not None and sharpe252 >= 0) else R)),
            ),
            "Sortino:",
            Text(
                f"{sortino:.2f}" if sortino is not None else "--",
                style=G if (sortino is not None and sortino >= 1.5) else (Y if (sortino is not None and sortino >= 0) else R),
            ),
        )
        anl.add_row(
            "Calmar:",
            Text(
                f"{calmar:.2f}" if calmar is not None else "--",
                style=G if (calmar is not None and calmar >= 0.5) else (Y if (calmar is not None and calmar >= 0) else R),
            ),
            "Win Rate (50T):",
            Text(
                f"{wr50:.0f}%" if wr50 is not None else "--",
                style=G if (wr50 is not None and wr50 >= 50) else (Y if (wr50 is not None and wr50 >= 42) else R),
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
                Text(f"{exp2:.2f}R" if exp2 is not None else "--", style=G if (exp2 is not None and exp2 >= 0) else R),
                "Max Drawdown:",
                Text(
                    f"-{abs(maxdd2):.1f}%" if maxdd2 is not None else "--",
                    style=(R if (maxdd2 is not None and abs(maxdd2) >= 15) else (Y if (maxdd2 is not None and abs(maxdd2) >= 5) else G)),
                ),
            )
        rows.append(anl)
        rows.append(Rule(style="dim"))

    # ── Risk metrics ──────────────────────────────────────────────────────────
    var95_val = risk.get("var95") if risk and not risk.get("_error") else None
    if var95_val is not None:
        try:
            var95_f = float(var95_val)
            if var95_f > 0 and risk is not None:
                rows.append(Text.from_markup("[dim bold]RISK METRICS[/]"))
                rtbl = Table.grid(padding=(0, 3), expand=False)
                rtbl.add_column("label", style="dim")
                rtbl.add_column("val")
                rtbl.add_column("label2", style="dim")
                rtbl.add_column("val2")

                # Extract all risk metrics with explicit None checks
                # Mypy type narrowing: explicitly verify risk is not None
                risk_dict: dict[str, Any] = risk
                beta = safe_float(risk_dict.get("beta"), default=None)
                conc5 = safe_float(risk_dict.get("conc5"), default=None)
                cvar95 = safe_float(risk_dict.get("cvar95"), default=None)
                svar = safe_float(risk_dict.get("svar"), default=None)
                risk_date = risk_dict.get("date")

                var_c = R if var95_f >= 4 else (Y if var95_f >= 2 else "white")

                cvar_display = f"{cvar95:.2f}%" if cvar95 is not None else "N/A"
                cvar_style = var_c if cvar95 is not None else "dim"
                rtbl.add_row(
                    "VaR (95%):",
                    Text(f"{var95_f:.2f}%", style=var_c),
                    "CVaR (95%):",
                    Text(cvar_display, style=cvar_style),
                )

                beta_display = f"{beta:.2f}" if beta is not None else "N/A"
                beta_c = (
                    R
                    if (beta is not None and beta >= 1.2)
                    else (Y if (beta is not None and beta >= 0.8) else (G if beta is not None else "dim"))
                )
                conc_display = f"{conc5:.0f}%" if conc5 is not None else "N/A"
                conc_c = (
                    R
                    if (conc5 is not None and conc5 >= 35)
                    else (Y if (conc5 is not None and conc5 >= 25) else (G if conc5 is not None else "dim"))
                )

                rtbl.add_row(
                    "Portfolio Beta:",
                    Text(beta_display, style=beta_c),
                    "Top-5 Concentration:",
                    Text(conc_display, style=conc_c),
                )
                if svar is not None and svar > 0:
                    rtbl.add_row(
                        "Stressed VaR:",
                        Text(f"{svar:.2f}%", style=R),
                        "Risk Date:",
                        Text(str(risk_date or "--")[:10], style="dim"),
                    )
                rows.append(rtbl)
        except (ValueError, TypeError):
            logger.warning(f"Risk metrics conversion failed: var95={var95_val}")

    # ── Position concentration ─────────────────────────────────────────────────
    if pos:
        pos_items, _, _ = normalize_positions_data(pos)
        if pos_items:
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("[dim bold]POSITION CONCENTRATION[/]"))
            pv_total_val = port.get("total_portfolio_value") if port and not port.get("_error") else None
            if pv_total_val is None:
                rows.append(Text("[red]Portfolio value unavailable — cannot compute concentration[/]", style="dim"))
            else:
                pv_total = float(pv_total_val)
                if pv_total <= 0:
                    rows.append(Text("[red]Portfolio value must be positive for concentration calculation[/]", style="dim"))
                else:
                    conc_rows: list[tuple[float, Any, float | None, float | None]] = []
                    for p in pos_items:
                        if not isinstance(p, dict):
                            continue
                        symbol_val = p.get("symbol")
                        sym = symbol_val if symbol_val is not None else "--"
                        val_raw = p.get("position_value")
                        val = float(val_raw) if val_raw is not None else None
                        pnl_raw = p.get("unrealized_pnl_pct")
                        pnl = float(pnl_raw) if pnl_raw is not None else None
                        if val is None:
                            logger.warning(
                                f"[PORTFOLIO_PANEL] Position {sym} has NULL position_value in concentration calculation"
                            )
                            pct = None
                        elif pv_total <= 0:
                            logger.critical(
                                f"[PORTFOLIO_PANEL CRITICAL] Portfolio total value is invalid ({pv_total}) "
                                f"for concentration calculation of {sym}"
                            )
                            raise ValueError(
                                f"Portfolio concentration calculation failed: total portfolio value is invalid ({pv_total})"
                            )
                        else:
                            pct = val / pv_total * 100
                        if pct is None:
                            continue
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
                        pnl_safe = pnl if pnl is not None else 0
                        pc = G if pnl_safe >= 0 else R
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
