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

    FAIL-FAST: buy_sigs must not be None; caller must validate.
    Tracks skipped items with explicit logging for audit trail.
    """
    if buy_sigs is None:
        raise ValueError(
            "[BUY_SIGNALS] Cannot build signal map: buy_sigs is None. Upstream pipeline did not return buy signal data."
        )
    out: dict[str, float] = {}
    skipped_count = 0
    for idx, bs in enumerate(buy_sigs):
        if not isinstance(bs, dict):
            logger.debug(f"[BUY_SIGNALS] Skipped item {idx}: not a dict (type={type(bs).__name__})")
            skipped_count += 1
            continue
        sym = bs.get("symbol")
        if not sym:
            logger.debug(f"[BUY_SIGNALS] Skipped item {idx}: missing or empty 'symbol' field")
            skipped_count += 1
            continue
        sym_norm = str(sym).upper().strip()

        score = bs.get("signal_quality_score")

        if score is not None:
            try:
                out[sym_norm] = float(score)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to convert score for {sym}: {e}")
        else:
            logger.warning(f"Buy signal {sym}: missing signal_quality_score")

    if skipped_count > 0:
        logger.warning(f"[BUY_SIGNALS] Skipped {skipped_count} invalid items out of {len(buy_sigs)} total")

    return out


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

    FAIL-FAST: phase_results must not be None; orchestrator must provide explicit phase-level data.
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

    # Explicit check for None: indicates orchestrator halted without returning phase results
    if phase_results is None:
        logger.error(
            "Phase execution results unavailable (phase_results is None). "
            "Orchestrator may have halted before returning phase-level data."
        )
        raise ValueError("Phase execution results unavailable, orchestrator may have halted")

    # Validate phase_results is a list or tuple
    if not isinstance(phase_results, (list, tuple)):
        logger.error(
            f"_best_halt_reason received invalid phase_results type: {type(phase_results).__name__}. "
            f"Expected list or tuple of phase execution results."
        )
        raise ValueError(f"Phase results must be a list or tuple, got {type(phase_results).__name__}")

    # Now phase_results is guaranteed to be a list/tuple - iterate without fallback
    skipped_non_dict = 0
    skipped_missing_name = 0
    for idx, p in enumerate(phase_results):
        if not isinstance(p, dict):
            logger.debug(f"Skipping phase result entry {idx}: not a dict (type={type(p).__name__})")
            skipped_non_dict += 1
            continue
        ps = p.get("status")
        ps = (ps if ps is not None else "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw = p.get("name")
        phase_field_used = "name"
        if raw is None:
            if "phase" not in p or p["phase"] is None:
                logger.debug(f"Halted phase result {idx}: no 'name' or 'phase' field; skipping")
                skipped_missing_name += 1
                continue
            raw = p["phase"]
            phase_field_used = "phase"
            logger.debug(f"Phase name extracted from '{phase_field_used}' field (primary 'name' not available)")
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
        # CRITICAL: Log which field was actually used (implicit fallback chain)
        detail = ""
        used_field = None
        for k in _FIELDS:
            if pdata and k in pdata and pdata[k] and len(str(pdata[k])) > 3:
                detail = str(pdata[k])
                used_field = k
                break
        if used_field and used_field != _FIELDS[0]:
            logger.info(
                f"Phase '{label}' halt reason found in field '{used_field}' (primary '{_FIELDS[0]}' not available)"
            )
        if detail:
            found.append((label, detail))
        elif pdata is None:
            logger.debug(f"No halt reason detail found in phase '{label}'")
    total_skipped = skipped_non_dict + skipped_missing_name
    if total_skipped > 0:
        skip_ratio = total_skipped / len(phase_results) if phase_results else 0
        logger.warning(
            f"[PHASE_RESULTS] Skipped {total_skipped} phase results "
            f"({100 * skip_ratio:.1f}% of {len(phase_results)}): "
            f"{skipped_non_dict} non-dict, {skipped_missing_name} missing name"
        )

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

    logger.debug(f"[_error_panel] {data_name}: no errors found - no error panel needed (data_valid)")
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
