"""Circuit breaker status panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from rich.console import ConsoleRenderable, RichCast

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from panel_registry import register_panel as register_panel
else:
    try:
        from panel_registry import register_panel
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
def panel_circuit(cb: Any) -> Panel:
    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS", border="blue")
    if err_panel:
        return err_panel
    if not isinstance(cb, dict):
        return Panel(
            Text("Circuit breaker data is invalid", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    n_raw = cb.get("n")
    any_raw = cb.get("any")
    if n_raw is None or any_raw is None:
        return Panel(
            Text("Circuit breaker data missing critical fields", style="dim"),
            title="[bold blue]CIRCUIT BREAKERS[/]",
            border_style="red",
            padding=(0, 1),
        )
    n_f = safe_int(n_raw, default=0, field_name="circuit_breaker_count")
    any_f = any_raw if isinstance(any_raw, bool) else bool(any_raw)
    hc = R if any_f else G
    hs = f"✗ {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED" if any_f else "✓ ALL CLEAR"
    tbl = Table.grid(padding=(0, 1), expand=True)
    tbl.add_column("a", ratio=1)
    tbl.add_column("b", ratio=1)
    bs = cb.get("bs")
    if bs is None:
        bs = []
    for a, b in zip(bs[::2], [*bs[1::2], None], strict=False):

        def fmt_b(br: Any) -> str:
            if br is None:
                return ""
            if not isinstance(br, dict):
                return ""
            fired = br.get("fired")
            if fired is None:
                return ""
            thr = br.get("thr")
            cur = br.get("cur")
            lbl_s = str(br.get("lbl", "N/A"))[:20]
            if thr is None or cur is None:
                thr_f = safe_float(thr, default=None)
                thr_s = "--" if thr_f is None else f"{thr_f:.0f}"
                cur_s = "--" if cur is None else str(cur)
                return (
                    f"[{R if fired else 'dim'}]{lbl_s}:[/]{cur_s}{br.get('u', '')!s}[dim]/{thr_s}{br.get('u', '')!s}[/]"
                )
            try:
                thr_f = safe_float(thr, strict=True, field_name="circuit_breaker_threshold")
                cur_f = safe_float(cur, strict=True, field_name="circuit_breaker_current")
            except StrictValidationError:
                return f"[{R}]{lbl_s}:[/] [red]✗ BAD DATA[/]"
            if thr_f > 0:
                util = cur_f / thr_f
            elif thr_f < 0 and cur_f < 0:
                util = min(cur_f / thr_f, 1.0)
            else:
                util = 0
            fc = R if fired else (Y if util >= 0.75 else G)
            ind = "[bold red] ![/]" if fired else ""
            pct_s = f"[dim] {util * 100:.0f}%[/]" if not fired else ""
            cur_fmt = f"{cur_f:.1f}" if cur_f != int(cur_f) else f"{int(cur_f)}"
            return (
                f"[{fc}]{lbl_s}:[/]{cur_fmt}{br.get('u', '')!s}"
                f"[dim]/{thr_f:.0f}{br.get('u', '')!s}[/]{hbar(cur_f, thr_f, w=4)}{pct_s}{ind}"
            )

        tbl.add_row(Text.from_markup(fmt_b(a)), Text.from_markup(fmt_b(b)))
    parts = [Text.from_markup(f"[{hc}][bold]{hs}[/bold][/]"), tbl]
    return Panel(
        Group(*cast(list[ConsoleRenderable | RichCast | str], parts)),
        title="[bold blue]CIRCUIT BREAKERS[/]  [dim][b] expand[/]",
        border_style="blue",
        padding=(0, 1),
    )


@register_panel(
    "circuit_expanded",
    endpoint_deps=["cb"],
    optional=False,
    description="Circuit Breakers Expanded",
)
def panel_circuit_expanded(cb: Any) -> Panel:
    """Full-screen circuit breaker status — wide bars, % utilization, per-breaker detail."""
    rows: list[Text | Rule | Table] = [
        Text.from_markup("[dim]press [/][bold blue]b[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    err_panel = _error_panel("circuit breakers", cb, "CIRCUIT BREAKERS - EXPANDED", border="blue")
    if err_panel:
        return err_panel

    n_f = cb["n"]
    any_f = cb["any"]
    if any_f:
        rows.append(
            Text.from_markup(f"[bold {R}]⚠  {n_f} BREAKER{'S' if n_f != 1 else ''} FIRED  —  TRADING HALTED[/]")
        )
    else:
        rows.append(Text.from_markup(f"[bold {G}]✓  ALL CLEAR  —  NO BREAKERS ACTIVE[/]"))
    rows.append(Rule(style="dim"))

    bs = cb.get("bs")
    if not bs:
        rows.append(Text("no breaker data", style="dim"))
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
            lbl_val = br.get("lbl")
            lbl = str(lbl_val if lbl_val is not None else "--")
            cur = br.get("cur")
            thr = br.get("thr")
            u_val = br.get("u")
            u = str(u_val if u_val is not None else "")
            fired = br["fired"]

            util_high = False
            if cur is None or thr is None:
                cur_s = f"{cur}{u}" if cur is not None else "--"
                thr_s = f"{thr}{u}" if thr is not None else "--"
                util_bar = Text("-- / --", style="dim")
                status = Text("UNKNOWN", style="dim")
            else:
                try:
                    thr_f = safe_float(thr, strict=True, field_name="circuit_breaker_threshold")
                    cur_f = safe_float(cur, strict=True, field_name="circuit_breaker_current")
                except StrictValidationError:
                    status = Text("BAD DATA", style=R)
                    util_bar = Text("!/ !", style=R)
                    cur_s = f"{cur}{u}"
                    thr_s = f"{thr}{u}"
                else:
                    if thr_f > 0:
                        util = cur_f / thr_f
                    elif thr_f < 0 and cur_f < 0:
                        util = min(cur_f / thr_f, 1.0)
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
