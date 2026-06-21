"""Portfolio exposure and risk factor panel functions."""

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


from ..formatters import (
    mini_bar,
    tier_from_pct,
)
from ..utilities import (
    TIER_COLOR,
    G,
    R,
    Y,
)
from ._helpers import _error_panel


@register_panel(
    "exp",
    endpoint_deps=["exp"],
    optional=True,
    description="Exposure",
)
def panel_exposure_compact(exp_f):
    """Exposure score breakdown - compact 2-col layout."""
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE FACTORS", border="blue")
    if err_panel:
        return err_panel
    raw = safe_float(exp_f.get("raw_score"), default=None)
    epct = safe_float(exp_f.get("exposure_pct"), default=None)
    regime = exp_f.get("regime", "")
    factors = exp_f.get("factors", {})
    tier = tier_from_pct(epct)
    tc = TIER_COLOR.get(tier, "dim")

    def factor_detail(key):
        """Return a short value string for a factor key."""
        if not factors or key not in factors:
            return ""
        f = factors[key]
        if not isinstance(f, dict):
            return ""
        if key == "trend_30wk":
            v = f.get("price_vs_ma_pct")
            return f" {'+' if v is not None and v >= 0 else ''}{v:.1f}%" if v is not None else ""
        if key == "breadth_50dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else ""
        if key == "breadth_200dma":
            v = f.get("value")
            return f" {v:.0f}%" if v is not None else ""
        if key == "spy_momentum":
            v = f.get("value")
            return f" {v:+.1f}%" if v is not None else ""
        if key == "put_call_ratio":
            v = f.get("value")
            if v is not None:
                return f" {v:.2f}"
            return " [yellow]⚠[/]" if f.get("reason") else ""
        if key == "vix_regime":
            v = f.get("value")
            return f" {v:.1f}" if v is not None else ""
        if key == "new_highs_lows":
            nh = f.get("new_highs")
            nl = f.get("new_lows")
            if nh is not None and nl is not None:
                net = nh - nl
                return f" {'+' if net >= 0 else ''}{net}"
            return ""
        if key == "credit_spread":
            v = f.get("value")
            return f" {v:.2f}" if v is not None else ""
        if key == "ad_line":
            rel = (f.get("relation", "")).replace("_", " ")[:8]
            return f" {rel}" if rel else ""
        if key == "aaii_sentiment":
            bull = f.get("bullish_pct")
            bear = f.get("bearish_pct")
            return f" B:{bull:.0f}/Be:{bear:.0f}" if bull is not None and bear is not None else ""
        if key == "naaim":
            v = f.get("value")
            return f" {v:.0f}" if v is not None else ""
        if key == "distribution_days":
            cnt = f.get("count")
            regime = (f.get("regime", ""))[:5]
            return f" {cnt}d/{regime}" if cnt is not None else ""
        return ""

    factor_map = [
        ("trend_30wk", "30-Week Trend", 15),
        ("spy_momentum", "SPY 12mo Mom", 10),
        ("breadth_200dma", "Breadth 200MA", 10),
        ("distribution_days", "Sell Pressure", 10),
        ("vix_regime", "VIX Regime", 10),
        ("credit_spread", "Credit Spread", 10),
        ("put_call_ratio", "Put/Call", 8),
        ("new_highs_lows", "New Hi vs Lo", 7),
        ("ad_line", "Adv/Dec Line", 6),
        ("breadth_50dma", "Breadth 50 MA", 6),
        ("naaim", "NAAIM Alloc", 5),
        ("aaii_sentiment", "AAII Survey", 3),
    ]

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)

    items = []
    for key, label, max_pts in factor_map:
        if not factors or key not in factors:
            f = {}
        else:
            f = factors[key]
            if not isinstance(f, dict):
                f = {}
        sf = f.get("score_factor")
        if sf is None:
            items.append(f"[dim]{label}:[/] [yellow]⚠ N/A[/][dim] /{max_pts}[/]")
        else:
            pts_raw = f.get("pts")
            pts = float(pts_raw) if pts_raw is not None else 0.0
            bar = mini_bar(pts, max_pts, w=4)
            fc = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
            det = factor_detail(key)
            det_s = f" [dim]{det.strip()}[/]" if det else ""
            items.append(f"[dim]{label}:[/] {bar} [{fc}]{pts:.0f}/{max_pts}[/]{det_s}")

    sr = None
    eco = None
    if factors and isinstance(factors, dict):
        sr_raw = factors.get("sector_rotation")
        if isinstance(sr_raw, dict):
            sr = sr_raw
        eco_raw = factors.get("economic_overlay")
        if isinstance(eco_raw, dict):
            eco = eco_raw

    sr_pen = safe_float(sr.get("pts") if sr else None, default=0)
    eco_pen = safe_float(eco.get("pts") if eco else None, default=0)
    if sr_pen < 0 and sr:
        sig = (sr.get("signal", "")).replace("_", " ")[:18]
        items.append(f"[dim]Sector Rotation:[/] [{R}]{sr_pen:+.0f}[/] [dim]{sig}[/]")
    if eco_pen < 0 and eco:
        eco_err = (eco.get("error", ""))[:18]
        items.append(f"[dim]Economic Overlay:[/] [{R}]{eco_pen:+.0f}[/]" + (f" [dim]{eco_err}[/]" if eco_err else ""))

    for a, b in zip(items[::2], [*items[1::2], ""], strict=False):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    raw_bar = mini_bar(raw if raw is not None else 0, 100, w=8)
    raw_s = f"{raw:.0f}" if raw is not None else "--"
    epct_s = f"{epct:.0f}" if epct is not None else "--"
    header = Text.from_markup(
        f"[dim]Score:[/] [white]{raw_s}[/][dim]/100[/] {raw_bar} [dim]↳ allocation[/] [{tc}][bold]{epct_s}%[/][/]  [dim]{regime[:24]}[/]"
    )
    return Panel(
        Group(header, tbl),
        title=f"[bold blue]EXPOSURE SCORE BREAKDOWN ({len(factor_map)} factors / 100pts)[/]  [dim][x] expand[/]",
        border_style="blue",
        padding=(0, 1),
    )


def panel_exposure_expanded(exp_f):
    """Full-screen exposure score detail — all 12 factors with values, thresholds, and signal context."""
    rows = [
        Text.from_markup("[dim]press [/][bold blue]x[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE SCORE - EXPANDED", border="blue")
    if err_panel:
        return err_panel

    raw = safe_float(exp_f.get("raw_score"), default=None)
    epct = safe_float(exp_f.get("exposure_pct"), default=None)
    regime = exp_f.get("regime", "")
    factors = exp_f.get("factors", {})
    tier = tier_from_pct(epct)
    tc = TIER_COLOR.get(tier, "dim")

    # Header summary
    raw_bar = mini_bar(raw if raw is not None else 0, 100, w=12)
    raw_s = f"{raw:.0f}" if raw is not None else "--"
    epct_s = f"{epct:.0f}" if epct is not None else "--"
    rows.append(
        Text.from_markup(
            f"[dim]Raw Score:[/] [white]{raw_s}[/][dim]/100[/] {raw_bar}  "
            f"[dim]→ Allocation:[/] [{tc}][bold]{epct_s}%[/][/]  [dim]{regime[:30]}[/]"
        )
    )
    rows.append(Rule(style="dim"))

    # Per-factor detail table
    factor_map_exp = [
        ("trend_30wk", "30-Week Trend", 15, "SPY above 30-week MA?"),
        ("spy_momentum", "SPY 12mo Momentum", 10, "12-month SPY return"),
        ("breadth_200dma", "Breadth 200 DMA", 10, "% stocks above 200DMA"),
        ("distribution_days", "Sell Pressure", 10, "Distribution day count"),
        ("vix_regime", "VIX + Structure", 10, "Fear gauge + market structure"),
        ("credit_spread", "Credit Spread", 10, "HY/IG spread compression"),
        ("put_call_ratio", "Put/Call Ratio", 8, "Options sentiment signal"),
        ("new_highs_lows", "New Highs vs Lows", 7, "NYSE new highs minus lows"),
        ("ad_line", "Advance/Decline", 6, "Breadth momentum direction"),
        ("breadth_50dma", "Breadth 50 DMA", 6, "% stocks above 50DMA"),
        ("naaim", "NAAIM Exposure", 5, "Active manager allocation"),
        ("aaii_sentiment", "AAII Sentiment", 3, "Retail investor bull/bear"),
    ]

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        padding=(0, 2),
        expand=True,
        row_styles=["", "dim"],
    )
    tbl.add_column("Factor", no_wrap=True, min_width=20)
    tbl.add_column("Pts", justify="right", no_wrap=True, min_width=5)
    tbl.add_column("Max", justify="right", no_wrap=True, min_width=4)
    tbl.add_column("Score", no_wrap=True, min_width=16)
    tbl.add_column("Value", no_wrap=True, min_width=12)
    tbl.add_column("Context", style="dim", no_wrap=False)

    for key, label, max_pts, context in factor_map_exp:
        f = factors.get(key, {})
        sf = f.get("score_factor")

        if sf is None:
            # Factor has no data — show ⚠ N/A rather than a misleading 0-point bar
            reason = (f.get("reason") or ("stale" if f.get("stale") else "no data"))[:18]
            bar_s = Text.from_markup(f"[yellow]⚠ N/A{'':>10}[/]  [dim]--/{max_pts}[/]")
            tbl.add_row(
                Text(label, style="yellow"),
                Text("--", style="yellow"),
                Text(str(max_pts), style="dim"),
                bar_s,
                Text(f"⚠ {reason}", style="yellow"),
                context,
            )
            continue

        pts_raw = f.get("pts")
        pts = float(pts_raw) if pts_raw is not None else 0.0
        bar_f = int(min(pts / max_pts, 1.0) * 12) if max_pts > 0 else 0
        fc = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
        bar_s = Text.from_markup(f"[{fc}]{'█' * bar_f}[/][dim]{'░' * (12 - bar_f)}[/]  [{fc}]{pts:.0f}/{max_pts}[/]")

        # Build value string per factor
        val_s = "--"
        if key == "trend_30wk":
            v = f.get("price_vs_ma_pct")
            val_s = f"{v:+.1f}% vs MA" if v is not None else "--"
        elif key == "breadth_200dma":
            v = f.get("value")
            val_s = f"{v:.0f}% above" if v is not None else "--"
        elif key == "breadth_50dma":
            v = f.get("value")
            val_s = f"{v:.0f}% above" if v is not None else "--"
        elif key == "spy_momentum":
            v = f.get("value")
            val_s = f"{v:+.1f}% 12mo" if v is not None else "--"
        elif key == "put_call_ratio":
            v = f.get("value")
            val_s = f"{v:.2f} P/C" if v is not None else "--"
        elif key == "vix_regime":
            v = f.get("value")
            val_s = f"VIX {v:.1f}" if v is not None else "--"
        elif key == "new_highs_lows":
            nh = f.get("new_highs") or 0
            nl = f.get("new_lows") or 0
            net = (nh if nh is not None else 0) - (nl if nl is not None else 0)
            val_s = f"NH:{nh} NL:{nl} net:{net:+d}"
        elif key == "credit_spread":
            v = f.get("value")
            val_s = f"{v:.2f}% OAS" if v is not None else "--"
        elif key == "ad_line":
            rel = (f.get("relation", "")).replace("_", " ")
            val_s = rel[:16] if rel else "--"
        elif key == "aaii_sentiment":
            bull = f.get("bullish_pct")
            bear = f.get("bearish_pct")
            val_s = f"B:{bull:.0f}% Bear:{bear:.0f}%" if (bull is not None and bear is not None) else "--"
        elif key == "naaim":
            v = f.get("value")
            val_s = f"{v:.0f}% allocated" if v is not None else "--"
        elif key == "distribution_days":
            cnt = f.get("count")
            rg = (f.get("regime", ""))[:10]
            val_s = f"{cnt}d / {rg}" if cnt is not None else "--"

        tbl.add_row(
            Text(label, style=fc),
            Text(f"{pts:.0f}", style=fc),
            Text(str(max_pts), style="dim"),
            bar_s,
            Text(val_s, style="white"),
            context,
        )

    rows.append(tbl)

    # Penalty/bonus adjustments
    sr = None
    eco = None
    if factors and isinstance(factors, dict):
        sr_raw = factors.get("sector_rotation")
        if isinstance(sr_raw, dict):
            sr = sr_raw
        eco_raw = factors.get("economic_overlay")
        if isinstance(eco_raw, dict):
            eco = eco_raw

    sr_pen = safe_float(sr.get("pts") if sr else None, default=0)
    eco_pen = safe_float(eco.get("pts") if eco else None, default=0)
    if sr_pen != 0 or eco_pen != 0:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim bold]ADJUSTMENTS[/]"))
        if sr_pen != 0 and sr:
            sig = (sr.get("signal", "")).replace("_", " ")
            sc = R if sr_pen < 0 else G
            rows.append(Text.from_markup(f"  [dim]Sector Rotation:[/] [{sc}]{sr_pen:+.0f} pts[/]  [dim]{sig}[/]"))
        if eco_pen != 0 and eco:
            eco_err = (eco.get("error", ""))[:30]
            ec = R if eco_pen < 0 else G
            rows.append(
                Text.from_markup(
                    f"  [dim]Economic Overlay:[/] [{ec}]{eco_pen:+.0f} pts[/]"
                    + (f"  [dim]{eco_err}[/]" if eco_err else "")
                )
            )

    return Panel(
        Group(*rows),
        title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
        border_style="blue",
        padding=(0, 1),
    )


__all__ = [
    "panel_exposure_compact",
    "panel_exposure_expanded",
]

