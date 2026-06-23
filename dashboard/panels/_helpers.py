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
    """
    out: dict[str, float] = {}
    for bs in buy_sigs or []:
        if not isinstance(bs, dict):
            continue
        sym = bs.get("symbol")
        if not sym:
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
    c = G if swing_v >= 80 else (CY if swing_v >= 70 else Y)
    return Text(f"▲{swing_v:.0f}", style=c)


def _composite_score_color(v: Any) -> str:
    """Color for composite scores: green >=80, cyan >=60, yellow >=40, else white."""
    return G if v >= 80 else (CY if v >= 60 else (Y if v >= 40 else "white"))


def _best_halt_reason(top_level: str, phase_results: list[Any]) -> list[tuple[str, str]]:
    """Return a list of (phase_label, reason) pairs drawn from phase-level data.

    Falls back to top_level if no per-phase detail is found.
    Tries multiple field names so the display is robust to orchestrator schema changes.
    """
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
            (str(pdata[k]) for k in fields if pdata and pdata.get(k) and len(str(pdata.get(k))) > 3),
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


def _error_panel(data_name: str, data: Any, title: str, border: str = "magenta") -> Panel | None:
    """Create a panel showing granular error info for failed data sources.

    Checks for both hard errors (_error) and stale data (_data_stale) using error_boundary.
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

    return None


__all__ = [
    "_best_halt_reason",
    "_build_buy_sig_map",
    "_composite_score_color",
    "_error_panel",
    "_fmt_phases_halted",
    "_score_cell",
    "_swing_cell",
]
