"""Mascot animation and loading layout functions."""

import json
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

from rich.align import Align
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from utilities import (
    MASCOT_W,
    MASCOT_FRAMES,
    MASCOT_COLORS,
    LOAD_SEQ,
)

from ._helpers import _error_panel

# MASCOT_H = 1 top border + 1 blank + 4 pose lines + 1 blank + 1 bottom border = 8
MASCOT_H = 8


def mascot_pose(data: dict, frame: int) -> int:
    """Determine mascot pose based on circuit breaker status."""
    if (data.get("cb") or {}).get("any"):
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        return seq[(frame // 2) % len(seq)]
    return LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]


@register_panel(
    "mascot",
    endpoint_deps=[],
    optional=False,
    description="Mascot",
)
def mascot_compact(data: dict, frame: int) -> Panel:
    fi = mascot_pose(data, frame)
    mc = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    # No justify= — strings are pre-padded to exactly 11 chars (panel content width).
    return Panel(
        Group(
            Text(" " * 11),
            Text(pose[0], style=f"bold {mc}", no_wrap=True),
            Text(pose[1], style=f"bold {mc}", no_wrap=True),
            Text(pose[2], style=f"bold {mc}", no_wrap=True),
            Text(pose[3], style=f"bold {mc}", no_wrap=True),
            Text(" " * 11),
        ),
        border_style=mc,
        padding=(0, 0),
    )


@register_panel(
    "loading",
    endpoint_deps=[],
    optional=False,
    description="Loading",
)
def loading_layout(frame: int, data_source: str = "AWS") -> Layout:
    """Show compact mascot in top-right corner with loading message below."""
    fi = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]  # 4fps loading animation
    mc = MASCOT_COLORS[fi]
    pose = MASCOT_FRAMES[fi]
    dots = "." * ((frame // 2 % 4) + 1)  # dots cycle at ~1Hz

    # Same pre-padded approach as mascot_compact (11-char strings)
    mascot_panel = Panel(
        Group(
            Text(" " * 11),
            Text(pose[0], style=f"bold {mc}", no_wrap=True),
            Text(pose[1], style=f"bold {mc}", no_wrap=True),
            Text(pose[2], style=f"bold {mc}", no_wrap=True),
            Text(pose[3], style=f"bold {mc}", no_wrap=True),
            Text(" " * 11),
        ),
        border_style=mc,
        padding=(0, 0),
    )

    source_color = "cyan" if data_source == "LOCAL" else "dim"
    hdr_text = Text.from_markup(
        f"[bold white]ALGO OPS DASHBOARD[/]  [dim]{dots}[/]  [{source_color}]{data_source}[/]"
    )
    hdr_panel = Panel(
        Align(hdr_text, vertical="middle"),
        border_style="blue",
        padding=(0, 1),
    )

    loading_body = Text.from_markup(
        f"\n\n[bold white]  Fetching market data{dots}[/]\n\n"
        "  [dim]Connecting to database...[/]\n\n"
        "  [dim]Keys: [/][cyan]p[/][dim] positions  [/][cyan]s[/][dim] signals  "
        "[/][cyan]h[/][dim] health  [/][cyan]r[/][dim] sectors  [/][cyan]t[/][dim] trades  "
        "[/][cyan]e[/][dim] economic  [/][cyan]f[/][dim] portfolio  [/][cyan]q[/][dim] quit[/]"
    )
    main_panel = Panel(
        Align(loading_body, align="left", vertical="middle"),
        border_style="blue",
        padding=(0, 1),
    )

    layout = Layout()
    layout.split_column(
        Layout(name="top", size=MASCOT_H),
        Layout(name="main", ratio=1),
    )
    layout["top"].split_row(
        Layout(name="hdr", ratio=1),
        Layout(name="mascot", size=MASCOT_W),
    )
    layout["top"]["hdr"].update(hdr_panel)
    layout["top"]["mascot"].update(mascot_panel)
    layout["main"].update(main_panel)
    return layout


def _expanded_layout(hdr_panel, exposure_panel, mascot_panel, main_panel) -> Layout:
    """Shared skeleton: market header row on top, one full-height panel below."""
    exp = Layout()
    exp.split_column(Layout(name="etop", size=10), Layout(name="emain"))
    exp["etop"].split_row(
        Layout(name="ehdr", ratio=1),
        Layout(name="eexp", ratio=2),
        Layout(name="emsc", size=MASCOT_W),
    )
    exp["etop"]["ehdr"].update(hdr_panel)
    exp["etop"]["eexp"].update(exposure_panel)
    exp["etop"]["emsc"].update(mascot_panel)
    exp["emain"].update(main_panel)
    return exp



__all__ = [
    "mascot_pose",
    "mascot_compact",
    "loading_layout",
    "_expanded_layout",
]
