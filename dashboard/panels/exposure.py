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

# 3-pillar architecture (2026-08-23 redesign, reweighted 2026-08-24 to Trend-only - see
# algo/risk/market_exposure.py's module docstring for the full evidence framework). Each
# pillar's "factors" entry carries a "components" sub-dict with the individual sub-signal
# detail used below for display. Deliberately no hardcoded max_pts here: the 2026-08-24
# pass dropped pillar_risk/pillar_confirm to 0 weight (veto/context only) while
# pillar_trend rose to 100 - the real weight always comes from each pillar's own "max"
# field in the API response so this file can't silently drift out of sync with
# market_exposure.py's W_PILLAR_* constants the way it did before this fix.
PILLAR_MAP = [
    ("pillar_trend", "Trend & Momentum"),
    ("pillar_risk", "Independent Risk"),
    ("pillar_confirm", "Breadth & Sentiment"),
]


def _stale_warning(exp_f: Any) -> str:
    """Server-computed staleness badge from the API's data_freshness field."""
    if not isinstance(exp_f, dict):
        return ""
    data_freshness = exp_f.get("data_freshness")
    if isinstance(data_freshness, dict) and data_freshness.get("is_stale"):
        warning_text = data_freshness.get("warning") or "stale"
        logger.warning(f"[EXPOSURE] Exposure data stale: {warning_text}")
        return " [yellow]⚠ STALE[/]"
    return ""


def _component_value(components: dict[str, Any], sub_key: str, field: str) -> float | None:
    """Read one numeric field from a sub-component, treating an error-marked or missing
    sub-component the same as a missing field (matches error_boundary.has_error's contract:
    a component that failed to compute must render as unavailable, not as a false zero)."""
    sub = components.get(sub_key)
    if error_boundary.has_error(sub) or not isinstance(sub, dict):
        return None
    return safe_float(sub.get(field), default=None)


def _pillar_detail(key: str, f: dict[str, Any]) -> str:
    """Short value string summarizing a pillar's component detail for the compact panel."""
    if error_boundary.has_error(f):
        return "[yellow]⚠[/]"
    components = f.get("components")
    if error_boundary.has_error(components) or not isinstance(components, dict):
        return "[yellow]⚠[/]"

    if key == "pillar_trend":
        # PASS 2026-08-24b: trend_30wk is the sole scored input (SUBW_TREND_30WK=1.0);
        # spy_momentum/market_technicals are computed/shown but no longer scored - see
        # market_exposure.py's "PILLAR 1 SUB-WEIGHT EVIDENCE". Tagged "(ctx)" so this
        # doesn't read as if momentum still moves the score.
        ma_pct = _component_value(components, "trend_30wk", "price_vs_ma_pct")
        mom_val = _component_value(components, "spy_momentum", "value")
        parts = []
        if ma_pct is not None:
            parts.append(f"MA:{'+' if ma_pct >= 0 else ''}{ma_pct:.1f}%")
        if mom_val is not None:
            parts.append(f"Mom:{mom_val:+.1f}%(ctx)")
        return f" {' '.join(parts)}" if parts else "[yellow]⚠[/]"

    if key == "pillar_risk":
        vix_v = _component_value(components, "vix_regime", "value")
        cs_v = _component_value(components, "credit_spread", "value")
        sp = components.get("selling_pressure")
        sp_c = None if error_boundary.has_error(sp) or not isinstance(sp, dict) else sp.get("count")
        parts = []
        if vix_v is not None:
            parts.append(f"VIX:{vix_v:.1f}")
        if cs_v is not None:
            parts.append(f"HY:{cs_v:.2f}%")
        if isinstance(sp_c, (int, float)):
            parts.append(f"SP:{int(sp_c)}d")
        return f" {' '.join(parts)}" if parts else "[yellow]⚠[/]"

    if key == "pillar_confirm":
        participation = components.get("participation")
        sentiment = components.get("sentiment")
        b50 = (
            None
            if error_boundary.has_error(participation) or not isinstance(participation, dict)
            else _component_value(participation, "breadth", "pct_above_50")
        )
        spread = (
            None
            if error_boundary.has_error(sentiment) or not isinstance(sentiment, dict)
            else _component_value(sentiment, "aaii_sentiment", "spread")
        )
        parts = []
        if b50 is not None:
            parts.append(f"B:{b50:.0f}%")
        if spread is not None:
            parts.append(f"AAII:{spread:+.0f}")
        return f" {' '.join(parts)}" if parts else "[yellow]⚠[/]"

    return "[yellow]⚠[/]"


def _vol_managed_scaling_item(factors: dict[str, Any]) -> str:
    """Compact-panel summary line for the vol-managed multiplier (Layer 2, Moreira &
    Muir - active since 2026-08-24). Degrades to an unavailable marker (never hidden -
    same convention as the pillar rows above) if the key is absent, e.g. an older cached
    row predating activation."""
    vms = factors.get("vol_managed_scaling")
    mult = vms.get("multiplier") if isinstance(vms, dict) else None
    if isinstance(mult, (int, float)):
        mc = G if mult > 1.02 else (Y if mult < 0.98 else "dim")
        return f"[dim]Vol-Managed Scaling:[/] [{mc}]x{mult:.2f}[/]"
    return "[dim]Vol-Managed Scaling:[/] [yellow]⚠ unavailable[/]"


def _policy_tier_compact_item(exp_f: dict[str, Any]) -> str:
    """Compact-panel summary line for the active EXPOSURE_TIERS policy tier - the concrete
    trading consequence of exposure_pct (how selective, how many new positions today, how
    concentrated a position can get), not just the score itself. See
    exposure_policy_tier_dashboard_gap_fixed_20260824 in memory for why this row exists:
    min_composite_score alone was retuned 3x in one day with no dashboard surface to see it.
    Degrades to a visible unavailable marker, same convention as every other row here."""
    tier = exp_f.get("active_tier") if isinstance(exp_f, dict) else None
    if not isinstance(tier, dict):
        return "[dim]Policy Tier:[/] [yellow]⚠ unavailable[/]"

    # _TIER_CONFIG (lambda/api/routes/algo_handlers/signals.py) always sets both the short
    # alias ("risk_mult"/"max_new"/"halt") and the long EXPOSURE_TIERS field name to the
    # identical value - reading just the short alias loses nothing and keeps this function
    # under the fail-fast lint's 5-.get()-lines-without-has_error() threshold.
    name, halted = tier.get("name", "?"), bool(tier.get("halt"))
    max_new, risk_mult = tier.get("max_new"), tier.get("risk_mult")
    min_score, max_conc = tier.get("min_composite_score"), tier.get("max_concentration_pct")

    status = "[red]HALTED[/]" if halted else (f"{max_new} new/day" if max_new is not None else "? new/day")
    parts = [f"[dim]Policy Tier:[/] [bold]{name}[/] · {status}"]
    if isinstance(risk_mult, (int, float)):
        parts.append(f"size x{risk_mult:g}")
    if isinstance(min_score, (int, float)):
        parts.append(f"min score {min_score:g}")
    if isinstance(max_conc, (int, float)):
        parts.append(f"max conc {max_conc:g}%")
    return " · ".join(parts)


@register_panel(
    "exp",
    endpoint_deps=["exp_factors"],
    optional=True,
    description="Exposure",
)
def panel_exposure_compact(exp_f: Any) -> Any:
    """Exposure score breakdown - compact 2-col layout (3 pillars + macro watch)."""
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

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)

    items = []
    for key, label in PILLAR_MAP:
        if not factors or key not in factors:
            logger.warning("[EXPOSURE] pillar %s not in response - data unavailable", key)
            items.append(f"[dim]{label}:[/] [yellow]⚠ pillar unavailable[/]")
            continue

        f: dict[str, Any] = factors[key]
        if not isinstance(f, dict):
            logger.warning("[EXPOSURE] pillar %s has invalid type: %s, expected dict", key, type(f).__name__)
            items.append(f"[dim]{label}:[/] [yellow]⚠ invalid data type[/]")
            continue

        pts_raw = f.get("pts")
        if pts_raw is None:
            reason = f.get("reason") or "data unavailable"
            logger.warning("[EXPOSURE] pillar %s missing pts field: %s", key, reason)
            items.append(f"[dim]{label}:[/] [yellow]⚠ {reason[:20]}[/]")
            continue

        try:
            pts = safe_float(pts_raw, field_name=f"{label}_pts", strict=True)
        except StrictValidationError as e:
            items.append(f"[dim]{label}:[/] [yellow]⚠ {str(e)[:30]}[/]")
            continue
        if not isinstance(pts, float):
            items.append(f"[dim]{label}:[/] [yellow]⚠ pts conversion failed[/]")
            continue

        max_raw = f.get("max")
        if max_raw is None:
            logger.warning("[EXPOSURE] pillar %s missing max field", key)
            items.append(f"[dim]{label}:[/] [yellow]⚠ pillar weight unavailable[/]")
            continue
        try:
            max_pts = safe_float(max_raw, field_name=f"{label}_max", strict=True)
        except StrictValidationError as e:
            items.append(f"[dim]{label}:[/] [yellow]⚠ {str(e)[:30]}[/]")
            continue
        if not isinstance(max_pts, float):
            logger.warning("[EXPOSURE] pillar %s missing max field", key)
            items.append(f"[dim]{label}:[/] [yellow]⚠ pillar weight unavailable[/]")
            continue

        det = _pillar_detail(key, f)
        det_s = f" [dim]{det.strip()}[/]" if det else ""

        if max_pts <= 0:
            # Zero-weight pillar (veto/context only, e.g. pillar_risk/pillar_confirm since
            # the 2026-08-24 reweight) - a colored 0/N bar here would misleadingly read as
            # "failing" rather than "not part of the composite by design". Show its raw
            # 0-100 internal reading instead, with no bar.
            score_raw = f.get("score")
            score_s = f"{score_raw:.0f}/100" if isinstance(score_raw, (int, float)) else "--"
            items.append(f"[dim]{label}:[/] [dim]not scored (veto/context only) · reads {score_s}[/]{det_s}")
        else:
            bar = mini_bar(pts, max_pts, w=4)
            fc = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
            items.append(f"[dim]{label}:[/] {bar} [{fc}]{pts:.0f}/{max_pts:g}[/]{det_s}")

    macro_watch = factors.get("macro_watch") if isinstance(factors, dict) else None
    if isinstance(macro_watch, dict):
        slow_veto = macro_watch.get("slow_macro_veto") or {}
        if slow_veto.get("triggered"):
            reasons = slow_veto.get("reasons") or []
            items.append(f"[yellow]Macro Watch:[/] [yellow]⚠ {'; '.join(reasons)[:60]}[/]")
        else:
            items.append("[dim]Macro Watch:[/] [dim]clear (Sahm/yield curve/inflation - slow veto only)[/]")

    # Vol-Managed Scaling (Layer 2, Moreira & Muir - active since 2026-08-24) multiplies
    # the pillar score BEFORE hard-veto capping (see market_exposure.py's compute()) - it
    # can move exposure_pct day-to-day on its own, so it must be visible here, not just
    # baked silently into the headline number.
    items.append(_vol_managed_scaling_item(factors))
    items.append(_policy_tier_compact_item(exp_f))

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
        title=rf"[bold blue]EXPOSURE SCORE BREAKDOWN (3 pillars / 100pts)[/]{age_s}{stale_warning}  [dim]\[x] expand[/]",
        border_style="blue" if not stale_warning else "yellow",
        padding=(0, 1),
    )


def _safe_component(components: dict[str, Any], sub_key: str) -> dict[str, Any]:
    """Read one sub-component, treating an error-marked entry as absent (matches
    error_boundary.has_error's contract: a component that failed to compute must render
    as unavailable, not have its stale/missing fields silently read as real values)."""
    sub = components.get(sub_key)
    return sub if isinstance(sub, dict) and not error_boundary.has_error(sub) else {}


def _pillar_expanded_rows(
    key: str, label: str, max_pts: float, context: str, f: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """Build (sub_label, value_string, context) rows for one pillar's components, used
    by the expanded panel to show each sub-signal beneath its pillar's summary row.
    """
    if error_boundary.has_error(f):
        return [("  (unavailable)", "--", "pillar failed to compute - see summary row above")]
    components = f.get("components")
    if error_boundary.has_error(components) or not isinstance(components, dict):
        return [("  (unavailable)", "--", "sub-component detail failed to compute")]
    rows: list[tuple[str, str, str]] = []

    if key == "pillar_trend":
        # PASS 2026-08-24b: trend_30wk alone is scored (SUBW_TREND_30WK=1.0); momentum
        # and market_technicals are still computed/persisted every run but contribute
        # zero to pillar_trend_score - see market_exposure.py's "PILLAR 1 SUB-WEIGHT
        # EVIDENCE" for the backtest that dropped their weight. Labeled "not scored" here
        # rather than the stale "35%/10% of pillar" so this panel can't imply they still
        # move the score.
        t30 = _safe_component(components, "trend_30wk")
        mom = _safe_component(components, "spy_momentum")
        mtech = _safe_component(components, "market_technicals")
        v = t30.get("price_vs_ma_pct")
        rows.append(
            (
                "  30-Week Trend",
                f"{v:+.1f}% vs MA" if isinstance(v, (int, float)) else "--",
                "SPY vs 30-week MA (100% of pillar - the sole scored input)",
            )
        )
        v = mom.get("value")
        rows.append(
            (
                "  SPY 12mo Momentum",
                f"{v:+.1f}%" if isinstance(v, (int, float)) else "--",
                "Trailing 12-month return, TSMOM (not scored - context/dashboard only)",
            )
        )
        if mtech.get("data_unavailable"):
            rows.append(
                (
                    "  Market Technicals",
                    f"⚠ {mtech.get('reason', '')[:30]}",
                    "RSI(14)+MACD, blended (not scored - context/dashboard only)",
                )
            )
        else:
            rsi = mtech.get("rsi_14")
            macd_z = mtech.get("macd_z")
            macd_s = f" MACD(z={macd_z:+.1f})" if isinstance(macd_z, (int, float)) else ""
            rows.append(
                (
                    "  Market Technicals",
                    f"RSI {rsi:.1f}{macd_s}" if isinstance(rsi, (int, float)) else "--",
                    "RSI(14)+MACD, blended (not scored - context/dashboard only)",
                )
            )

    elif key == "pillar_risk":
        vix = _safe_component(components, "vix_regime")
        cs = _safe_component(components, "credit_spread")
        sp = _safe_component(components, "selling_pressure")
        v = vix.get("value")
        rows.append(
            (
                "  VIX Regime",
                f"VIX {v:.1f}" if isinstance(v, (int, float)) else "--",
                "Volatility level + 5-session trend",
            )
        )
        v = cs.get("value")
        rows.append(
            ("  Credit Spread", f"{v:.2f}% OAS" if isinstance(v, (int, float)) else "--", "HY OAS, credit leads equity")
        )
        cnt = sp.get("count")
        rg = sp.get("regime")
        rg_s = rg[:10] if isinstance(rg, str) else "?"
        rows.append(
            (
                "  Selling Pressure",
                f"{cnt}d / {rg_s}" if cnt is not None else "--",
                "Heavy-volume down days, last 25 sessions",
            )
        )

    elif key == "pillar_confirm":
        participation = _safe_component(components, "participation")
        sentiment = _safe_component(components, "sentiment")
        breadth = _safe_component(participation, "breadth")
        nhnl = _safe_component(participation, "new_highs_lows")
        ad = _safe_component(participation, "ad_line")
        aaii = _safe_component(sentiment, "aaii_sentiment")
        pc = _safe_component(sentiment, "put_call_ratio")
        b50 = breadth.get("pct_above_50")
        b200 = breadth.get("pct_above_200")
        rows.append(
            (
                "  Breadth",
                f"50d:{b50:.0f}% / 200d:{b200:.0f}%"
                if isinstance(b50, (int, float)) and isinstance(b200, (int, float))
                else "--",
                "% stocks above 50/200-DMA, blended 37.5%/62.5%",
            )
        )
        nh, nl = nhnl.get("new_highs"), nhnl.get("new_lows")
        rows.append(
            (
                "  New Highs/Lows",
                f"NH:{nh} NL:{nl} {nh - nl:+d}" if isinstance(nh, int) and isinstance(nl, int) else "--",
                "52-week new highs vs lows",
            )
        )
        rel = ad.get("relation")
        rows.append(
            ("  Advance/Decline", rel.replace("_", " ") if isinstance(rel, str) else "--", "A/D direction vs SPY")
        )
        bull, bear = aaii.get("bullish_pct"), aaii.get("bearish_pct")
        rows.append(
            (
                "  Retail Sentiment (AAII)",
                f"Bull:{bull:.0f}% Bear:{bear:.0f}%"
                if isinstance(bull, (int, float)) and isinstance(bear, (int, float))
                else "--",
                "Contrarian at extremes only",
            )
        )
        if pc.get("data_unavailable"):
            rows.append(
                ("  Put/Call Ratio", f"⚠ {pc.get('reason', '')[:30]}", "Options sentiment, contrarian at extremes")
            )
        else:
            v = pc.get("value")
            rows.append(
                (
                    "  Put/Call Ratio",
                    f"{v:.2f} P/C" if isinstance(v, (int, float)) else "--",
                    "Options sentiment, contrarian at extremes",
                )
            )

    return rows


def panel_exposure_expanded(exp_f: Any) -> Any:  # noqa: C901
    """Full-screen exposure score detail - 3 pillars with sub-component values, plus macro watch."""
    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold blue]x[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]
    err_panel = _error_panel("exposure factors", exp_f, "EXPOSURE SCORE - EXPANDED", border="blue")
    if err_panel:
        return err_panel

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

    pillar_context = {
        "pillar_trend": "100% Faber 30wk-MA trend (sole scored input) - backtest-confirmed vs TSMOM blend, 2026-08-24b",
        "pillar_risk": "Equal-weighted: VIX, Credit Spread, Selling Pressure - mechanically distinct, co-move in risk-off",
        "pillar_confirm": "Confirmation role - Participation (breadth/NH-NL/A-D) + Sentiment (AAII/Put-Call), 50/50",
    }

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        padding=(0, 2),
        expand=True,
        row_styles=["", "dim"],
    )
    tbl.add_column("Pillar / Component", no_wrap=True, min_width=22, max_width=30)
    tbl.add_column("Pts", justify="right", no_wrap=True, width=5)
    tbl.add_column("Max", justify="right", no_wrap=True, width=9)
    tbl.add_column("Score", no_wrap=True, width=19)
    tbl.add_column("Value", no_wrap=False, ratio=2, min_width=16, max_width=36)
    tbl.add_column("Context", style="dim", no_wrap=False, ratio=3, min_width=18)

    for key, label in PILLAR_MAP:
        f: dict[str, Any] = {}
        if error_boundary.has_error(factors):
            f = {}
        elif key not in factors:
            logger.debug("[EXPOSURE_EXPANDED] pillar %s not in response", key)
            f = {}
        else:
            f = factors[key]
            if not isinstance(f, dict):
                logger.warning("[EXPOSURE_EXPANDED] pillar %s has invalid type: %s", key, type(f).__name__)
                f = {}
            elif error_boundary.has_error(f):
                f = {}

        max_raw = f.get("max") if f else None
        max_pts = safe_float(max_raw, default=None) if max_raw is not None else None

        pts_raw = f.get("pts") if f else None
        if pts_raw is None or max_pts is None or (f and f.get("data_unavailable")):
            reason_val = f.get("reason") if f else None
            if reason_val is None:
                reason_val = "stale" if f and f.get("stale") else "no data"
            reason = reason_val[:18]
            logger.error("[EXPOSURE_EXPANDED] data_unavailable: pillar=%s, reason=%s", key, reason)
            max_s = f"{max_pts:g}" if max_pts is not None else "?"
            bar_s = Text.from_markup(f"[yellow]⚠ N/A{'':>7}[/]  [dim]--/{max_s}[/]")
            tbl.add_row(
                Text(label, style="yellow bold"),
                Text("--", style="yellow"),
                Text(max_s, style="dim"),
                bar_s,
                Text(f"⚠ {reason}", style="yellow"),
                pillar_context.get(key, ""),
            )
            continue

        try:
            pts = safe_float(pts_raw, field_name=f"{label}_pts", strict=True)
        except StrictValidationError as e:
            reason = f"invalid: {str(e)[:12]}"
            bar_s = Text.from_markup(f"[red]✗ ERR{'':>7}[/]  [dim]--/{max_pts:g}[/]")
            tbl.add_row(
                Text(label, style="red bold"),
                Text("--", style="red"),
                Text(f"{max_pts:g}", style="dim"),
                bar_s,
                Text(f"✗ {reason}", style="red"),
                pillar_context.get(key, ""),
            )
            continue
        if not isinstance(pts, float):
            bar_s = Text.from_markup(f"[red]✗ ERR{'':>7}[/]  [dim]--/{max_pts:g}[/]")
            tbl.add_row(
                Text(label, style="red bold"),
                Text("--", style="red"),
                Text(f"{max_pts:g}", style="dim"),
                bar_s,
                Text("✗ pts conversion failed", style="red"),
                pillar_context.get(key, ""),
            )
            continue

        score_val = f.get("score")
        if max_pts <= 0:
            # Zero-weight pillar (veto/context only since the 2026-08-24 reweight) - a
            # pts/max bar here would either divide by zero or (worse) render as a
            # misleadingly full/empty bar. Show its raw 0-100 internal reading instead.
            score_s = f"{score_val:.1f}/100" if isinstance(score_val, (int, float)) else "--"
            bar_s = Text.from_markup(f"[dim]not scored{'':>2}[/]  [dim]--/0[/]")
            tbl.add_row(
                Text(label, style="dim bold"),
                Text("--", style="dim"),
                Text("0", style="dim"),
                bar_s,
                Text(f"veto/context only · reads {score_s}", style="dim"),
                pillar_context.get(key, ""),
            )
        else:
            bar_f = int(min(pts / max_pts, 1.0) * 12)
            fc = G if pts >= max_pts * 0.75 else (Y if pts >= max_pts * 0.35 else R)
            bar_s = Text.from_markup(
                f"[{fc}]{'█' * bar_f}[/][dim]{'░' * (12 - bar_f)}[/]  [{fc}]{pts:.0f}/{max_pts:g}[/]"
            )
            tbl.add_row(
                Text(label, style=f"{fc} bold"),
                Text(f"{pts:.1f}", style=fc),
                Text(f"{max_pts:g}", style="dim"),
                bar_s,
                Text(f"score {score_val:.1f}/100" if isinstance(score_val, (int, float)) else "--", style="white"),
                pillar_context.get(key, ""),
            )
        for sub_label, val_s, ctx in _pillar_expanded_rows(key, label, max_pts, "", f):
            tbl.add_row(Text(sub_label, style="dim"), Text(""), Text(""), Text(""), Text(val_s, style="white"), ctx)

    rows.append(tbl)
    rows.append(Rule(style="dim"))

    # Macro Watch - Sahm Rule / Yield Curve / Inflation Expectations. Not scored in the
    # composite (see market_exposure.py's module docstring, "Slow macro veto") - they
    # lead by 6-24 months (Estrella-Mishkin), the wrong horizon for this system's
    # responsive dial, so they feed only a slow, wide veto instead of composite points.
    macro_watch = factors.get("macro_watch")
    if isinstance(macro_watch, dict):
        slow_veto = macro_watch.get("slow_macro_veto") or {}
        triggered = slow_veto.get("triggered")
        veto_style = "yellow" if triggered else "dim"
        veto_s = "⚠ TRIGGERED - exposure capped 45%" if triggered else "clear"
        header_text = f"[bold]Macro Watch[/] [dim](Sahm/Yield Curve/Inflation - slow veto only, not composite-scored)[/]  [{veto_style}]{veto_s}[/]"
        rows.append(Text.from_markup(header_text))

        sahm = macro_watch.get("sahm_rule") or {}
        yc = macro_watch.get("yield_curve") or {}
        infl = macro_watch.get("inflation_expectations") or {}

        macro_tbl = Table.grid(padding=(0, 2), expand=True)
        macro_tbl.add_column("a", ratio=1)
        macro_tbl.add_column("b", ratio=1)
        macro_tbl.add_column("c", ratio=1)

        sahm_v = sahm.get("value")
        sahm_trig = sahm.get("triggered")
        sahm_s = (
            f"Sahm: {sahm_v:+.2f}pp{' TRIG' if sahm_trig else ''}"
            if isinstance(sahm_v, (int, float))
            else "Sahm: ⚠ unavailable"
        )

        t2 = yc.get("t10y2y", {}).get("value") if isinstance(yc.get("t10y2y"), dict) else None
        t3 = yc.get("t10y3m", {}).get("value") if isinstance(yc.get("t10y3m"), dict) else None
        yc_parts = []
        if isinstance(t2, (int, float)):
            yc_parts.append(f"2s10s{t2:+.2f}")
        if isinstance(t3, (int, float)):
            yc_parts.append(f"3m10y{t3:+.2f}")
        yc_s = f"Yield Curve: {' '.join(yc_parts)}" if yc_parts else "Yield Curve: ⚠ unavailable"

        infl_v = infl.get("value")
        infl_s = (
            f"Inflation Exp: {infl_v:.2f}% BE" if isinstance(infl_v, (int, float)) else "Inflation Exp: ⚠ unavailable"
        )

        macro_tbl.add_row(Text(sahm_s, style="dim"), Text(yc_s, style="dim"), Text(infl_s, style="dim"))
        rows.append(macro_tbl)

    # Vol-Managed Scaling (Layer 2, Moreira & Muir - active since 2026-08-24): a real
    # multiplier applied to the pillar score before hard-veto capping, so it can move
    # exposure_pct day-to-day independent of the pillars/vetoes shown above.
    vms = factors.get("vol_managed_scaling") if isinstance(factors, dict) else None
    if isinstance(vms, dict):
        mult = vms.get("multiplier")
        note = vms.get("note")
        if isinstance(mult, (int, float)):
            mc = G if mult > 1.02 else (Y if mult < 0.98 else "dim")
            note_s = f"  [dim]{note[:60]}[/]" if isinstance(note, str) else ""
            rows.append(
                Text.from_markup(
                    f"[bold]Vol-Managed Scaling[/] [dim](applied to pillar score before veto caps)[/]  "
                    f"[{mc}]x{mult:.2f}[/]{note_s}"
                )
            )
        else:
            rows.append(Text.from_markup("[bold]Vol-Managed Scaling[/]  [yellow]⚠ unavailable[/]"))

    # Active Policy Tier (algo/risk/exposure_policy.py's EXPOSURE_TIERS) - the concrete
    # trading consequence of exposure_pct/regime above: how selective (min_composite_score),
    # how many new positions today, how concentrated one position can get, and any size-down
    # multiplier - not just the score itself. See exposure_policy_tier_dashboard_gap_fixed_
    # 20260824 in memory: min_composite_score alone was retuned 3x in one day with no
    # dashboard surface to observe the live value.
    rows.append(Rule(style="dim"))
    active_tier = exp_f.get("active_tier") if isinstance(exp_f, dict) else None
    if isinstance(active_tier, dict):
        tier_name = active_tier.get("name", "?")
        tier_halted = bool(active_tier.get("halt") or active_tier.get("halt_new_entries"))
        tier_max_new = active_tier.get("max_new", active_tier.get("max_new_positions_today"))
        tier_risk_mult = active_tier.get("risk_mult", active_tier.get("risk_multiplier"))
        tier_min_score = active_tier.get("min_composite_score")
        tier_max_conc = active_tier.get("max_concentration_pct")
        tier_desc = active_tier.get("description")

        status_s = (
            "[red bold]HALTED - no new entries[/]"
            if tier_halted
            else (
                f"[green]{tier_max_new} new entries allowed/day[/]"
                if tier_max_new is not None
                else "[dim]? entries allowed/day[/]"
            )
        )
        desc_s = f"  [dim]{tier_desc[:60]}[/]" if isinstance(tier_desc, str) else ""
        rows.append(Text.from_markup(f"[bold]Active Policy Tier[/]  [bold]{tier_name}[/]  {status_s}{desc_s}"))

        risk_s = f"x{tier_risk_mult:g}" if isinstance(tier_risk_mult, (int, float)) else "--"
        min_score_s = f"{tier_min_score:g}" if isinstance(tier_min_score, (int, float)) else "--"
        max_conc_s = f"{tier_max_conc:g}%" if isinstance(tier_max_conc, (int, float)) else "--"
        max_new_s = str(tier_max_new) if tier_max_new is not None else "--"

        tier_tbl = Table.grid(padding=(0, 2), expand=True)
        tier_tbl.add_column("a", ratio=1)
        tier_tbl.add_column("b", ratio=1)
        tier_tbl.add_column("c", ratio=1)
        tier_tbl.add_column("d", ratio=1)
        tier_tbl.add_row(
            Text(f"Size multiplier: {risk_s}", style="dim"),
            Text(f"Min composite score: {min_score_s}", style="dim"),
            Text(f"Max concentration: {max_conc_s}", style="dim"),
            Text(f"Max new positions/day: {max_new_s}", style="dim"),
        )
        rows.append(tier_tbl)
    else:
        rows.append(Text.from_markup("[bold]Active Policy Tier[/]  [yellow]⚠ unavailable[/]"))

    timestamp_val = exp_f.get("timestamp") if isinstance(exp_f, dict) else None
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    stale_warning = _stale_warning(exp_f)
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title=rf"[bold blue]EXPOSURE SCORE - EXPANDED[/]{age_s}{stale_warning}  [dim]\[x] return[/]",
        border_style="blue" if not stale_warning else "yellow",
        padding=(0, 1),
    )


@register_panel(
    "cap_route",
    endpoint_deps=["capital_routing"],
    optional=True,
    description="Capital Routing",
)
def panel_capital_routing(cr: Any) -> Any:
    """GLD/IEF/DBC/cash leftover-capital routing - see algo/risk/capital_routing.py."""
    err_panel = _error_panel("capital routing", cr, "CAPITAL ROUTING", border="blue")
    if err_panel:
        return err_panel

    if not isinstance(cr, dict) or cr.get("data_unavailable"):
        reason = cr.get("reason") if isinstance(cr, dict) else "no data"
        return Panel(
            Text.from_markup(f"[dim]Capital routing unavailable: {reason}[/]"),
            title="[bold blue]CAPITAL ROUTING[/]",
            border_style="blue",
            padding=(0, 1),
        )

    uninvested = cr.get("uninvested_capital_pct")
    uninvested_s = f"{uninvested:.1f}%" if isinstance(uninvested, (int, float)) else "--"

    tbl = Table.grid(padding=(0, 2), expand=True)
    tbl.add_column("leg", ratio=1)
    tbl.add_column("trend", ratio=1)
    tbl.add_column("vol(20d)", ratio=1)
    tbl.add_column("weight", ratio=1)

    # vol_20d (annualized 20-day realized vol) is the actual inverse-vol sizing INPUT that
    # determines each leg's weight (see capital_routing.py's module docstring, "SIZING:
    # inverse-volatility... weighting") - was computed and persisted to capital_routing_daily
    # but never rendered on either dashboard, same "computed but invisible" bug class as
    # vol_managed_multiplier/active_policy_tier before this fix: an operator could see GLD at
    # 60% and DBC at 15% with no way to see why (GLD's lower realized vol).
    legs = [
        ("GLD", cr.get("gld_trend_up"), cr.get("gld_vol_20d"), cr.get("gld_weight")),
        ("IEF", cr.get("ief_trend_up"), cr.get("ief_vol_20d"), cr.get("ief_weight")),
        ("DBC", cr.get("dbc_trend_up"), cr.get("dbc_vol_20d"), cr.get("dbc_weight")),
    ]
    for symbol, trend_up, vol_20d, weight in legs:
        if trend_up is True:
            trend_s = f"[{G}]UP[/]"
        elif trend_up is False:
            trend_s = f"[{R}]DOWN[/]"
        else:
            trend_s = "[dim]--[/]"
        if symbol == "IEF" and cr.get("move_veto"):
            trend_s += f" [{Y}](MOVE veto)[/]"
        vol_s = f"{vol_20d * 100:.1f}%" if isinstance(vol_20d, (int, float)) else "--"
        weight_s = f"{weight * 100:.1f}%" if isinstance(weight, (int, float)) else "--"
        tbl.add_row(Text(symbol, style="bold"), Text.from_markup(trend_s), Text(vol_s, style="dim"), Text(weight_s))

    cash_weight = cr.get("cash_weight")
    cash_s = f"{cash_weight * 100:.1f}%" if isinstance(cash_weight, (int, float)) else "--"
    tbl.add_row(Text("CASH", style="bold"), Text("--", style="dim"), Text("--", style="dim"), Text(cash_s))

    move_index = cr.get("move_index")
    move_s = f"MOVE: {move_index:.1f}" if isinstance(move_index, (int, float)) else "MOVE: [dim]unavailable[/]"

    rows: list[Any] = [
        Text.from_markup(f"[dim]Uninvested capital:[/] {uninvested_s}   [dim]{move_s}[/]"),
        Rule(style="dim"),
        tbl,
    ]

    timestamp_val = cr.get("timestamp")
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    stale_warning = _stale_warning(cr)
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title=f"[bold blue]CAPITAL ROUTING[/]{age_s}{stale_warning}",
        border_style="blue" if not stale_warning else "yellow",
        padding=(0, 1),
    )


__all__ = [
    "panel_capital_routing",
    "panel_exposure_compact",
    "panel_exposure_expanded",
]
