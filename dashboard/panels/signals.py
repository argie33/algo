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

from dashboard.data_validation import safe_float

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
    _composite_score_color,
    _error_panel,
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
    t_safe = t if t is not None else ""
    t = t_safe.replace("WEEKLY_", "W_").replace("STAGE_2", "S2").replace("STAGE2", "S2")
    t = t.replace("BREAKOUT", "BKT").replace("MOMENTUM", "MOM").replace("REVERSAL", "REV")
    t = t.replace("PULLBACK", "PB").replace("TREND", "TRD").replace("_FOLLOW", "")
    return t[:12]


def _build_signal_header(sig_data: dict[str, Any]) -> tuple[list[Text], int, int]:
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
    ga = int(ga_val) if ga_val is not None else None
    gb_val = safe_get_field(grades, "b")
    gb = int(gb_val) if gb_val is not None else None
    gc_val = safe_get_field(grades, "c")
    gc = int(gc_val) if gc_val is not None else None
    gd_val = safe_get_field(grades, "d")
    gd = int(gd_val) if gd_val is not None else None

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


def _build_buy_signals_table(buy_sigs: list[Any]) -> list[Text | Table | Rule]:
    """Build active buy signals table: entry/target/exit + technicals/strength per candidate.

    buy_sigs items come from /api/algo/dashboard-signals, enriched (LEFT JOIN buy_sell_daily +
    trend_template_data) with the same entry-zone/target/technical fields the web Trading
    Signals page shows - see lambda/api/routes/algo_handlers/dashboard.py::_get_dashboard_signals.

    Validates input is list before accessing fields. Logs all validation failures.
    """
    rows: list[Text | Table | Rule] = []
    if not isinstance(buy_sigs, list):
        logger.error(f"_build_buy_signals_table: buy_sigs is not list, got {type(buy_sigs).__name__}")
        return rows
    if not buy_sigs:
        logger.debug("_build_buy_signals_table: buy_sigs is empty (no active signals)")
        return rows

    rows.append(
        Text.from_markup(f"[{G}][bold]ACTIVE BUY SIGNALS ★[/][/] [dim]({len(buy_sigs)} with price targets)[/]")
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
    sig_table.add_column("Quality", justify="right", no_wrap=True, min_width=7)
    sig_table.add_column("Price", justify="right", no_wrap=True, min_width=7)
    sig_table.add_column("Buy Lvl", justify="right", no_wrap=True, min_width=8)
    sig_table.add_column("Stop", justify="right", no_wrap=True, min_width=7)
    sig_table.add_column("Target", justify="right", no_wrap=True, min_width=8)
    sig_table.add_column("RSI", justify="right", no_wrap=True, min_width=5)
    sig_table.add_column("Setup", no_wrap=True, max_width=18)
    sig_table.add_column("R/R", justify="right", no_wrap=True, min_width=5)

    for sig_obj in buy_sigs:
        sym = safe_get_field(sig_obj, "symbol", "--")
        quality = safe_get_field(sig_obj, "signal_quality_score")
        price = safe_get_field(sig_obj, "close")
        if price is None:
            price = safe_get_field(sig_obj, "entry_price")
        buy_lvl = safe_get_field(sig_obj, "buylevel")
        if buy_lvl is None:
            buy_lvl = safe_get_field(sig_obj, "pivot_price")
        stop_lvl = safe_get_field(sig_obj, "initial_stop")
        if stop_lvl is None:
            stop_lvl = safe_get_field(sig_obj, "stoplevel")
        target = safe_get_field(sig_obj, "profit_target_20pct")
        rsi = safe_get_field(sig_obj, "rsi")
        rr_ratio = safe_get_field(sig_obj, "risk_reward_ratio")
        base_type = safe_get_field(sig_obj, "base_type")
        market_stage = safe_get_field(sig_obj, "market_stage")

        quality_v: float | None = safe_float(quality)
        quality_c: str = _composite_score_color(quality_v) if quality_v is not None else "dim"
        rr_v: float | None = safe_float(rr_ratio)
        rr_c: str = (
            G if rr_v is not None and rr_v > 1.5 else (Y if rr_v is not None and rr_v > 1 else (CY if rr_v is not None else DIM))
        )

        price_f: float | None = safe_float(price)
        buy_lvl_f: float | None = safe_float(buy_lvl)
        stop_lvl_f: float | None = safe_float(stop_lvl)
        target_f: float | None = safe_float(target)
        rsi_f: float | None = safe_float(rsi)

        setup_parts = [p for p in (base_type, market_stage.replace("Stage ", "S") if market_stage else None) if p]
        setup_s = " · ".join(setup_parts) if setup_parts else "--"

        sig_table.add_row(
            Text(str(sym), style=f"bold {G}"),
            Text(f"{quality_v:.0f}" if quality_v is not None else "⚠", style=quality_c),
            Text(f"${price_f:.2f}" if price_f is not None else "--", style="dim"),
            Text(f"${buy_lvl_f:.2f}" if buy_lvl_f is not None else "--", style=CY),
            Text(f"${stop_lvl_f:.2f}" if stop_lvl_f is not None else "--", style=R),
            Text(f"${target_f:.2f}" if target_f is not None else "--", style=G),
            Text(
                f"{rsi_f:.0f}" if rsi_f is not None else "--",
                style=R if rsi_f is not None and rsi_f > 70 else (G if rsi_f is not None and rsi_f < 30 else "white"),
            ),
            Text(setup_s, style=DIM if setup_s == "--" else "white"),
            Text(f"{rr_v:.2f}" if rr_v is not None else "--", style=rr_c),
        )
    rows.append(sig_table)
    rows.append(Rule(style="dim"))
    return rows


@register_panel(
    "signals",
    endpoint_deps=["sig"],
    optional=True,
    description="Signals",
)
def panel_signals_compact(sig: Any, sig_eval: Any = None) -> Panel | None:
    """Signals - pipeline funnel context + active buy signals with entry/target/exit/technicals."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel

    overview = extract_signal_overview(sig)
    if has_error(overview):
        return _error_panel(
            "signals",
            {"_error": "Signal overview extraction failed"},
            "SIGNALS",
            border="magenta",
        )

    buy_sigs = safe_get_field(overview, "buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []

    rows_text, _, _ = _build_signal_header(sig)
    rows: list[Text | Table | Rule] = cast(list[Text | Table | Rule], rows_text)
    rows.extend(_build_grade_radar(sig))
    rows.append(Rule(style="dim"))
    rows.extend(_build_funnel_row(sig_eval))
    rows.append(Rule(style="dim"))

    valid_buy_sigs = [bs for bs in buy_sigs if isinstance(bs, dict) and bs.get("symbol")]
    rows.extend(_build_buy_signals_table(valid_buy_sigs[:15]))

    # MEDIUM FIX: Eliminate redundant safe_get_field calls - call once and check result
    near_val = safe_get_field(overview, "near")
    near = near_val if near_val is not None else []
    top_a_val = safe_get_field(overview, "top_a")
    top_a = top_a_val if top_a_val is not None else []
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
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    title = "[bold magenta]SIGNALS[/]"
    return Panel(
        Group(*rows),
        title=f"{title}{age_s}  [dim][s] expand[/]",
        border_style="magenta",
        padding=(0, 1),
    )


def panel_signals_expanded(sig: Any, sig_eval: Any = None) -> Panel | None:
    """Full-screen signals - pipeline funnel context + full entry/target/exit/technicals detail
    for every active buy signal (component scores live in the separate Scores panel/'c' view)."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel

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

    buy_sigs = safe_get_field(overview, "buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []
    ds = _format_signal_date(safe_get_field(overview, "date"))

    # MEDIUM FIX: Eliminate redundant safe_get_field calls - call once and check result
    grades_val = safe_get_field(overview, "grades")
    grades = grades_val if grades_val is not None else {}
    ga_val = safe_get_field(grades, "a")
    ga = int(ga_val) if ga_val is not None else None
    gb_val = safe_get_field(grades, "b")
    gb = int(gb_val) if gb_val is not None else None
    gc_val = safe_get_field(grades, "c")
    gc = int(gc_val) if gc_val is not None else None
    gd_val = safe_get_field(grades, "d")
    gd = int(gd_val) if gd_val is not None else None

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
    top_a = top_a_val_exp if top_a_val_exp is not None else []
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
    rows.append(Text.from_markup(f"[{Y}][bold]ENTRY / TARGETS & EXITS / TECHNICALS[/][/]"))
    rows.append(Text.from_markup(f"[dim]{len(buy_sigs)} active buy signals[/]"))

    valid_buy_sigs = [bs for bs in buy_sigs if isinstance(bs, dict) and bs.get("symbol")]
    if valid_buy_sigs:
        sig_tbl = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            row_styles=["", "dim"],
        )
        sig_tbl.add_column("Sym", style="bold white", no_wrap=True, min_width=5)
        sig_tbl.add_column("Quality", justify="right", no_wrap=True, min_width=6)
        sig_tbl.add_column("Price", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("Buy Zone", justify="right", no_wrap=True, min_width=15)
        sig_tbl.add_column("Init Stop", justify="right", no_wrap=True, min_width=8)
        sig_tbl.add_column("Trail Stop", justify="right", no_wrap=True, min_width=8)
        sig_tbl.add_column("T +8%", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("T +20%", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("T +25%", justify="right", no_wrap=True, min_width=7)
        sig_tbl.add_column("RSI", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("ADX", justify="right", no_wrap=True, min_width=4)
        sig_tbl.add_column("Vol Surge", justify="right", no_wrap=True, min_width=8)
        sig_tbl.add_column("R/R", justify="right", no_wrap=True, min_width=5)
        sig_tbl.add_column("Base/Stage", no_wrap=True, max_width=18)
        sig_tbl.add_column("Sector", no_wrap=True, max_width=16)

        for bs in valid_buy_sigs:
            sym = str(safe_get_field(bs, "symbol", "--"))
            quality = safe_float(safe_get_field(bs, "signal_quality_score"))
            price = safe_float(safe_get_field(bs, "close") or safe_get_field(bs, "entry_price"))
            zone_start = safe_float(safe_get_field(bs, "buy_zone_start"))
            zone_end = safe_float(safe_get_field(bs, "buy_zone_end"))
            init_stop = safe_float(safe_get_field(bs, "initial_stop"))
            trail_stop = safe_float(safe_get_field(bs, "trailing_stop"))
            t8 = safe_float(safe_get_field(bs, "profit_target_8pct"))
            t20 = safe_float(safe_get_field(bs, "profit_target_20pct"))
            t25 = safe_float(safe_get_field(bs, "profit_target_25pct"))
            rsi_v = safe_float(safe_get_field(bs, "rsi"))
            adx_v = safe_float(safe_get_field(bs, "adx"))
            vol_surge = safe_float(safe_get_field(bs, "volume_surge_pct"))
            rr_v = safe_float(safe_get_field(bs, "risk_reward_ratio"))
            base_type = safe_get_field(bs, "base_type")
            market_stage = safe_get_field(bs, "market_stage")
            sector = (safe_get_field(bs, "sector", "") or "")[:16]

            quality_c = _composite_score_color(quality) if quality is not None else DIM
            zone_s = (
                f"${zone_start:.2f}-{zone_end:.2f}" if zone_start is not None and zone_end is not None else "--"
            )
            setup_parts = [p for p in (base_type, market_stage.replace("Stage ", "S") if market_stage else None) if p]
            setup_s = " · ".join(setup_parts) if setup_parts else "--"

            sig_tbl.add_row(
                sym,
                Text(f"{quality:.0f}" if quality is not None else "--", style=quality_c),
                Text(f"${price:.2f}" if price is not None else "--", style=DIM),
                Text(zone_s, style=CY),
                Text(f"${init_stop:.2f}" if init_stop is not None else "--", style=R),
                Text(f"${trail_stop:.2f}" if trail_stop is not None else "--", style=R),
                Text(f"${t8:.2f}" if t8 is not None else "--", style=G),
                Text(f"${t20:.2f}" if t20 is not None else "--", style=G),
                Text(f"${t25:.2f}" if t25 is not None else "--", style=G),
                Text(
                    f"{rsi_v:.0f}" if rsi_v is not None else "--",
                    style=R if rsi_v is not None and rsi_v > 70 else (G if rsi_v is not None and rsi_v < 30 else "white"),
                ),
                Text(f"{adx_v:.0f}" if adx_v is not None else "--", style=DIM),
                Text(
                    f"{vol_surge:+.0f}%" if vol_surge is not None else "--",
                    style=G if vol_surge is not None and vol_surge > 0 else DIM,
                ),
                Text(f"{rr_v:.2f}" if rr_v is not None else "--", style=CY),
                Text(setup_s, style=DIM if setup_s == "--" else "white"),
                Text(sector, style=DIM),
            )
        rows.append(sig_tbl)
    else:
        rows.append(Text.from_markup(f"[{Y}]No active buy signals[/]"))

    timestamp_val = safe_get_field(overview, "timestamp")
    age_s = f"  [dim]{fmt_age(timestamp_val)}[/]" if timestamp_val is not None else ""
    title = f"[bold magenta]SIGNALS - EXPANDED[/]{age_s}"
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
