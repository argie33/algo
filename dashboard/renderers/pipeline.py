"""Core rendering pipeline for dashboard."""

import time
import traceback
from datetime import datetime
from typing import Any

from rich.console import Group
from rich.layout import Layout
from rich.markup import escape as _escape_markup
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from dashboard.core import DashboardContext
from dashboard.error_boundary import (
    error_summary_panel_expanded,
    has_error,
)
from dashboard.formatters import mkt_hours_str
from dashboard.panels import (
    _expanded_layout,
    panel_algo_health,
    panel_algo_health_expanded,
    panel_circuit,
    panel_circuit_expanded,
    panel_economic_expanded,
    panel_economic_pulse,
    panel_exposure_compact,
    panel_exposure_expanded,
    panel_header_market,
    panel_market_expanded,
    panel_performance_spark,
    panel_portfolio,
    panel_portfolio_perf_expanded,
    panel_positions,
    panel_recent_trades,
    panel_sector_compact,
    panel_sectors_expanded,
    panel_signals_compact,
    panel_signals_expanded,
    panel_trades_expanded,
)
from dashboard.utilities import ET, logger


def render_error_panel(e: Exception, recovery_status: str | None = None) -> Panel:
    logger.error(f"Dashboard render error: {type(e).__name__}: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")

    error_line = _escape_markup(f"{type(e).__name__}: {str(e)[:80]}")
    if recovery_status:
        content = f"[bold red]⚠  Render Error[/]\n[dim]{error_line}[/]\n\n{recovery_status}"
    else:
        content = f"[bold red]⚠  Render Error[/]\n[dim]{error_line}[/]"

    return Panel(
        Text.from_markup(content),
        title="[bold red]ERROR[/]",
        border_style="red",
    )


def check_auth_lost() -> Panel | None:
    """Check if authentication was lost and return error panel if needed.

    Returns:
        Panel: Error panel if authentication has been lost
        None: If authentication is still valid (no error panel needed)
    """
    from dashboard.api_data_layer import get_cognito_auth

    auth = get_cognito_auth()
    if auth and auth.has_lost_authentication():
        content = (
            "[bold red]Authentication Lost[/]\n"
            "[dim]Token refresh failed - please re-authenticate[/]\n\n"
            "[yellow]To continue:[/]\n"
            "[dim]• Restart the dashboard\n"
            "• Or set COGNITO_USERNAME + COGNITO_PASSWORD environment variables\n"
            "• Then run the dashboard again[/]"
        )
        return Panel(
            Text.from_markup(content),
            title="[bold red]RE-AUTHENTICATION REQUIRED[/]",
            border_style="red",
        )
    logger.debug("[RENDERER] Authentication status check passed - no auth error panel needed (auth_valid)")
    return None


def render_header_components(
    ctx: DashboardContext,
    elapsed: float,
    watch_interval: int | None,
    last_load_time: float | None,
    refreshing: bool,
    data_source: str,
) -> tuple[Panel, Panel]:
    """Render header and exposure panels."""
    now_et = datetime.now(ET)
    _mkt_badge, _mkt_cdown = mkt_hours_str()
    mkt_s = f"{_mkt_badge}  [dim]{_mkt_cdown}[/]"
    ts = now_et.strftime("%a %b %d  %I:%M %p ET")

    refresh_s = ""
    if refreshing:
        refresh_s = "  [cyan]↻[/]"
    elif watch_interval is not None and last_load_time is not None:
        secs = max(0, watch_interval - int(time.monotonic() - last_load_time))
        refresh_s = f"  [dim]↻{secs}s[/]"

    if has_error(ctx.mkt) or has_error(ctx.cfg):
        error_msg = "[red]Market/Config Error - Dashboard data unavailable[/]"

        hdr_panel = Panel(
            Text.from_markup(error_msg),
            title="[bold red]✗ Data Error[/]",
            border_style="red",
        )
    else:
        hdr_panel = panel_header_market(
            ctx.mkt,
            ctx.sentiment,
            ts,
            mkt_s,
            elapsed,
            refresh_s,
            cfg=ctx.cfg,
            data_source=data_source,
        )

    exp_panel = (
        panel_exposure_compact(ctx.exp_factors)
        if not has_error(ctx.exp_factors)
        else Panel("[red]Exposure factors unavailable[/]")
    )
    return hdr_panel, exp_panel


def render_dashboard_body(outer: Layout, ctx: DashboardContext, compact: bool) -> None:
    """Render main dashboard body layout."""

    def safe_render(panel_fn: Any, *args: Any, **kwargs: Any) -> Panel:
        try:
            result = panel_fn(*args, **kwargs)
            if isinstance(result, Panel):
                return result
            return Panel(str(result))
        except Exception as e:
            return Panel(
                Text.from_markup(f"[red]Panel rendering failed[/]: {type(e).__name__}\n[dim]{str(e)[:80]}[/]"),
                title="[bold red]ERROR[/]",
                border_style="red",
                padding=(0, 1),
            )

    cb_panel = (
        safe_render(panel_circuit, ctx.cb)
        if not has_error(ctx.cb)
        else Panel("[red]Circuit breakers unavailable[/]", border_style="red")
    )
    health_panel = (
        safe_render(
            panel_algo_health,
            ctx.run,
            ctx.activity,
            ctx.health,
            ctx.notifs,
            ctx.algo_metrics,
            ctx.audit,
            ctx.exec_hist,
            risk=ctx.risk,
        )
        if not (has_error(ctx.run) or has_error(ctx.health))
        else Panel("[red]Health data unavailable[/]", border_style="red")
    )

    outer["r1"].split_row(
        Layout(cb_panel, ratio=3, name="cb"),
        Layout(health_panel, ratio=5, name="health"),
    )

    port_panel = (
        safe_render(panel_portfolio, ctx.port, ctx.cfg, risk=ctx.risk, perf=ctx.perf)
        if not (has_error(ctx.port) or has_error(ctx.cfg))
        else Panel("[red]Portfolio data unavailable[/]", border_style="red")
    )
    perf_panel = (
        safe_render(panel_performance_spark, ctx.perf, ctx.trades, ctx.perf_anl, pos=ctx.pos)
        if not (has_error(ctx.perf) or has_error(ctx.trades))
        else Panel("[red]Performance unavailable[/]", border_style="red")
    )
    eco_panel = (
        safe_render(panel_economic_pulse, ctx.eco, ctx.econ_cal)
        if not has_error(ctx.eco)
        else Panel("[red]Economic data unavailable[/]", border_style="red")
    )

    outer["r2"].split_row(
        Layout(port_panel, name="portfolio"),
        Layout(perf_panel, name="perf"),
        Layout(eco_panel, name="eco"),
    )

    sig_panel = (
        safe_render(panel_signals_compact, ctx.sig, ctx.sig_eval, scores=ctx.scores)
        if not has_error(ctx.sig)
        else Panel("[red]Signals unavailable[/]", border_style="red")
    )
    sector_panel = (
        safe_render(panel_sector_compact, ctx.srank, ctx.pos, ctx.port, ctx.sec_rot, ctx.irank)
        if not (has_error(ctx.srank) or has_error(ctx.pos) or has_error(ctx.port))
        else Panel("[red]Sector data unavailable[/]", border_style="red")
    )

    outer["r3"].split_row(
        Layout(sig_panel, ratio=3, name="signals"),
        Layout(sector_panel, ratio=2, name="sectors"),
    )

    pos_panel = (
        safe_render(panel_positions, ctx.pos, compact, trades=ctx.trades)
        if not (has_error(ctx.pos) or has_error(ctx.trades))
        else Panel("[red]Positions unavailable[/]", border_style="red")
    )
    trades_panel = (
        safe_render(panel_recent_trades, ctx.trades)
        if not has_error(ctx.trades)
        else Panel("[red]Recent trades unavailable[/]", border_style="red")
    )

    outer["pos"].split_row(
        Layout(pos_panel, ratio=5, name="positions"),
        Layout(trades_panel, ratio=3, name="recent_trades"),
    )


def render_expanded_view(  # noqa: C901
    view_mode: str, ctx: DashboardContext, hdr_panel: Panel, exp_panel: Panel, mascot_panel: Panel, compact: bool
) -> Layout | None:
    """Render expanded detail view for given mode."""
    if view_mode == "normal":
        logger.debug(
            "[RENDERER] Expanded view mode is 'normal' - using normal dashboard layout (no expanded view needed)"
        )
        return None

    _exp_top = (hdr_panel, exp_panel, mascot_panel)

    match view_mode:
        case "circuit":
            if has_error(ctx.cb):
                return _expanded_layout(
                    *_exp_top, Panel("[red]Circuit breaker data unavailable[/]", border_style="red")
                )
            return _expanded_layout(*_exp_top, panel_circuit_expanded(ctx.cb))
        case "exposure":
            if has_error(ctx.exp_factors):
                return _expanded_layout(*_exp_top, Panel("[red]Exposure factors unavailable[/]", border_style="red"))
            return _expanded_layout(*_exp_top, panel_exposure_expanded(ctx.exp_factors))
        case "market":
            if has_error(ctx.mkt):
                return _expanded_layout(*_exp_top, Panel("[red]Market data unavailable[/]", border_style="red"))
            return _expanded_layout(*_exp_top, panel_market_expanded(ctx.mkt, ctx.sentiment))
        case "positions":
            if has_error(ctx.pos):
                return _expanded_layout(*_exp_top, Panel("[red]Positions data unavailable[/]", border_style="red"))
            if isinstance(ctx.pos, list):
                _pos_items = ctx.pos
            elif isinstance(ctx.pos, dict) and "items" in ctx.pos:
                _pos_items = ctx.pos["items"]
            else:
                return _expanded_layout(
                    *_exp_top, Panel("[red]Positions data structure invalid[/]", border_style="red")
                )
            hint = Text.from_markup("[dim]press [/][bold cyan]p[/][dim] to return to dashboard[/]")
            pos_panel = panel_positions(ctx.pos, compact=False, trades=ctx.trades, extended=True)
            return _expanded_layout(
                *_exp_top,
                Panel(
                    Group(
                        hint,
                        Rule(style="dim"),
                        pos_panel,
                    ),
                    title=f"{pos_panel.title}  [dim][p] return[/]",
                    border_style="cyan",
                    padding=(0, 1),
                ),
            )
        case "signals":
            sig_panel = panel_signals_expanded(ctx.sig, ctx.sig_eval, scores=ctx.scores)
            if sig_panel is None:
                return _expanded_layout(*_exp_top, Panel("[red]Signals panel unavailable[/]", border_style="red"))
            return _expanded_layout(*_exp_top, sig_panel)
        case "health":
            if has_error(ctx.run) or has_error(ctx.health):
                return _expanded_layout(*_exp_top, Panel("[red]Health data unavailable[/]", border_style="red"))
            return panel_algo_health_expanded(
                ctx.run, ctx.activity, ctx.health, ctx.notifs, ctx.algo_metrics, ctx.audit, ctx.exec_hist, risk=ctx.risk
            )
        case "sectors":
            return _expanded_layout(
                *_exp_top, panel_sectors_expanded(ctx.srank, ctx.pos, ctx.port, ctx.sec_rot, ctx.irank)
            )
        case "trades":
            if has_error(ctx.trades):
                return _expanded_layout(*_exp_top, Panel("[red]Trade history unavailable[/]", border_style="red"))
            return _expanded_layout(*_exp_top, panel_trades_expanded(ctx.trades))
        case "economic":
            if has_error(ctx.eco):
                return _expanded_layout(*_exp_top, Panel("[red]Economic data unavailable[/]", border_style="red"))
            return _expanded_layout(*_exp_top, panel_economic_expanded(ctx.eco, ctx.econ_cal))
        case "portfolio":
            return _expanded_layout(
                *_exp_top,
                panel_portfolio_perf_expanded(
                    ctx.port, ctx.cfg, risk=ctx.risk, perf=ctx.perf, perf_anl=ctx.perf_anl, pos=ctx.pos
                ),
            )
        case "errors":
            error_panel_exp = error_summary_panel_expanded(ctx.data)
            if error_panel_exp:
                return _expanded_layout(*_exp_top, error_panel_exp)
            logger.warning("Error summary panel not available for expanded view")
            return _expanded_layout(*_exp_top, Panel("[red]Error data unavailable[/]", border_style="red"))

    logger.warning(f"Unmatched expanded view mode: {view_mode}")
    return _expanded_layout(*_exp_top, Panel(f"[red]Unknown view mode: {view_mode}[/]", border_style="red"))
