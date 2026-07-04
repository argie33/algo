"""Portfolio exposure and risk factor panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from rich.console import ConsoleRenderable, RichCast

from .. import error_boundary

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

from dashboard.data_validation import StrictValidationError, safe_float

from ..formatter_strategies import TierFormatter
from ..formatters import mini_bar
from ..utilities import (
    TIER_COLOR,
    G,
    R,
    Y,
)
from ._helpers import _error_panel

_tier_formatter = TierFormatter()


@register_panel(
    "exp",
    endpoint_deps=["exp"],
    optional=True,
    description="Exposure",
)
def panel_exposure_compact(exp_f: Any) -> Any:  # noqa: C901
    """Exposure score breakdown - compact 2-col layout."""
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE FACTORS", border="blue")
    if err_panel:
        return err_panel

    # CRITICAL: Fail fast if required fields missing. No fallback to defaults.
    required_fields = ["raw_score", "exposure_pct", "regime", "factors"]
    missing = [f for f in required_fields if f not in exp_f]
    if missing:
        logger.error("[EXPOSURE] Required fields missing from API response: %s", missing)
        return Text.from_markup(f"[red]✗ Exposure data incomplete (missing: {', '.join(missing)})[/]")

    raw = exp_f["raw_score"]
    epct = exp_f["exposure_pct"]
    regime = exp_f["regime"]
    factors = exp_f["factors"]

    # Validate types
    if not isinstance(epct, (int, float)):
        logger.error("[EXPOSURE] exposure_pct is not numeric: %s", type(epct).__name__)
        return Text.from_markup("[red]✗ Exposure data has invalid type[/]")
    if not isinstance(regime, str):
        logger.error("[EXPOSURE] regime is not string: %s", type(regime).__name__)
        return Text.from_markup("[red]✗ Regime data has invalid type[/]")
    if not isinstance(factors, dict):
        logger.error("[EXPOSURE] factors is not dict: %s", type(factors).__name__)
        return Text.from_markup("[red]✗ Exposure factors has invalid type[/]")

    tier = _tier_formatter.format(epct)
    tc = TIER_COLOR.get(tier, "dim")

    def factor_detail(key: Any) -> str:  # noqa: C901 - key dispatch lookup table is inherently complex
        """Return a short value string for a factor key."""
        # Early return if factors dict has error markers
        if error_boundary.has_error(factors):
            return "[yellow]⚠[/]"  # Mark as unavailable, not empty
        if not factors or key not in factors:
            return "[yellow]⚠[/]"  # Data unavailable, not empty
        f = factors[key]
        if not isinstance(f, dict):
            return "[yellow]⚠[/]"  # Corrupted data structure
        # Early return if factor data has error markers
        if error_boundary.has_error(f):
            return "[yellow]⚠[/]"  # Data unavailable
        if key == "trend_30wk":
            v = safe_float(f.get("price_vs_ma_pct"), default=None)
            return f" {'+' if v is not None and v >= 0 else ''}{v:.1f}%" if v is not None else "[yellow]⚠[/]"
        if key == "breadth_50dma":
            v = safe_float(f.get("value"), default=None)
            return f" {v:.0f}%" if v is not None else "[yellow]⚠[/]"
        if key == "breadth_200dma":
            v = safe_float(f.get("value"), default=None)
            return f" {v:.0f}%" if v is not None else "[yellow]⚠[/]"
        if key == "spy_momentum":
            v = safe_float(f.get("value"), default=None)
            return f" {v:+.1f}%" if v is not None else "[yellow]⚠[/]"
        if key == "put_call_ratio":
            v = safe_float(f.get("value"), default=None)
            # Handle nested structure: put_call_ratio might be {put_call_ratio, pts, max, score}
            if v is None and isinstance(f.get("put_call_ratio"), dict):
                v = safe_float(f["put_call_ratio"].get("put_call_ratio"), default=None)
            if v is None and isinstance(f.get("put_call_ratio"), dict):
                # CRITICAL: pts score is DIFFERENT from actual put_call_ratio
                # Do not silently use it as fallback - only use if we explicitly log it
                pts_fallback = safe_float(f["put_call_ratio"].get("pts"), default=None)
                if pts_fallback is not None:
                    logger.warning(
                        "[EXPOSURE] Actual put_call_ratio unavailable. "
                        "Showing derived pts score instead. "
                        "Risk metrics may be estimated, not precise."
                    )
                    v = pts_fallback
            if v is not None:
                return f" {v:.2f}"
            reason = f.get("reason")
            if not reason and isinstance(f.get("put_call_ratio"), dict):
                reason = f["put_call_ratio"].get("reason")
            return " [yellow]⚠[/]" if reason else "[yellow]⚠[/]"  # Always mark unavailable
        if key == "vix_regime":
            v = safe_float(f.get("value"), default=None)
            return f" {v:.1f}" if v is not None else "[yellow]⚠[/]"
        if key == "new_highs_lows":
            nh = safe_float(f.get("new_highs"), default=None)
            nl = safe_float(f.get("new_lows"), default=None)
            if nh is not None and nl is not None:
                net = nh - nl
                return f" {'+' if net >= 0 else ''}{int(net)}"
            return "[yellow]⚠[/]"  # Missing metric data
        if key == "credit_spread":
            v = safe_float(f.get("value"), default=None)
            return f" {v:.2f}" if v is not None else "[yellow]⚠[/]"
        if key == "ad_line":
            rel = f.get("relation")
            if rel and isinstance(rel, str):
                rel_display = rel.replace("_", " ")[:8]
                return f" {rel_display}"
            return "[yellow]⚠[/]"  # Missing relation field
        if key == "aaii_sentiment":
            bull = safe_float(f.get("bullish_pct"), default=None)
            bear = safe_float(f.get("bearish_pct"), default=None)
            if bull is not None and bear is not None:
                # Values are fractions (0.4 = 40%); multiply to display as percentages
                b_pct = bull * 100 if bull <= 1.0 else bull
                be_pct = bear * 100 if bear <= 1.0 else bear
                return f" B:{b_pct:.0f}%/Be:{be_pct:.0f}%"
            return "[yellow]⚠[/]"  # Missing sentiment data
        if key == "naaim":
            v = safe_float(f.get("value"), default=None)
            return f" {v:.0f}" if v is not None else "[yellow]⚠[/]"
        if key == "distribution_days":
            cnt = safe_float(f.get("count"), default=None)
            regime = f.get("regime")
            if cnt is not None:
                regime_display = regime[:5] if regime else "?"
                return f" {int(cnt)}d/{regime_display}"
            return "[yellow]⚠[/]"  # Missing count data
        return "[yellow]⚠[/]"  # Unknown factor key

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
            logger.warning("[EXPOSURE] factor %s not in response - data unavailable", key)
            items.append(f"[dim]{label}:[/] [yellow]⚠ factor unavailable[/][dim] /{max_pts}[/]")
            continue

        f: dict[str, Any] = factors[key]
        if not isinstance(f, dict):
            logger.warning("[EXPOSURE] factor %s has invalid type: %s, expected dict", key, type(f).__name__)
            items.append(f"[dim]{label}:[/] [yellow]⚠ invalid data type[/][dim] /{max_pts}[/]")
            continue

        pts_raw = f.get("pts")
        if pts_raw is None:
            reason = f.get("reason")
            if reason is None:
                reason = "data unavailable"
            logger.warning("[EXPOSURE] factor %s missing pts field: %s", key, reason)
            items.append(f"[dim]{label}:[/] [yellow]⚠ {reason[:20]}[/][dim] /{max_pts}[/]")
        else:
            try:
                pts = safe_float(pts_raw, field_name=f"{label}_pts")
            except StrictValidationError as e:
                items.append(f"[dim]{label}:[/] [yellow]⚠ {str(e)[:30]}[/]")
                continue
            bar = mini_bar(pts, max_pts, w=4)
            fc = (
                G
                if pts is not None and pts >= max_pts * 0.75
                else (Y if pts is not None and pts >= max_pts * 0.35 else R)
            )
            det = factor_detail(key)
            det_s = f" [dim]{det.strip()}[/]" if det else ""
            items.append(f"[dim]{label}:[/] {bar} [{fc}]{pts:.0f}/{max_pts}[/]{det_s}")

    sr = None
    eco = None
    if factors and isinstance(factors, dict):
        sr_raw = factors.get("sector_rotation")
        if isinstance(sr_raw, dict):
            sr = sr_raw
        else:
            logger.debug(
                "[EXPOSURE] sector_rotation not available or invalid type: %s",
                type(sr_raw).__name__ if sr_raw is not None else "None",
            )
        eco_raw = factors.get("economic_overlay")
        if isinstance(eco_raw, dict):
            eco = eco_raw
        else:
            logger.debug(
                "[EXPOSURE] economic_overlay not available or invalid type: %s",
                type(eco_raw).__name__ if eco_raw is not None else "None",
            )

    sr_pen = None
    eco_pen = None
    if sr:
        sr_pts_raw = sr.get("pts")
        if sr_pts_raw is None:
            logger.warning("[EXPOSURE] sector_rotation factor present but missing 'pts' field")
        else:
            try:
                sr_pen = safe_float(sr_pts_raw, None, field_name="sector_rotation_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE] sector_rotation pts conversion failed: %s", e)
    if eco:
        eco_pts_raw = eco.get("pts")
        if eco_pts_raw is None:
            logger.warning("[EXPOSURE] economic_overlay factor present but missing 'pts' field")
        else:
            try:
                eco_pen = safe_float(eco_pts_raw, None, field_name="economic_overlay_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE] economic_overlay pts conversion failed: %s", e)
    if sr_pen is not None and sr_pen < 0 and sr:
        sig = sr.get("signal")
        sig_display = sig.replace("_", " ")[:18] if isinstance(sig, str) else ""
        items.append(f"[dim]Sector Rotation:[/] [{R}]{sr_pen:+.0f}[/] [dim]{sig_display}[/]")
    if eco_pen is not None and eco_pen < 0 and eco:
        eco_err = eco.get("error")
        eco_err_display = eco_err[:18] if isinstance(eco_err, str) else ""
        items.append(
            f"[dim]Economic Overlay:[/] [{R}]{eco_pen:+.0f}[/]"
            + (f" [dim]{eco_err_display}[/]" if eco_err_display else "")
        )

    for a, b in zip(items[::2], [*items[1::2], ""], strict=False):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    if raw is None or epct is None:
        header = Text.from_markup("[red]Exposure score calculation failed — raw_score or exposure_pct missing[/]")
    else:
        raw_bar = mini_bar(raw, 100, w=8)
        raw_s = f"{raw:.0f}"
        epct_s = f"{epct:.0f}"
        header = Text.from_markup(
            f"[dim]Score:[/] [white]{raw_s}[/][dim]/100[/] {raw_bar} [dim]↳ allocation[/] [{tc}][bold]{epct_s}%[/][/]  [dim]{regime[:24]}[/]"
        )
    return Panel(
        Group(header, tbl),
        title=f"[bold blue]EXPOSURE SCORE BREAKDOWN ({len(factor_map)} factors / 100pts)[/]  [dim][x] expand[/]",
        border_style="blue",
        padding=(0, 1),
    )


def panel_exposure_expanded(exp_f: Any) -> Any:  # noqa: C901
    """Full-screen exposure score detail — all 12 factors with values, thresholds, and signal context."""
    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold blue]x[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]
    # Check for error markers on response object
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE SCORE - EXPANDED", border="blue")
    if err_panel:
        return err_panel

    # Early exit if exp_f has error markers
    if error_boundary.has_error(exp_f):
        error_msg = error_boundary.get_error_message(exp_f)
        return Panel(
            Text.from_markup(f"[red]Exposure data fetch failed[/]\n[dim]{error_msg}[/]"),
            title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )

    if "factors" not in exp_f:
        logger.error("[EXPOSURE_EXPANDED] factors field missing from API response")
        rows.append(Text.from_markup("[red]✗ Exposure data missing 'factors' field — API schema mismatch[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    raw = exp_f.get("raw_score")
    epct = exp_f.get("exposure_pct")
    # If raw_score or exposure_pct are missing, return explicit data_unavailable marker
    if raw is None or epct is None:
        missing_fields = []
        if raw is None:
            logger.warning("[EXPOSURE_EXPANDED] raw_score field missing")
            missing_fields.append("raw_score")
        if epct is None:
            logger.warning("[EXPOSURE_EXPANDED] exposure_pct field missing")
            missing_fields.append("exposure_pct")
        rows.append(
            Text.from_markup(
                f"[yellow]⚠ Exposure data incomplete[/]\n"
                f"[dim]Missing required fields: {', '.join(missing_fields)}\n"
                f"Available: {', '.join(list(exp_f.keys()))}[/]"
            )
        )
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    regime = exp_f.get("regime")
    if not regime or not isinstance(regime, str):
        logger.warning("[EXPOSURE_EXPANDED] regime field missing or invalid type")
        rows.append(Text.from_markup("[yellow]⚠ Market regime unavailable[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    factors = exp_f.get("factors")
    if not isinstance(factors, dict):
        logger.error("[EXPOSURE_EXPANDED] factors field is not a dict, received type: %s", type(factors).__name__)
        rows.append(Text.from_markup("[red]✗ Exposure factors data invalid[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    tier = _tier_formatter.format(epct)
    tc = TIER_COLOR.get(tier, "dim")

    # Header summary
    raw_bar = mini_bar(raw, 100, w=12)
    raw_s = f"{raw:.0f}"
    epct_s = f"{epct:.0f}"
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
        # Early exit if factors dict has error markers
        f: dict[str, Any] = {}
        if error_boundary.has_error(factors):
            logger.debug("[EXPOSURE_EXPANDED] factors dict has error markers, skipping factor %s", key)
            f = {}
        elif key not in factors:
            # Factor missing from API response — log and skip
            logger.debug("[EXPOSURE_EXPANDED] factor %s not in response", key)
            f = {}
        else:
            f = factors[key]
            if not isinstance(f, dict):
                logger.warning(
                    "[EXPOSURE_EXPANDED] factor %s has invalid type: %s, expected dict", key, type(f).__name__
                )
                f = {}
            # Early exit if individual factor has error markers
            elif error_boundary.has_error(f):
                logger.debug("[EXPOSURE_EXPANDED] factor %s has error markers", key)
                f = {}

        pts_raw = f.get("pts") if f else None
        if pts_raw is None:
            # Factor has no data — show ⚠ N/A rather than a misleading 0-point bar
            reason_val = f.get("reason")
            if reason_val is None:
                # Check for explicit stale marker
                if f.get("stale"):
                    logger.debug("[EXPOSURE_EXPANDED] factor %s marked stale", key)
                    reason_val = "stale"
                else:
                    logger.debug("[EXPOSURE_EXPANDED] factor %s missing pts and reason", key)
                    reason_val = "no data"
            reason = reason_val[:18]
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

        try:
            pts = safe_float(pts_raw, field_name=f"{label}_pts")
        except StrictValidationError as e:
            reason = f"invalid: {str(e)[:12]}"
            bar_s = Text.from_markup(f"[red]✗ ERR{'':>12}[/]  [dim]--/{max_pts}[/]")
            tbl.add_row(
                Text(label, style="red"),
                Text("--", style="red"),
                Text(str(max_pts), style="dim"),
                bar_s,
                Text(f"✗ {reason}", style="red"),
                context,
            )
            continue
        bar_f = int(min(pts / max_pts, 1.0) * 12) if max_pts > 0 and pts is not None else 12
        fc = G if pts is not None and pts >= max_pts * 0.75 else (Y if pts is not None and pts >= max_pts * 0.35 else R)
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
            nh_val = f.get("new_highs")
            nl_val = f.get("new_lows")
            if (
                nh_val is None
                or nl_val is None
                or not (isinstance(nh_val, (int, float)) and isinstance(nl_val, (int, float)))
            ):
                val_s = "[red]✗ Missing new highs/lows data[/]"
            else:
                nh = int(nh_val)
                nl = int(nl_val)
                net = nh - nl
                val_s = f"NH:{nh} NL:{nl} net:{net:+d}"
        elif key == "credit_spread":
            v = f.get("value")
            val_s = f"{v:.2f}% OAS" if v is not None else "--"
        elif key == "ad_line":
            rel = f.get("relation")
            rel_display = rel.replace("_", " ")[:16] if isinstance(rel, str) else "--"
            val_s = rel_display
        elif key == "aaii_sentiment":
            bull = f.get("bullish_pct")
            bear = f.get("bearish_pct")
            if bull is not None and bear is not None:
                b_pct = bull * 100 if bull <= 1.0 else bull
                be_pct = bear * 100 if bear <= 1.0 else bear
                val_s = f"Bull:{b_pct:.0f}% Bear:{be_pct:.0f}%"
            else:
                val_s = "--"
        elif key == "naaim":
            v = f.get("value")
            val_s = f"{v:.0f}% allocated" if v is not None else "--"
        elif key == "distribution_days":
            cnt = f.get("count")
            rg = f.get("regime")
            rg_display = rg[:10] if isinstance(rg, str) else "?"
            val_s = f"{cnt}d / {rg_display}" if cnt is not None else "--"

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
    if factors and isinstance(factors, dict) and not error_boundary.has_error(factors):
        sr_raw = factors.get("sector_rotation")
        if isinstance(sr_raw, dict) and not error_boundary.has_error(sr_raw):
            sr = sr_raw
        else:
            logger.debug(
                "[EXPOSURE_EXPANDED_ADJ] sector_rotation not available or invalid type: %s",
                type(sr_raw).__name__ if sr_raw is not None else "None",
            )
        eco_raw = factors.get("economic_overlay")
        if isinstance(eco_raw, dict) and not error_boundary.has_error(eco_raw):
            eco = eco_raw
        else:
            logger.debug(
                "[EXPOSURE_EXPANDED_ADJ] economic_overlay not available or invalid type: %s",
                type(eco_raw).__name__ if eco_raw is not None else "None",
            )

    sr_pen = None
    eco_pen = None
    if sr:
        sr_pts_raw = sr.get("pts")
        if sr_pts_raw is None:
            logger.error(
                "[EXPOSURE_EXPANDED_ADJ] sector_rotation factor present but missing 'pts' field — cannot calculate adjustment"
            )
        else:
            try:
                sr_pen = safe_float(sr_pts_raw, field_name="sector_rotation_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE_EXPANDED_ADJ] sector_rotation pts conversion failed: %s", e)
    if eco:
        eco_pts_raw = eco.get("pts")
        if eco_pts_raw is None:
            logger.error(
                "[EXPOSURE_EXPANDED_ADJ] economic_overlay factor present but missing 'pts' field — cannot calculate adjustment"
            )
        else:
            try:
                eco_pen = safe_float(eco_pts_raw, field_name="economic_overlay_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE_EXPANDED_ADJ] economic_overlay pts conversion failed: %s", e)
    if sr_pen is not None or eco_pen is not None:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim bold]ADJUSTMENTS[/]"))
        if sr_pen is not None and sr:
            sig = sr.get("signal")
            sig_display = sig.replace("_", " ") if isinstance(sig, str) else ""
            sc = R if sr_pen < 0 else G
            rows.append(
                Text.from_markup(f"  [dim]Sector Rotation:[/] [{sc}]{sr_pen:+.0f} pts[/]  [dim]{sig_display}[/]")
            )
        elif sr:
            logger.debug("[EXPOSURE_EXPANDED_ADJ] sector_rotation present but pts field missing")
            rows.append(Text.from_markup("  [dim]Sector Rotation:[/] [red]✗ pts calculation failed[/]"))
        if eco_pen is not None and eco:
            eco_err = eco.get("error")
            eco_err_display = eco_err[:30] if isinstance(eco_err, str) else ""
            ec = R if eco_pen < 0 else G
            rows.append(
                Text.from_markup(
                    f"  [dim]Economic Overlay:[/] [{ec}]{eco_pen:+.0f} pts[/]"
                    + (f"  [dim]{eco_err_display}[/]" if eco_err_display else "")
                )
            )
        elif eco:
            logger.debug("[EXPOSURE_EXPANDED_ADJ] economic_overlay present but pts field missing")
            rows.append(Text.from_markup("  [dim]Economic Overlay:[/] [red]✗ pts calculation failed[/]"))

    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title="[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim][x] return[/]",
        border_style="blue",
        padding=(0, 1),
    )


__all__ = [
    "panel_exposure_compact",
    "panel_exposure_expanded",
]
