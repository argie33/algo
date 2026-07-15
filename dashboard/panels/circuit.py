"""Circuit breaker status panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from rich.console import ConsoleRenderable, RichCast

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

from ..data_validation import StrictValidationError, safe_float, safe_int
from ..formatters import (
    hbar,
)
from ..utilities import (
    G,
    R,
    Y,
)
from ._helpers import _error_panel


@register_panel(
    "circuit",
    endpoint_deps=["cb"],
    optional=False,
    description="Circuit breaker status",
)
def panel_circuit(cb: Any) -> Panel:  # noqa: C901
    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS", border="blue")
    if err_panel:
        return err_panel

    # Check data freshness: warn if circuit breaker status is stale
    # GOVERNANCE FIX: Check nested data_freshness dict (API response structure)
    # instead of looking for top-level timestamp field
    cb_stale_warning = ""
    if isinstance(cb, dict):
        data_freshness = cb.get("data_freshness")
        if isinstance(data_freshness, dict) and data_freshness.get("is_stale"):
            age_days = data_freshness.get("data_age_days", "?")
            cb_stale_warning = f" ⚠ STALE (data {age_days}d old)"

    if not isinstance(cb, dict):
        logger.error("[CIRCUIT] Circuit breaker data is not a dict: got %s", type(cb).__name__)
        return Panel(
            Text("Circuit breaker data is invalid", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    n_raw = cb.get("triggered_count")
    any_raw = cb.get("any_triggered")
    if n_raw is None:
        logger.error("[CIRCUIT] Missing critical field 'triggered_count' (breaker count)")
        return Panel(
            Text("Circuit breaker count missing (data_unavailable)", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    if any_raw is None:
        logger.error("[CIRCUIT] Missing critical field 'any_triggered' (breach flag)")
        return Panel(
            Text("Circuit breaker status missing (data_unavailable)", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    try:
        n_f = safe_int(n_raw, field_name="circuit_breaker_count")
    except StrictValidationError as e:
        logger.error("[CIRCUIT] Failed to parse breaker count: %s", e)
        return Panel(
            Text("Circuit breaker count invalid (data_unavailable)", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    any_f = any_raw if isinstance(any_raw, bool) else bool(any_raw)
    hc = R if any_f else G
    if not any_f:
        logger.debug("[CIRCUIT] No breakers triggered - display color defaulting to GREEN")
    hs = f"✗ {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED" if any_f else "✓ ALL CLEAR"
    tbl = Table.grid(padding=(0, 1), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)
    bs = cb.get("breakers")
    if bs is None:
        logger.warning("[CIRCUIT] Missing breaker list 'breakers' - no individual breaker data available")
        bs = None
    elif not isinstance(bs, list):
        logger.error("[CIRCUIT] Breaker list 'breakers' is not a list: got %s", type(bs).__name__)
        bs = None

    def fmt_b(br: Any) -> str:
        if br is None:
            return "[red]✗ INVALID[/]"  # Breaker data missing
        if not isinstance(br, dict):
            logger.debug("[CIRCUIT] Breaker entry is not a dict: got %s", type(br).__name__)
            return "[red]✗ INVALID[/]"  # Corrupted data
        fired = br.get("triggered")
        if fired is None:
            logger.debug("[CIRCUIT] Breaker missing 'triggered' status - cannot render")
            return "[red]✗ INVALID[/]"  # Critical field missing
        if not isinstance(fired, bool):
            logger.debug("[CIRCUIT] Breaker 'triggered' is not bool: got %s", type(fired).__name__)
            return "[red]✗ INVALID[/]"  # Data type error
        thr = br.get("threshold")
        cur = br.get("current")
        lbl_raw = br.get("label")
        if lbl_raw is None:
            logger.debug("[CIRCUIT] Breaker missing 'label' field")
            lbl_s = "[dim]-[/]"
        else:
            lbl_s = str(lbl_raw)[:20]
        if thr is None or cur is None:
            thr_f = safe_float(thr, default=None)
            thr_s = "[dim]-[/]" if thr_f is None else f"{thr_f:.0f}"
            cur_s = "[dim]-[/]" if cur is None else str(cur)
            unit_raw = br.get("unit")
            if unit_raw is None:
                logger.debug("[CIRCUIT] Breaker %s missing unit field 'unit'", lbl_s)
                unit_display = "[yellow]?[/]"
            else:
                unit_display = str(unit_raw)
            return f"[{R if fired else 'dim'}]{lbl_s}:[/]{cur_s}{unit_display}[dim]/{thr_s}{unit_display}[/]"
        try:
            thr_f = safe_float(thr, field_name="circuit_breaker_threshold", strict=True)
            cur_f = safe_float(cur, field_name="circuit_breaker_current", strict=True)
        except StrictValidationError as e:
            logger.error("[CIRCUIT] Breaker %s failed validation: %s", lbl_s, e)
            return f"[{R}]{lbl_s}:[/] [red]✗ BAD DATA[/]"
        if thr_f is not None and cur_f is not None:
            if thr_f > 0:
                util = cur_f / thr_f
            elif thr_f < 0 and cur_f < 0:
                util = min(cur_f / thr_f, 1.0)
            else:
                util = 0
        else:
            util = 0
        fc = R if fired else (Y if util >= 0.75 else G)
        if not fired and util < 0.75:
            logger.debug(
                f"[CIRCUIT] Breaker {lbl_s} not fired and utilization {util:.1%} "
                f"below warning threshold - color defaulting to GREEN"
            )
        ind = "[bold red] ![/]" if fired else ""
        pct_s = f"[dim] {util * 100:.0f}%[/]" if not fired else ""
        cur_fmt = (
            f"{cur_f:.1f}"
            if cur_f is not None and cur_f != int(cur_f)
            else (f"{int(cur_f)}" if cur_f is not None else "0")
        )
        unit_str = br.get("unit")
        if unit_str is None:
            logger.debug("[CIRCUIT] Breaker %s missing unit for display", lbl_s)
            unit_str = ""
        else:
            unit_str = str(unit_str)
        return (
            f"[{fc}]{lbl_s}:[/]{cur_fmt}{unit_str}[dim]/{thr_f:.0f}{unit_str}[/]{hbar(cur_f, thr_f, w=4)}{pct_s}{ind}"
        )

    if bs is not None:
        for a, b in zip(bs[::2], [*bs[1::2], None], strict=False):
            tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    parts = [Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl]
    title = f"[bold blue]CIRCUIT BREAKERS[/]{cb_stale_warning}  [dim][b] expand[/]"
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], parts)),
        title=title,
        border_style="blue",
        padding=(0, 1),
    )


@register_panel(
    "circuit_expanded",
    endpoint_deps=["cb"],
    optional=False,
    description="Circuit Breakers Expanded",
)
def panel_circuit_expanded(cb: Any) -> Panel:  # noqa: C901
    """Full-screen circuit breaker status - wide bars, % utilization, per-breaker detail."""
    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold blue]b[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS - EXPANDED", border="blue")
    if err_panel:
        return err_panel

    # Explicit validation of critical fields
    if not isinstance(cb, dict):
        logger.error("[CIRCUIT_EXPANDED] Circuit breaker data is not a dict: got %s", type(cb).__name__)
        return Panel(
            Text("Circuit breaker data is invalid", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS - EXPANDED[/]",
            border_style="red",
            padding=(0, 1),
        )

    n_f = cb.get("triggered_count")
    if n_f is None:
        logger.error("[CIRCUIT_EXPANDED] Missing critical field 'triggered_count' (breaker count)")
        return Panel(
            Text("Circuit breaker count missing (data_unavailable)", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS - EXPANDED[/]",
            border_style="red",
            padding=(0, 1),
        )

    any_f_raw = cb.get("any_triggered")
    if any_f_raw is None:
        logger.error("[CIRCUIT_EXPANDED] Missing critical field 'any_triggered' (breach flag)")
        return Panel(
            Text("Circuit breaker status missing (data_unavailable)", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS - EXPANDED[/]",
            border_style="red",
            padding=(0, 1),
        )

    if any_f_raw is None:
        logger.warning(
            "[CIRCUIT] Missing 'any' field in expanded circuit breaker data - defaulting to no breakers fired"
        )
        any_f = False
    else:
        any_f = any_f_raw if isinstance(any_f_raw, bool) else bool(any_f_raw)

    if any_f:
        rows.append(
            Text.from_markup(f"[bold {R}]⚠  {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED  -  TRADING HALTED[/]")
        )
    else:
        rows.append(Text.from_markup(f"[bold {G}]✓  ALL CLEAR  -  NO BREAKERS ACTIVE[/]"))
    rows.append(Rule(style="dim"))

    bs = cb.get("breakers")
    if bs is None or not isinstance(bs, list):
        error_type = "missing" if bs is None else f"invalid type {type(bs).__name__}"
        logger.warning(f"[CIRCUIT_EXPANDED] Breaker list 'breakers' {error_type} - no breaker data available")
        rows.append(Text(f"breaker list {error_type} (data_unavailable)", style="dim"))
    elif len(bs) == 0:
        logger.warning("[CIRCUIT_EXPANDED] Breaker list 'breakers' is empty")
        rows.append(Text("no breaker entries", style="dim"))
    else:
        tbl = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="dim bold",
            padding=(0, 2),
            expand=True,
            row_styles=["", "dim"],
        )
        tbl.add_column("Breaker", no_wrap=True, min_width=20)
        tbl.add_column("Current", justify="right", no_wrap=True, min_width=8)
        tbl.add_column("Threshold", justify="right", no_wrap=True, min_width=9)
        tbl.add_column("Utilization", no_wrap=True, min_width=18)
        tbl.add_column("Status", justify="center", no_wrap=True, min_width=8)

        for br in bs:
            if not isinstance(br, dict):
                logger.debug("[CIRCUIT_EXPANDED] Breaker entry is not a dict: got %s", type(br).__name__)
                continue

            lbl_val = br.get("label")
            if lbl_val is None:
                logger.debug("[CIRCUIT_EXPANDED] Breaker missing 'label' field")
                lbl = "[dim]-[/]"
            else:
                lbl = str(lbl_val)

            cur = br.get("current")
            thr = br.get("threshold")
            u_val = br.get("unit")
            if u_val is None:
                logger.debug("[CIRCUIT_EXPANDED] Breaker %s missing unit field 'unit'", lbl)
                u = "[dim]?[/]"
            else:
                u = str(u_val)

            fired_val = br.get("triggered")
            if fired_val is None:
                logger.debug("[CIRCUIT_EXPANDED] Breaker %s missing 'triggered' status", lbl)
                continue
            if not isinstance(fired_val, bool):
                logger.debug(
                    "[CIRCUIT_EXPANDED] Breaker %s 'triggered' is not bool: got %s", lbl, type(fired_val).__name__
                )
                continue
            fired = fired_val

            util_high = False
            if cur is None or thr is None:
                cur_s = f"{cur}{u}" if cur is not None else "[dim]-[/]"
                thr_s = f"{thr}{u}" if thr is not None else "[dim]-[/]"
                util_bar = Text("[dim]- / -[/]", style="dim")
                status = Text("UNKNOWN", style="dim")
            else:
                try:
                    thr_f = safe_float(thr, field_name="circuit_breaker_threshold", strict=True)
                    cur_f = safe_float(cur, field_name="circuit_breaker_current", strict=True)
                except StrictValidationError as e:
                    logger.error("[CIRCUIT_EXPANDED] Breaker %s failed validation: %s", lbl, e)
                    status = Text("BAD DATA", style=R)
                    util_bar = Text("!/ !", style=R)
                    cur_s = f"{cur}{u}"
                    thr_s = f"{thr}{u}"
                else:
                    if thr_f is not None and cur_f is not None:
                        if thr_f > 0:
                            util = cur_f / thr_f
                        elif thr_f < 0 and cur_f < 0:
                            util = min(cur_f / thr_f, 1.0)
                        else:
                            util = 0
                    else:
                        util = 0
                    util_high = util >= 0.75
                    util_pct = util * 100
                    fc = R if fired else (Y if util >= 0.75 else G)
                    bar_f = int(min(util, 1.0) * 12)
                    bar_s = Text.from_markup(
                        f"[{fc}]{'█' * bar_f}[/][dim]{'░' * (12 - bar_f)}[/]  [{fc}]{util_pct:.0f}%[/]"
                    )
                    cur_s = f"{cur_f:.1f}{u}" if u else f"{cur_f:.2f}"
                    thr_s = f"{thr_f:.1f}{u}" if u else f"{thr_f:.2f}"
                    util_bar = bar_s
                    if fired:
                        status = Text.from_markup(f"[bold {R}]FIRED[/]")
                    elif util >= 0.75:
                        status = Text.from_markup(f"[{Y}]WARNING[/]")
                    else:
                        if util < 0.75:
                            logger.debug(
                                f"[CIRCUIT_EXPANDED] Breaker {lbl} utilization {util:.1%} "
                                f"below threshold - status defaulting to CLEAR"
                            )
                        status = Text.from_markup(f"[{G}]CLEAR[/]")

            tbl.add_row(
                Text(
                    lbl,
                    style=(f"bold {R}" if fired else ("white" if util_high else "dim")),
                ),
                Text(cur_s, style=R if fired else "white"),
                Text(thr_s, style="dim"),
                util_bar,
                status,
            )
        rows.append(tbl)

        if any_f:
            rows.append(Rule(style="dim"))
            rows.append(
                Text.from_markup(
                    f"[bold {R}]Trading is halted until the circuit breaker condition clears.[/]\n"
                    f"[dim]Breakers auto-reset when the monitored metric falls below threshold.[/]"
                )
            )

    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], rows)),
        title="[bold blue]CIRCUIT BREAKERS - EXPANDED[/]  [dim][b] return[/]",
        border_style="blue",
        padding=(0, 1),
    )


__all__ = [
    "panel_circuit",
    "panel_circuit_expanded",
]
