"""Economic indicators and calendar panel functions."""

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


from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float

from ..error_boundary import has_error
from ..utilities import (
    G,
    R,
    Y,
)
from ._helpers import _error_panel
from .data_extractors import extract_economic_indicators


def _build_calendar_rows(econ_cal) -> list:
    """Extract and format economic calendar events."""
    rows: list[Text | Rule] = []
    # Fail-fast: return early if API error detected
    if has_error(econ_cal):
        return rows

    econ_cal_items = (
        econ_cal.get("items")
        if isinstance(econ_cal, dict) and "items" in econ_cal
        else (econ_cal if isinstance(econ_cal, list) else [])
    )
    valid_cal = econ_cal_items if econ_cal_items else []

    if not valid_cal:
        return rows

    from datetime import date

    rows.append(Rule(style="dim"))
    imp_c = {"HIGH": "bold bright_red", "MEDIUM": "yellow", "LOW": "dim"}
    today = date.today()
    seen_keys = set()

    for ev in valid_cal[:6]:
        ed_raw = ev.get("event_date")
        try:
            ed = date.fromisoformat(str(ed_raw)) if ed_raw else None
        except (ValueError, TypeError):
            ed = None
        full_nm = ev.get("event_name") or ""
        name = str(full_nm)[:24]
        key = (str(ed_raw) + str(full_nm)[:24]).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        imp = (ev.get("importance") or "LOW").upper()
        ic = imp_c.get(imp, "dim")
        f_v = ev.get("forecast") if ev.get("forecast") is not None else ev.get("forecast_value")
        a_v = ev.get("actual") if ev.get("actual") is not None else ev.get("actual_value")
        p_v = ev.get("previous") if ev.get("previous") is not None else ev.get("previous_value")
        if ed == today:
            when = "TODAY"
        elif ed is not None:
            delta = (ed - today).days
            when = f"+{delta}d" if delta > 0 else "YST"
        else:
            when = "--"
        vals = ""
        f_f: float | None = None
        if a_v is not None:
            a_f = safe_float(a_v, default=None)
            if a_f is not None:
                f_f = safe_float(f_v, default=a_f) or a_f
                ac = G if a_f <= f_f else R
                vals = f" [{ac}]A={a_f:.1f}[/]"
        elif f_v is not None:
            f_f = safe_float(f_v, default=None)
            if f_f is not None:
                vals = f" [dim]F={f_f:.1f}[/]"
        if p_v is not None:
            p_f = safe_float(p_v, default=None)
            if p_f is not None:
                vals += f"[dim] P={p_f:.1f}[/]"
        et = ev.get("event_time")
        et_s = f" [dim]{str(et)[:5]}[/]" if et else ""
        rows.append(Text.from_markup(f"[{ic}]{when!s:<5}[/]{et_s} [white]{name!s}[/]{vals}"))

    return rows


@register_panel(
    "eco",
    endpoint_deps=["eco"],
    optional=True,
    description="Economic Pulse",
)
def panel_economic_pulse(eco, econ_cal=None):
    """Economic factors the algo uses to calculate market exposure score."""
    err_panel = _error_panel("economic pulse", eco, "ECONOMIC INPUTS", border="bright_magenta")
    if err_panel:
        return err_panel
    rows: list = []

    indicators = extract_economic_indicators(eco)
    t10 = indicators.get("t10")
    t2 = indicators.get("t2")
    t3m = indicators.get("t3m")
    t6m = indicators.get("t6m")
    yc10_2 = indicators.get("yc_10_2")
    yc10_3m = indicators.get("yc_10_3m")
    hy = indicators.get("hy")
    ig = indicators.get("ig")
    oil = indicators.get("oil")
    nfci = indicators.get("nfci")
    fed_funds = indicators.get("fed_funds")
    cpi_yoy = indicators.get("cpi_yoy")
    unrate = indicators.get("unrate")
    be10 = indicators.get("be10")
    be5 = indicators.get("be5")
    dxy = indicators.get("dxy")
    mortgage = indicators.get("mortgage")
    umcsent = indicators.get("umcsent")

    # Treasury yields (short to long) + Fed Funds Rate
    y_parts = []
    if t3m is not None:
        y_parts.append(f"[dim]3M Treasury:[/][white]{t3m:.2f}%[/]")
    if t6m is not None:
        y_parts.append(f"[dim]6M:[/][white]{t6m:.2f}%[/]")
    if t2 is not None:
        y_parts.append(f"[dim]2Y:[/][white]{t2:.2f}%[/]")
    if t10 is not None:
        y_parts.append(f"[dim]10Y:[/][white]{t10:.2f}%[/]")
    if fed_funds is not None:
        y_parts.append(f"[dim]Fed Rate:[/][white]{fed_funds:.2f}%[/]")
    if y_parts:
        rows.append(Text.from_markup("  ".join(y_parts)))

    # Yield curve
    if yc10_2 is not None:
        ycc = G if yc10_2 >= 0.5 else (Y if yc10_2 >= 0 else R)
        inv = "  [bold red]INV[/]" if yc10_2 < 0 else ""
        c3m = f"  [dim]10Y-3M:[/][{ycc}]{yc10_3m:+.2f}%[/]" if yc10_3m is not None else ""
        rows.append(Text.from_markup(f"[dim]10Y-2Y:[/][{ycc}]{yc10_2:+.2f}%[/]{inv}{c3m}"))

    # Credit spreads
    if hy is not None or ig is not None:
        parts = []
        if hy is not None:
            hy_c = G if hy <= 3.5 else (Y if hy <= 6.0 else R)
            parts.append(f"[dim]HY OAS:[/][{hy_c}]{hy:.2f}%[/]")
        if ig is not None:
            ig_c = G if ig <= 1.0 else (Y if ig <= 2.0 else R)
            parts.append(f"[dim]IG OAS:[/][{ig_c}]{ig:.2f}%[/]")
        rows.append(Text.from_markup("  ".join(parts)))

    # Macro: CPI YoY + unemployment — natural pair, keep on one line
    macro_parts = []
    if cpi_yoy is not None:
        cpi_c = G if cpi_yoy <= 2.5 else (Y if cpi_yoy <= 4.0 else R)
        macro_parts.append(f"[dim]CPI YoY:[/][{cpi_c}]{cpi_yoy:.1f}%[/]")
    if unrate is not None:
        ur_c = G if unrate <= 4.5 else (Y if unrate <= 6.0 else R)
        macro_parts.append(f"[dim]Unemployment:[/][{ur_c}]{unrate:.1f}%[/]")
    if macro_parts:
        rows.append(Text.from_markup("  ".join(macro_parts)))

    # Oil + NFCI + DXY — 2-column grid so long labels don't crowd each other
    other_cells = []
    if oil is not None:
        other_cells.append(f"[dim]WTI Crude Oil:[/][white]${oil:.2f}[/]")
    if nfci is not None:
        nc = G if nfci <= -0.3 else (Y if nfci <= 0.3 else R)
        lbl = "accommodative" if nfci < 0 else ("tight" if nfci > 0.3 else "neutral")
        other_cells.append(f"[dim]NFCI:[/][{nc}]{nfci:+.3f}[/][dim] {lbl}[/]")
    if dxy is not None:
        dxy_c = R if dxy >= 110 else (Y if dxy >= 100 else G)
        other_cells.append(f"[dim]USD Index (DXY):[/][{dxy_c}]{dxy:.1f}[/]")
    if other_cells:
        if len(other_cells) >= 3:
            _ot = Table.grid(padding=(0, 2), expand=True)
            _ot.add_column("a", ratio=1)
            _ot.add_column("b", ratio=1)
            _ot.add_row(Text.from_markup(other_cells[0]), Text.from_markup(other_cells[1]))
            _ot.add_row(Text.from_markup(other_cells[2]), Text(""))
            rows.append(_ot)
        else:
            rows.append(Text.from_markup("  ".join(other_cells)))

    # Inflation breakevens + mortgage + consumer sentiment — 2-column grid
    extra_cells = []
    if be10 is not None:
        be_c = R if be10 >= 3.0 else (Y if be10 >= 2.5 else G)
        extra_cells.append(f"[dim]10Y Breakeven:[/][{be_c}]{be10:.2f}%[/]")
    if be5 is not None:
        be5_c = R if be5 >= 3.0 else (Y if be5 >= 2.5 else G)
        extra_cells.append(f"[dim]5Y Breakeven:[/][{be5_c}]{be5:.2f}%[/]")
    if mortgage is not None:
        mg_c = R if mortgage >= 7.0 else (Y if mortgage >= 6.0 else G)
        extra_cells.append(f"[dim]30Y Mortgage:[/][{mg_c}]{mortgage:.2f}%[/]")
    if umcsent is not None:
        uc = G if umcsent >= 80 else (Y if umcsent >= 60 else R)
        extra_cells.append(f"[dim]Consumer Sentiment:[/][{uc}]{umcsent:.0f}[/]")
    if extra_cells:
        _ex = Table.grid(padding=(0, 2), expand=True)
        _ex.add_column("a", ratio=1)
        _ex.add_column("b", ratio=1)
        for i in range(0, len(extra_cells), 2):
            left = extra_cells[i]
            right = extra_cells[i + 1] if i + 1 < len(extra_cells) else ""
            _ex.add_row(Text.from_markup(left), Text.from_markup(right) if right else Text(""))
        rows.append(_ex)

    rows.extend(_build_calendar_rows(econ_cal))

    if not rows:
        rows.append(Text("[dim]no economic data[/]"))
    return Panel(
        Group(*rows),
        title="[bold bright_magenta]ECONOMIC INPUTS → Exposure Score[/]  [dim][e] expand[/]",
        border_style="bright_magenta",
        padding=(0, 1),
    )


def panel_economic_expanded(eco, econ_cal=None):
    """Full-screen economic inputs — all macro indicators, yield curve, calendar."""
    err_panel = _error_panel("economic pulse", eco, "ECONOMIC INPUTS", border="bright_magenta")
    if err_panel:
        return err_panel

    rows = [
        Text.from_markup("[dim]press [/][bold bright_magenta]e[/][dim] to return to dashboard[/]"),
        Rule(style="dim"),
    ]

    indicators = extract_economic_indicators(eco)
    t10 = indicators.get("t10")
    t2 = indicators.get("t2")
    t3m = indicators.get("t3m")
    t6m = indicators.get("t6m")
    yc10_2 = indicators.get("yc_10_2")
    yc10_3m = indicators.get("yc_10_3m")
    hy = indicators.get("hy")
    ig = indicators.get("ig")
    oil = indicators.get("oil")
    nfci = indicators.get("nfci")
    fed_funds = indicators.get("fed_funds")
    cpi_yoy = indicators.get("cpi_yoy")
    unrate = indicators.get("unrate")
    be10 = indicators.get("be10")
    be5 = indicators.get("be5")
    dxy = indicators.get("dxy")
    mortgage = indicators.get("mortgage")
    umcsent = indicators.get("umcsent")

    # Treasury Yields table
    rows.append(Text.from_markup("[dim bold]TREASURY YIELDS & YIELD CURVE[/]"))
    ytbl = Table.grid(padding=(0, 3), expand=False)
    ytbl.add_column("label", style="dim")
    ytbl.add_column("val", style="white")
    ytbl.add_column("label2", style="dim")
    ytbl.add_column("val2", style="white")
    _y = [
        ("3M T-Bill", f"{t3m:.2f}%" if t3m else "--"),
        ("6M T-Bill", f"{t6m:.2f}%" if t6m else "--"),
        ("2Y Note", f"{t2:.2f}%" if t2 else "--"),
        ("10Y Note", f"{t10:.2f}%" if t10 else "--"),
        ("Fed Funds Rate", f"{fed_funds:.2f}%" if fed_funds else "--"),
    ]
    spreads_data = []
    if yc10_2 is not None:
        ycc = G if yc10_2 >= 0.5 else (Y if yc10_2 >= 0 else R)
        inv = "  ⚠ INVERTED" if yc10_2 < 0 else ""
        spreads_data.append(
            (
                "10Y-2Y Spread",
                Text.from_markup(f"[{ycc}]{yc10_2:+.2f}%[/][{R if yc10_2 < 0 else 'dim'}]{inv}[/]"),
            )
        )
    if yc10_3m is not None:
        ycc2 = G if yc10_3m >= 0.5 else (Y if yc10_3m >= 0 else R)
        spreads_data.append(("10Y-3M Spread", Text.from_markup(f"[{ycc2}]{yc10_3m:+.2f}%[/]")))
    pairs = list(zip(_y[::2], [*_y[1::2], ("", "")], strict=False))
    for (la, va), (lb, vb) in pairs:
        ytbl.add_row(la + ":", va, lb + (":" if lb else ""), vb)
    rows.append(ytbl)

    if spreads_data:
        rows.append(Text.from_markup("[dim bold]YIELD CURVE SPREADS[/]"))
        for lbl, val in spreads_data:
            if isinstance(val, Text):
                rows.append(Group(Text.from_markup(f"  [dim]{lbl}:[/]  "), val))
            else:
                rows.append(Text.from_markup(f"  [dim]{lbl}:[/]  [white]{val}[/]"))

    rows.append(Rule(style="dim"))

    # Credit spreads section
    if hy is not None or ig is not None:
        rows.append(Text.from_markup("[dim bold]CREDIT SPREADS (OAS)[/]"))
        ctbl = Table.grid(padding=(0, 3), expand=False)
        ctbl.add_column("label", style="dim")
        ctbl.add_column("val")
        ctbl.add_column("context", style="dim")
        if hy is not None:
            hy_c = G if hy <= 3.5 else (Y if hy <= 6.0 else R)
            hy_ctx = "tight" if hy <= 3.5 else ("elevated" if hy <= 6.0 else "distressed")
            ctbl.add_row("HY OAS (ICE BofA):", Text.from_markup(f"[{hy_c}]{hy:.2f}%[/]"), hy_ctx)
        if ig is not None:
            ig_c = G if ig <= 1.0 else (Y if ig <= 2.0 else R)
            ig_ctx = "tight" if ig <= 1.0 else ("normal" if ig <= 2.0 else "wide")
            ctbl.add_row("IG OAS (ICE BofA):", Text.from_markup(f"[{ig_c}]{ig:.2f}%[/]"), ig_ctx)
        rows.append(ctbl)
        rows.append(Rule(style="dim"))

    # Macro indicators
    rows.append(Text.from_markup("[dim bold]MACRO INDICATORS[/]"))
    mtbl = Table.grid(padding=(0, 3), expand=False)
    mtbl.add_column("label", style="dim")
    mtbl.add_column("val")
    mtbl.add_column("context", style="dim")
    if cpi_yoy is not None:
        cpi_c = G if cpi_yoy <= 2.5 else (Y if cpi_yoy <= 4.0 else R)
        cpi_ctx = "on target" if cpi_yoy <= 2.5 else ("elevated" if cpi_yoy <= 4.0 else "high inflation")
        mtbl.add_row("CPI YoY:", Text.from_markup(f"[{cpi_c}]{cpi_yoy:.1f}%[/]"), cpi_ctx)
    if unrate is not None:
        ur_c = G if unrate <= 4.5 else (Y if unrate <= 6.0 else R)
        ur_ctx = "healthy" if unrate <= 4.5 else ("rising" if unrate <= 6.0 else "elevated")
        mtbl.add_row("Unemployment:", Text.from_markup(f"[{ur_c}]{unrate:.1f}%[/]"), ur_ctx)
    if oil is not None:
        oil_c = G if oil <= 70 else (Y if oil <= 90 else R)
        mtbl.add_row("WTI Crude Oil:", Text.from_markup(f"[{oil_c}]${oil:.2f}[/]"), "per barrel")
    if nfci is not None:
        nc = G if nfci <= -0.3 else (Y if nfci <= 0.3 else R)
        nfci_ctx = "accommodative (below 0)" if nfci < 0 else ("tight (above 0.3)" if nfci > 0.3 else "neutral")
        mtbl.add_row("Chicago Fed (NFCI):", Text.from_markup(f"[{nc}]{nfci:+.3f}[/]"), nfci_ctx)
    if dxy is not None:
        dxy_c = R if dxy >= 110 else (Y if dxy >= 100 else G)
        mtbl.add_row(
            "USD Index (DXY):",
            Text.from_markup(f"[{dxy_c}]{dxy:.1f}[/]"),
            "broad trade-weighted",
        )
    if mortgage is not None:
        mg_c = R if mortgage >= 7.0 else (Y if mortgage >= 6.0 else G)
        mtbl.add_row(
            "30Y Mortgage Rate:",
            Text.from_markup(f"[{mg_c}]{mortgage:.2f}%[/]"),
            "weekly average",
        )
    if umcsent is not None:
        uc = G if umcsent >= 80 else (Y if umcsent >= 60 else R)
        mtbl.add_row(
            "UMich Consumer Sentiment:",
            Text.from_markup(f"[{uc}]{umcsent:.0f}[/]"),
            "survey index",
        )
    rows.append(mtbl)

    # Inflation breakevens
    if be10 is not None or be5 is not None:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim bold]INFLATION EXPECTATIONS (BREAKEVENS)[/]"))
        btbl = Table.grid(padding=(0, 3), expand=False)
        btbl.add_column("label", style="dim")
        btbl.add_column("val")
        btbl.add_column("context", style="dim")
        if be10 is not None:
            be_c = R if be10 >= 3.0 else (Y if be10 >= 2.5 else G)
            btbl.add_row(
                "10Y Breakeven:",
                Text.from_markup(f"[{be_c}]{be10:.2f}%[/]"),
                "market inflation expectation",
            )
        if be5 is not None:
            be5_c = R if be5 >= 3.0 else (Y if be5 >= 2.5 else G)
            btbl.add_row(
                "5Y Breakeven:",
                Text.from_markup(f"[{be5_c}]{be5:.2f}%[/]"),
                "5Y forward expectation",
            )
        rows.append(btbl)

    cal_rows = _build_calendar_rows(econ_cal)
    if cal_rows:
        rows.append(Rule(style="dim"))
        rows.append(Text.from_markup("[dim bold]ECONOMIC CALENDAR (UPCOMING)[/]"))
        rows.extend(cal_rows[1:])

    if not rows:
        rows.append(Text("[dim]no economic data[/]"))
    return Panel(
        Group(*rows),
        title="[bold bright_magenta]ECONOMIC INPUTS - EXPANDED[/]  [dim][e] return[/]",
        border_style="bright_magenta",
        padding=(0, 1),
    )


__all__ = [
    "panel_economic_expanded",
    "panel_economic_pulse",
]
