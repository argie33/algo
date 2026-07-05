"""Signal analysis panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

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

from ..error_boundary import has_error
from ..formatters import (
    fmt_age,
)
from ..utilities import (
    CY,
    DIM,
    SPARKLINE_CHARS,
    G,
    R,
    Y,
)
from ._helpers import (
    _build_buy_sig_map,
    _composite_score_color,
    _error_panel,
    _score_cell,
    _swing_cell,
)
from .data_extractors import (
    extract_eval_funnel,
    extract_signal_overview,
    safe_get_dict,
    safe_get_field,
    safe_get_list,
)


def _format_signal_date(date_val: Any) -> str:
    """Format date value for display."""
    if hasattr(date_val, "strftime"):
        return cast(str, date_val.strftime("%b %d"))
    if date_val and isinstance(date_val, str) and len(date_val) >= 10:
        try:
            from datetime import date as _date

            return _date.fromisoformat(str(date_val)[:10]).strftime("%b %d")
        except (ValueError, TypeError):
            return str(date_val)[:10]
    return "--"


def _shorten_reason(r: str) -> str:
    r = r.lower()
    if "52w" in r or "52-w" in r or ("low" in r and "proximity" in r):
        return "52wLow"
    if "sector" in r and ("cap" in r or "concentr" in r or "already" in r):
        return "SctCap"
    if "industry" in r and ("cap" in r or "concentr" in r or "already" in r):
        return "IndCap"
    if "stage" in r:
        return "Stage"
    if "volume" in r:
        return "Vol"
    if "rs" in r or "relative strength" in r:
        return "RS"
    return r[:7].title()


def _shorten_type(t: str) -> str:
    # MEDIUM FIX: Explicit None check instead of or operator for signal type
    t_safe = (t if t is not None else "")
    t = t_safe.replace("WEEKLY_", "W_").replace("STAGE_2", "S2").replace("STAGE2", "S2")
    t = t.replace("BREAKOUT", "BKT").replace("MOMENTUM", "MOM").replace("REVERSAL", "REV")
    t = t.replace("PULLBACK", "PB").replace("TREND", "TRD").replace("_FOLLOW", "")
    return t[:12]


def _build_signal_header(sig_data: dict[str, Any], scores_data: dict[str, Any] | None) -> tuple[list[Text], int, int]:
    """Build signal header row (count, sparkline, grades, date).

    Returns empty rows if input validation fails (missing required structure).
    Logs errors for all validation failures.
    """
    rows: list[Text] = []
    if not isinstance(sig_data, dict):
        logger.error(f"_build_signal_header: sig_data is not dict, got {type(sig_data).__name__}")
        return rows, 0, 0
    if has_error(sig_data):
        logger.error(f"_build_signal_header: sig_data contains error - {sig_data.get('_error', 'unknown error')}")
        return rows, 0, 0
    try:
        overview = extract_signal_overview(sig_data)
    except (TypeError, ValueError) as e:
        logger.error(f"_build_signal_header: extract_signal_overview failed - {e}")
        return rows, 0, 0
    if has_error(overview):
        logger.error(
            f"_build_signal_header: overview extraction produced error - {overview.get('_error', 'unknown error')}"
        )
        return rows, 0, 0

    raw_val = safe_get_field(overview, "n")
    if raw_val is None or not isinstance(raw_val, (int, float)):
        logger.warning(f"_build_signal_header: signal count 'n' missing or invalid, got {type(raw_val).__name__}")
        return rows, 0, 0
    raw = int(raw_val)
    total_val = safe_get_field(overview, "total")
    if total_val is None or not isinstance(total_val, (int, float)):
        logger.warning(
            f"_build_signal_header: total screened 'total' missing or invalid, got {type(total_val).__name__}"
        )
        return rows, 0, 0
    total = int(total_val)
    ds = _format_signal_date(safe_get_field(overview, "date"))

    grades_field = safe_get_field(overview, "grades", {})
    grades = safe_get_dict(grades_field) if grades_field else {}
    # MEDIUM FIX: Eliminate redundant safe_get_field calls - call once and check result
    ga_val = safe_get_field(grades, "a")
    ga = (int(ga_val) if ga_val is not None else None)
    gb_val = safe_get_field(grades, "b")
    gb = (int(gb_val) if gb_val is not None else None)
    gc_val = safe_get_field(grades, "c")
    gc = (int(gc_val) if gc_val is not None else None)
    gd_val = safe_get_field(grades, "d")
    gd = (int(gd_val) if gd_val is not None else None)

    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))

    spark_s: str = ""
    trend_field = safe_get_field(overview, "trend", [])
    trend_result = safe_get_list(trend_field) if trend_field else None
    trend: list[Any] = trend_result if isinstance(trend_result, list) else []
    if trend and len(trend) >= 2:
        # GOVERNANCE: Fail-fast on incomplete historical data. Do NOT synthesize missing points as zeros.
        # Missing data in historical trends indicates data quality issue, must be visible to user.
        counts: list[int] = []
        has_complete_trend = True
        for t in reversed(trend):
            buy_n_val = safe_get_field(t, "buy_n")
            if buy_n_val is None:
                logger.warning(
                    "[SIGNALS] Trend history incomplete: buy_n field missing from signal data. "
                    "Cannot display sparkline with missing data points. "
                    "Check signal data freshness and completeness."
                )
                has_complete_trend = False
                break
            counts.append(int(buy_n_val))

        # Only create sparkline if trend history is complete
        if has_complete_trend and counts:
            max_b = max(counts) if counts else 1
            spark = "".join(SPARKLINE_CHARS[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
            spark_s = f"  [{CY}]{spark}[/]"

    near_field = safe_get_field(overview, "near", [])
    near_result = safe_get_list(near_field) if near_field else None
    near: list[Any] = near_result if isinstance(near_result, list) else []
    n_near: int = len(near)
    near_hint: str = f"  [{CY}]{n_near} near[/]" if n_near > 0 else ""

    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"

    rows.append(
        Text.from_markup(
            f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
            f"  [{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]{near_hint}"
        )
    )

    return rows, raw, total


def _build_grade_radar(sig_data: dict[str, Any]) -> list[Text]:
    """Build A-grade radar row or near-miss fallback.

    Returns empty list if input validation fails (missing required structure).
    Logs errors for all validation failures.
    """
    rows: list[Text] = []
    if not isinstance(sig_data, dict):
        logger.error(f"_build_grade_radar: sig_data is not dict, got {type(sig_data).__name__}")
        return rows
    if has_error(sig_data):
        logger.error(f"_build_grade_radar: sig_data contains error - {sig_data.get('_error', 'unknown error')}")
        return rows
    try:
        overview = extract_signal_overview(sig_data)
    except (TypeError, ValueError) as e:
        logger.error(f"_build_grade_radar: extract_signal_overview failed - {e}")
        return rows
    if has_error(overview):
        logger.error(
            f"_build_grade_radar: overview extraction produced error - {overview.get('_error', 'unknown error')}"
        )
        return rows
    top_a_result = safe_get_list(safe_get_field(overview, "top_a", []))
    top_a: list[Any] = top_a_result if isinstance(top_a_result, list) else []
    near_result = safe_get_list(safe_get_field(overview, "near", []))
    near: list[Any] = near_result if isinstance(near_result, list) else []

    if top_a:
        parts = []
        for s in top_a[:8]:
            score_raw = safe_get_field(s, "score")
            sc = safe_float(score_raw)
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{safe_get_field(s, 'symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{safe_get_field(s, 'symbol', '')}[/][dim]--[/]")
        grades_field = safe_get_field(overview, "grades", {})
        grades_dict = safe_get_dict(grades_field) if grades_field else {}
        ga = safe_get_field(grades_dict, "a")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga is not None and ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        parts = []
        for a in near[:8]:
            score_raw = safe_get_field(a, "score")
            sc = safe_float(score_raw)
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = safe_get_field(a, "symbol", "")
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    return rows


def _build_funnel_row(sig_eval_data: dict[str, Any] | None) -> list[Text]:
    """Build funnel arrow chain row with avg score and top blockers.

    Returns empty list if input is missing or has errors.
    Logs errors for all validation failures.
    """
    rows: list[Text] = []
    if not sig_eval_data:
        logger.debug("_build_funnel_row: sig_eval_data is None (optional field)")
        return rows
    if has_error(sig_eval_data):
        logger.warning(
            f"_build_funnel_row: sig_eval_data contains error - {sig_eval_data.get('_error', 'unknown error')}"
        )
        return rows
    if not isinstance(sig_eval_data, dict):
        logger.error(f"_build_funnel_row: sig_eval_data is not dict, got {type(sig_eval_data).__name__}")
        return rows

    try:
        funnel = extract_eval_funnel(sig_eval_data)
    except (TypeError, ValueError) as e:
        logger.warning(f"_build_funnel_row: extract_eval_funnel failed - {e}")
        return rows
    if has_error(funnel):
        logger.warning(f"_build_funnel_row: funnel extraction produced error - {funnel.get('_error', 'unknown error')}")
        return rows
    ev_tot = safe_get_field(funnel, "total")
    ev_t1 = safe_get_field(funnel, "t1")
    ev_t2 = safe_get_field(funnel, "t2")
    ev_t3 = safe_get_field(funnel, "t3")
    ev_t4 = safe_get_field(funnel, "t4")
    ev_t5 = safe_get_field(funnel, "t5")
    ev_avg = safe_get_field(funnel, "avg_score")

    if ev_tot is not None and ev_t5 is not None:
        ev_c = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
        rejected_result = safe_get_list(safe_get_field(funnel, "rejected", []))
        rejected: list[Any] = rejected_result if isinstance(rejected_result, list) else []

        blocks_s: str = ""
        if rejected:
            block_parts: list[str] = []
            for rj in rejected[:3]:
                reason_abbr = _shorten_reason(safe_get_field(rj, "evaluation_reason", ""))
                description = safe_get_field(rj, "description", "")
                if description:
                    block_parts.append(
                        f"[dim]{reason_abbr}:{safe_get_field(rj, 'n', 0)}[/] [bright_black]({description})[/]"
                    )
                else:
                    block_parts.append(f"[dim]{reason_abbr}:{safe_get_field(rj, 'n', 0)}[/]")
            blocks_s = "  [dim]blocked:[/]  " + "  ".join(block_parts)

        has_full_funnel: bool = all(v is not None for v in [ev_t1, ev_t2, ev_t3, ev_t4])
        if has_full_funnel:
            funnel_s: str = (
                f"[dim]Funnel:[/] {ev_tot}[dim]→[/]{ev_t1}[dim]→[/]{ev_t2}"
                f"[dim]→[/]{ev_t3}[dim]→[/]{ev_t4}[dim]→[/][{ev_c}]{ev_t5}[/]"
            )
        else:
            funnel_s = f"[dim]{ev_tot} →[/] [{ev_c}]{ev_t5} qualified[/]"

        avg_s: str = f"  [dim]avg score:[/][white]{ev_avg:.0f}[/]" if ev_avg is not None else ""
        rows.append(Text.from_markup(funnel_s + avg_s + blocks_s))

    return rows


def _build_buy_signals_table(
    scored_with_signals: list[Any], buy_sig_details: dict[str, Any]
) -> list[Text | Table | Rule]:
    """Build active buy signals table section.

    Validates input is list and dict before accessing fields.
    Logs all validation failures.
    """
    rows: list[Text | Table | Rule] = []
    if not isinstance(scored_with_signals, list):
        logger.error(
            f"_build_buy_signals_table: scored_with_signals is not list, got {type(scored_with_signals).__name__}"
        )
        return rows
    if not scored_with_signals:
        logger.debug("_build_buy_signals_table: scored_with_signals is empty (no active signals)")
        return rows
    if not isinstance(buy_sig_details, dict):
        logger.error(f"_build_buy_signals_table: buy_sig_details is not dict, got {type(buy_sig_details).__name__}")
        return rows

    rows.append(
        Text.from_markup(
            f"[{G}][bold]ACTIVE BUY SIGNALS ★[/][/] [dim]({len(scored_with_signals)} trades with price targets)[/]"
        )
    )
    sig_table: Table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=True,
        row_styles=["", "dim"],
    )
    sig_table.add_column("Symbol", style="bold white", no_wrap=True, min_width=6)
    sig_table.add_column("Comp Score", justify="right", no_wrap=True, min_width=7)
    sig_table.add_column("Price", justify="right", no_wrap=True, min_width=7)
    sig_table.add_column("Buy Level", justify="right", no_wrap=True, min_width=9)
    sig_table.add_column("Stop Level", justify="right", no_wrap=True, min_width=9)
    sig_table.add_column("R/R", justify="right", no_wrap=True, min_width=6)
    sig_table.add_column("Swing", justify="right", no_wrap=True, min_width=6)
    sig_table.add_column("Entry Q", justify="right", no_wrap=True, min_width=7)

    for score_item in scored_with_signals:
        sym = safe_get_field(score_item, "symbol", "--")
        comp_score = safe_get_field(score_item, "composite_score")
        sym_norm = str(sym).upper().strip()
        sig_obj = buy_sig_details.get(sym_norm)

        if sig_obj:
            swing_score = safe_get_field(sig_obj, "swing_score")
            if swing_score is None:
                swing_score = safe_get_field(sig_obj, "signal_quality_score")
                if swing_score is not None:
                    logger.debug(f"[SIGNALS_PANEL] {sym}: swing_score missing, using signal_quality_score")
            entry_qual = safe_get_field(sig_obj, "entry_quality_score", swing_score)
            buy_lvl = safe_get_field(sig_obj, "buylevel")
            stop_lvl = safe_get_field(sig_obj, "stoplevel")
            price = safe_get_field(sig_obj, "close")
            if price is None:
                price = safe_get_field(score_item, "current_price")
        else:
            swing_score = None
            entry_qual = None
            buy_lvl = None
            stop_lvl = None
            price = safe_get_field(score_item, "current_price")

        rr_ratio: float | None = None
        if buy_lvl is not None and stop_lvl is not None:
            try:
                buy_lvl_ratio = safe_float(buy_lvl, field_name="buylevel")
                stop_lvl_ratio = safe_float(stop_lvl, field_name="stoplevel")
                if stop_lvl_ratio is not None and stop_lvl_ratio > 0 and buy_lvl_ratio is not None:
                    rr_ratio = (buy_lvl_ratio - stop_lvl_ratio) / stop_lvl_ratio
            except (StrictValidationError, ValueError, TypeError, ZeroDivisionError) as e:
                logger.warning(f"[SIGNAL_PANEL] R/R ratio calculation failed (buy={buy_lvl}, stop={stop_lvl}): {e}")

        comp_v: float | None = None
        try:
            comp_v = safe_float(comp_score, field_name="composite_score")
        except (StrictValidationError, ValueError, TypeError) as e:
            logger.warning(f"[SIGNAL_PANEL] Composite score conversion failed (comp_score={comp_score}): {e}")
        comp_c: str = _composite_score_color(comp_v) if comp_v is not None else "dim"
        swing_c: str = (
            G
            if (swing_score is not None and swing_score >= 80)
            else (CY if (swing_score is not None and swing_score >= 70) else Y)
        )
        rr_c: str = (
            G
            if rr_ratio is not None and rr_ratio > 1.5
            else (Y if rr_ratio is not None and rr_ratio > 1 else (CY if rr_ratio is not None else DIM))
        )

        price_f: float | None = safe_float(price)
        buy_lvl_f: float | None = safe_float(buy_lvl)
        stop_lvl_f: float | None = safe_float(stop_lvl)
        sig_table.add_row(
            Text(sym, style=f"bold {G}"),
            Text(f"{comp_v:.0f}" if comp_v is not None else "⚠", style=comp_c),
            Text(f"${price_f:.2f}" if price_f is not None else "--", style="dim"),
            Text(f"${buy_lvl_f:.2f}" if buy_lvl_f is not None else "--", style=CY),
            Text(f"${stop_lvl_f:.2f}" if stop_lvl_f is not None else "--", style=R),
            Text(f"{rr_ratio:.2f}" if rr_ratio else "--", style=rr_c),
            Text(f"▲{swing_score:.0f}" if swing_score is not None else "--", style=swing_c),
            Text(f"{entry_qual:.0f}" if entry_qual is not None else "--", style=CY),
        )
    rows.append(sig_table)
    rows.append(Rule(style="dim"))
    return rows


def _build_scores_table(top_scores: list[Any]) -> list[Text | Table]:
    """Build stock quality scores table.

    Validates input is list before accessing items.
    Logs all validation failures.
    """
    rows: list[Text | Table] = []
    if not isinstance(top_scores, list):
        logger.error(f"_build_scores_table: top_scores is not list, got {type(top_scores).__name__}")
        rows.append(Text.from_markup(f"[{Y}]Invalid score data structure — check Data Health[/]"))
        return rows
    if not top_scores:
        logger.debug("_build_scores_table: top_scores is empty (no score data available)")
        rows.append(Text.from_markup(f"[{Y}]No score data — check Data Health[/]"))
        return rows

    rows.append(
        Text.from_markup(f"[{Y}][bold]TOP STOCK SCORES[/][/] [dim](additional candidates without active signals)[/]")
    )
    t: Table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=True,
        row_styles=["", "dim"],
    )
    t.add_column("Symbol", style="bold white", no_wrap=True, min_width=6)
    t.add_column("Composite", justify="right", no_wrap=True, min_width=7)
    t.add_column("Momentum", justify="right", no_wrap=True, min_width=8)
    t.add_column("Quality", justify="right", no_wrap=True, min_width=7)
    t.add_column("Growth", justify="right", no_wrap=True, min_width=7)
    t.add_column("Stability", justify="right", no_wrap=True, min_width=8)
    t.add_column("RS%", justify="right", no_wrap=True, min_width=5)
    t.add_column("Change%", justify="right", no_wrap=True, min_width=7)
    t.add_column("Sector", no_wrap=True, max_width=12)

    for sc in top_scores[:15]:
        sym = safe_get_field(sc, "symbol", "--")
        comp = safe_get_field(sc, "composite_score")
        mom = safe_get_field(sc, "momentum_score")
        qual = safe_get_field(sc, "quality_score")
        grwth = safe_get_field(sc, "growth_score")
        stab = safe_get_field(sc, "stability_score")
        rs_pct = safe_get_field(sc, "rs_percentile")
        chg = safe_get_field(sc, "change_percent")
        sector = (safe_get_field(sc, "sector", ""))[:12]
        comp_v: float | None = safe_float(comp)
        sc_c: str = _composite_score_color(comp_v) if comp_v is not None else DIM
        chg_v: float | None = safe_float(chg)
        chg_c: str = G if chg_v is not None and chg_v > 0 else (R if chg_v is not None and chg_v < 0 else DIM)
        rs_v: float | None = safe_float(rs_pct)

        t.add_row(
            sym,
            Text(f"{comp_v:.0f}" if comp_v is not None else "--", style=sc_c),
            _score_cell(mom),
            _score_cell(qual),
            _score_cell(grwth),
            _score_cell(stab),
            Text(
                f"{rs_v:.0f}" if rs_v is not None else "--",
                style=G if rs_v is not None and rs_v >= 70 else DIM,
            ),
            Text(f"{chg_v:+.1f}%" if chg_v is not None else "--", style=chg_c),
            Text(sector, style=DIM),
        )
    rows.append(t)
    return rows


@register_panel(
    "signals",
    endpoint_deps=["sig", "sig_eval", "scores"],
    optional=True,
    description="Signals",
)
def panel_signals_compact(sig: Any, sig_eval: Any = None, scores: Any = None) -> Panel | None:
    """Signals & screening — composite score top candidates with pipeline funnel context."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel
    if scores and has_error(scores):
        return _error_panel("scores", scores, "SIGNALS", border="magenta")

    overview = extract_signal_overview(sig)
    if has_error(overview):
        return _error_panel(
            "signals",
            {"_error": "Signal overview extraction failed"},
            "SIGNALS",
            border="magenta",
        )

    top_scores = None
    if scores and isinstance(scores, dict) and not has_error(scores):
        top_scores = safe_get_field(scores, "top")
    if not isinstance(top_scores, list):
        top_scores = []

    buy_sigs = safe_get_field(overview, "buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []

    rows_text, _, _ = _build_signal_header(sig, scores)
    rows: list[Text | Table | Rule] = cast(list[Text | Table | Rule], rows_text)
    rows.extend(_build_grade_radar(sig))
    rows.append(Rule(style="dim"))
    rows.extend(_build_funnel_row(sig_eval))
    rows.append(Rule(style="dim"))

    buy_sig_details = {}
    for bs in buy_sigs:
        if not isinstance(bs, dict):
            logger.warning(f"panel_signals_compact: buy_sig item is not dict, got {type(bs).__name__} - skipping")
            continue
        sym = bs.get("symbol")
        if not sym:
            logger.debug("panel_signals_compact: buy_sig item missing 'symbol' field - skipping")
            continue
        sym_norm = str(sym).upper().strip()
        buy_sig_details[sym_norm] = bs

    scored_with_signals = [
        s for s in top_scores if str(safe_get_field(s, "symbol", "")).upper().strip() in buy_sig_details
    ][:10]

    rows.extend(_build_buy_signals_table(scored_with_signals, buy_sig_details))

    if scored_with_signals:
        rows.append(Text.from_markup(f"[{Y}][bold]TOP STOCK SCORES[/][/] [dim](all candidates)[/]"))
    rows.extend(_build_scores_table(top_scores))

    # MEDIUM FIX: Eliminate redundant safe_get_field calls - call once and check result
    near_val = safe_get_field(overview, "near")
    near = (near_val if near_val is not None else [])
    top_a_val = safe_get_field(overview, "top_a")
    top_a = (top_a_val if top_a_val is not None else [])
    if near and top_a:
        rows.append(Rule(style="dim"))
        parts = []
        for a in near[:8]:
            score_val = safe_get_field(a, "score")
            sc = safe_float(score_val)
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = safe_get_field(a, "symbol", "")
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near BUY (55-69):[/]  " + "  ".join(parts)))

    # MEDIUM FIX: Eliminate redundant safe_get_field calls for timestamp
    timestamp_val = safe_get_field(overview, "timestamp")
    age_s = (
        f"  [dim]{fmt_age(timestamp_val)}[/]"
        if timestamp_val is not None
        else ""
    )
    title = "[bold magenta]TOP SCORES & SIGNALS[/]"
    return Panel(
        Group(*rows),
        title=f"{title}{age_s}  [dim][s] expand[/]",
        border_style="magenta",
        padding=(0, 1),
    )


def panel_signals_expanded(sig: Any, sig_eval: Any = None, scores: Any = None) -> Panel | None:
    """Full-screen signals & scores - pipeline funnel context, detailed score breakdowns, and all top candidates."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel
    if scores and has_error(scores):
        return _error_panel("scores", scores, "SIGNALS", border="magenta")

    overview = extract_signal_overview(sig)
    if has_error(overview):
        return _error_panel(
            "signals",
            {"_error": "Signal overview extraction failed"},
            "SIGNALS",
            border="magenta",
        )

    raw = safe_get_field(overview, "n")
    total = safe_get_field(overview, "total")

    if raw is None or total is None:
        return _error_panel("signals", {"_error": "Missing signal counts"}, "SIGNALS", border="magenta")

    top_scores = None
    if scores and isinstance(scores, dict) and not has_error(scores):
        top_scores = safe_get_field(scores, "top")
    if not isinstance(top_scores, list):
        top_scores = []

    buy_sigs = safe_get_field(overview, "buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []
    ds = _format_signal_date(safe_get_field(overview, "date"))

    # MEDIUM FIX: Eliminate redundant safe_get_field calls - call once and check result
    grades_val = safe_get_field(overview, "grades")
    grades = (grades_val if grades_val is not None else {})
    ga_val = safe_get_field(grades, "a")
    ga = (int(ga_val) if ga_val is not None else None)
    gb_val = safe_get_field(grades, "b")
    gb = (int(gb_val) if gb_val is not None else None)
    gc_val = safe_get_field(grades, "c")
    gc = (int(gc_val) if gc_val is not None else None)
    gd_val = safe_get_field(grades, "d")
    gd = (int(gd_val) if gd_val is not None else None)

    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))

    rows: list[Text | Table | Rule] = [
        Text.from_markup(f"[{CY}][bold]SIGNAL OVERVIEW[/][/]"),
        Text.from_markup(
            f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
            f"[{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]  "
            "[dim]press [/][bold magenta]s[/][dim] to return[/]"
        ),
    ]

    # MEDIUM FIX: Eliminate redundant safe_get_field calls for top_a
    top_a_val_exp = safe_get_field(overview, "top_a")
    top_a = (top_a_val_exp if top_a_val_exp is not None else [])
    if top_a:
        parts = []
        for s in top_a:
            score_val = safe_get_field(s, "score")
            sc = safe_float(score_val)
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{safe_get_field(s, 'symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{safe_get_field(s, 'symbol', '')}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    rows.extend(_build_funnel_row(sig_eval))
    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[{Y}][bold]DETAILED SCORE BREAKDOWN[/][/]"))

    buy_sig_map_exp = _build_buy_sig_map(buy_sigs)
    # GOVERNANCE: Log explicitly when optional data is missing (fail-fast visibility).
    if top_scores is None:
        logger.warning("Signals panel: top_scores is None, showing 0 candidates")
        display_count = 0
    else:
        display_count = len(top_scores)
    rows.append(Text.from_markup(f"[dim]Top {display_count} candidates with component scores[/]"))

    if top_scores:
        sig_tbl = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            row_styles=["", "dim"],
        )
        sig_tbl.add_column("Sym", style="bold white", no_wrap=True, min_width=5)
        sig_tbl.add_column("Score", justify="right", no_wrap=True, min_width=5)
        sig_tbl.add_column("Swing", justify="right", no_wrap=True, min_width=5)
        sig_tbl.add_column("Mom", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Qual", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Val", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Grwth", justify="right", no_wrap=True, min_width=5)
        sig_tbl.add_column("Stab", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Pos", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("RS%", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Price", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("Chg%", justify="right", no_wrap=True, min_width=6)
        sig_tbl.add_column("vs50%", justify="right", no_wrap=True, min_width=6)
        sig_tbl.add_column("vs200%", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("Sector", no_wrap=True, max_width=14)

        for sc in top_scores:
            sym = str(safe_get_field(sc, "symbol", "--"))
            sym_norm = sym.upper().strip()
            comp = safe_get_field(sc, "composite_score")
            mom = safe_get_field(sc, "momentum_score")
            qual = safe_get_field(sc, "quality_score")
            val = safe_get_field(sc, "value_score")
            grwth = safe_get_field(sc, "growth_score")
            stab = safe_get_field(sc, "stability_score")
            pos = safe_get_field(sc, "positioning_score")
            rs_pct = safe_get_field(sc, "rs_percentile")
            chg = safe_get_field(sc, "change_percent")
            price = safe_get_field(sc, "current_price")
            price_f = safe_float(price)
            mom_inputs = safe_get_field(sc, "momentum_inputs")
            vs50 = safe_get_field(sc, "price_vs_sma_50")
            if vs50 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs50 = safe_get_field(mom_inputs, "price_vs_sma_50")
            vs200 = safe_get_field(sc, "price_vs_sma_200")
            if vs200 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs200 = safe_get_field(mom_inputs, "price_vs_sma_200")
            sector = (safe_get_field(sc, "sector", ""))[:14]
            # CRITICAL: Fail-fast on missing composite_score. Never silently fallback to 0.
            if comp is None:
                logger.warning(f"Signal composite_score missing for {sym_norm} — data unavailable")
                comp_v = None
                sc_c = "dim"
            else:
                comp_v = safe_float(comp)
                sc_c = _composite_score_color(comp_v) if comp_v is not None else DIM

            chg_v = safe_float(chg)
            vs50_v = safe_float(vs50)
            vs200_v = safe_float(vs200)
            rs_v = safe_float(rs_pct)
            chg_c = G if chg_v is not None and chg_v > 0 else (R if chg_v is not None and chg_v < 0 else DIM)

            comp_display = f"{comp_v:.0f}" if comp_v is not None else "N/A"
            sig_tbl.add_row(
                sym,
                Text(comp_display, style=sc_c),
                _swing_cell(buy_sig_map_exp.get(sym_norm)),
                _score_cell(mom),
                _score_cell(qual),
                _score_cell(val),
                _score_cell(grwth),
                _score_cell(stab),
                _score_cell(pos),
                Text(
                    f"{rs_v:.0f}" if rs_v is not None else "--",
                    style=G if rs_v is not None and rs_v >= 70 else DIM,
                ),
                Text(f"${price_f:.2f}" if price_f is not None else "--", style=DIM),
                Text(f"{chg_v:+.1f}%" if chg_v is not None else "--", style=chg_c),
                Text(
                    f"{vs50_v:+.1f}%" if vs50_v is not None else "--",
                    style=G if vs50_v is not None and vs50_v > 0 else R,
                ),
                Text(
                    f"{vs200_v:+.1f}%" if vs200_v is not None else "--",
                    style=G if vs200_v is not None and vs200_v > 0 else R,
                ),
                Text(sector, style=DIM),
            )
        rows.append(sig_tbl)
    else:
        rows.append(Text.from_markup(f"[{Y}]No composite score data — check Data Health[/]"))

    title = "[bold magenta]SIGNALS & SCORES - EXPANDED[/]"
    return Panel(
        Group(*rows),
        title=title,
        border_style="magenta",
        padding=(0, 1),
    )


__all__ = [
    "panel_signals_compact",
    "panel_signals_expanded",
]
