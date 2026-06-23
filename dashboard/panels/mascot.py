"""Mascot animation and loading layout functions."""

import logging
from typing import Any, cast

from rich.align import Align
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)


class _RenderCache:
    """Cache rendered Panel/Layout objects to avoid redundant rendering on every frame."""

    def __init__(self) -> None:
        self.mascot_compact_pose_index: int | None = None
        self.mascot_compact_panel: Panel | None = None
        self.loading_layout_pose_index: int | None = None
        self.loading_layout_dots_idx: int | None = None
        self.loading_layout_cache: Layout | None = None
        self.loading_layout_data_source: str | None = None

    def get_mascot_panel(self, pose_index: int, data: dict[str, Any]) -> Panel:
        """Return cached Panel if pose hasn't changed, otherwise render new one."""
        if self.mascot_compact_pose_index == pose_index:
            return cast(Panel, self.mascot_compact_panel)

        self.mascot_compact_pose_index = pose_index
        mc = MASCOT_COLORS[pose_index]
        pose = MASCOT_FRAMES[pose_index]
        self.mascot_compact_panel = Panel(
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
        return self.mascot_compact_panel

    def get_loading_layout(self, pose_index: int, dots_idx: int, data_source: str) -> Layout:
        """Return cached Layout if pose and dots haven't changed."""
        if (
            self.loading_layout_pose_index == pose_index
            and self.loading_layout_dots_idx == dots_idx
            and self.loading_layout_data_source == data_source
        ):
            return cast(Layout, self.loading_layout_cache)

        self.loading_layout_pose_index = pose_index
        self.loading_layout_dots_idx = dots_idx
        self.loading_layout_data_source = data_source
        mc = MASCOT_COLORS[pose_index]
        pose = MASCOT_FRAMES[pose_index]
        dots = "." * (dots_idx + 1)

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
            "[/][cyan]e[/][dim] economic  [/][cyan]f[/][dim] portfolio  [/][cyan]b[/][dim] circuit  "
            "[/][cyan]x[/][dim] exposure  [/][cyan]m[/][dim] market  [/][cyan]d[/][dim] data issues  "
            "[/][cyan]q[/][dim] quit[/]"
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
        self.loading_layout_cache = layout
        return layout


_render_cache = _RenderCache()

try:
    from panel_registry import register_panel
except ImportError as e:
    logger.warning(f"Panel registry not available: {e} - panels will not auto-register")

    def register_panel(*args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn


from ..utilities import (
    LOAD_SEQ,
    MASCOT_COLORS,
    MASCOT_FRAMES,
    MASCOT_W,
)

# MASCOT_H = 1 top border + 1 blank + 4 pose lines + 1 blank + 1 bottom border = 8
MASCOT_H = 8


def _get_safe_frame_index(frame_index: int) -> int:
    """Validate frame index is within bounds of MASCOT_FRAMES and MASCOT_COLORS."""
    max_index = len(MASCOT_FRAMES) - 1
    if frame_index < 0 or frame_index > max_index:
        logger.warning(
            f"Frame index {frame_index} out of bounds [0-{max_index}]. "
            f"MASCOT_FRAMES has {len(MASCOT_FRAMES)} frames, MASCOT_COLORS has {len(MASCOT_COLORS)} colors. "
            f"Falling back to frame 0."
        )
        return 0
    return frame_index


def mascot_pose(data: dict[str, Any], frame: int) -> int:
    """Determine mascot pose based on circuit breaker status."""
    if (data.get("cb") or {}).get("any"):
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        idx = seq[(frame // 2) % len(seq)]
    else:
        idx = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]
    return _get_safe_frame_index(idx)


@register_panel(  # type: ignore[untyped-decorator]
    "mascot",
    endpoint_deps=[],
    optional=False,
    description="Mascot",
)
def mascot_compact(data: dict[str, Any], frame: int) -> Panel:
    fi = mascot_pose(data, frame)
    return _render_cache.get_mascot_panel(fi, data)


@register_panel(  # type: ignore[untyped-decorator]
    "loading",
    endpoint_deps=[],
    optional=False,
    description="Loading",
)
def loading_layout(frame: int, data_source: str = "AWS") -> Layout:
    """Show compact mascot in top-right corner with loading message below."""
    idx = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]  # 4fps loading animation
    fi = _get_safe_frame_index(idx)
    dots_idx = frame // 2 % 4  # dots cycle at ~1Hz
    return _render_cache.get_loading_layout(fi, dots_idx, data_source)


def _expanded_layout(hdr_panel: Panel, exposure_panel: Panel, mascot_panel: Panel, main_panel: Panel) -> Layout:
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
    "_expanded_layout",
    "loading_layout",
    "mascot_compact",
    "mascot_pose",
]
