"""Shared helper functions for panel modules."""

import json
import logging
from typing import Any

from rich.panel import Panel
from rich.text import Text

from .. import error_boundary
from ..utilities import (
    CY,
    DIM,
    PHASE_NAMES,
    G,
    R,
    Y,
)

logger = logging.getLogger(__name__)


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
    """Map symbol -> score from buy-signal records (normalized symbols).

    Uses signal_quality_score if present, falls back to swing_score if available,
    but logs warning if neither field is present (not silent fallback to 0).

    FAIL-FAST: buy_sigs must not be None; caller must validate.
    """
    if buy_sigs is None:
        raise ValueError(
            "[BUY_SIGNALS] Cannot build signal map: buy_sigs is None. Upstream pipeline did not return buy signal data."
        )
    out: dict[str, float] = {}
    for bs in buy_sigs:
        if not isinstance(bs, dict):
            continue
        sym = bs.get("symbol")
        if not sym:
            logger.debug("[HELPERS] Buy signal missing or empty symbol field — skipping")
            continue
        sym_norm = str(sym).upper().strip()

        # Try signal_quality_score first, then swing_score
        score = bs.get("signal_quality_score")
        if score is None:
            score = bs.get("swing_score")

        # Only use the score if we found one; log warning if both missing
        if score is not None:
            try:
                out[sym_norm] = float(score)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to convert score for {sym}: {e}")
        else:
            logger.warning(f"Buy signal {sym}: missing signal_quality_score and swing_score")

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


def _composite_score_color(v: Any) -> str:
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

    FAIL-FAST: phase_results must not be None; caller must validate.
    """
    if phase_results is None:
        raise ValueError(
            "[PHASE_RESULTS] Cannot extract halt reasons: phase_results is None. "
            "Upstream orchestrator did not return phase data."
        )
    fields = (
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
    for p in phase_results:
        ps = p.get("status")
        ps = (ps if ps is not None else "").lower()
        if ps not in ("halt", "halted"):
            continue
        raw = p.get("name")
        if raw is None:
            if "phase" not in p or p["phase"] is None:
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
                logger.warning(f"Failed to parse phase data JSON: {e}")
                pdata = None
        elif not isinstance(pdata, dict) and pdata is not None:
            pdata = None
        detail = next(
            (str(pdata[k]) for k in fields
             if pdata and k in pdata and pdata[k] is not None and len(str(pdata[k])) > 3),
            "",
        )
        if detail:
            found.append((label, detail))
    if not found and top_level:
        found.append(("", top_level))
    return found


def _fmt_phases_halted(phases_halted: Any) -> str:
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


def _get_age_hours(item: Any) -> float | None:
    """Extract age in hours from a data item.

    Checks age_hours first, then age (assumed to be in days and converted).
    Returns None if no age data available.
    """
    if not isinstance(item, dict):
        return None

    age_hours = item.get("age_hours")
    if age_hours is not None:
        try:
            return float(age_hours)
        except (ValueError, TypeError):
            pass

    age_days = item.get("age")
    if age_days is not None:
        try:
            return float(age_days) * 24
        except (ValueError, TypeError):
            pass

    return None


def _is_stale(item: Any, stale_threshold_hours: float = 24) -> bool:
    """Check if a data item is stale (age > threshold).

    Args:
        item: Data dict with optional age_hours or age field
        stale_threshold_hours: Threshold in hours (default 24h = 1 day)

    Returns:
        True if item is stale or age data unavailable, False if fresh
    """
    age = _get_age_hours(item)
    if age is None:
        # No age data available — treat as potentially stale
        logger.debug("Data item missing age_hours/age fields — cannot assess freshness")
        return True
    return age > stale_threshold_hours


def _format_age(item: Any) -> str:
    """Format age from data item for display."""
    age = _get_age_hours(item)
    if age is None:
        return "?"
    if age < 1:
        return f"{int(age * 60)}m"
    if age < 24:
        return f"{age:.0f}h"
    return f"{age / 24:.1f}d"


def _error_panel(data_name: str, data: Any, title: str, border: str = "magenta") -> Panel | None:
    """Create a panel showing granular error info for failed data sources.

    Checks for both hard errors (_error) and stale data (_stale_cache) using error_boundary.

    Returns:
        Panel: Error panel if data is empty or has errors
        None: If data exists and has no errors (no panel needed)
    """
    if not data:
        return Panel(
            Text(f"{data_name}: no data", style="dim"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    if error_boundary.has_error(data):
        error_msg = error_boundary.get_error_message(data)
        return Panel(
            Text.from_markup(f"[{R}]{data_name}[/] fetch failed:\n[dim]{error_msg}[/]"),
            title=f"[bold]{title}[/]",
            border_style=border,
            padding=(0, 1),
        )

    logger.debug(f"[_error_panel] {data_name}: no errors found - no error panel needed (data_valid)")
    return None


__all__ = [
    "_best_halt_reason",
    "_build_buy_sig_map",
    "_composite_score_color",
    "_error_panel",
    "_fmt_phases_halted",
    "_format_age",
    "_get_age_hours",
    "_is_stale",
    "_score_cell",
    "_swing_cell",
]
