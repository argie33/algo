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


def mascot_pose(data: dict[str, Any], frame: int) -> int:
    """Get mascot pose index based on circuit breaker status and frame.

    Validates data is dict before accessing fields.
    """
    if not isinstance(data, dict):
        return _get_safe_frame_index(LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)])
    cb = data.get("cb")
    if cb and isinstance(cb, dict) and cb.get("any") is True:
        seq = [4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 3, 4, 1, 0, 3, 4, 0, 1, 7]
        idx = seq[(frame // 2) % len(seq)]
    else:
        idx = LOAD_SEQ[(frame // 2) % len(LOAD_SEQ)]
    return _get_safe_frame_index(idx)


def _score_cell(v: Any) -> Text:
    """Colored 0-100 sub-score cell: green >=70, cyan >=50, yellow >=30, else red."""
    if v is None or v == "":
        return Text("--", style=DIM)
    try:
        fv = float(v)
    except (ValueError, TypeError):
        return Text("--", style=DIM)
    c = G if fv >= 70 else (CY if fv >= 50 else (Y if fv >= 30 else R))
    return Text(f"{fv:.0f}", style=c)


def _build_buy_sig_map(buy_sigs: Any) -> dict[str, float]:
    """Map symbol -> signal-quality (swing) score from buy-signal records. Uses normalized symbols.

    Validates buy_sigs is iterable before processing.
    """
    out: dict[str, float] = {}
    if not isinstance(buy_sigs, (list, tuple)):
        logger.warning(
            f"buy_sigs is not a list/tuple (got {type(buy_sigs).__name__}). "
            f"Cannot build signal map."
        )
        return out
    for bs in buy_sigs:
        if not isinstance(bs, dict):
            logger.debug(f"Skipping non-dict buy signal record: {type(bs).__name__}")
            continue
        sym = bs.get("symbol")
        if sym is None:
            logger.debug("Skipping buy signal record with missing symbol field")
            continue
        sym_norm = str(sym).upper().strip()
        score = bs.get("signal_quality_score")
        if score is None:
            score = bs.get("swing_score")
        if score is None:
            logger.debug(f"No scoring field found for symbol {sym_norm}; using 0")
            score = 0
        try:
            out[sym_norm] = float(score)
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to convert score to float for {sym_norm}: {e}; using 0.0")
            out[sym_norm] = 0.0
    return out


def _swing_cell(swing_v: Any) -> Text:
    """Swing-signal cell: ▲score colored by strength, or dim -- when absent."""
    if swing_v is None:
        return Text("--", style=DIM)
    try:
        sv_f = float(swing_v)
    except (TypeError, ValueError):
        return Text("--", style=DIM)
    c = G if sv_f >= 80 else (CY if sv_f >= 70 else Y)
    return Text(f"▲{sv_f:.0f}", style=c)


def _composite_score_color(v: float) -> str:
    """Color for composite scores: green >=80, cyan >=60, yellow >=40, else white."""
    try:
        v_f = float(v)
    except (TypeError, ValueError):
        return "white"
    return G if v_f >= 80 else (CY if v_f >= 60 else (Y if v_f >= 40 else "white"))


def _best_halt_reason(top_level: str, phase_results: list[Any]) -> list[tuple[str, str]]:
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
    if not isinstance(phase_results, (list, tuple)):
        logger.warning(
            f"_best_halt_reason received non-list phase_results (got {type(phase_results).__name__}); "
            f"skipping phase-level detail parsing"
        )
        phase_results = []
    for p in phase_results or []:
        if not isinstance(p, dict):
            logger.debug(f"Skipping non-dict phase result entry: {type(p).__name__}")
            continue
        ps = p.get("status")
        ps = (ps if ps is not None else "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw = p.get("name")
        if raw is None:
            if "phase" not in p or p["phase"] is None:
                logger.debug("Halted phase has no 'name' or 'phase' field; skipping")
                continue
            raw = p["phase"]
        raw = (raw if raw is not None else "").lower()
        parts = raw.split("_")
        base = "_".join(parts[:2]) if len(parts) >= 2 else raw
        label = PHASE_NAMES.get(base, raw.replace("phase_", "P"))
        pdata = p.get("data")
        if isinstance(pdata, str):
            try:
                pdata = json.loads(pdata)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse phase data JSON for '{label}': {e}; skipping phase detail")
                pdata = None
        elif not isinstance(pdata, dict) and pdata is not None:
            logger.debug(f"Phase '{label}' data is {type(pdata).__name__} (expected dict); skipping")
            pdata = None
        detail = next(
            (str(pdata[k]) for k in _FIELDS if pdata and k in pdata and pdata[k] and len(str(pdata[k])) > 3),
            "",
        )
        if detail:
            found.append((label, detail))
        elif pdata is None:
            logger.debug(f"No halt reason detail found in phase '{label}'")
    if not found and top_level:
        logger.debug(f"No per-phase halt details found; using top-level reason: {top_level}")
        found.append(("", top_level))
    elif not found:
        logger.warning("No halt reasons found in phase results and no top-level reason provided")
    return found


def _fmt_phases_halted(phases_halted: Any) -> str:
    """Turn a phases_halted array into a compact human-readable label.

    Returns empty string only when data is genuinely unavailable or empty.
    Logs all fallback paths explicitly.
    """
    if not phases_halted:
        logger.debug("phases_halted is falsy (None, empty, 0, or False); returning empty string")
        return ""
    if isinstance(phases_halted, int):
        logger.debug(f"phases_halted is int ({phases_halted}); cannot format as phase list")
        return ""
    if isinstance(phases_halted, str):
        try:
            phases_halted = json.loads(phases_halted)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse phases_halted JSON: {e}; treating as single phase name")
            phases_halted = [phases_halted]
    if not isinstance(phases_halted, (list, tuple)):
        logger.debug(
            f"phases_halted is {type(phases_halted).__name__} (expected list/tuple after parsing); "
            f"cannot format as phase list"
        )
        return ""
    names: list[str] = []
    for p in phases_halted:
        raw = str(p).lower()
        parts = raw.split("_")
        base = "_".join(parts[:2]) if len(parts) >= 2 else raw
        names.append(PHASE_NAMES.get(base, raw.replace("phase_", "P")))
    return ", ".join(names[:3])


def _error_panel(data_name: str, data: Any, title: str, border: str = "magenta") -> Panel | None:
    """Create a panel showing granular error info for failed data sources.

    Requires data to be a dict with explicit error markers, or returns None.
    """
    if not data:
        logger.debug(f"_error_panel called with empty/falsy data for {data_name}")
        return Panel(
            Text(f"{data_name}: no data", style="dim"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    if has_error(data):
        error_msg = data.get("_error") if isinstance(data, dict) else None
        if not error_msg:
            logger.error(
                f"Data source '{data_name}' has error marker but missing _error field. "
                f"Cannot render error details. Data type: {type(data).__name__}"
            )
            error_msg = f"[{data_name}] Error occurred but details are missing"
        return Panel(
            Text.from_markup(f"[{R}]{data_name}[/] fetch failed:\n[dim]{error_msg}[/]"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    return None


def _rdelta(r: Any, wk: str = "rank_1w_ago", wk4: str | None = None) -> str:
    """Rank delta formatter: shows rank change with ↑/↓ symbols and color coding.

    Validates r is dict before accessing fields. Returns dim '--' when data unavailable.
    """
    if not isinstance(r, dict):
        logger.debug(f"_rdelta called with non-dict rank data (got {type(r).__name__})")
        return "[dim]--[/]"
    cur = r.get("current_rank")
    if cur is None:
        logger.debug("_rdelta: current_rank field missing or None in rank data")
        return "[dim]--[/]"
    old = r.get(wk)
    if old is None:
        logger.debug(f"_rdelta: primary timeframe field '{wk}' missing or None in rank data")
        return "[dim]--[/]"
    try:
        d = int(old) - int(cur)
    except (ValueError, TypeError) as e:
        logger.debug(f"_rdelta: Failed to convert ranks to int (cur={cur}, old={old}): {e}")
        return "[dim]--[/]"
    s1 = f"[{G}]↑{d}[/]" if d > 0 else (f"[{R}]↓{abs(d)}[/]" if d < 0 else "[dim]=[/]")
    if wk4:
        old4 = r.get(wk4)
        if old4 is not None:
            try:
                d4 = int(old4) - int(cur)
                s4 = f"[{G}]↑{d4}[/]" if d4 > 0 else (f"[{R}]↓{abs(d4)}[/]" if d4 < 0 else "[dim]=[/]")
                return f"{s1}[dim]/[/]{s4}"
            except (ValueError, TypeError) as e:
                logger.debug(f"_rdelta: Failed to convert 4w rank to int (old4={old4}): {e}; returning 1w delta only")
    return s1
