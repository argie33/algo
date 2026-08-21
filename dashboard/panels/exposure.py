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
from ..formatters import fmt_age, mini_bar
from ..utilities import TIER_COLOR, G, R, Y
from ._helpers import _error_panel

_tier_formatter = TierFormatter()


def _delta_bar_markup(pts: float | None, neg_span: float, pos_span: float | None = None, w: int = 12) -> str:
    """Render a signed +/- adjustment as a filled/empty bar + point value (markup string).

    Unlike mini_bar() (a 0..max budget filled green/yellow/red by fraction), the four
    "adjustment" factors (sector rotation, economic overlay, cross-asset, fundamental
    quality) are discounts/bonuses around a zero midpoint, so the bar fills from empty
    proportional to |pts| and colors green (bonus) / red (penalty) by sign. Shared by
    both the compact and expanded panels so they render these factors identically
    (BUG FOUND 2026-08-21: compact panel showed a bare +/-N with no bar at all, unlike
    every other factor in that panel).

    neg_span/pos_span are the factor's own bounds on each side of zero (e.g. economic
    overlay is -7..+2, not symmetric) - a maxed-out bonus must fill the bar exactly as
    fully as a maxed-out penalty does. Passing one span for both sides (BUG FOUND
    2026-08-21: economic overlay always divided by its 7pt penalty span even when
    scoring its own +2pt bonus side, so a full bonus only ever showed ~29% filled)
    silently understates whichever side isn't the one `neg_span` was tuned for.
    """
    if pts is None:
        return "[yellow]⚠ N/A[/]"
    if pts == 0:
        return f"[dim]{'░' * w}[/]  0"
    c = G if pts > 0 else R
    span = (pos_span if pos_span is not None else neg_span) if pts > 0 else neg_span
    filled = max(int(min(abs(pts) / span, 1.0) * w), 1) if span > 0 else w
    return f"[{c}]{'█' * filled}[/][dim]{'░' * (w - filled)}[/]  [{c}]{pts:+.0f}[/]"


def _range_label(low: float, high: float) -> str:
    """Format an adjustment factor's point range consistently as "low to high".

    BUG FOUND 2026-08-21: sector rotation/cross-asset/fundamental quality wrote their
    range as "0/-10" (max-then-min) while economic overlay wrote "-7/+2" (min-then-max)
    - two different orderings for the same kind of value on the same table, which reads
    as arbitrary +/- noise. Every adjustment row now goes through this one function.
    """

    def fmt(v: float) -> str:
        return f"{v:+.0f}" if v != 0 else "0"

    return f"{fmt(low)} to {fmt(high)}"


def _stale_warning(exp_f: Any) -> str:
    """Server-computed staleness badge from the API's data_freshness field.

    BUG FOUND 2026-08-17: unlike MARKET/POSITIONS/TRADES/SIGNALS/SCORES, the EXPOSURE panel
    had no staleness detection at all - just a passive "Xh ago" age string (fmt_age does no
    threshold check). Same root cause as the MARKET panel fix (see
    [[unwrap_api_response_data_freshness_root_cause_fix_20260817]] in memory): fetch_exp_factors()
    (dashboard/fetchers_market.py) never propagated data_freshness from the /api/algo/markets
    response it shares with fetch_market(), and stamped "timestamp" with the client's own fetch
    time instead. The 12-factor exposure breakdown feeds position-sizing gating, same as MARKET.
    """
    if not isinstance(exp_f, dict):
        return ""
    data_freshness = exp_f.get("data_freshness")
    if isinstance(data_freshness, dict) and data_freshness.get("is_stale"):
        warning_text = data_freshness.get("warning") or "stale"
        logger.warning(f"[EXPOSURE] Exposure data stale: {warning_text}")
        return " [yellow]⚠ STALE[/]"
    return ""


@register_panel(
    "exp",
    endpoint_deps=["exp_factors"],
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
            if v is None:
                reason = f.get("reason", "missing_value")
                logger.warning("[EXPOSURE] Risk factor missing: spy_momentum unavailable. reason=%s", reason)
            return f" {v:+.1f}%" if v is not None else "[yellow]⚠[/]"
        if key == "put_call_ratio":
            v = safe_float(f.get("value"), default=None)
            # Handle nested structure: put_call_ratio might be {put_call_ratio, pts, max, score}
            put_call_data = f.get("put_call_ratio")
            if v is None and isinstance(put_call_data, dict):
                v = safe_float(put_call_data.get("put_call_ratio"), default=None)

            if v is not None:
                return f" {v:.2f}"

            # GOVERNANCE FIX: Do NOT use pts score as fallback when actual put_call_ratio missing.
            # Pts is derived metric, different from actual put_call_ratio.
            # Per GOVERNANCE.md: "Never use secondary fallback when primary unavailable"
            reason = f.get("reason")
            if not reason and isinstance(put_call_data, dict):
                reason = put_call_data.get("reason")
            logger.error(
                "[EXPOSURE] Risk factor missing: put_call_ratio unavailable. reason=%s. Position sizing will be degraded.",
                reason,
            )
            return " [yellow]⚠[/]"  # Mark unavailable, don't use derived metric
        if key == "vix_regime":
            v = safe_float(f.get("value"), default=None)
            if v is None:
                logger.warning("[EXPOSURE] Risk factor missing: vix_regime unavailable")
            return f" {v:.1f}" if v is not None else "[yellow]⚠[/]"
        if key == "new_highs_lows":
            nh = safe_float(f.get("new_highs"), default=None)
            nl = safe_float(f.get("new_lows"), default=None)
            if nh is not None and nl is not None:
                net = nh - nl
                return f" {'+' if net >= 0 else ''}{int(net)}"
            logger.warning("[EXPOSURE] Risk factor missing: new_highs_lows unavailable (nh=%s, nl=%s)", nh, nl)
            return "[yellow]⚠[/]"  # Missing metric data
        if key == "credit_spread":
            v = safe_float(f.get("value"), default=None)
            if v is None:
                logger.warning("[EXPOSURE] Risk factor missing: credit_spread unavailable")
            return f" {v:.2f}" if v is not None else "[yellow]⚠[/]"
        if key == "ad_line":
            rel = f.get("relation")
            if rel and isinstance(rel, str):
                rel_display = rel.replace("_", " ")[:8]
                return f" {rel_display}"
            logger.warning("[EXPOSURE] Risk factor missing: ad_line missing relation field")
            return "[yellow]⚠[/]"  # Missing relation field
        if key == "aaii_sentiment":
            # bullish_pct/bearish_pct are 0-100 scale - MarketFactorCalculator.aaii() converts
            # from the DB's stored 0-1 fraction scale before returning (fixed 2026-08-20; the
            # raw aaii_sentiment.bullish/bearish columns are fractions, not percentage-points).
            bull = safe_float(f.get("bullish_pct"), default=None)
            bear = safe_float(f.get("bearish_pct"), default=None)
            if bull is not None and bear is not None:
                return f" B:{bull:.0f}%/Be:{bear:.0f}%"
            logger.warning("[EXPOSURE] Risk factor missing: aaii_sentiment unavailable (bull=%s, bear=%s)", bull, bear)
            return "[yellow]⚠[/]"  # Missing sentiment data
        if key == "positioning":
            v = safe_float(f.get("value"), default=None)
            if v is None:
                logger.warning("[EXPOSURE] Risk factor missing: positioning unavailable")
            return f" {v:.0f}" if v is not None else "[yellow]⚠[/]"
        if key == "distribution_days":
            cnt = safe_float(f.get("count"), default=None)
            regime = f.get("regime")
            if cnt is not None:
                regime_display = regime[:5] if regime else "?"
                return f" {int(cnt)}d/{regime_display}"
            logger.warning("[EXPOSURE] Risk factor missing: distribution_days unavailable (cnt=%s)", cnt)
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
        ("positioning", "Positioning", 5),
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
    xasset = None
    fq = None
    sahm = None
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
        xasset_raw = factors.get("cross_asset_confirmation")
        if isinstance(xasset_raw, dict):
            xasset = xasset_raw
        fq_raw = factors.get("fundamental_quality")
        if isinstance(fq_raw, dict):
            fq = fq_raw
        sahm_raw = factors.get("sahm_rule")
        if isinstance(sahm_raw, dict):
            sahm = sahm_raw

    sr_pen = None
    eco_pen = None
    xasset_pen = None
    fq_pen = None
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
    if xasset:
        try:
            xasset_pen = safe_float(xasset.get("pts"), None, field_name="cross_asset_confirmation_pts")
        except StrictValidationError as e:
            logger.error("[EXPOSURE] cross_asset_confirmation pts conversion failed: %s", e)
    if fq:
        try:
            fq_pen = safe_float(fq.get("pts"), None, field_name="fundamental_quality_pts")
        except StrictValidationError as e:
            logger.error("[EXPOSURE] fundamental_quality pts conversion failed: %s", e)
    # All four adjustment factors gate on "!= 0" (not "< 0"): sector rotation/cross-asset/
    # fundamental quality are penalty-only so this is equivalent to "< 0" for them, but
    # economic overlay can also score a +2 bonus (BUG FOUND 2026-08-21: this panel used
    # to gate all four on "< 0", so an active economic overlay bonus was silently invisible
    # here even though the expanded panel always shows it - one unified rule now covers both).
    if sr_pen is not None and sr_pen != 0 and sr:
        sig = sr.get("signal")
        sig_display = sig.replace("_", " ")[:18] if isinstance(sig, str) else ""
        items.append(f"[dim]Sector Rotation:[/] {_delta_bar_markup(sr_pen, 10, w=4)} [dim]{sig_display}[/]")
    if eco_pen is not None and eco_pen != 0 and eco:
        # Check for error marker in economic overlay data
        eco_err = None
        if error_boundary.has_error(eco):
            eco_err = error_boundary.get_error_message(eco)
        eco_err_display = eco_err[:18] if isinstance(eco_err, str) else ""
        items.append(
            f"[dim]Economic Overlay:[/] {_delta_bar_markup(eco_pen, 7, pos_span=2, w=4)}"
            + (f" [dim]{eco_err_display}[/]" if eco_err_display else "")
        )
    if xasset_pen is not None and xasset_pen != 0 and xasset:
        sigs = xasset.get("risk_off_signals")
        sig_display = ", ".join(sigs)[:24] if isinstance(sigs, list) and sigs else ""
        items.append(f"[dim]Cross-Asset:[/] {_delta_bar_markup(xasset_pen, 8, w=4)} [dim]{sig_display}[/]")
    if fq_pen is not None and fq_pen != 0 and fq:
        fscore = fq.get("fundamental_score")
        fscore_display = f"score {fscore:.0f}" if isinstance(fscore, (int, float)) else ""
        items.append(f"[dim]Fundamental Qual:[/] {_delta_bar_markup(fq_pen, 5, w=4)} [dim]{fscore_display}[/]")
    if sahm is not None and sahm.get("triggered"):
        sahm_val = safe_float(sahm.get("value"), default=None)
        val_display = f"{sahm_val:.2f}pp" if sahm_val is not None else "--"
        items.append(f"[dim]Sahm Rule:[/] [{R}]VETO[/] [dim]{val_display} recession signal, capped 25%[/]")

    for a, b in zip(items[::2], [*items[1::2], ""], strict=False):
        tbl.add_row(Text.from_markup(a), Text.from_markup(b))

    if raw is None or epct is None:
        header = Text.from_markup("[red]Exposure score calculation failed - raw_score or exposure_pct missing[/]")
    else:
        raw_bar = mini_bar(raw, 100, w=8)
        raw_s = f"{raw:.0f}"
        epct_s = f"{epct:.0f}"
        header = Text.from_markup(
            f"[dim]Score:[/] [white]{raw_s}[/][dim]/100[/] {raw_bar} [dim]↳ allocation[/] [{tc}][bold]{epct_s}%[/][/]  [dim]{regime[:24]}[/]"
        )
    timestamp_val = exp_f.get("timestamp") if isinstance(exp_f, dict) else None
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    stale_warning = _stale_warning(exp_f)
    return Panel(
        Group(header, tbl),
        title=rf"[bold blue]EXPOSURE SCORE BREAKDOWN ({len(factor_map)} factors / 100pts)[/]{age_s}{stale_warning}  [dim]\[x] expand[/]",
        border_style="blue" if not stale_warning else "yellow",
        padding=(0, 1),
    )


def panel_exposure_expanded(exp_f: Any) -> Any:  # noqa: C901
    """Full-screen exposure score detail - all 12 factors with values, thresholds, and signal context."""
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
            title=r"[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim]\[x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )

    if "factors" not in exp_f:
        logger.error("[EXPOSURE_EXPANDED] factors field missing from API response")
        rows.append(Text.from_markup("[red]✗ Exposure data missing 'factors' field - API schema mismatch[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title=r"[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim]\[x] return[/]",
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
            title=r"[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim]\[x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    regime = exp_f.get("regime")
    if not regime or not isinstance(regime, str):
        logger.warning("[EXPOSURE_EXPANDED] regime field missing or invalid type")
        rows.append(Text.from_markup("[yellow]⚠ Market regime unavailable[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title=r"[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim]\[x] return[/]",
            border_style="blue",
            padding=(0, 1),
        )
    factors = exp_f.get("factors")
    if not isinstance(factors, dict):
        logger.error("[EXPOSURE_EXPANDED] factors field is not a dict, received type: %s", type(factors).__name__)
        rows.append(Text.from_markup("[red]✗ Exposure factors data invalid[/]"))
        return Panel(
            Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
            title=r"[bold blue]EXPOSURE SCORE - EXPANDED[/]  [dim]\[x] return[/]",
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
        ("positioning", "Positioning & Flows", 5, "Insider buying breadth + short interest trend"),
        ("aaii_sentiment", "AAII Sentiment", 3, "Retail investor bull/bear"),
    ]

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        # No vertical padding: this panel renders inside Live(screen=True), which clips
        # content taller than the real terminal instead of scrolling it (confirmed live:
        # a trailing blank line per row pushed the last 1-2 rows off-screen entirely,
        # e.g. Sahm Rule silently disappearing). With 17 rows already wrapping to
        # multiple lines each, there is no vertical budget to spend on padding here -
        # see _shorten_adjustment_value() below for the height-neutral fix instead.
        padding=(0, 2),
        expand=True,
        row_styles=["", "dim"],
    )
    # Factor/Pts/Max/Score are fixed/bounded so they never truncate; Value and Context
    # share whatever width remains via ratio, so Context gets a fair, legible column
    # instead of being squeezed to a sliver that wraps every word onto its own line
    # (BUG FOUND 2026-08-21: all six columns used to be no_wrap or unbounded, so the
    # Value column's rare long strings ate the table's width and left Context <20 cols).
    tbl.add_column("Factor", no_wrap=True, min_width=20, max_width=26)
    tbl.add_column("Pts", justify="right", no_wrap=True, width=5)
    # width=9 fits the longest range label ("-10 to 0" / "-7 to +2", 8 chars) without
    # truncating (BUG FOUND 2026-08-21: width=7 truncated both to "-10 to…"/"-7 to …").
    tbl.add_column("Max", justify="right", no_wrap=True, width=9)
    tbl.add_column("Score", no_wrap=True, width=19)
    tbl.add_column("Value", no_wrap=False, ratio=2, min_width=16, max_width=36)
    tbl.add_column("Context", style="dim", no_wrap=False, ratio=3, min_width=18)

    for key, label, max_pts, context in factor_map_exp:
        # Early exit if factors dict has error markers
        f: dict[str, Any] = {}
        if error_boundary.has_error(factors):
            logger.debug("[EXPOSURE_EXPANDED] factors dict has error markers, skipping factor %s", key)
            f = {}
        elif key not in factors:
            # Factor missing from API response - log and skip
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
            # Factor has no data - show ⚠ N/A rather than a misleading 0-point bar
            reason_val = f.get("reason")
            if reason_val is None:
                # Check for explicit stale marker
                if f.get("stale"):
                    reason_val = "stale"
                else:
                    reason_val = "no data"
            reason = reason_val[:18]
            logger.error(
                "[EXPOSURE_EXPANDED] data_unavailable: factor=%s, key=%s, reason=%s. "
                "Risk factor missing affects position sizing. Check upstream data source.",
                label,
                key,
                reason_val,
            )
            # Pad "⚠ N/A" (5 chars) out to the same 12-char width as a real bar so this
            # row lines up with the rest of the Score column instead of overflowing it.
            bar_s = Text.from_markup(f"[yellow]⚠ N/A{'':>7}[/]  [dim]--/{max_pts}[/]")
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
            # Same 12-char alignment as the N/A case above ("✗ ERR" is also 5 chars).
            bar_s = Text.from_markup(f"[red]✗ ERR{'':>7}[/]  [dim]--/{max_pts}[/]")
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
            # API returns "nh" and "nl" keys (not "new_highs" and "new_lows")
            nh_val = f.get("nh")
            if nh_val is None:
                nh_val = f.get("new_highs")
            nl_val = f.get("nl")
            if nl_val is None:
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
                val_s = f"NH:{nh} NL:{nl} {net:+d}"
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
                val_s = f"Bull:{bull:.0f}% Bear:{bear:.0f}%"
            else:
                val_s = "--"
        elif key == "positioning":
            v = f.get("value")
            val_s = f"{v:.0f} blended" if v is not None else "--"
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

    # Same table, same columns as the 12 factors above - these are just the remaining
    # 5 rows of the same "what feeds the score" picture, not a separate concept the
    # user has to learn. Only difference: Max is a +/- range (not a fixed budget) since
    # each of these is a bounded discount/bonus, and Sahm Rule caps the final allocation
    # directly instead of adding/subtracting points.
    def _delta_bar(pts: float | None, neg_span: float, pos_span: float | None = None) -> Text:
        return Text.from_markup(_delta_bar_markup(pts, neg_span, pos_span=pos_span, w=12))

    sr = None
    eco = None
    xasset = None
    fq = None
    sahm = None
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
        xasset_raw = factors.get("cross_asset_confirmation")
        if isinstance(xasset_raw, dict) and not error_boundary.has_error(xasset_raw):
            xasset = xasset_raw
        fq_raw = factors.get("fundamental_quality")
        if isinstance(fq_raw, dict) and not error_boundary.has_error(fq_raw):
            fq = fq_raw
        sahm_raw = factors.get("sahm_rule")
        if isinstance(sahm_raw, dict) and not error_boundary.has_error(sahm_raw):
            sahm = sahm_raw

    if sr:
        sr_pts_raw = sr.get("pts")
        if sr_pts_raw is None:
            logger.error("[EXPOSURE_EXPANDED_ADJ] sector_rotation factor present but missing 'pts' field")
            tbl.add_row(
                Text("Sector Rotation", style="red"),
                Text("--", style="red"),
                Text(_range_label(-10, 0), style="dim"),
                Text.from_markup("[red]✗ ERR[/]"),
                Text("calculation failed", style="red"),
                "Defensive-sector leadership vs. cyclicals",
            )
        else:
            try:
                sr_pen = safe_float(sr_pts_raw, field_name="sector_rotation_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE_EXPANDED_ADJ] sector_rotation pts conversion failed: %s", e)
                sr_pen = None
            sig = sr.get("signal")
            dls = sr.get("defensive_lead_score")
            if sig == "data_unavailable":
                reason = sr.get("reason") or "insufficient rotation history yet (<12wk)"
                val_s = f"n/a — {reason}"
            else:
                sig_display = sig.replace("_", " ") if isinstance(sig, str) else "unknown"
                dls_display = f", lead {dls:.0f}/100" if isinstance(dls, (int, float)) else ""
                val_s = f"{sig_display}{dls_display}"
            tbl.add_row(
                Text("Sector Rotation", style="white" if sr_pen else "dim"),
                Text(f"{sr_pen:+.0f}" if sr_pen is not None else "--", style="white"),
                Text(_range_label(-10, 0), style="dim"),
                _delta_bar(sr_pen, 10),
                Text(val_s, style="white"),
                "Defensive-sector leadership vs. cyclicals",
            )

    if eco:
        eco_pts_raw = eco.get("pts")
        if eco_pts_raw is None:
            logger.error("[EXPOSURE_EXPANDED_ADJ] economic_overlay factor present but missing 'pts' field")
            tbl.add_row(
                Text("Economic Overlay", style="red"),
                Text("--", style="red"),
                Text(_range_label(-7, 2), style="dim"),
                Text.from_markup("[red]✗ ERR[/]"),
                Text("calculation failed", style="red"),
                "Yield curve + jobless claims + financial stress composite",
            )
        else:
            try:
                eco_pen = safe_float(eco_pts_raw, field_name="economic_overlay_pts")
            except StrictValidationError as e:
                logger.error("[EXPOSURE_EXPANDED_ADJ] economic_overlay pts conversion failed: %s", e)
                eco_pen = None
            stress = eco.get("macro_stress_score")
            stress_display = f"stress {stress:.0f}/100" if isinstance(stress, (int, float)) else "stress n/a"
            eco_signals = eco.get("signals")
            sig_display = (
                "; ".join(str(s) for s in eco_signals[:2])
                if isinstance(eco_signals, list) and eco_signals
                else "no stress signals active"
            )
            eco_err = error_boundary.get_error_message(eco) if error_boundary.has_error(eco) else None
            val_s = f"{stress_display} — {sig_display}" + (f" [{eco_err[:20]}]" if eco_err else "")
            tbl.add_row(
                Text("Economic Overlay", style="white" if eco_pen else "dim"),
                Text(f"{eco_pen:+.0f}" if eco_pen is not None else "--", style="white"),
                Text(_range_label(-7, 2), style="dim"),
                _delta_bar(eco_pen, 7, pos_span=2),
                Text(val_s, style="white"),
                "Yield curve + jobless claims + financial stress composite",
            )
            if isinstance(eco_signals, list) and len(eco_signals) > 2:
                tbl.add_row(
                    "",
                    "",
                    "",
                    "",
                    Text(f"+ {len(eco_signals) - 2} more: " + "; ".join(str(s) for s in eco_signals[2:5]), style="dim"),
                    "",
                )

    if xasset:
        try:
            xasset_pen = safe_float(xasset.get("pts"), field_name="cross_asset_confirmation_pts")
        except StrictValidationError as e:
            logger.error("[EXPOSURE_EXPANDED_ADJ] cross_asset_confirmation pts conversion failed: %s", e)
            xasset_pen = None
        sigs = xasset.get("risk_off_signals")
        if isinstance(sigs, list) and sigs:
            val_s = "; ".join(sigs)
        else:
            chg_parts = [
                f"{label} {v:+.1f}%"
                for label, key in (
                    ("SPY", "spy_chg_20d"),
                    ("GLD", "gld_chg_20d"),
                    ("TLT", "tlt_chg_20d"),
                    ("USD", "usd_chg_20d"),
                    ("Oil", "oil_chg_20d"),
                )
                if isinstance((v := xasset.get(key)), (int, float))
            ]
            val_s = "no disagreement (needs 2 of 4)" + (f" — 20d: {' '.join(chg_parts)}" if chg_parts else "")
        tbl.add_row(
            Text("Cross-Asset Confirmation", style="white" if xasset_pen else "dim"),
            Text(f"{xasset_pen:+.0f}" if xasset_pen is not None else "--", style="white"),
            Text(_range_label(-8, 0), style="dim"),
            _delta_bar(xasset_pen, 8),
            Text(val_s, style="white"),
            "Gold/bonds/USD/oil disagreeing with bullish equities",
        )

    if fq:
        try:
            fq_pen = safe_float(fq.get("pts"), field_name="fundamental_quality_pts")
        except StrictValidationError as e:
            logger.error("[EXPOSURE_EXPANDED_ADJ] fundamental_quality pts conversion failed: %s", e)
            fq_pen = None
        fscore = fq.get("fundamental_score")
        rev = fq.get("revision_breadth_pct")
        ins = fq.get("insider_buying_breadth_pct")
        val = fq.get("valuation_extension_breadth_pct")
        rev_s = f"{rev:.0f}%" if isinstance(rev, (int, float)) else "n/a"
        ins_s = f"{ins:.0f}%" if isinstance(ins, (int, float)) else "n/a"
        val_s_pct = f"{val:.0f}%" if isinstance(val, (int, float)) else "n/a"
        fscore_display = f"{fscore:.0f}/100" if isinstance(fscore, (int, float)) else "n/a"
        val_s = f"score {fscore_display} (rev {rev_s}, insider {ins_s}, val-ext {val_s_pct})"
        tbl.add_row(
            Text("Fundamental Quality", style="white" if fq_pen else "dim"),
            Text(f"{fq_pen:+.0f}" if fq_pen is not None else "--", style="white"),
            Text(_range_label(-5, 0), style="dim"),
            _delta_bar(fq_pen, 5),
            Text(val_s, style="white"),
            "Analyst/insider/valuation confirmation of a bullish tape",
        )

    if sahm is not None:
        sahm_val = sahm.get("value")
        sahm_triggered = sahm.get("triggered")
        val_display = f"{sahm_val:.2f}pp" if isinstance(sahm_val, (int, float)) else "--"
        val_s = f"{val_display} vs. 0.50pp" + (" — TRIGGERED, capped 25%" if sahm_triggered else " — not triggered")
        indicator = Text.from_markup("[red]⛔ VETO[/]") if sahm_triggered else Text.from_markup("[dim]✓ clear[/]")
        tbl.add_row(
            # Not a points contribution like the rows above it - a hard veto that caps the
            # final allocation directly - so Pts/Max stay "--" rather than smuggling "cap 25%"
            # into what's otherwise a numeric points-range column (BUG FOUND 2026-08-21).
            Text("Sahm Rule", style="red bold" if sahm_triggered else "dim"),
            Text("VETO" if sahm_triggered else "--", style="red bold" if sahm_triggered else "dim"),
            Text("--", style="dim"),
            indicator,
            Text(val_s, style="red" if sahm_triggered else "white"),
            "Recession veto — 3mo avg unemployment vs. trailing-12mo low",
        )

    rows.append(tbl)

    timestamp_val = exp_f.get("timestamp") if isinstance(exp_f, dict) else None
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    stale_warning = _stale_warning(exp_f)
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title=rf"[bold blue]EXPOSURE SCORE - EXPANDED[/]{age_s}{stale_warning}  [dim]\[x] return[/]",
        border_style="blue" if not stale_warning else "yellow",
        padding=(0, 1),
    )


__all__ = [
    "panel_exposure_compact",
    "panel_exposure_expanded",
]
