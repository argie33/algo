#!/usr/bin/env python3
"""Intraday portfolio-risk re-check against LIVE broker state (not the daily snapshot).

REAL-MONEY-READINESS FINDING (documented 2026-09-06 as `intraday_monitoring_architecture_
gap`, paused pending a design decision, now scoped down and built): `algo/risk/var.py`'s
beta_exposure()/concentration_report() and `pretrade_checks.py`'s beta/top5-concentration
checks only ever run (a) once/day via Phase 9's end-of-cycle risk report, or (b) at the
moment of a NEW candidate entry. Nothing re-evaluates portfolio beta or top-5 concentration
against positions that are ALREADY open as prices drift intraday - a position can walk
past the 2.0 beta cap or the top-5-concentration cap purely from price movement, with no
new entry involved, and nothing will notice until the next Phase 9 run at end of day.

This module closes the VISIBILITY half of that gap: a recheck, meant to run on a tight
intraday cadence (see terraform/modules/services/intraday-risk-monitor.tf, disabled by
default same as stop-loss-guardian.tf) via `mode: "intraday_risk_monitor"` in
lambda_function.py.

Uses LIVE broker state (AlpacaBrokerAdapter.fetch_account()/fetch_positions()), not
algo_positions.current_price - that column is only refreshed once/day by Phase 3 off the
EOD price_daily loader (see phase3_position_monitor.py), so intraday it can be hours stale
- exactly the kind of gap this check exists to catch, so it must not rely on it.

REAL-MONEY-READINESS FIX (2026-09-10, product decision made): a breach now also sets the
same HaltFlagManager flag Phase 2's circuit breaker uses, with
`triggered_by="intraday_risk_monitor"` - blocking Phase 8 from placing NEW entries (and, via
set_halt_flag's own `_cancel_pending_entry_orders_on_halt`, cancelling any not-yet-filled
entry order already resting at the broker) until this check next runs clean. Deliberately
does NOT touch already-open positions: existing positions keep exiting only through their
own configured stop-loss/take-profit/exit-strategy logic, exactly as before - this check
adds no forced liquidation or de-risking of its own, on the user's explicit direction that a
beta/concentration breach on an already-open swing-trade book is a "stop adding risk", not a
"start selling" signal. When a later run finds both metrics back under cap, it self-clears
ONLY a halt it recognizes as its own (mirrors phase2_circuit_breaker's self-clear pattern in
orchestrator_phases_executor.py) - never touches a halt set by Phase 1/Phase 2/Phase 9/a
manual operator. Still also sends the AlertManager alert on every breach, same as before, so
a human is notified even though the system now also acts.
"""

import logging
from decimal import Decimal
from typing import Any

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.reporting import AlertManager
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def check_intraday_risk(
    config: Any, alerts: AlertManager | None = None, halt_manager: Any | None = None
) -> dict[str, Any]:
    """Recompute portfolio beta and top-5 concentration against LIVE broker state; alert and
    halt new entries (never raises for a breach itself - only for a genuine infrastructure
    failure) if either exceeds this account's configured `max_portfolio_beta`/
    `max_top5_concentration_pct`.

    Returns a result dict (for the caller's own logging) with the computed values and
    whether either threshold was breached - never silently swallows a breach (see module
    docstring for exactly what action is and isn't taken).
    """
    alerts = alerts or AlertManager()
    if halt_manager is None:
        from algo.orchestration.halt_flag_manager import HaltFlagManager

        halt_manager = HaltFlagManager(alerts, lambda *a, **k: None)
    broker = AlpacaBrokerAdapter(config)

    account = broker.fetch_account()
    portfolio_value = Decimal(str(account["portfolio_value"]))
    positions = broker.fetch_positions()

    if not positions:
        # No open positions - can't be over a beta/concentration cap. Same self-clear as the
        # bottom of this function: only touch a halt this check itself previously set.
        if halt_manager.get_halt_triggered_by() == "intraday_risk_monitor":
            halt_manager.clear_halt_flag(
                "Intraday risk re-check found no open positions",
                allowed_triggers=frozenset({"intraday_risk_monitor"}),
            )
        return {
            "portfolio_value": float(portfolio_value),
            "portfolio_beta": 0.0,
            "top5_concentration_pct": 0.0,
            "beta_breach": False,
            "concentration_breach": False,
            "symbols_missing_beta": [],
        }

    if portfolio_value <= 0:
        # Same "cannot evaluate risk without a real denominator" stance pretrade_checks.py
        # and var.py already take - never silently report 0% exposure against a bad/zero
        # equity figure, since that would read as "safe" when it actually means "unknown."
        raise RuntimeError(
            f"[INTRADAY_RISK_MONITOR CRITICAL] Alpaca reports non-positive portfolio_value "
            f"({portfolio_value}) with {len(positions)} open position(s) - cannot compute "
            f"beta/concentration exposure against an invalid denominator."
        )

    symbols = [p["symbol"] for p in positions]
    with DatabaseContext("read") as cur:
        cur.execute(
            "SELECT symbol, beta FROM stability_metrics WHERE symbol = ANY(%s) AND data_unavailable IS NOT TRUE",
            (symbols,),
        )
        beta_by_symbol = {row[0]: float(row[1]) for row in cur.fetchall() if row[1] is not None}

    symbols_missing_beta = sorted(s for s in symbols if s not in beta_by_symbol)

    # Same convention as pretrade_checks.py._check_portfolio_beta/var.py.beta_exposure:
    # weighted by each position's live dollar value over TOTAL account equity (cash
    # included), not invested-capital-only - see that check's 2026-09-06 fix for why this
    # denominator choice matters.
    #
    # REAL-MONEY-READINESS FIX (2026-09-06 audit): a symbol with no known beta used to be
    # excluded entirely from the weighted sum - its full dollar value still counted in the
    # portfolio_value denominator but contributed NOTHING to the numerator, which is
    # mathematically identical to assuming beta=0.0 for it. A newly-entered high-beta
    # position without beta history yet could push true portfolio beta well past
    # max_portfolio_beta while this monitor kept reporting a comfortably low number and
    # never breaching - defeating the exact drift this check exists to catch. Weight a
    # missing-beta position at a conservative beta=1.0 (market-average assumption) instead
    # of silently zero-weighting it; symbols_missing_beta below still reports which
    # positions are on an assumed rather than measured beta.
    missing_beta_conservative_assumption = 1.0
    weighted_beta_sum = Decimal("0")
    for p in positions:
        beta = beta_by_symbol.get(p["symbol"], missing_beta_conservative_assumption)
        weighted_beta_sum += Decimal(str(p["market_value"])) * Decimal(str(beta))
    portfolio_beta = float(weighted_beta_sum / portfolio_value)

    position_values = sorted((Decimal(str(p["market_value"])) for p in positions), reverse=True)
    top5_value = sum(position_values[:5])
    top5_concentration_pct = float(top5_value / portfolio_value * 100)

    try:
        max_portfolio_beta = float(config["max_portfolio_beta"])
        max_top5_concentration_pct = float(config["max_top5_concentration_pct"])
    except KeyError as e:
        raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

    beta_breach = portfolio_beta > max_portfolio_beta
    concentration_breach = top5_concentration_pct > max_top5_concentration_pct

    if symbols_missing_beta:
        logger.warning(
            f"[INTRADAY_RISK_MONITOR] {len(symbols_missing_beta)} open position(s) have no "
            f"stability_metrics.beta on file, weighted at an assumed beta="
            f"{missing_beta_conservative_assumption} in the calc below: {symbols_missing_beta}. "
            f"Reported portfolio_beta may not reflect their true (unknown) exposure."
        )

    if beta_breach or concentration_breach:
        reasons = []
        if beta_breach:
            reasons.append(f"portfolio beta {portfolio_beta:.2f} exceeds cap {max_portfolio_beta:.2f}")
        if concentration_breach:
            reasons.append(
                f"top-5 concentration {top5_concentration_pct:.1f}% exceeds cap {max_top5_concentration_pct:.1f}%"
            )
        alerts.send_position_alert(
            "PORTFOLIO",
            "INTRADAY_RISK_BREACH",
            "Intraday risk re-check found the EXISTING book (no new entry involved) has "
            "drifted past a configured risk limit purely from price movement: " + "; ".join(reasons),
            {
                "portfolio_value": float(portfolio_value),
                "portfolio_beta": portfolio_beta,
                "top5_concentration_pct": top5_concentration_pct,
                "max_portfolio_beta": max_portfolio_beta,
                "max_top5_concentration_pct": max_top5_concentration_pct,
                "symbols_missing_beta": symbols_missing_beta,
            },
        )
        # Block new entries only - existing positions keep exiting through their own
        # configured stop-loss/take-profit/exit-strategy logic, untouched (see module
        # docstring). set_halt_flag() itself cancels only not-yet-filled entry orders.
        halt_manager.set_halt_flag(
            "Intraday risk breach: " + "; ".join(reasons),
            triggered_by="intraday_risk_monitor",
        )
    else:
        # Self-clear only a halt this check itself previously set - mirrors
        # phase2_circuit_breaker's self-clear pattern. Never touches a halt set by Phase 1,
        # Phase 2, Phase 9, or a manual operator.
        current_trigger = halt_manager.get_halt_triggered_by()
        if current_trigger == "intraday_risk_monitor":
            logger.info(
                "[INTRADAY_RISK_MONITOR] Portfolio beta and top-5 concentration are back under "
                "cap - clearing the halt flag this check previously set."
            )
            halt_manager.clear_halt_flag(
                "Intraday risk re-check found beta/concentration back under cap",
                allowed_triggers=frozenset({"intraday_risk_monitor"}),
            )

    return {
        "portfolio_value": float(portfolio_value),
        "portfolio_beta": portfolio_beta,
        "top5_concentration_pct": top5_concentration_pct,
        "beta_breach": beta_breach,
        "concentration_breach": concentration_breach,
        "symbols_missing_beta": symbols_missing_beta,
    }
