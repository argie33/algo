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
        # FIXED 2026-08-22 (exposure-model integrity review): these 7 used to be a
        # separate "adjustment" display category (sector_rotation/economic_overlay/
        # cross_asset_confirmation/fundamental_quality, penalty-only, own bar rendering
        # via _delta_bar_markup). They're now normal scored factors on the same 0-100/pts-
        # of-max footing as everything above, so they get normal factor_detail entries too
        # instead of a special-cased second table section.
        if key == "yield_curve":
            t2 = f.get("t10y2y", {}).get("value") if isinstance(f.get("t10y2y"), dict) else None
            t3 = f.get("t10y3m", {}).get("value") if isinstance(f.get("t10y3m"), dict) else None
            parts = []
            if isinstance(t2, (int, float)):
                parts.append(f"2s10s{t2:+.2f}")
            if isinstance(t3, (int, float)):
                parts.append(f"3m10y{t3:+.2f}")
            return f" {' '.join(parts)}" if parts else "[yellow]⚠[/]"
        if key == "financial_conditions":
            v = safe_float(f.get("value"), default=None)
            return f" ANFCI {v:.2f}" if v is not None else "[yellow]⚠[/]"
        if key == "financial_stress":
            v = safe_float(f.get("value"), default=None)
            return f" STLFSI4 {v:.2f}" if v is not None else "[yellow]⚠[/]"
        if key == "inflation_expectations":
            v = safe_float(f.get("value"), default=None)
            return f" BE {v:.2f}%" if v is not None else "[yellow]⚠[/]"
        if key == "sector_rotation":
            sig = f.get("signal")
            dls = f.get("defensive_lead_score")
            if isinstance(sig, str) and isinstance(dls, (int, float)):
                return f" {sig.replace('_', ' ')[:14]} {dls:.0f}"
            return "[yellow]⚠[/]"
        if key == "cross_asset_confirmation":
            z = safe_float(f.get("composite_z"), default=None)
            n = f.get("n_signals")
            return f" z={z:+.1f} n={n}" if z is not None else "[yellow]⚠[/]"
        if key == "earnings_revision_breadth":
            rev = f.get("revision_breadth_pct")
            return f" {rev:.0f}% rising" if isinstance(rev, (int, float)) else "[yellow]⚠[/]"
        if key == "valuation_extension_breadth":
            bp = f.get("breadth_pct")
            return f" {bp:.0f}% extended" if isinstance(bp, (int, float)) else "[yellow]⚠[/]"
        return "[yellow]⚠[/]"  # Unknown factor key

    factor_map = [
        ("trend_30wk", "30-Week Trend", 11.25),
        ("spy_momentum", "SPY 12mo Mom", 7.5),
        ("breadth_200dma", "Breadth 200MA", 7.5),
        ("distribution_days", "Sell Pressure", 7.5),
        ("vix_regime", "VIX Regime", 7.5),
        ("credit_spread", "Credit Spread", 7.5),
        ("put_call_ratio", "Put/Call", 6),
        ("new_highs_lows", "New Hi vs Lo", 5.25),
        ("ad_line", "Adv/Dec Line", 4.5),
        ("breadth_50dma", "Breadth 50 MA", 4.5),
        ("positioning", "Positioning", 3.75),
        ("aaii_sentiment", "AAII Survey", 2.25),
        ("yield_curve", "Yield Curve", 4),
        ("financial_conditions", "Fin Conditions", 4),
        ("financial_stress", "Fin Stress", 2),
        ("inflation_expectations", "Infl Expect", 1),
        ("sector_rotation", "Sector Rotation", 5),
        ("cross_asset_confirmation", "Cross-Asset", 5),
        ("earnings_revision_breadth", "Earnings Revisions", 2.5),
        ("valuation_extension_breadth", "Valuation Ext", 1.5),
    ]

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)

    items = []
    for key, label, max_pts in factor_map:
        if not factors or key not in factors:
            logger.warning("[EXPOSURE] factor %s not in response - data unavailable", key)
            items.append(f"[dim]{label}:[/] [yellow]⚠ factor unavailable[/][dim] /{max_pts:g}[/]")
            continue

        f: dict[str, Any] = factors[key]
        if not isinstance(f, dict):
            logger.warning("[EXPOSURE] factor %s has invalid type: %s, expected dict", key, type(f).__name__)
            items.append(f"[dim]{label}:[/] [yellow]⚠ invalid data type[/][dim] /{max_pts:g}[/]")
            continue

        pts_raw = f.get("pts")
        if pts_raw is None:
            reason = f.get("reason")
            if reason is None:
                reason = "data unavailable"
            logger.warning("[EXPOSURE] factor %s missing pts field: %s", key, reason)
            items.append(f"[dim]{label}:[/] [yellow]⚠ {reason[:20]}[/][dim] /{max_pts:g}[/]")
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
            items.append(f"[dim]{label}:[/] {bar} [{fc}]{pts:.0f}/{max_pts:g}[/]{det_s}")

    # FIXED 2026-08-22 (exposure-model integrity review): sector_rotation, the old
    # economic_overlay (now 4 separate factors), cross_asset_confirmation, and the old
    # fundamental_quality (now split into earnings_revision_breadth and
    # valuation_extension_breadth) used to be a special "adjustment" display category
    # rendered here as a second block of rows with their own bar style. They're normal
    # scored factors now (see factor_map above) and render through the same loop as
    # everything else. Sahm Rule is the one signal that's still genuinely different in kind
    # (a hard veto, not a graded score), so it keeps its own block below.
    sahm = None
    if factors and isinstance(factors, dict):
        sahm_raw = factors.get("sahm_rule")
        if isinstance(sahm_raw, dict):
            sahm = sahm_raw

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
    """Full-screen exposure score detail - all 19 factors with values, thresholds, and signal context."""
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

    # Per-factor detail table. FIXED 2026-08-22 (exposure-model integrity review):
    # sector_rotation/economic_overlay/cross_asset_confirmation/fundamental_quality used
    # to be a separate "adjustment" table section below this one, rendered as +/- deltas
    # around zero with their own bar style. They're normal weighted factors now (0..max,
    # same footing as everything else), so they're rows in this same table - the old
    # economic_overlay is 4 separate rows (yield_curve/financial_conditions/
    # financial_stress/inflation_expectations), each a real standalone or correlation-
    # checked-non-redundant signal rather than one blended composite. Only Sahm Rule keeps
    # its own block below - it's a hard veto, not a graded score, genuinely a different
    # kind of thing.
    factor_map_exp = [
        ("trend_30wk", "30-Week Trend", 11.25, "SPY above 30-week MA?"),
        ("spy_momentum", "SPY 12mo Momentum", 7.5, "12-month SPY return"),
        ("breadth_200dma", "Breadth 200 DMA", 7.5, "% stocks above 200DMA"),
        ("distribution_days", "Sell Pressure", 7.5, "Distribution day count"),
        ("vix_regime", "VIX + Trend", 7.5, "Fear gauge + genuine day-over-day trend"),
        ("credit_spread", "Credit Spread", 7.5, "HY OAS level + 20d widening"),
        ("put_call_ratio", "Put/Call Ratio", 6, "Options sentiment signal"),
        ("new_highs_lows", "New Highs vs Lows", 5.25, "NYSE new highs minus lows"),
        ("ad_line", "Advance/Decline", 4.5, "Breadth momentum direction"),
        ("breadth_50dma", "Breadth 50 DMA", 4.5, "% stocks above 50DMA"),
        ("positioning", "Positioning & Flows", 3.75, "Insider buying breadth + short interest trend"),
        ("aaii_sentiment", "AAII Sentiment", 2.25, "Retail investor bull/bear"),
        ("yield_curve", "Yield Curve", 4, "T10Y2Y + T10Y3M avg, z-scored vs own history"),
        ("financial_conditions", "Financial Conditions", 4, "ANFCI (Chicago Fed), z-scored standalone"),
        ("financial_stress", "Financial Stress", 2, "STLFSI4 (St. Louis Fed), z-scored standalone"),
        ("inflation_expectations", "Inflation Expectations", 1, "T5YIE + T10YIE breakeven avg, z-scored"),
        ("sector_rotation", "Sector Rotation", 5, "Defensive vs. cyclical sector leadership"),
        ("cross_asset_confirmation", "Cross-Asset Confirmation", 5, "Gold/bonds/USD/oil vs. equities, z-scored"),
        ("earnings_revision_breadth", "Earnings Revision Breadth", 2.5, "Analyst target-price revisions, 30d"),
        ("valuation_extension_breadth", "Valuation Extension Breadth", 1.5, "% of universe at extended P/E or P/S"),
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
            bar_s = Text.from_markup(f"[yellow]⚠ N/A{'':>7}[/]  [dim]--/{max_pts:g}[/]")
            tbl.add_row(
                Text(label, style="yellow"),
                Text("--", style="yellow"),
                Text(f"{max_pts:g}", style="dim"),
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
            bar_s = Text.from_markup(f"[red]✗ ERR{'':>7}[/]  [dim]--/{max_pts:g}[/]")
            tbl.add_row(
                Text(label, style="red"),
                Text("--", style="red"),
                Text(f"{max_pts:g}", style="dim"),
                bar_s,
                Text(f"✗ {reason}", style="red"),
                context,
            )
            continue
        bar_f = int(min(pts / max_pts, 1.0) * 12) if max_pts > 0 and pts is not None else 12
        fc = G if pts is not None and pts >= max_pts * 0.75 else (Y if pts is not None and pts >= max_pts * 0.35 else R)
        bar_s = Text.from_markup(f"[{fc}]{'█' * bar_f}[/][dim]{'░' * (12 - bar_f)}[/]  [{fc}]{pts:.0f}/{max_pts:g}[/]")

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
        elif key == "yield_curve":
            t2 = f.get("t10y2y", {}).get("value") if isinstance(f.get("t10y2y"), dict) else None
            t3 = f.get("t10y3m", {}).get("value") if isinstance(f.get("t10y3m"), dict) else None
            parts = []
            if isinstance(t2, (int, float)):
                parts.append(f"2s10s {t2:+.2f}")
            if isinstance(t3, (int, float)):
                parts.append(f"3m10y {t3:+.2f}")
            val_s = " / ".join(parts) if parts else "--"
        elif key == "financial_conditions":
            v = f.get("value")
            z = f.get("z")
            val_s = f"ANFCI {v:.2f} (z={z:+.1f})" if isinstance(v, (int, float)) else "--"
        elif key == "financial_stress":
            v = f.get("value")
            z = f.get("z")
            val_s = f"STLFSI4 {v:.2f} (z={z:+.1f})" if isinstance(v, (int, float)) else "--"
        elif key == "inflation_expectations":
            v = f.get("value")
            val_s = f"breakeven {v:.2f}%" if isinstance(v, (int, float)) else "--"
        elif key == "sector_rotation":
            sig = f.get("signal")
            dls = f.get("defensive_lead_score")
            if sig == "data_unavailable":
                reason = f.get("reason") or "insufficient rotation history yet (<12wk)"
                val_s = f"n/a — {reason}"
            else:
                sig_display = sig.replace("_", " ") if isinstance(sig, str) else "unknown"
                dls_display = f", lead {dls:.0f}/100" if isinstance(dls, (int, float)) else ""
                val_s = f"{sig_display}{dls_display}"
        elif key == "cross_asset_confirmation":
            z = f.get("composite_z")
            chg_parts = [
                f"{label_ca} {v:+.1f}%"
                for label_ca, key_ca in (
                    ("Gold", "gld_vs_spy_chg_20d"),
                    ("Bonds", "tlt_vs_spy_chg_20d"),
                    ("USD", "usd_chg_20d"),
                    ("Oil", "oil_chg_20d"),
                )
                if isinstance((v := f.get(key_ca)), (int, float))
            ]
            val_s = (f"z={z:+.1f}" if isinstance(z, (int, float)) else "--") + (
                f" — {' '.join(chg_parts)}" if chg_parts else ""
            )
        elif key == "earnings_revision_breadth":
            rev = f.get("revision_breadth_pct")
            val_s = f"{rev:.0f}% of universe rising" if isinstance(rev, (int, float)) else "--"
        elif key == "valuation_extension_breadth":
            bp = f.get("breadth_pct")
            active = f.get("active_count")
            active_s = f" (n={active})" if isinstance(active, (int, float)) else ""
            val_s = f"{bp:.0f}% at extended P/E or P/S{active_s}" if isinstance(bp, (int, float)) else "--"

        tbl.add_row(
            Text(label, style=fc),
            Text(f"{pts:.1f}", style=fc),
            Text(f"{max_pts:g}", style="dim"),
            bar_s,
            Text(val_s, style="white"),
            context,
        )

    # FIXED 2026-08-22 (exposure-model integrity review): sector_rotation, the old
    # economic_overlay, cross_asset_confirmation, and fundamental_quality used to render
    # here as a separate "adjustment" block (+/- deltas around zero, own bar style). All
    # of them (now including the earnings-revision/valuation-extension split of what was
    # fundamental_quality - see market_exposure.py's module docstring) are normal weighted
    # factors and already rendered by the factor_map_exp loop above. Sahm Rule is the one
    # signal that's still genuinely different in kind (a hard veto, not a graded score),
    # so it keeps its own row below.
    sahm = None
    if factors and isinstance(factors, dict) and not error_boundary.has_error(factors):
        sahm_raw = factors.get("sahm_rule")
        if isinstance(sahm_raw, dict) and not error_boundary.has_error(sahm_raw):
            sahm = sahm_raw

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
