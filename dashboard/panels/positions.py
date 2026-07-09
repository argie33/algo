"""Position panel functions."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dashboard.data_validation import safe_float
from dashboard.error_boundary import get_error_message_plain

from ..formatters import (
    fmt_age,
    fmt_money_short,
    sign,
)
from ..utilities import (
    G,
    R,
    Y,
    normalize_positions_data,
)


@register_panel(
    "positions",
    endpoint_deps=["pos", "trades"],
    optional=True,
    description="Positions",
)
def panel_positions(pos: Any, compact: bool = False, trades: Any = None, extended: bool = False) -> Any:  # noqa: C901
    """Display open positions table. Normalizes input from {"items": [...]} format.

    Data Contract:
    - Expects pos as dict with {"items": [position_dicts]} or list of positions
    - Error handling via "_error" field (hard errors)
    - Optional data unavailability via "_data_unavailable" flag (graceful degradation)
    - Each position dict requires: symbol, current_price, avg_entry_price, position_value
    - Optional fields: weinstein_stage, sector, company_name/name
    - Coverage metrics: valid_count, total_count, filtered_count for data quality visibility
    """
    # Issue 3.1 FIX: Use unified normalization function
    pos_items, pos_timestamp, has_err = normalize_positions_data(pos)
    if has_err:
        # Hard error: data layer returned explicit error marker
        # Use error_boundary function which validates _error message MUST exist
        err_msg = get_error_message_plain(pos)
        if err_msg is None:
            raise RuntimeError(
                "Positions panel received error flag but error_boundary could not extract message. "
                "Cannot display positions without error context. "
                "Check data structure: _error marker present but message is None/empty."
            )
        return Panel(
            Text(f"  Error: {err_msg}", style="red"),
            title="[bold red]POSITIONS[/]",
            border_style="red",
            padding=(0, 1),
        )

    if not pos_items:
        return Panel(
            Text("  No open positions - algo is flat", style="dim"),
            title="[bold]POSITIONS[/]",
            border_style="cyan",
            padding=(0, 1),
        )

    # Check for graceful degradation: explicit data unavailability marker
    # GOVERNANCE: Data unavailability must be explicit. Missing marker means unknown state.
    is_data_unavailable = False
    if isinstance(pos, dict) and "_data_unavailable" in pos:
        is_data_unavailable = bool(pos["_data_unavailable"])
    if is_data_unavailable:
        # Optional data marked unavailable by loader (e.g., missing enrichment)
        # CRITICAL: Validate that unavailable marker includes reason (fail-fast if missing)
        reason = pos.get("reason")
        if reason is None:
            raise ValueError(
                f"[POSITIONS] Data unavailability marker missing required 'reason' field. "
                f"API contract violation: _data_unavailable=True requires reason. Response: {pos}"
            )
        logger.warning(f"Positions data marked unavailable: {reason}")
        return Panel(
            Text.from_markup(
                "[red]✗ POSITIONS DATA UNAVAILABLE[/]\nOptional position enrichment unavailable. Check logs for details."
            ),
            title="[bold red]POSITIONS (DATA UNAVAILABLE)[/]",
            border_style="red",
            padding=(0, 1),
        )

    t = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="dim bold",
        padding=(0, 1),
        row_styles=["", "dim"],
        expand=True,
    )
    t.add_column("Symbol", style="bold white", no_wrap=True, min_width=6)
    t.add_column("Name", style="dim", no_wrap=True, max_width=16)
    t.add_column("Val", justify="right", no_wrap=True, min_width=5)
    t.add_column("Entry", justify="right", no_wrap=True)
    t.add_column("Price", justify="right", no_wrap=True)
    t.add_column("P&L%", justify="right", no_wrap=True, min_width=7)
    if extended:
        t.add_column("R-Mult", justify="right", no_wrap=True, min_width=6)
    t.add_column("Stop", justify="right", no_wrap=True)
    t.add_column("Dist%", justify="right", no_wrap=True)
    if not compact:
        t.add_column("T1->", justify="right", no_wrap=True)
        t.add_column("Days", justify="right", no_wrap=True, min_width=4)
        t.add_column("Stage", justify="center", no_wrap=True, min_width=3)
        t.add_column("M-Trend", justify="right", no_wrap=True, min_width=6)
        t.add_column("Sector", style="dim", no_wrap=True, max_width=12)
    valid_count = 0
    for p in pos_items:
        if p.get("position_value") is None:
            raise RuntimeError(
                f"[POSITIONS_PANEL] Position {p.get('symbol', 'unknown')} has missing position_value. "
                f"API layer should have validated this. Check lambda/api/routes/algo_handlers/dashboard.py."
            )
    sorted_pos_items = sorted(pos_items, key=lambda x: float(x.get("position_value")), reverse=True)
    for p in sorted_pos_items:
        # TRUST API FILTERING: All positions here are already validated by API layer
        # If data is invalid, it's a contract violation — don't silently skip, raise to catch bugs
        symbol = p.get("symbol")
        entry = p.get("avg_entry_price")
        price = p.get("current_price")
        pval = p.get("position_value")

        # Fail fast if API contract is violated (API should have filtered these)
        if not symbol or entry is None or price is None or pval is None:
            raise RuntimeError(
                f"[POSITIONS_PANEL] API contract violation: required field missing. "
                f"API should have filtered this: symbol={symbol}, entry={entry}, price={price}, value={pval}. "
                f"Check: (1) API filtering in lambda/api/routes/algo_handlers/dashboard.py, "
                f"(2) Dashboard data contract in shared_contracts/"
            )

        # Convert to float (safe, no try-except needed — API already validated these are numeric)
        entry = float(entry) if not isinstance(entry, float) else entry
        price = float(price) if not isinstance(price, float) else price
        pval = float(pval) if not isinstance(pval, float) else pval

        # Optional fields - safe_float handles None gracefully
        stop = safe_float(p.get("stop_loss_price"), default=None, field_name=f"{symbol}.stop")
        pnl = safe_float(p.get("unrealized_pnl_pct"), default=None, field_name=f"{symbol}.pnl")

        # Extract optional enrichment fields (low-priority data — graceful degradation)
        days_raw = p.get("days_since_entry")
        if days_raw is None:
            logger.debug(f"[POSITIONS_PANEL] Position {symbol}: days_since_entry unavailable (optional enrichment)")
            days = "--"
        else:
            days = str(days_raw)
        stg = p.get("weinstein_stage")  # Optional: Weinstein stage (may be unavailable)
        if stg is None:
            logger.debug(f"[POSITIONS_PANEL] Position {symbol}: weinstein_stage unavailable (optional enrichment)")
        swg = p.get("minervini_trend_score")  # Optional: Minervini trend score from API
        if swg is None:
            logger.debug(
                f"[POSITIONS_PANEL] Position {symbol}: minervini_trend_score unavailable (optional enrichment)"
            )
        sec_val = p.get("sector")
        if sec_val is None:
            logger.debug(f"[POSITIONS_PANEL] Position {symbol}: sector unavailable (optional enrichment)")
            sec = "--"
        else:
            sec = str(sec_val)[:12]
        rmul = safe_float(
            p.get("r_multiple"), default=None, field_name=f"{symbol}.r_multiple"
        )  # Optional: risk multiple
        dist = safe_float(
            p.get("distance_to_stop_pct"), default=None, field_name=f"{symbol}.distance_to_stop_pct"
        )  # Optional: distance metric
        t1pct = safe_float(
            p.get("distance_to_t1_pct"), default=None, field_name=f"{symbol}.distance_to_t1_pct"
        )  # Optional: target distance

        # Extract display name — NO SECONDARY FALLBACK (remove name field secondary source)
        # Use only company_name if available, don't fall back to generic name field
        # CRITICAL: Don't silently default company_name to empty string — log if missing
        company_name_val = p.get("company_name")
        if company_name_val is None:
            logger.debug(f"[POSITIONS] company_name enrichment missing for {symbol} — position tracking incomplete")
            name = "?"  # Explicit indicator that enrichment unavailable
        else:
            name = company_name_val[:16]

        # Determine row styling based on metrics
        pc = G if (pnl is not None and pnl >= 0) else R
        rc = G if (rmul is not None and rmul >= 0) else R
        dc = R if (dist is not None and dist < 3) else (Y if (dist is not None and dist < 5) else "white")

        # Build table row
        row = [
            symbol,
            Text(name, style="dim"),
            fmt_money_short(pval) if pval is not None else "--",
            f"${entry:.2f}" if entry is not None else "--",
            f"${price:.2f}" if price is not None else "--",
            Text(f"{sign(pnl)}{pnl:.2f}%" if pnl is not None else "--", style=pc),
        ]
        if extended:
            row.append(Text(f"{sign(rmul)}{rmul:.2f}R" if rmul is not None else "--", style=rc))
        row += [
            f"${stop:.2f}" if stop is not None else "--",
            Text(f"{dist:.1f}%" if dist is not None else "--", style=dc),
        ]
        if not compact:
            swg_s = float(swg) if swg is not None else None
            swg_c = (
                G if (swg_s is not None and swg_s >= 80) else (Y if (swg_s is not None and swg_s >= 60) else "white")
            )
            row += [
                f"+{t1pct:.1f}%" if t1pct is not None else "--",
                str(days),
                f"S{stg}" if stg else "--",
                Text(f"{swg_s:.0f}" if swg_s is not None else "--", style=swg_c),
                sec,
            ]
        t.add_row(*row)
        valid_count += 1

    content = t

    # GOVERNANCE FIX: Check data freshness and warn if stale (>24h old)
    stale_warning = ""
    if pos_timestamp is not None:
        from datetime import datetime as dt_cls
        from datetime import timezone as tz_cls

        try:
            now = dt_cls.now(tz_cls.utc)
            if isinstance(pos_timestamp, dt_cls):
                # Ensure both are timezone-aware for comparison
                if pos_timestamp.tzinfo is None:
                    pos_ts_aware = pos_timestamp.replace(tzinfo=tz_cls.utc)
                else:
                    pos_ts_aware = pos_timestamp
                age_hours = (now - pos_ts_aware).total_seconds() / 3600
                if age_hours > 24:
                    stale_warning = " [yellow]⚠ STALE[/]"
                    logger.warning(f"[POSITIONS] Position data stale ({age_hours:.0f}h old)")
        except (ValueError, TypeError, AttributeError):
            logger.debug("[POSITIONS] Could not calculate staleness")

    age_s = f"  [dim]{fmt_age(pos_timestamp)}[/]{stale_warning}" if pos_timestamp is not None else ""

    # Show filtering status from API if available
    coverage = None
    if isinstance(pos, dict):
        coverage = pos.get("coverage")

    if coverage is None:
        logger.warning("[POSITIONS_PANEL] Coverage metadata missing from API - filtering visibility unavailable")

    # Display filtering status with clear explanation of what was filtered
    # Fail-fast: Check that coverage data is valid before using. Do not silently default to 0.
    coverage_valid = coverage is not None and isinstance(coverage, dict)
    has_filtering_info = False
    if coverage_valid and isinstance(coverage, dict):
        total_count = coverage.get("total_count")
        filtered_count = coverage.get("filtered_count")
        has_filtering_info = (
            total_count is not None and total_count > 0 and filtered_count is not None and filtered_count > 0
        )
    if has_filtering_info and coverage_valid:
        # coverage is guaranteed to be dict at this point
        total = coverage.get("total_count", 0)  # type: ignore[union-attr]
        valid = coverage.get("valid_count", 0)  # type: ignore[union-attr]
        filt = coverage.get("filtered_count", 0)  # type: ignore[union-attr]
        border = "yellow"
        # Show: "POSITIONS (2/15 valid, 13 filtered)"
        title_str = f"[bold yellow]POSITIONS ({valid}/{total} valid, {filt} filtered)[/]"
    else:
        border = "cyan"
        title_str = f"[bold cyan]POSITIONS ({valid_count})[/]"
    return Panel(
        content,
        title=f"{title_str}{age_s}  [dim][p] expand[/]",
        border_style=border,
        padding=(0, 0),
    )


__all__ = [
    "panel_positions",
]
