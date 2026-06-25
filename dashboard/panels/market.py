"""Market regime, internals, breadth, sentiment panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from rich.console import ConsoleRenderable, RichCast

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from panel_registry import register_panel as register_panel
else:
    try:
        from panel_registry import register_panel
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

from ..data_validation import safe_float, safe_int
from ..error_boundary import has_error
from ..formatters import (
    exp_bar,
    next_run_str,
    sign,
)
from ..utilities import (
    DIM,
    TIER_COLOR,
    TIER_SHORT,
    G,
    R,
    Y,
)
from ._helpers import _error_panel
from .data_extractors import (
    safe_get_list,
)


def _get_market_halts(mkt_data: dict[str, Any], panel_name: str) -> list[Any]:
    """Extract market halts with validation and logging.

    Args:
        mkt_data: Market data dict from endpoint
        panel_name: Panel name for logging context

    Returns:
        List of halts (empty list if missing/invalid)
    """
    halts_raw = mkt_data.get("halts")
    if halts_raw is None:
        logger.warning(f"{panel_name}: halts data missing from market endpoint")
        return []
    halts = safe_get_list(halts_raw) or []
    if not halts and halts_raw:
        logger.warning(f"{panel_name}: halts data failed validation, got: {halts_raw}")
    return halts


@register_panel(
    "market",
    endpoint_deps=["mkt", "sentiment"],
    optional=False,
    description="Market",
)
def panel_market_full(mkt: Any, sentiment: Any = None) -> Panel:
    """Market regime + internals combined."""
    err_panel = _error_panel("market", mkt, "MARKET", border="blue")
    if err_panel:
        return err_panel

    # Extract market fields in batch after error check
    tier = mkt.get("tier", "unknown")
    tc = TIER_COLOR.get(tier, "dim")
    lbl = TIER_SHORT.get(tier, "LOADING")
    exp = mkt.get("pct")
    vix = mkt.get("vix")
    spy_raw = mkt.get("spy")

    # Validate and convert critical fields to safe types
    vix = safe_float(vix, strict=False)
    spy_raw = safe_float(spy_raw, strict=False)
    if vix is None or spy_raw is None:
        return Panel(
            Text.from_markup(
                "[dim]Market data validation failed - critical fields missing (VIX or SPY).[/]\nCheck data loading status."
            ),
            title="[bold blue]MARKET (CRITICAL DATA MISSING)[/]",
            border_style="red",
            padding=(0, 1),
        )

    dist = mkt.get("dist", "N/A")
    stage = mkt.get("stage", "N/A")
    spy_chg = safe_float(mkt.get("spy_chg"), strict=False)
    trend = mkt.get("trend", "")
    halts = _get_market_halts(mkt, "Market panel")

    upvol = safe_float(mkt.get("upvol"), strict=False)
    adr = safe_float(mkt.get("adr"), strict=False)
    nh = safe_int(mkt.get("nh"), strict=False)
    nl = safe_int(mkt.get("nl"), strict=False)
    pcr = safe_float(mkt.get("pcr"), strict=False)
    bmom = safe_float(mkt.get("bmom"), strict=False)
    fed = mkt.get("fed")

    # Derived values from extracted fields (critical fields guaranteed non-None)
    exp_s = f"{float(exp):.0f}%" if exp is not None else "N/A"
    bar = exp_bar(exp or 0, w=10)
    vix_s = f"{vix:.1f}"
    vc = R if vix >= 30 else (Y if vix >= 20 else G)
    trend_s = trend.upper()
    halt_s = " ".join(str(h)[:16] for h in halts[:2]) if halts else "none"
    hc = Y if halts else DIM

    uvc = G if upvol is not None and upvol >= 60 else (Y if upvol is not None and upvol >= 50 else R)
    pcr_c = DIM if pcr is None else (G if pcr <= 0.8 else (Y if pcr <= 1.0 else R))
    nhnl = (nh - nl) if (nh is not None and nl is not None) else None
    nhnl_c = (
        (G if nhnl is not None and nhnl >= 50 else (Y if nhnl is not None and nhnl >= 0 else R))
        if nhnl is not None
        else DIM
    )

    spy_s = f"SPY:[white]${spy_raw:.2f}[/]"
    if spy_chg is not None:
        spy_chg_s = f" [{G if spy_chg >= 0 else R}]{sign(spy_chg)}{spy_chg:.1f}%[/]"
        spy_s += spy_chg_s

    lines = [
        f"[{tc}][bold]{lbl}[/]  [dim]exposure[/][{tc}]{exp_s}[/]  {bar}",
        f"VIX:[{vc}]{vix_s}[/]  [dim]Dist Days:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]"
        + (f"  [dim]Trend:[/][white]{trend_s}[/]" if trend else "")
        + f"  {spy_s}",
    ]
    if upvol is not None:
        adr_s = f"  [dim]Adv/Dec:[/][white]{adr:.1f}[/]" if adr is not None else ""
        nhnl_s = f"  [dim]NH-NL:[/][{nhnl_c}]{sign(nhnl)}{int(nhnl)}[/]" if nhnl is not None else ""
        lines.append(
            f"[dim]Up Volume:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  [dim]New Highs:[/][{G}]{nh or '--'!s}[/] [dim]Lows:[/][{R}]{nl or '--'!s}[/]{nhnl_s}"
        )
    ycs = safe_float(mkt.get("ycs"), strict=False)
    bmom_pcr = []
    if pcr is not None:
        bmom_pcr.append(f"[dim]Put/Call:[/][{pcr_c}]{pcr:.3f}[/]")
    else:
        bmom_pcr.append("[dim]Put/Call:[/][yellow]⚠ N/A[/]")
    if bmom is not None:
        bmc = G if bmom >= 0.5 else (Y if bmom >= 0 else R)
        bmom_pcr.append(f"[dim]Breadth Momentum:[/][{bmc}]{bmom:.2f}[/]")
    if ycs is not None:
        yc_c = G if ycs >= 0.5 else (Y if ycs >= 0 else R)
        bmom_pcr.append(f"[dim]Yield Curve Slope:[/][{yc_c}]{ycs:+.2f}[/]")
    if bmom_pcr:
        lines.append("  ".join(bmom_pcr))
    halt_fed = f"[dim]Trading Halt:[/][{hc}]{halt_s}[/]"
    if fed and str(fed).lower() not in ("unknown", "n/a", "none", ""):
        halt_fed += f"  [dim]Fed Environment:[/][white]{fed[:20]}[/]"
    lines.append(halt_fed)

    # Fear & Greed
    if sentiment and not has_error(sentiment):
        fg_v = sentiment.get("fg")
        if fg_v is not None:
            fg_lbl = (sentiment.get("label", ""))[:16]
            fg_c = sentiment.get("color", "dim")
            fg_bar = int(fg_v / 100 * 8)
            fg_bar_s = f"[{fg_c}]{'█' * fg_bar}[/][dim]{'░' * (8 - fg_bar)}[/]"
            lines.append(f"[dim]Fear & Greed:[/][{fg_c}]{fg_v:.0f}%  {fg_lbl}[/] {fg_bar_s}")

    txt = Text.from_markup("\n".join(lines))
    return Panel(txt, title="[bold blue]MARKET[/]", border_style="blue", padding=(0, 1))


@register_panel(
    "market_expanded",
    endpoint_deps=["mkt", "sentiment"],
    optional=False,
    description="Market Expanded",
)
def panel_market_expanded(mkt: Any, sentiment: Any = None) -> Panel:
    """Full-screen market internals — regime, breadth, sentiment, macro."""
    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold blue]m[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]
    err_panel = _error_panel("market", mkt, "MARKET - EXPANDED", border="blue")
    if err_panel:
        return err_panel

    tier = mkt.get("tier", "unknown")
    tc = TIER_COLOR.get(tier, "dim")
    lbl = TIER_SHORT.get(tier, "LOADING")
    exp = mkt.get("pct")
    exp_s = f"{float(exp):.0f}%" if exp is not None else "--"
    bar = exp_bar(exp or 0, w=14)
    vix_raw = mkt.get("vix")
    vix = safe_float(vix_raw, strict=False)
    vc = DIM if vix is None else (R if vix >= 30 else (Y if vix >= 20 else G))
    vix_s = f"{vix:.1f}" if vix is not None else "--"
    rows.append(
        Text.from_markup(
            f"[{tc}][bold]{lbl}[/]  [dim]Exposure:[/][{tc}]{exp_s}[/]  {bar}  [dim]VIX:[/][{vc}]{vix_s}[/]"
        )
    )
    rows.append(Rule(style="dim"))

    spy_raw = safe_float(mkt.get("spy"), strict=False)
    spy_chg = safe_float(mkt.get("spy_chg"), strict=False)
    stage = str(mkt.get("stage", "--"))
    trend = (mkt.get("trend", "")).upper() or "--"
    dist = safe_float(mkt.get("dist"), strict=False)
    _fed_raw = mkt.get("fed")
    fed = "--" if (_fed_raw is None or str(_fed_raw).lower() in ("unknown", "n/a", "none", "")) else str(_fed_raw)
    ycs = safe_float(mkt.get("ycs"), strict=False)
    upvol = safe_float(mkt.get("upvol"), strict=False)
    adr = safe_float(mkt.get("adr"), strict=False)
    nh = safe_int(mkt.get("nh"), strict=False)
    nl = safe_int(mkt.get("nl"), strict=False)
    pcr = safe_float(mkt.get("pcr"), strict=False)
    bmom = safe_float(mkt.get("bmom"), strict=False)
    halts = _get_market_halts(mkt, "Market summary panel")

    spy_s = f"${spy_raw:.2f}" if spy_raw else "--"
    spy_chg_safe = spy_chg if spy_chg is not None else 0
    spy_chg_c = G if spy_chg_safe >= 0 else R
    spy_chg_s = f"{sign(spy_chg)}{spy_chg:.2f}%" if spy_chg is not None else "--"
    dist_safe = dist if dist is not None else 0
    dist_c = R if dist_safe >= 5 else (Y if dist_safe >= 3 else G)
    dist_s = f"{dist} days" if dist is not None else "--"
    ycs_safe = ycs if ycs is not None else 0
    yc_c = G if ycs_safe >= 0.5 else (Y if ycs_safe >= 0 else R)
    yc_s = f"{ycs:+.3f}" if ycs is not None else "--"
    uvc = DIM if upvol is None else (G if upvol >= 60 else (Y if upvol >= 50 else R))
    upvol_s = f"{upvol:.1f}%" if upvol is not None else "--"
    adr_s = f"{adr:.2f}" if adr is not None else "--"
    nh_s = str(nh) if nh is not None else "--"
    nl_s = str(nl) if nl is not None else "--"
    nhnl = (nh - nl) if (nh is not None and nl is not None) else None
    nhnl_safe = nhnl if nhnl is not None else 0
    nhnl_c = (G if nhnl_safe >= 50 else (Y if nhnl_safe >= 0 else R)) if nhnl is not None else DIM
    nhnl_s = f"{sign(nhnl)}{nhnl}" if nhnl is not None else "--"
    bmc = DIM if bmom is None else (G if bmom >= 0.5 else (Y if bmom >= 0 else R))
    bmom_s = f"{bmom:.3f}" if bmom is not None else "--"
    pcr_c = DIM if pcr is None else (G if pcr <= 0.8 else (Y if pcr <= 1.0 else R))
    pcr_s = f"{pcr:.3f}" if pcr is not None else "⚠ N/A"

    grid = Table.grid(padding=(0, 4), expand=True)
    grid.add_column("left", ratio=1)
    grid.add_column("right", ratio=1)

    left = [
        Text.from_markup("[dim bold]PRICE & REGIME[/]"),
        Text.from_markup(f"  [dim]SPY Price:[/]       [white]{spy_s}[/]"),
        Text.from_markup(f"  [dim]SPY Change:[/]      [{spy_chg_c}]{spy_chg_s}[/]"),
        Text.from_markup(f"  [dim]VIX Level:[/]       [{vc}]{vix_s}[/]"),
        Text.from_markup(f"  [dim]Market Stage:[/]    [white]{stage}[/]"),
        Text.from_markup(f"  [dim]Market Trend:[/]    [white]{trend}[/]"),
        Text.from_markup(f"  [dim]Distribution:[/]    [{dist_c}]{dist_s}[/]"),
        Text(""),
        Text.from_markup("[dim bold]MACRO & FED[/]"),
        Text.from_markup(f"  [dim]Yield Curve:[/]     [{yc_c}]{yc_s}[/]"),
        Text.from_markup(f"  [dim]Fed Environment:[/] [white]{fed[:28]}[/]"),
    ]

    right = [
        Text.from_markup("[dim bold]BREADTH & INTERNALS[/]"),
        Text.from_markup(f"  [dim]Up Volume:[/]       [{uvc}]{upvol_s}[/]"),
        Text.from_markup(f"  [dim]Adv/Dec Ratio:[/]   [white]{adr_s}[/]"),
        Text.from_markup(f"  [dim]New Highs:[/]       [{G}]{nh_s}[/]"),
        Text.from_markup(f"  [dim]New Lows:[/]        [{R}]{nl_s}[/]"),
        Text.from_markup(f"  [dim]NH-NL Net:[/]       [{nhnl_c}]{nhnl_s}[/]"),
        Text.from_markup(f"  [dim]Breadth Momentum:[/][{bmc}]{bmom_s}[/]"),
        Text(""),
        Text.from_markup("[dim bold]OPTIONS & SENTIMENT[/]"),
        Text.from_markup(f"  [dim]Put/Call Ratio:[/]  [{pcr_c}]{pcr_s}[/]"),
        Text(""),
    ]

    for left_item, right_item in zip(left, right, strict=False):
        grid.add_row(left_item, right_item)
    rows.append(grid)

    if sentiment and not has_error(sentiment):
        fg_v = sentiment.get("fg")
        if fg_v is not None:
            rows.append(Rule(style="dim"))
            fg_lbl = (sentiment.get("label", ""))[:22]
            fg_c = sentiment.get("color", "dim")
            fg_bar_f = int(fg_v / 100 * 24)
            fg_bar_s = f"[{fg_c}]{'█' * fg_bar_f}[/][dim]{'░' * (24 - fg_bar_f)}[/]"
            rows.append(Text.from_markup(f"  [dim]Fear & Greed:[/]  [{fg_c}]{fg_v:.0f}  {fg_lbl}[/]  {fg_bar_s}"))

    rows.append(Rule(style="dim"))
    hc = Y if halts else G
    halt_s = "  |  ".join(str(h)[:35] for h in halts[:3]) if halts else "none"
    rows.append(Text.from_markup(f"  [dim]Trading Halt:[/] [{hc}]{halt_s}[/]"))

    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title="[bold blue]MARKET - EXPANDED[/]  [dim][m] return[/]",
        border_style="blue",
        padding=(0, 1),
    )


@register_panel("header", endpoint_deps=["mkt", "sentiment"], optional=False, description="Header")
def panel_header_market(
    mkt: Any,
    sentiment: Any,
    ts: Any,
    mkt_s: Any,
    elapsed: Any,
    refresh_s: str = "",
    cfg: Any = None,
    data_source: str = "AWS",
) -> Panel:
    """Compact market header - fits alongside exposure factors + monkey in the top row."""
    source_color = "cyan" if data_source == "LOCAL" else "dim"
    rows: list[Text | Rule] = [
        Text.from_markup(f"{mkt_s}  [dim]{ts}[/]  [dim]{elapsed:.1f}s[/]{refresh_s}  [{source_color}]{data_source}[/]")
    ]
    if mkt and not has_error(mkt):
        tier = mkt.get("tier", "unknown")
        tc = TIER_COLOR.get(tier, "dim")
        lbl = TIER_SHORT.get(tier, "LOADING")
        exp = mkt.get("pct")
        exp_s = f"{float(exp):.0f}%" if exp is not None else "--"
        bar = exp_bar(exp or 0, w=8)
        vix_val = safe_float(mkt.get("vix"), strict=False)
        vix = f"{vix_val:.1f}" if vix_val is not None else "--"
        vc = DIM if vix_val is None else (R if vix_val >= 30 else (Y if vix_val >= 20 else G))
        dist = str(mkt.get("dist", "--"))
        stage = str(mkt.get("stage", "--"))
        trend_raw = (mkt.get("trend", "")).upper()
        trend_s = f"  [dim]Trend:[/][white]{trend_raw[:10]}[/]" if trend_raw else ""
        spy_raw = safe_float(mkt.get("spy"), strict=False)
        spy_chg = safe_float(mkt.get("spy_chg"), strict=False)
        spy_chg_safe = spy_chg if spy_chg is not None else 0
        spy_chg_s = (
            f" [{G if spy_chg_safe >= 0 else R}]{sign(spy_chg_safe)}{spy_chg:.1f}%[/]" if spy_chg is not None else ""
        )
        spy_s = f"  SPY:[white]${spy_raw:.2f}[/]{spy_chg_s}" if spy_raw else ""
        rows.append(
            Text.from_markup(
                f"[{tc}][bold]{lbl}[/]  [dim]Exp:[/][{tc}]{exp_s}[/]{bar}  "
                f"VIX:[{vc}]{vix}[/]  [dim]Dist. Days:[/][white]{dist}[/]  [dim]Stage:[/][white]{stage}[/]{trend_s}{spy_s}"
            )
        )
        upvol = safe_float(mkt.get("upvol"), strict=False)
        nh = safe_int(mkt.get("nh"), strict=False)
        nl = safe_int(mkt.get("nl"), strict=False)
        adr = safe_float(mkt.get("adr"), strict=False)
        if upvol is not None:
            uvc = G if upvol >= 60 else (Y if upvol >= 50 else R)
            nhnl = (nh - nl) if (nh is not None and nl is not None) else None
            nhnl_safe = nhnl if nhnl is not None else 0
            nhnl_c = (G if nhnl_safe >= 50 else (Y if nhnl_safe >= 0 else R)) if nhnl is not None else DIM
            adr_s = f"  [dim]Adv/Dec:[/][white]{adr:.1f}[/]" if adr is not None else ""
            nhnl_s = (
                f"[dim]New Hi-Lo:[/][{nhnl_c}]{sign(nhnl_safe)}{int(nhnl_safe)}[/]"
                if nhnl is not None
                else "[dim]New Hi-Lo: --[/]"
            )
            rows.append(
                Text.from_markup(
                    f"[dim]Up Volume:[/][{uvc}]{upvol:.0f}%[/]{adr_s}  "
                    f"[dim]New High:[/][{G}]{nh or '--'!s}[/] [dim]New Low:[/][{R}]{nl or '--'!s}[/]  "
                    f"{nhnl_s}"
                )
            )
        pcr = safe_float(mkt.get("pcr"), strict=False)
        bmom = safe_float(mkt.get("bmom"), strict=False)
        ycs = safe_float(mkt.get("ycs"), strict=False)
        fed = mkt.get("fed")
        _fed_ok = fed and str(fed).lower() not in ("unknown", "n/a", "none", "")
        parts4 = []
        if pcr is not None:
            pcr_c = G if pcr <= 0.8 else (Y if pcr <= 1.0 else R)
            parts4.append(f"[dim]Put/Call:[/][{pcr_c}]{pcr:.3f}[/]")
        else:
            parts4.append("[dim]Put/Call:[/][yellow]⚠ N/A[/]")
        if bmom is not None:
            bmc = G if bmom >= 0.5 else (Y if bmom >= 0 else R)
            parts4.append(f"[dim]Breadth Mom:[/][{bmc}]{bmom:.2f}[/]")
        else:
            parts4.append("[dim]Breadth Mom:[/][dim]--[/]")
        if ycs is not None:
            yc_c = G if ycs >= 0.5 else (Y if ycs >= 0 else R)
            parts4.append(f"[dim]Yield Curve:[/][{yc_c}]{ycs:+.2f}[/]")
        if parts4:
            rows.append(Text.from_markup("  ".join(parts4)))
        halts = _get_market_halts(mkt, "Market details panel")
        halt_s = " ".join(str(h)[:14] for h in halts[:2]) if halts else "none"
        hc_col = Y if halts else DIM
        line5 = f"[dim]Halt:[/][{hc_col}]{halt_s}[/]"
        if _fed_ok:
            line5 += f"  [dim]Fed:[/][white]{str(fed)[:18]}[/]"
        if sentiment and not has_error(sentiment):
            fg_v = sentiment.get("fg")
            if fg_v is not None:
                fg_lbl_raw = sentiment.get("label")
                fg_lbl = (fg_lbl_raw if fg_lbl_raw is not None else "")[:14]
                fg_c = sentiment.get("color")
                if fg_c is None:
                    fg_c = "dim"
                fg_bar = int(fg_v / 100 * 6)
                fg_bar_s = f"[{fg_c}]{'█' * fg_bar}[/][dim]{'░' * (6 - fg_bar)}[/]"
                line5 += f"  [dim]Fear/Greed:[/][{fg_c}]{fg_v:.0f}%  {fg_lbl}[/] {fg_bar_s}"
        rows.append(Text.from_markup(line5))
        if cfg:
            mode = cfg.get("mode")
            if mode is None:
                mode = "?"
            mc2 = G if "LIVE" in str(mode) else Y
            enabled = cfg.get("enabled")
            if enabled is None:
                enabled = True
            en_s = "ENABLED" if enabled else "DISABLED"
            ec = G if enabled else R
            min_score = cfg.get("min_score")
            max_n = cfg.get("max_pos_n")
            max_sec = cfg.get("max_sec_n")
            base_risk = cfg.get("base_risk")
            t1r = cfg.get("t1_r")
            parts6 = [f"[{mc2}]{mode}[/]", f"[{ec}]{en_s}[/]"]
            if min_score:
                parts6.append(f"[dim]score≥[/][white]{float(min_score):.0f}[/]")
            if max_n:
                parts6.append(f"[dim]slots:[/][white]{max_n}[/]")
            if max_sec:
                parts6.append(f"[dim]sec≤[/][white]{max_sec}[/]")
            if base_risk:
                parts6.append(f"[dim]risk:[/][white]{base_risk}%[/]")
            if t1r:
                parts6.append(f"[dim]T1:[/][white]{t1r}R[/]")
            parts6.append(f"[dim]next run:[/][white]{next_run_str()}[/]")
            rows.append(Rule(style="dim"))
            rows.append(Text.from_markup("  ".join(parts6)))
    else:
        rows.append(Text("no market data", style="dim"))
    return Panel(
        Group(*rows),
        title="[bold blue]MARKET[/]  [dim][m] expand[/]",
        border_style="blue",
        padding=(0, 1),
    )


__all__ = [
    "panel_header_market",
    "panel_market_expanded",
    "panel_market_full",
]
