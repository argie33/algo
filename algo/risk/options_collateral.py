"""Options-sleeve collateral accounting - phase 4 of the options-strategy plan
(steering/OPTIONS_STRATEGY_SPEC.md).

Pure accounting logic only - no order submission (that's phase 5, not started). Every
function here reads `algo_options_positions` (migration 1285) and does math; nothing writes
to it. `algo/risk/circuit_breaker_options.py` is the pretrade gate built on top of these
functions.

SINGLE SOURCE OF TRUTH: `compute_committed_collateral()` is the ONLY place collateral
accounting should ever be summed from. Every other function in this module (and every future
caller, including phase 5's execution code) must call it rather than re-deriving a collateral
total independently - that is exactly how a double-count bug gets introduced (two code paths
computing "committed collateral" slightly differently and drifting apart under a real edit).
It sums `collateral_amount` over `status = 'open'` rows only - a CSP that has been assigned,
closed, rolled, or expired no longer has cash committed against it (assignment converts the
cash collateral into owned shares, tracked instead via `cost_basis` * `assigned_shares` on the
now-`'assigned'` row), so those statuses are correctly excluded here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# 5% of live account equity - see steering/OPTIONS_STRATEGY_SPEC.md section 0 for the
# rationale (percentage-of-equity, not a fixed dollar figure, recomputed live every call -
# never cached at strategy-design time).
SLEEVE_CAP_PCT = Decimal("0.05")


def _as_decimal(value: Any) -> Decimal:
    """Convert a DB-returned numeric (Decimal, float, str, or None) to Decimal safely."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def compute_committed_collateral(cur: Any) -> Decimal:
    """Sum of `collateral_amount` over every currently-`open` row in
    `algo_options_positions`. THE single source of truth for committed cash collateral - see
    module docstring. Never negative in a healthy state; a negative result indicates a data
    integrity problem the caller (circuit_breaker_options.check_options_pretrade) treats as a
    halt-worthy condition, not something this function silently clamps or hides.
    """
    cur.execute(
        """
        SELECT COALESCE(SUM(collateral_amount), 0)
        FROM algo_options_positions
        WHERE status = 'open'
        """
    )
    row = cur.fetchone()
    return _as_decimal(row[0] if row is not None else 0)


def available_sleeve_capital(cur: Any, account_equity: Decimal) -> Decimal:
    """Remaining sleeve capital = 5% of live account equity minus collateral already
    committed to open CSPs, floored at 0 (never negative - a caller with negative "available"
    capital would be a bug elsewhere, not something to surface as a negative number here).
    """
    account_equity = _as_decimal(account_equity)
    sleeve_cap = account_equity * SLEEVE_CAP_PCT
    committed = compute_committed_collateral(cur)
    available = sleeve_cap - committed
    return available if available > 0 else Decimal("0")


def _symbol_committed_exposure(cur: Any, symbol: str) -> Decimal:
    """Dollar exposure the sleeve currently carries in one underlying: open-CSP collateral
    (cash committed, not yet assigned) PLUS assigned-share cost basis (shares already owned
    via a prior CSP assignment, whether or not a covered call is currently written against
    them - the covered-call leg's own row carries no `collateral_amount` of its own, so
    summing it here would double-count nothing).
    """
    cur.execute(
        """
        SELECT
            COALESCE(SUM(collateral_amount) FILTER (WHERE status = 'open'), 0) AS open_collateral,
            COALESCE(SUM(cost_basis * assigned_shares) FILTER (WHERE status = 'assigned'), 0) AS assigned_exposure
        FROM algo_options_positions
        WHERE symbol = %s
        """,
        (symbol,),
    )
    row = cur.fetchone()
    if row is None:
        return Decimal("0")
    return _as_decimal(row[0]) + _as_decimal(row[1])


def _sector_committed_exposure(cur: Any, sector: str) -> Decimal:
    """Same idea as `_symbol_committed_exposure`, aggregated across every symbol tagged with
    this sector in `algo_options_positions.sector`."""
    cur.execute(
        """
        SELECT
            COALESCE(SUM(collateral_amount) FILTER (WHERE status = 'open'), 0) AS open_collateral,
            COALESCE(SUM(cost_basis * assigned_shares) FILTER (WHERE status = 'assigned'), 0) AS assigned_exposure
        FROM algo_options_positions
        WHERE sector = %s
        """,
        (sector,),
    )
    row = cur.fetchone()
    if row is None:
        return Decimal("0")
    return _as_decimal(row[0]) + _as_decimal(row[1])


def _exposure_pct(exposure: Decimal, sleeve_capital: Decimal) -> Decimal:
    """Exposure as a percentage of the sleeve's total capital (5% of equity - the fixed cap,
    NOT the remaining `available_sleeve_capital`; per-underlying/sector caps in spec section 4
    are stated as a percentage of the sleeve's total size).

    Guards division by a non-positive sleeve_capital (e.g. a misconfigured/zero account
    equity) by treating any real exposure as fully breaching (100%) rather than raising -
    this is a pretrade CAP check, and failing toward "breached" is the safe direction for a
    risk gate whose whole job is to block new exposure, not compute a display metric.
    """
    if sleeve_capital <= 0:
        return Decimal("0") if exposure <= 0 else Decimal("100")
    return (exposure / sleeve_capital) * Decimal("100")


def underlying_exposure_pct(cur: Any, symbol: str, sleeve_capital: Decimal) -> Decimal:
    """Current sleeve exposure to `symbol` as a percentage of the sleeve's total capital -
    feeds the 20%-per-underlying cap check (spec section 4)."""
    exposure = _symbol_committed_exposure(cur, symbol)
    return _exposure_pct(exposure, _as_decimal(sleeve_capital))


def sector_exposure_pct(cur: Any, sector: str, sleeve_capital: Decimal) -> Decimal:
    """Current sleeve exposure to `sector` as a percentage of the sleeve's total capital -
    feeds the 40%-sector cap check (spec section 4)."""
    exposure = _sector_committed_exposure(cur, sector)
    return _exposure_pct(exposure, _as_decimal(sleeve_capital))


def has_equity_overlap(cur: Any, symbol: str) -> bool:
    """True if `symbol` currently has ANY open equity-strategy position OR any open/assigned
    sleeve position - the hard equity-overlap rule from spec section 6.

    Symmetric by construction (checks both tables), so it serves both directions of the rule:
    `algo/risk/circuit_breaker_options.py`'s `check_options_pretrade()` calls this before the
    sleeve opens a new CSP; `algo/orchestrator/phase8_entry_execution.py`'s per-candidate
    pre-filter loop (2026-09-12 fix) calls this before the equity strategy opens a new
    position, closing what was previously a one-directional gap (see git history / memory
    `options_strategy_full_plan_and_phase1_20260912` for the phase-4-vs-phase-8-fix split).
    """
    cur.execute("SELECT 1 FROM algo_positions WHERE symbol = %s AND status = 'open' LIMIT 1", (symbol,))
    if cur.fetchone() is not None:
        return True

    cur.execute(
        "SELECT 1 FROM algo_options_positions WHERE symbol = %s AND status IN ('open', 'assigned') LIMIT 1",
        (symbol,),
    )
    return cur.fetchone() is not None
