"""Signal analysis panel functions."""

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
    safe_get_field,
    safe_get_list,
)


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

    # Extract fields once after error checks — no placeholder data in fail-fast
    top_scores = safe_get_list(safe_get_field(scores, "top")) if scores and not has_error(scores) else []
    buy_sigs = safe_get_list(safe_get_field(sig, "buy_sigs")) or []

    raw = safe_get_field(sig, "n") or 0
    total = safe_get_field(sig, "total") or 0
    d = safe_get_field(sig, "date")
    if hasattr(d, "strftime"):
        ds = d.strftime("%b %d")
    elif d and isinstance(d, str) and len(d) >= 10:
        try:
            from datetime import date as _date

            ds = _date.fromisoformat(str(d)[:10]).strftime("%b %d")
        except (ValueError, TypeError):
            ds = str(d)[:10]
    else:
        ds = "--"
    # Extract grade counts once
    grades = safe_get_field(sig, "grades") or {}
    ga = int(safe_get_field(grades, "a")) if safe_get_field(grades, "a") is not None else None
    gb = int(safe_get_field(grades, "b")) if safe_get_field(grades, "b") is not None else None
    gc = int(safe_get_field(grades, "c")) if safe_get_field(grades, "c") is not None else None
    gd = int(safe_get_field(grades, "d")) if safe_get_field(grades, "d") is not None else None
    top_a = safe_get_list(safe_get_field(sig, "top_a"))
    near = safe_get_list(safe_get_field(sig, "near"))
    trend = safe_get_list(safe_get_field(sig, "trend"))

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

    # ── Row 1: count  ·  7-day sparkline  ·  grade pool  ·  date ─────────────
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    spark_s = ""
    if len(trend) >= 2:
        counts = [int(safe_get_field(t, "buy_n")) if safe_get_field(t, "buy_n") is not None else 0 for t in reversed(trend)]
        max_b = max(counts) if counts else 1
        spark = "".join(SPARKLINE_CHARS[min(7, int(v / max(max_b, 1) * 7.9))] for v in counts)
        spark_s = f"  [{CY}]{spark}[/]"
    n_near = len(near)
    near_hint = f"  [{CY}]{n_near} near[/]" if n_near else ""
    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    rows = [
        Text.from_markup(
            f"[{buy_c}][bold]{raw} BUY[/][/]{spark_s}  [dim]from {total} screened  {ds}[/]"
            f"  [{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]{near_hint}"
        )
    ]

    # ── Row 2: A-grade radar (always; near-misses only when nothing better) ──
    if top_a:
        parts = []
        for s in top_a[:8]:
            sc = float(safe_get_field(s, "score")) if safe_get_field(s, "score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{safe_get_field(s, 'symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{safe_get_field(s, 'symbol', '')}[/][dim]--[/]")
        extra = f"  [dim]+{ga - min(ga, 8)} more[/]" if ga is not None and ga > 8 else ""
        rows.append(Text.from_markup("[dim]A radar:[/]  " + "  ".join(parts) + extra))
    elif near:
        parts = []
        for a in near[:8]:
            sc = float(safe_get_field(a, "score")) if safe_get_field(a, "score") is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = safe_get_field(a, "symbol", "")
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near threshold:[/]  " + "  ".join(parts)))

    # ── Row 3: Funnel arrow chain  ·  avg score  ·  top blockers ─────────────
    if sig_eval and not has_error(sig_eval):
        ev_tot = safe_get_field(sig_eval, "total")
        ev_t1 = safe_get_field(sig_eval, "t1")
        ev_t2 = safe_get_field(sig_eval, "t2")
        ev_t3 = safe_get_field(sig_eval, "t3")
        ev_t4 = safe_get_field(sig_eval, "t4")
        ev_t5 = safe_get_field(sig_eval, "t5")
        ev_avg = safe_get_field(sig_eval, "avg_score")
        # Validate required funnel fields
        if ev_tot is not None and ev_t5 is not None:
            ev_c = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
            rejected = safe_get_list(safe_get_field(sig_eval, "rejected"))
            if rejected:
                block_parts = []
                for rj in rejected[:3]:
                    reason_full = safe_get_field(rj, "evaluation_reason", "")
                    reason_abbr = _shorten_reason(reason_full)
                    description = safe_get_field(rj, "description", "")
                    n_count = safe_get_field(rj, "n", 0)
                    if description:
                        block_parts.append(f"[dim]{reason_abbr}:{n_count}[/] [bright_black]({description})[/]")
                    else:
                        block_parts.append(f"[dim]{reason_abbr}:{n_count}[/]")
                blocks_s = "  [dim]blocked:[/]  " + "  ".join(block_parts)
            else:
                blocks_s = ""
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

    rows.append(Rule(style="dim"))

    # ── Top Scores WITH Buy Signals (actionable opportunities) ────────────────
    # Build full buy signal details map for this section (normalize symbols for matching)
    buy_sig_details = {}
    for bs in buy_sigs:
        sym = safe_get_field(bs, "symbol")
        if sym:
            sym_norm = str(sym).upper().strip()
            buy_sig_details[sym_norm] = bs

    # Find stocks that have BOTH high composite score AND active buy signal
    scored_with_signals = [s for s in top_scores if str(safe_get_field(s, "symbol", "")).upper().strip() in buy_sig_details][
        :10
    ]  # Limit to top 10

    if scored_with_signals:
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
            sym = safe_get_field(score_item, "symbol", "--")
            comp_score = safe_get_field(score_item, "composite_score")
            sector = (safe_get_field(score_item, "sector", ""))[:12]
            sym_norm = str(sym).upper().strip()
            sig_obj = buy_sig_details.get(sym_norm)

            # Extract signal details (use score_item defaults if sig_obj missing)
            if sig_obj:
                swing_score = safe_get_field(sig_obj, "swing_score") or safe_get_field(sig_obj, "signal_quality_score")
                if swing_score is None:
                    swing_score = 0
                entry_qual = safe_get_field(sig_obj, "entry_quality_score", swing_score)
                buy_lvl = safe_get_field(sig_obj, "buylevel")
                stop_lvl = safe_get_field(sig_obj, "stoplevel")
                price = safe_get_field(sig_obj, "close")
                if price is None:
                    price = safe_get_field(score_item, "current_price")
            else:
                swing_score = 0
                entry_qual = 0
                buy_lvl = None
                stop_lvl = None
                price = safe_get_field(score_item, "current_price")

            # Calculate R/R ratio
            rr_ratio = None
            if buy_lvl and stop_lvl and float(stop_lvl) > 0:
                try:
                    rr_ratio = (float(buy_lvl) - float(stop_lvl)) / float(stop_lvl)
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.debug(f"Failed to calculate R/R ratio for {sym}: {e}")

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

    # ── Stock quality scores table (always show if data exists) ──
    show_full_scores = bool(top_scores)
    if show_full_scores:
        scores_msg = "(all candidates)" if not scored_with_signals else "(additional candidates without active signals)"
        rows.append(Text.from_markup(f"[{Y}][bold]TOP STOCK SCORES[/][/] [dim]{scores_msg}[/]"))
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
            sym = safe_get_field(sc, "symbol", "--")
            comp = safe_get_field(sc, "composite_score")
            mom = safe_get_field(sc, "momentum_score")
            qual = safe_get_field(sc, "quality_score")
            grwth = safe_get_field(sc, "growth_score")
            stab = safe_get_field(sc, "stability_score")
            rs_pct = safe_get_field(sc, "rs_percentile")
            chg = safe_get_field(sc, "change_percent")
            sector = (safe_get_field(sc, "sector", ""))[:12]
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
            sym_norm = str(sym).upper().strip()
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
    else:
        rows.append(Text.from_markup(f"[{Y}]No score data — check Data Health[/]"))

    # ── Near-miss strip (only when A-grade stocks exist above; otherwise shown on row 2) ──
    if near and top_a:
        rows.append(Rule(style="dim"))
        parts = []
        for a in near[:8]:
            sc = float(safe_get_field(a, "score")) if safe_get_field(a, "score") is not None else None
            sc_s = f"{sc:.0f}" if sc is not None else "--"
            sym = safe_get_field(a, "symbol", "")
            parts.append(f"[{CY}]{sym}[/][dim]{sc_s}[/]")
        rows.append(Text.from_markup("[dim]Near BUY (55-69):[/]  " + "  ".join(parts)))

    age_s = f"  [dim]{fmt_age(safe_get_field(sig, 'timestamp'))}[/]" if safe_get_field(sig, "timestamp") is not None else ""
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
    if scores and _error_panel("scores", scores, "SIGNALS", border="magenta"):
        return _error_panel("scores", scores, "SIGNALS", border="magenta")

    top_scores = []
    if isinstance(scores, dict) and isinstance(safe_get_field(scores, "top"), list):
        top_scores = safe_get_field(scores, "top")
    buy_sigs = safe_get_list(safe_get_field(sig, "buy_sigs")) or []
    if not isinstance(buy_sigs, list):
        buy_sigs = []
    total = safe_get_field(sig, "total")
    if total is None:
        return _error_panel("signals", {"_error": "Missing signal total count"}, "SIGNALS", border="magenta")

    raw = safe_get_field(sig, "n")
    if raw is None:
        return _error_panel("signals", {"_error": "Missing signal count (n)"}, "SIGNALS", border="magenta")
    total = safe_get_field(sig, "total")
    d = safe_get_field(sig, "date")
    if hasattr(d, "strftime"):
        ds = d.strftime("%b %d")
    elif d and isinstance(d, str) and len(d) >= 10:
        try:
            from datetime import date as _date

            ds = _date.fromisoformat(str(d)[:10]).strftime("%b %d")
        except (ValueError, TypeError):
            ds = str(d)[:10]
    else:
        ds = "--"
    g = safe_get_field(sig, "grades")
    if g and isinstance(g, dict):
        ga, gb, gc, gd = (int(safe_get_field(g, k)) if safe_get_field(g, k) is not None else None for k in ("a", "b", "c", "d"))
    else:
        ga, gb, gc, gd = None, None, None, None
    ga_s = f"{ga}" if ga is not None else "--"
    gb_s = f"{gb}" if gb is not None else "--"
    gc_s = f"{gc}" if gc is not None else "--"
    gd_s = f"{gd}" if gd is not None else "--"
    buy_c = G if raw >= 5 else (Y if raw >= 1 else (DIM if total == 0 else R))
    is_placeholder = False
    rows = [
        Text.from_markup(f"[{CY}][bold]SIGNAL OVERVIEW[/][/]"),
        Text.from_markup(
            f"[{buy_c}][bold]{raw} BUY SIGNALS[/][/]  [dim]from {total} screened  {ds}[/]  "
            f"[{G}]A:{ga_s}[/] [{CY}]B:{gb_s}[/] [{Y}]C:{gc_s}[/] [{R}]D:{gd_s}[/]  "
            "[dim]press [/][bold magenta]s[/][dim] to return[/]"
        ),
    ]

    top_a = safe_get_list(safe_get_field(sig, "top_a"))
    if top_a:
        parts = []
        for s in top_a:
            sc = float(safe_get_field(s, "score")) if safe_get_field(s, "score") is not None else None
            if sc is not None:
                sc_c = G if sc >= 90 else ("bright_green" if sc >= 85 else "green")
                parts.append(f"[{sc_c}]{safe_get_field(s, 'symbol', '')}[/][dim]{sc:.0f}[/]")
            else:
                parts.append(f"[dim]{safe_get_field(s, 'symbol', '')}[/][dim]--[/]")
        rows.append(Text.from_markup("[dim]A-grade radar:[/] " + "  ".join(parts)))

    if sig_eval and not has_error(sig_eval):
        ev_tot = safe_get_field(sig_eval, "total")
        ev_t5 = safe_get_field(sig_eval, "t5")
        ev_avg = safe_get_field(sig_eval, "avg_score")
        if ev_tot is not None and ev_t5 is not None:
            ev_c = G if ev_t5 >= 20 else (Y if ev_t5 >= 5 else R)
            t1 = safe_get_field(sig_eval, "t1")
            t2 = safe_get_field(sig_eval, "t2")
            t3 = safe_get_field(sig_eval, "t3")
            t4 = safe_get_field(sig_eval, "t4")
            has_full = all(v is not None for v in [t1, t2, t3, t4])
            if has_full:
                avg_score_str = f"{ev_avg:.0f}" if ev_avg is not None else "--"
                funnel = (
                    f"[dim]Funnel:[/] {ev_tot}[dim]→[/]{t1}[dim]→[/]{t2}"
                    f"[dim]→[/]{t3}[dim]→[/]{t4}[dim]→[/][{ev_c}]{ev_t5} qualified[/]"
                    f"  [dim]avg score:[/]{avg_score_str}"
                )
            else:
                avg_score_str = f"{ev_avg:.0f}" if ev_avg is not None else "--"
                funnel = f"[dim]Funnel:[/] {ev_tot}[dim]→[/][{ev_c}]{ev_t5} qualified[/]  [dim]avg score:[/]{avg_score_str}"
            rejected = safe_get_list(safe_get_field(sig_eval, "rejected"))
            if rejected:
                block_items = []
                for rj in rejected:
                    reason_full = safe_get_field(rj, "evaluation_reason", "")[:32]
                    description = safe_get_field(rj, "description", "")
                    n_count = safe_get_field(rj, "n", 0)
                    if description:
                        block_items.append(f"[dim]{reason_full}:{n_count}[/] [bright_black]({description[:40]})[/]")
                    else:
                        block_items.append(f"[dim]{reason_full}:{n_count}[/]")
                blocks = "  ".join(block_items)
                funnel += f"  [dim]blocked:[/] {blocks}"
            rows.append(Text.from_markup(funnel))

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
            price = safe_get_field(sc, "current_price")
            chg = safe_get_field(sc, "change_percent")
            mom_inputs = safe_get_field(sc, "momentum_inputs")
            vs50 = safe_get_field(sc, "price_vs_sma_50")
            if vs50 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs50 = safe_get_field(mom_inputs, "price_vs_sma_50")
            vs200 = safe_get_field(sc, "price_vs_sma_200")
            if vs200 is None and mom_inputs and isinstance(mom_inputs, dict):
                vs200 = safe_get_field(mom_inputs, "price_vs_sma_200")
            sector = (safe_get_field(sc, "sector", ""))[:14]
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

    # Add placeholder warning if needed
    if is_placeholder:
        rows.insert(
            0,
            Text.from_markup("[bold red]NO DATA - Scores unavailable[/]"),
        )

    border = "red" if is_placeholder else "magenta"
    title = (
        "[bold red]SIGNALS & SCORES ⚠ NO DATA[/]" if is_placeholder else "[bold magenta]SIGNALS & SCORES - EXPANDED[/]"
    )
    return Panel(
        Group(*rows),
        title=title,
        border_style=border,
        padding=(0, 1),
    )


__all__ = [
    "panel_signals_compact",
    "panel_signals_expanded",
]
