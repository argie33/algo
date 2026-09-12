"""Options-sleeve pretrade checks - phase 4 of the options-strategy plan
(steering/OPTIONS_STRATEGY_SPEC.md).

Mirrors the shape `algo.risk.circuit_breaker.CircuitBreaker.check_all()` already returns
(`{"halted": bool, "halt_reasons": [...], "checks": {name: {"halted": ..., "reason": ...}}}`)
so this slots into the same reporting/logging conventions the equity strategy's circuit
breaker already uses, rather than inventing a parallel shape.

NOT wired into the live orchestrator yet - there is nothing for it to gate. No options
execution code exists (phase 5, not started); this module is what phase 5's future
order-submission code is expected to call before submitting any CSP/covered-call order, per
spec section 7's go/no-go item 2 ("risk/collateral infrastructure (phase 4) is live ... the
sleeve's own pretrade checks wired into the existing halt_flag_manager, same halt propagation
the equity strategy already has - not a parallel, disconnected halt system").

Per that same go/no-go item, this module uses `algo.orchestration.halt_flag_manager.
HaltFlagManager` (not a bespoke halt mechanism) for the one condition here severe enough to
warrant a real trading halt: collateral accounting being internally inconsistent (negative
committed collateral, or committed collateral already exceeding the 5% sleeve cap on its own
- both indicate a bug in the accounting, not a normal "this trade doesn't fit" rejection).
Every other check here is a plain reject-this-candidate result, exactly like
`CircuitBreakerTradeSectorMixin._check_sector_concentration`'s advisory-only pattern - it
would be wrong to halt ALL trading (equity included) just because one options candidate
doesn't fit the sleeve's per-underlying/sector/collateral caps.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from algo.risk.options_collateral import (
    SLEEVE_CAP_PCT,
    available_sleeve_capital,
    compute_committed_collateral,
    has_equity_overlap,
    sector_exposure_pct,
    underlying_exposure_pct,
)

logger = logging.getLogger(__name__)

# Spec section 4.
PER_UNDERLYING_CAP_PCT = Decimal("20")
SECTOR_CAP_PCT = Decimal("40")

CHECK_LABELS = {
    "collateral_accounting_sane": "Collateral Accounting Internally Consistent",
    "sleeve_cap": "Sleeve Capital Cap (5% of equity)",
    "per_underlying_cap": "Per-Underlying Concentration Cap (20% of sleeve)",
    "sector_cap": "Sector Concentration Cap (40% of sleeve)",
    "no_equity_overlap": "Equity/Sleeve Overlap Rule",
    "cash_collateral_available": "Cash Collateral Actually Available",
}


def _get_halt_manager(halt_manager: Any | None) -> Any:
    if halt_manager is not None:
        return halt_manager
    from algo.orchestration.halt_flag_manager import HaltFlagManager
    from algo.reporting import AlertManager

    return HaltFlagManager(AlertManager(), lambda *a, **kw: None)


def _check_collateral_accounting_sane(cur: Any, account_equity: Decimal, halt_manager: Any) -> dict[str, Any]:
    """Real halt condition (per spec section 7 item 2): committed collateral must never be
    negative, and must never already exceed the 5% sleeve cap on its own (both indicate the
    accounting itself is broken, not that this specific candidate is a bad fit) - routed
    through HaltFlagManager, the same halt propagation the equity strategy already uses, not
    a bespoke mechanism local to this module.
    """
    committed = compute_committed_collateral(cur)
    sleeve_cap = account_equity * SLEEVE_CAP_PCT
    if committed < 0 or committed > sleeve_cap:
        reason = (
            f"Committed collateral ${committed} is "
            f"{'negative' if committed < 0 else f'already over the sleeve cap (${sleeve_cap})'} - "
            "collateral accounting is internally inconsistent"
        )
        logger.critical(f"[CIRCUIT_BREAKER_OPTIONS] {reason} - halting via HaltFlagManager")
        try:
            halt_manager.set_halt_flag(reason=reason, triggered_by="circuit_breaker_options")
        except Exception as e:
            # HaltFlagManager.set_halt_flag raises if BOTH DynamoDB and RDS fail (see its own
            # docstring: "trading must not proceed with an unmanageable halt flag"). This
            # check already found a real inconsistency; failing to also set the halt flag
            # must not be silently swallowed - re-raise so the caller (and its own caller,
            # phase 5's future execution code) does not proceed believing this check merely
            # "rejected the candidate" when the underlying failure is far worse.
            raise RuntimeError(
                f"Collateral accounting inconsistency detected AND halt flag could not be set: {e}"
            ) from e
        return {"halted": True, "reason": reason, "value": float(committed)}
    return {"halted": False, "reason": f"Committed collateral ${committed} within sleeve cap ${sleeve_cap}"}


def _check_sleeve_cap(
    cur: Any, account_equity: Decimal, strike: Decimal, contracts: int, strategy_leg: str
) -> dict[str, Any]:
    """New CSP collateral must fit within whatever sleeve capital remains available. A
    covered call requires no NEW cash collateral (share-collateralized against shares the
    sleeve already owns from a prior assignment), so it always passes this check."""
    if strategy_leg != "csp":
        return {"halted": False, "reason": "Covered call - no new cash collateral required"}

    new_collateral = strike * Decimal(100) * Decimal(contracts)
    available = available_sleeve_capital(cur, account_equity)
    fits = new_collateral <= available
    return {
        "halted": not fits,
        "reason": (
            f"New CSP collateral ${new_collateral} exceeds available sleeve capital ${available}"
            if not fits
            else f"New CSP collateral ${new_collateral} fits within available sleeve capital ${available}"
        ),
        "value": float(new_collateral),
        "threshold": float(available),
    }


def _check_per_underlying_cap(cur: Any, symbol: str, sleeve_capital: Decimal) -> dict[str, Any]:
    pct = underlying_exposure_pct(cur, symbol, sleeve_capital)
    breached = pct > PER_UNDERLYING_CAP_PCT
    return {
        "halted": breached,
        "reason": (
            f"{symbol} exposure {pct:.1f}% of sleeve exceeds {PER_UNDERLYING_CAP_PCT}% cap"
            if breached
            else f"{symbol} exposure {pct:.1f}% of sleeve within {PER_UNDERLYING_CAP_PCT}% cap"
        ),
        "value": float(pct),
        "threshold": float(PER_UNDERLYING_CAP_PCT),
    }


def _check_sector_cap(cur: Any, sector: str | None, sleeve_capital: Decimal) -> dict[str, Any]:
    if not sector:
        # Fail closed on missing sector data, same convention as
        # CircuitBreakerTradeSectorMixin._check_sector_concentration's NULL-sector handling -
        # a real risk check must not silently treat "we don't know the sector" as "no risk".
        return {"halted": True, "reason": "Sector is missing/unknown - cannot verify sector cap"}
    pct = sector_exposure_pct(cur, sector, sleeve_capital)
    breached = pct > SECTOR_CAP_PCT
    return {
        "halted": breached,
        "reason": (
            f"{sector} sector exposure {pct:.1f}% of sleeve exceeds {SECTOR_CAP_PCT}% cap"
            if breached
            else f"{sector} sector exposure {pct:.1f}% of sleeve within {SECTOR_CAP_PCT}% cap"
        ),
        "value": float(pct),
        "threshold": float(SECTOR_CAP_PCT),
    }


def _check_no_equity_overlap(cur: Any, symbol: str) -> dict[str, Any]:
    overlap = has_equity_overlap(cur, symbol)
    return {
        "halted": overlap,
        "reason": (
            f"{symbol} already has open equity-strategy exposure or open sleeve exposure"
            if overlap
            else f"{symbol} has no equity/sleeve overlap"
        ),
    }


def _check_cash_collateral_available(
    cur: Any, account_equity: Decimal, strike: Decimal, contracts: int, strategy_leg: str
) -> dict[str, Any]:
    """Strict cash-secured posture (spec section 4): a CSP's collateral must be cash the
    sleeve actually holds, never an assumption of margin/buying-power borrowed from the
    equity sleeve. This repeats the sleeve-cap arithmetic deliberately (not a duplicate of
    `_check_sleeve_cap`): that check asks "does this fit the 5% budget", this one is the
    explicit statement of the cash-only constraint the spec calls out as its own named
    go/no-go item, so a future reader auditing "is the cash-collateral rule actually
    enforced" finds a check named exactly that rather than having to infer it from the
    sleeve-cap check's math.
    """
    if strategy_leg != "csp":
        return {"halted": False, "reason": "Covered call - share-collateralized, no cash collateral required"}
    required = strike * Decimal(100) * Decimal(contracts)
    available = available_sleeve_capital(cur, account_equity)
    sufficient = required <= available
    return {
        "halted": not sufficient,
        "reason": (
            f"Required cash collateral ${required} not available (${available} free in sleeve) - "
            "no margin/buying-power assumption permitted"
            if not sufficient
            else f"Required cash collateral ${required} is available in sleeve cash (${available})"
        ),
        "value": float(required),
        "threshold": float(available),
    }


def check_options_pretrade(
    cur: Any,
    symbol: str,
    sector: str | None,
    strategy_leg: str,
    strike: Decimal,
    contracts: int,
    account_equity: Decimal,
    halt_manager: Any | None = None,
) -> dict[str, Any]:
    """Run every options-sleeve pretrade check for a candidate CSP/covered-call order.

    Returns the same `{"halted", "halt_reasons", "checks"}` shape as
    `CircuitBreaker.check_all()`. `halted=True` means THIS candidate should be rejected -
    it does not mean all trading (equity included) is halted, except for the
    `collateral_accounting_sane` check, which additionally sets the real orchestrator-wide
    halt flag via HaltFlagManager (see module docstring).

    Not currently called by any live orchestrator phase - there is no options execution code
    yet (phase 5, not started). This is what that future code is expected to call before
    submitting any order.
    """
    account_equity = Decimal(str(account_equity))
    strike = Decimal(str(strike))
    halt_manager = _get_halt_manager(halt_manager)
    sleeve_capital = account_equity * SLEEVE_CAP_PCT

    checks: dict[str, Any] = {}
    checks["collateral_accounting_sane"] = _check_collateral_accounting_sane(cur, account_equity, halt_manager)
    checks["sleeve_cap"] = _check_sleeve_cap(cur, account_equity, strike, contracts, strategy_leg)
    checks["per_underlying_cap"] = _check_per_underlying_cap(cur, symbol, sleeve_capital)
    checks["sector_cap"] = _check_sector_cap(cur, sector, sleeve_capital)
    checks["no_equity_overlap"] = _check_no_equity_overlap(cur, symbol)
    checks["cash_collateral_available"] = _check_cash_collateral_available(
        cur, account_equity, strike, contracts, strategy_leg
    )

    results: dict[str, Any] = {"halted": False, "halt_reasons": [], "checks": {}}
    for name, state in checks.items():
        state["label"] = CHECK_LABELS.get(name, name)
        results["checks"][name] = state
        if state["halted"]:
            results["halted"] = True
            results["halt_reasons"].append(f"{state['label']}: {state['reason']}")

    return results
