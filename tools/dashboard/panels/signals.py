"""Signal analysis panel functions."""

import logging

from utils.safe_data_conversion import safe_float


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


def _format_signal_date(date_val):
    """Format date value for display."""
    if hasattr(date_val, "strftime"):
        return date_val.strftime("%b %d")
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
    t = (t or "").replace("WEEKLY_", "W_").replace("STAGE_2", "S2").replace("STAGE2", "S2")
    t = t.replace("BREAKOUT", "BKT").replace("MOMENTUM", "MOM").replace("REVERSAL", "REV")
    t = t.replace("PULLBACK", "PB").replace("TREND", "TRD").replace("_FOLLOW", "")
    return t[:12]


def _build_signal_header(sig_data: dict, scores_data: dict | None) -> tuple[list, int, int]:
    """Build signal header row (count, sparkline, grades, date).

    Returns empty rows if input validation fails (missing required structure).
    """
    rows: list[Text] = []
    if not isinstance(sig_data, dict) or has_error(sig_data):
        return rows, 0, 0
    overview = extract_signal_overview(sig_data)
    if has_error(overview):
        return rows, 0, 0

    raw = safe_get_field(overview, "n") or 0
    total = safe_get_field(overview, "total") or 0
    ds = _format_signal_date(safe_get_field(overview, "date"))

    grades = safe_get_dict(safe_get_field(overview, "grades", {}))
    ga = int(safe_get_field(grades, "a")) if safe_get_field(grades, "a") is not None else None
    gb = int(safe_get_field(grades, "b")) if safe_get_field(grades, "b") is not None else None
    gc = int(safe_get_field(grades, "c")) if safe_get_field(grades, "c") is not None else None
    gd = int(safe_get_field(grades, "d")) if safe_get_field(grades, "d") is not None else None

    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))

    spark_s = ""
    trend = safe_get_list(safe_get_field(overview, "trend", []))
    if len(trend) >= 2:
        counts = [int(safe_get_field(t, "buy_n")) if safe_get_field(t, "buy_n") is not None else 0 for t in reversed(trend)]
        max_b = max(counts) if counts else 1
        spark = "".join(SPARKLINE_CHARS[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
        spark_s = f"  [{CY}]{spark}[/]"

    near = safe_get_list(safe_get_field(overview, "near", []))
    n_near = len(near)
    near_hint = f"  [{CY}]{n_near} near[/]" if n_near else ""

    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"

    rows.append(Text.from_markup(
        f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
        f"  [{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]{near_hint}"
    ))

    return rows, raw, total


def _build_grade_radar(sig_data: dict) -> list:
    """Build A-grade radar row or near-miss fallback.

    Returns empty list if input validation fails (missing required structure).
    """
    rows: list[Text] = []
    if not isinstance(sig_data, dict) or has_error(sig_data):
        return rows
    overview = extract_signal_overview(sig_data)
    if has_error(overview):
        return rows
    top_a = safe_get_list(safe_get_field(overview, "top_a", []))
    near = safe_get_list(safe_get_field(overview, "near", []))

    if top_a:
        parts = []
        for s in top_a[:8]:
            sc = float(safe_get_field(s, "score")) if safe_get_field(s, "score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{safe_get_field(s, 'symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{safe_get_field(s, 'symbol', '')}[/][dim]--[/]")
        grades_dict = safe_get_dict(safe_get_field(overview, "grades", {}))
        ga = safe_get_field(grades_dict, "a")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga is not None and ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        parts = []
        for a in near[:8]:
            sc = float(safe_get_field(a, "score")) if safe_get_field(a, "score") is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = safe_get_field(a, 'symbol', '')
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    return rows


def _build_funnel_row(sig_eval_data: dict | None) -> list:
    """Build funnel arrow chain row with avg score and top blockers.

    Returns empty list if input is missing or has errors.
    """
    rows: list[Text] = []
    if not sig_eval_data or has_error(sig_eval_data):
        return rows
    if not isinstance(sig_eval_data, dict):
        return rows

    funnel = extract_eval_funnel(sig_eval_data)
    if has_error(funnel):
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
        rejected = safe_get_list(safe_get_field(funnel, "rejected", []))

        blocks_s = ""
        if rejected:
            block_parts = []
            for rj in rejected[:3]:
                reason_abbr = _shorten_reason(safe_get_field(rj, "evaluation_reason", ""))
                description = safe_get_field(rj, "description", "")
                if description:
                    block_parts.append(f"[dim]{reason_abbr}:{safe_get_field(rj, 'n', 0)}[/] [bright_black]({description})[/]")
                else:
                    block_parts.append(f"[dim]{reason_abbr}:{safe_get_field(rj, 'n', 0)}[/]")
            blocks_s = "  [dim]blocked:[/]  " + "  ".join(block_parts)

        has_full_funnel = all(v is not None for v in [ev_t1, ev_t2, ev_t3, ev_t4])
        if has_full_funnel:
            funnel_s = (
                f"[dim]Funnel:[/] {ev_tot}[dim]→[/]{ev_t1}[dim]→[/]{ev_t2}"
                f"[dim]→[/]{ev_t3}[dim]→[/]{ev_t4}[dim]→[/][{ev_c}]{ev_t5}[/]"
            )
        else:
            funnel_s = f"[dim]{ev_tot} →[/] [{ev_c}]{ev_t5} qualified[/]"

        avg_s = f"  [dim]avg score:[/][white]{ev_avg:.0f}[/]" if ev_avg is not None else ""
        rows.append(Text.from_markup(funnel_s + avg_s + blocks_s))

    return rows


def _build_buy_signals_table(scored_with_signals: list, buy_sig_details: dict) -> list:
    """Build active buy signals table section.

    Validates input is list and dict before accessing fields.
    """
    rows: list[Text | Table | Rule] = []
    if not isinstance(scored_with_signals, list):
        return rows
    if not scored_with_signals:
        return rows
    if not isinstance(buy_sig_details, dict):
        return rows

    rows.append(
        Text.from_markup(
            f"[{G}][bold]ACTIVE BUY SIGNALS ★[/][/] [dim]({len(scored_with_signals)} trades with price targets)[/]"
        )
    )
    sig_table = Table(
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
        sym = score_item.get("symbol", "--")
        comp_score = score_item.get("composite_score")
        sym_norm = str(sym).upper().strip()
        sig_obj = buy_sig_details.get(sym_norm)

        if sig_obj:
            swing_score = sig_obj.get("swing_score") or sig_obj.get("signal_quality_score") or 0
            entry_qual = sig_obj.get("entry_quality_score", swing_score)
            buy_lvl = sig_obj.get("buylevel")
            stop_lvl = sig_obj.get("stoplevel")
            price = sig_obj.get("close") or score_item.get("current_price")
        else:
            swing_score = 0
            entry_qual = 0
            buy_lvl = None
            stop_lvl = None
            price = score_item.get("current_price")

        rr_ratio = None
        if buy_lvl and stop_lvl and float(stop_lvl) > 0:
            try:
                rr_ratio = (float(buy_lvl) - float(stop_lvl)) / float(stop_lvl)
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        comp_v = float(comp_score) if comp_score is not None else 0
        comp_c = _composite_score_color(comp_v)
        swing_c = G if swing_score >= 80 else (CY if swing_score >= 70 else Y)
        rr_c = G if rr_ratio and rr_ratio > 1.5 else (Y if rr_ratio and rr_ratio > 1 else (CY if rr_ratio else DIM))

        sig_table.add_row(
            Text(sym, style=f"bold {G}"),
            Text(f"{comp_v:.0f}", style=comp_c),
            Text(f"▲{swing_score:.0f}", style=swing_c),
            Text(f"${float(price):.2f}" if price else "--", style="dim"),
            Text(f"${float(buy_lvl):.2f}" if buy_lvl else "--", style=CY),
            Text(f"${float(stop_lvl):.2f}" if stop_lvl else "--", style=R),
            Text(f"{rr_ratio:.2f}" if rr_ratio else "--", style=rr_c),
            Text(f"{entry_qual:.0f}", style=CY),
        )
    rows.append(sig_table)
    rows.append(Rule(style="dim"))
    return rows


def _build_scores_table(top_scores: list) -> list:
    """Build stock quality scores table.

    Validates input is list before accessing items.
    """
    rows: list[Text | Table] = []
    if not isinstance(top_scores, list):
        rows.append(Text.from_markup(f"[{Y}]Invalid score data structure — check Data Health[/]"))
        return rows
    if not top_scores:
        rows.append(Text.from_markup(f"[{Y}]No score data — check Data Health[/]"))
        return rows

    rows.append(Text.from_markup(f"[{Y}][bold]TOP STOCK SCORES[/][/] [dim](additional candidates without active signals)[/]"))
    t = Table(
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
        sym = sc.get("symbol", "--")
        comp = sc.get("composite_score")
        mom = sc.get("momentum_score")
        qual = sc.get("quality_score")
        grwth = sc.get("growth_score")
        stab = sc.get("stability_score")
        rs_pct = sc.get("rs_percentile")
        chg = sc.get("change_percent")
        sector = (sc.get("sector", ""))[:12]
        comp_v = float(comp) if comp is not None else 0
        sc_c = _composite_score_color(comp_v)

        try:
            chg_v = float(chg) if chg is not None and chg != "" else None
        except (ValueError, TypeError):
            chg_v = None
        chg_c = G if (chg_v or 0) > 0 else (R if (chg_v or 0) < 0 else DIM)

        try:
            rs_v = float(rs_pct) if rs_pct is not None and rs_pct != "" else None
        except (ValueError, TypeError):
            rs_v = None

        t.add_row(
            sym,
            Text(f"{comp_v:.0f}", style=sc_c),
            _score_cell(mom),
            _score_cell(qual),
            _score_cell(grwth),
            _score_cell(stab),
            Text(f"{rs_v:.0f}" if rs_v is not None else "--", style=G if (rs_v or 0) >= 70 else DIM),
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
def panel_signals_compact(sig, sig_eval=None, scores=None):
    """Signals & screening — composite score top candidates with pipeline funnel context."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel
    if scores and has_error(scores):
        return _error_panel("scores", scores, "SIGNALS", border="magenta")

    overview = extract_signal_overview(sig)
    if has_error(overview):
        return _error_panel("signals", {"_error": "Signal overview extraction failed"}, "SIGNALS", border="magenta")

    top_scores = None
    if scores and isinstance(scores, dict) and not has_error(scores):
        top_scores = scores.get("top")
    if not isinstance(top_scores, list):
        top_scores = []

    buy_sigs = overview.get("buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []

    rows, _, _ = _build_signal_header(sig, scores)
    rows.extend(_build_grade_radar(sig))
    rows.append(Rule(style="dim"))
    rows.extend(_build_funnel_row(sig_eval))
    rows.append(Rule(style="dim"))

    buy_sig_details = {}
    for bs in buy_sigs:
        sym = bs.get("symbol")
        if sym:
            sym_norm = str(sym).upper().strip()
            buy_sig_details[sym_norm] = bs

    scored_with_signals = [s for s in top_scores if str(s.get("symbol", "")).upper().strip() in buy_sig_details][:10]

    rows.extend(_build_buy_signals_table(scored_with_signals, buy_sig_details))

    if scored_with_signals:
        rows.append(Text.from_markup(f"[{Y}][bold]TOP STOCK SCORES[/][/] [dim](all candidates)[/]"))
    rows.extend(_build_scores_table(top_scores))

    near = overview.get("near") if overview.get("near") is not None else []
    top_a = overview.get("top_a") if overview.get("top_a") is not None else []
    if near and top_a:
        rows.append(Rule(style="dim"))
        parts = []
        for a in near[:8]:
            sc = safe_float(a.get("score"), default=0.0, context="score") if a.get("score") is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = a.get('symbol', '')
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near BUY (55-69):[/]  " + "  ".join(parts)))

    age_s = f"  [dim]{fmt_age(overview.get('timestamp'))}[/]" if overview.get("timestamp") is not None else ""
    title = "[bold magenta]TOP SCORES & SIGNALS[/]"
    return Panel(
        Group(*rows),
        title=f"{title}{age_s}  [dim][s] expand[/]",
        border_style="magenta",
        padding=(0, 1),
    )


def panel_signals_expanded(sig, sig_eval=None, scores=None):
    """Full-screen signals & scores - pipeline funnel context, detailed score breakdowns, and all top candidates."""
    err_panel = _error_panel("signals", sig, "SIGNALS", border="magenta")
    if err_panel:
        return err_panel
    if scores and has_error(scores):
        return _error_panel("scores", scores, "SIGNALS", border="magenta")

    overview = extract_signal_overview(sig)
    if has_error(overview):
        return _error_panel("signals", {"_error": "Signal overview extraction failed"}, "SIGNALS", border="magenta")

    raw = overview.get("n")
    total = overview.get("total")

    if raw is None or total is None:
        return _error_panel("signals", {"_error": "Missing signal counts"}, "SIGNALS", border="magenta")

    top_scores = None
    if scores and isinstance(scores, dict) and not has_error(scores):
        top_scores = scores.get("top")
    if not isinstance(top_scores, list):
        top_scores = []

    buy_sigs = overview.get("buy_sigs")
    if not isinstance(buy_sigs, list):
        buy_sigs = []
    ds = _format_signal_date(overview.get("date"))

    grades = overview.get("grades") if overview.get("grades") is not None else {}
    ga = int(grades.get("a")) if grades.get("a") is not None else None
    gb = int(grades.get("b")) if grades.get("b") is not None else None
    gc = int(grades.get("c")) if grades.get("c") is not None else None
    gd = int(grades.get("d")) if grades.get("d") is not None else None

    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))

    rows = [
        Text.from_markup(f"[{CY}][bold]SIGNAL OVERVIEW[/][/]"),
        Text.from_markup(
            f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
            f"[{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]  "
            "[dim]press [/][bold magenta]s[/][dim] to return[/]"
        ),
    ]

    top_a = overview.get("top_a") if overview.get("top_a") is not None else []
    if top_a:
        parts = []
        for s in top_a:
            sc = safe_float(s.get("score"), default=0.0, context="score") if s.get("score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{s.get('symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{s.get('symbol', '')}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    rows.extend(_build_funnel_row(sig_eval))
    rows.append(Rule(style="dim"))
    rows.append(Text.from_markup(f"[{Y}][bold]DETAILED SCORE BREAKDOWN[/][/]"))

    buy_sig_map_exp = _build_buy_sig_map(buy_sigs)
    rows.append(Text.from_markup(f"[dim]Top {len(top_scores or [])} candidates with component scores[/]"))

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
            sym = str(sc.get("symbol", "--"))
            sym_norm = sym.upper().strip()
            comp = sc.get("composite_score")
            mom = sc.get("momentum_score")
            qual = sc.get("quality_score")
            val = sc.get("value_score")
            grwth = sc.get("growth_score")
            stab = sc.get("stability_score")
            pos = sc.get("positioning_score")
            rs_pct = sc.get("rs_percentile")
            price = sc.get("current_price")
            chg = sc.get("change_percent")
            mom_inputs = sc.get("momentum_inputs")
            vs50 = sc.get("price_vs_sma_50")
            if vs50 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs50 = mom_inputs.get("price_vs_sma_50")
            vs200 = sc.get("price_vs_sma_200")
            if vs200 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs200 = mom_inputs.get("price_vs_sma_200")
            sector = (sc.get("sector", ""))[:14]
            comp_v = float(comp) if comp is not None else 0
            sc_c = _composite_score_color(comp_v)

            try:
                chg_v = float(chg) if chg is not None and chg != "" else None
            except (ValueError, TypeError):
                chg_v = None
            try:
                vs50_v = float(vs50) if vs50 is not None else None
                vs200_v = float(vs200) if vs200 is not None else None
                rs_v = float(rs_pct) if rs_pct is not None and rs_pct != "" else None
            except (ValueError, TypeError):
                vs50_v = vs200_v = rs_v = None
            chg_c = G if (chg_v or 0) > 0 else (R if (chg_v or 0) < 0 else DIM)

            sig_tbl.add_row(
                sym,
                Text(f"{comp_v:.0f}", style=sc_c),
                _swing_cell(buy_sig_map_exp.get(sym_norm)),
                _score_cell(mom),
                _score_cell(qual),
                _score_cell(val),
                _score_cell(grwth),
                _score_cell(stab),
                _score_cell(pos),
                Text(f"{rs_v:.0f}" if rs_v is not None else "--", style=G if (rs_v or 0) >= 70 else DIM),
                Text(f"${float(price):.2f}" if price else "--", style=DIM),
                Text(f"{chg_v:+.1f}%" if chg_v is not None else "--", style=chg_c),
                Text(f"{vs50_v:+.1f}%" if vs50_v is not None else "--", style=G if (vs50_v or 0) > 0 else R),
                Text(f"{vs200_v:+.1f}%" if vs200_v is not None else "--", style=G if (vs200_v or 0) > 0 else R),
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
