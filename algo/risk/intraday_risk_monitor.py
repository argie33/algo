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

This module closes the VISIBILITY half of that gap: an ALERT-ONLY (deliberately not
auto-halting - see this module's own docstring note below) recheck, meant to run on a tight
intraday cadence (see terraform/modules/services/intraday-risk-monitor.tf, disabled by
default same as stop-loss-guardian.tf) via `mode: "intraday_risk_monitor"` in
lambda_function.py.

Uses LIVE broker state (AlpacaBrokerAdapter.fetch_account()/fetch_positions()), not
algo_positions.current_price - that column is only refreshed once/day by Phase 3 off the
EOD price_daily loader (see phase3_position_monitor.py), so intraday it can be hours stale
- exactly the kind of gap this check exists to catch, so it must not rely on it.

DELIBERATELY ALERT-ONLY, NOT AUTO-HALT: whether an intraday risk breach should
automatically halt new trading (via HaltFlagManager.set_halt_flag) is a real product
decision (a false-positive halt on a real trading day has its own cost) that the 2026-09-06
architecture-gap note explicitly left for the user to decide, not something this session
should decide unilaterally. This module surfaces the breach immediately via AlertManager
(the same durable, multi-channel path every other real-money risk alert in this codebase
uses) so a human can act; wiring an automatic halt on top of this is a small, separate
follow-up once that product decision is made.
"""

import logging
from decimal import Decimal
from typing import Any

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
from algo.reporting import AlertManager
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def check_intraday_risk(config: Any, alerts: AlertManager | None = None) -> dict[str, Any]:
    """Recompute portfolio beta and top-5 concentration against LIVE broker state and
    alert (never raises for a breach - only for a genuine infrastructure failure) if either
    exceeds this account's configured `max_portfolio_beta`/`max_top5_concentration_pct`.

    Returns a result dict (for the caller's own logging) with the computed values and
    whether either threshold was breached - never silently swallows a breach, but also
    never takes a trading-affecting action itself (see module docstring).
    """
    alerts = alerts or AlertManager()
    broker = AlpacaBrokerAdapter(config)

    account = broker.fetch_account()
    portfolio_value = Decimal(str(account["portfolio_value"]))
    positions = broker.fetch_positions()

    if not positions:
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
    # denominator choice matters. A symbol with no known beta is excluded from the weighted
    # sum (its dollar value is real, but there is no real beta to weight it by) - reported
    # separately via symbols_missing_beta rather than silently assumed to be beta=0 or
    # beta=1, either of which would misstate the true exposure.
    weighted_beta_sum = Decimal("0")
    for p in positions:
        beta = beta_by_symbol.get(p["symbol"])
        if beta is not None:
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
            f"stability_metrics.beta on file, excluded from the weighted beta calc: "
            f"{symbols_missing_beta}. Reported portfolio_beta may understate true exposure."
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

    return {
        "portfolio_value": float(portfolio_value),
        "portfolio_beta": portfolio_beta,
        "top5_concentration_pct": top5_concentration_pct,
        "beta_breach": beta_breach,
        "concentration_breach": concentration_breach,
        "symbols_missing_beta": symbols_missing_beta,
    }
