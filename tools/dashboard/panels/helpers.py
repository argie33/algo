"""Shared helper functions and utilities for dashboard panels."""

import json
import logging
from typing import Any

from rich.panel import Panel
from rich.text import Text

from ..error_boundary import has_error
from ..utilities import (
    CY,
    DIM,
    LOAD_SEQ,
    MASCOT_COLORS,
    MASCOT_FRAMES,
    PHASE_NAMES,
    G,
    R,
    Y,
)


logger = logging.getLogger(__name__)


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


def mascot_pose(data: dict, frame: int) -> int:
    """Get mascot pose index based on circuit breaker status and frame."""
    cb = data.get("cb")
    if cb and isinstance(cb, dict) and cb.get("any") is True:
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        idx = seq[(frame // 2) % len(seq)]
    else:
        idx = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]
    return _get_safe_frame_index(idx)


def _score_cell(v):
    """Colored 0-100 sub-score cell: green >=70, cyan >=50, yellow >=30, else red."""
    if v is None or v == "":
        return Text("--", style=DIM)
    try:
        fv = float(v)
    except (ValueError, TypeError):
        return Text("--", style=DIM)
    c = G if fv >= 70 else (CY if fv >= 50 else (Y if fv >= 30 else R))
    return Text(f"{fv:.0f}", style=c)


def _build_buy_sig_map(buy_sigs) -> dict:
    """Map symbol -> signal-quality (swing) score from buy-signal records. Uses normalized symbols."""
    out: dict = {}
    for bs in buy_sigs or []:
        sym = bs.get("symbol")
        if sym:
            sym_norm = str(sym).upper().strip()
            score = bs.get("signal_quality_score")
            if score is None:
                score = bs.get("swing_score")
            if score is None:
                score = 0
            try:
                out[sym_norm] = float(score)
            except (ValueError, TypeError):
                out[sym_norm] = 0.0
    return out


def _swing_cell(swing_v):
    """Swing-signal cell: ▲score colored by strength, or dim -- when absent."""
    if swing_v is None:
        return Text("--", style=DIM)
    c = G if swing_v >= 80 else (CY if swing_v >= 70 else Y)
    return Text(f"▲{swing_v:.0f}", style=c)


def _composite_score_color(v) -> str:
    """Color for composite scores: green >=80, cyan >=60, yellow >=40, else white."""
    return G if v >= 80 else (CY if v >= 60 else (Y if v >= 40 else "white"))


def _best_halt_reason(top_level: str, phase_results: list) -> list[tuple[str, str]]:
    """Return a list of (phase_label, reason) pairs drawn from phase-level data.

    Falls back to top_level if no per-phase detail is found.
    Tries multiple field names so the display is robust to orchestrator schema changes.
    """
    _FIELDS = (  # noqa: N806
        "halt_reason",
        "reason",
        "message",
        "error",
        "halt_message",
        "circuit_breaker",
        "triggered_by",
        "details",
    )
    found: list[tuple[str, str]] = []
    for p in phase_results or []:
        ps = (p.get("status") or "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw = (p.get("name") or p.get("phase", "")).lower()
        parts = raw.split("_")
        base = "_".join(parts[:2]) if len(parts) >= 2 else raw
        label = PHASE_NAMES.get(base, raw.replace("phase_", "P"))
        pdata = p.get("data")
        if isinstance(pdata, str):
            try:
                pdata = json.loads(pdata)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse phase data JSON: {e}")
                pdata = None
        elif not isinstance(pdata, dict) and pdata is not None:
            pdata = None
        detail = next(
            (str(pdata[k]) for k in _FIELDS if pdata and pdata.get(k) and len(str(pdata.get(k))) > 3),
            "",
        )
        if detail:
            found.append((label, detail))
    if not found and top_level:
        found.append(("", top_level))
    return found


def _fmt_phases_halted(phases_halted) -> str:
    """Turn a phases_halted array into a compact human-readable label."""
    if not phases_halted:
        return ""
    if isinstance(phases_halted, int):
        return ""
    if isinstance(phases_halted, str):
        try:
            phases_halted = json.loads(phases_halted)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse phases_halted JSON: {e}")
            phases_halted = [phases_halted]
    if not isinstance(phases_halted, (list, tuple)):
        return ""
    names = []
    for p in phases_halted:
        raw = str(p).lower()
        parts = raw.split("_")
        base = "_".join(parts[:2]) if len(parts) >= 2 else raw
        names.append(PHASE_NAMES.get(base, raw.replace("phase_", "P")))
    return ", ".join(names[:3])


def _error_panel(data_name: str, data: Any, title: str, border="magenta") -> Panel | None:
    """Create a panel showing granular error info for failed data sources."""
    if not data:
        return Panel(
            Text(f"{data_name}: no data", style="dim"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    if has_error(data):
        error_msg = data.get("_error", "Unknown error")
        return Panel(
            Text.from_markup(f"[{R}]{data_name}[/] fetch failed:\n[dim]{error_msg}[/]"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    return None


def _rdelta(r, wk="rank_1w_ago", wk4=None):
    """Rank delta formatter: shows rank change with ↑/↓ symbols and color coding."""
    cur = r.get("current_rank")
    if cur is None:
        return "[dim]--[/]"
    old = r.get(wk)
    if old is None:
        return ""
    d = int(old) - int(cur)
    s1 = f"[{G}]↑{d}[/]" if d > 0 else (f"[{R}]↓{abs(d)}[/]" if d < 0 else "[dim]=[/]")
    if wk4:
        old4 = r.get(wk4)
        if old4 is not None:
            d4 = int(old4) - int(cur)
            s4 = f"[{G}]↑{d4}[/]" if d4 > 0 else (f"[{R}]↓{abs(d4)}[/]" if d4 < 0 else "[dim]=[/]")
            return f"{s1}[dim]/[/]{s4}"
    return s1
