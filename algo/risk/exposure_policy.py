#!/usr/bin/env python3

import logging
import math
from datetime import date as _date
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

# Four tiers aligned with RegimeManager vocabulary so both systems speak the same language.
# Ranges mirror the regime thresholds in algo_market_exposure.py:
#   confirmed_uptrend    >= 70%
#   uptrend_under_pressure 45-70%
#   caution              25-45%
#   correction           < 25%
#
# Upper bounds are exclusive (except the top tier) — no boundary overlap.
EXPOSURE_TIERS: list[dict[str, Any]] = [
    {
        "name": "confirmed_uptrend",
        "min_pct": 70,
        "max_pct": 100,
        "description": "Confirmed bull market — full deployment",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 5,
        "min_swing_score": 60.0,
        "min_swing_grade": "B",
        "tighten_winners_at_r": None,
        "force_partial_at_r": None,
        "halt_new_entries": False,
        "force_exit_negative_r": False,
        "max_concentration_pct": 20.0,
        "color": "green",
    },
    {
        "name": "uptrend_under_pressure",
        "min_pct": 45,
        "max_pct": 70,
        "description": "Uptrend intact but weakening — reduced position size",
        "risk_multiplier": 0.65,
        "max_new_positions_today": 3,
        "min_swing_score": 68.0,
        "min_swing_grade": "B",
        "tighten_winners_at_r": 2.5,
        "force_partial_at_r": None,
        "halt_new_entries": False,
        "force_exit_negative_r": False,
        "max_concentration_pct": 16.0,
        "color": "yellow",
    },
    {
        "name": "caution",
        "min_pct": 25,
        "max_pct": 45,
        "description": "Market under significant stress — entries halted",
        "risk_multiplier": 0.35,
        "max_new_positions_today": 1,
        "min_swing_score": 75.0,
        "min_swing_grade": "A",
        "tighten_winners_at_r": 1.5,
        "force_partial_at_r": 2.5,
        "halt_new_entries": True,
        "force_exit_negative_r": False,
        "max_concentration_pct": 12.0,
        "color": "orange",
    },
    {
        "name": "correction",
        "min_pct": 0,
        "max_pct": 25,
        "description": "Market correction — preserve capital, no new entries",
        "risk_multiplier": 0.0,
        "max_new_positions_today": 0,
        "min_swing_score": 100.0,
        "min_swing_grade": "A+",
        "tighten_winners_at_r": 1.0,
        "force_partial_at_r": 1.5,
        "halt_new_entries": True,
        "force_exit_negative_r": True,
        "max_concentration_pct": 10.0,
        "color": "red",
    },
]


def tier_for_exposure(exposure_pct: float | None) -> dict[str, Any]:
    """Return the active policy tier for a given exposure %.

    Upper bounds are exclusive so exact boundary values (e.g. 70.0) land in the
    higher (more aggressive) tier, matching the >= thresholds in algo_market_exposure.py.
    CRITICAL: Fails fast (raises) if exposure_pct is None or NaN — never silently defaults.
    Missing market exposure indicates Phase 4 failure; trading must halt to prevent stale data usage.
    """
    if exposure_pct is None or (isinstance(exposure_pct, float) and math.isnan(exposure_pct)):
        msg = (
            f"[EXPOSURE POLICY CRITICAL] Market exposure percentage is missing or invalid ({exposure_pct}). "
            f"Phase 4 market exposure calculation must succeed for position sizing. "
            f"Cannot proceed with trading when risk tier cannot be determined. "
            f"Check: (1) Is Phase 4 market exposure loader running? (2) Does market_exposure_daily have today's data? "
            f"(3) Is Phase 4 computation returning valid values?"
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    for i, tier in enumerate(EXPOSURE_TIERS):
        is_last = i == len(EXPOSURE_TIERS) - 1
        upper_ok = exposure_pct <= tier["max_pct"] if is_last else exposure_pct < tier["max_pct"]
        if tier["min_pct"] <= exposure_pct and upper_ok:
            return tier

    return EXPOSURE_TIERS[-1] if exposure_pct < 0 else EXPOSURE_TIERS[0]


class ExposurePolicy:
    """Apply market exposure tier policies to portfolio state."""

    def __init__(self) -> None:
        pass

    def get_active_tier(self, eval_date: _date | None = None) -> dict[str, Any]:
        """Look up the most recent exposure score and return its policy tier.

        CRITICAL: Fails fast if exposure data unavailable. Market exposure tier
        determines entry constraints, exit rules, and risk adjustments. Trading
        without this data violates risk management.
        """
        if eval_date is None:
            eval_date = _date.today()

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT date, exposure_pct, regime, halt_reasons FROM market_exposure_daily
                       WHERE date <= %s ORDER BY date DESC LIMIT 1""",
                    (eval_date,),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"CRITICAL: No market exposure data available for {eval_date}. "
                        "Phase 4 must compute daily market exposure. Cannot apply entry/exit policies without it."
                    )
                exposure = float(row[1])
                tier = tier_for_exposure(exposure)
                return {
                    "as_of_date": row[0].isoformat(),
                    "exposure_pct": exposure,
                    "regime": row[2],
                    "halt_reasons": row[3],
                    "tier": tier,
                }
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def review_existing_positions(self, eval_date: _date | None = None) -> list[dict[str, Any]]:
        """Apply tier policy to all open positions.

        Returns list of recommended actions per position:
          { trade_id, symbol, action, reason, new_stop, exit_fraction }

        Actions are recommendations — orchestrator decides whether to execute.
        """
        active = self.get_active_tier(eval_date)
        if not active:
            raise RuntimeError(
                f"No active exposure policy tier for {eval_date} — cannot generate position recommendations"
            )

        tier = active["tier"]
        if eval_date is None:
            eval_date = _date.today()

        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                           t.target_1_price, t.target_2_price, t.target_3_price,
                           t.trade_date,
                           p.position_id, p.quantity, p.target_levels_hit,
                           p.current_stop_price, p.current_price,
                           p.unrealized_pnl_pct
                    FROM algo_positions p
                    CROSS JOIN LATERAL UNNEST(p.trade_ids_arr) AS tid(id)
                    JOIN algo_trades t ON t.trade_id = tid.id
                    WHERE t.status IN ('open','pending') AND p.status = 'open' AND p.quantity > 0
                    """)
                positions = cur.fetchall()
                actions = []
                for row in positions:
                    action = self._evaluate_position(row, tier)
                    if action and action["action"] != "hold":
                        actions.append(action)
                return actions
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Position review failed: {e}") from e

    def _evaluate_position(self, row: Any, tier: dict[str, Any]) -> dict[str, Any] | None:
        (
            trade_id,
            symbol,
            entry_price,
            init_stop,
            _t1_price,
            _t2_price,
            _t3_price,
            _trade_date,
            position_id,
            _qty,
            target_hits,
            cur_stop,
            cur_price,
            _pnl_pct,
        ) = row

        entry_price = float(entry_price)
        init_stop = float(init_stop)
        active_stop = float(cur_stop) if cur_stop else init_stop

        # CRITICAL: target_hits configuration must be present. Do not mask missing config with fallback to 0.
        if target_hits is None:
            raise ValueError(
                f"CRITICAL: {symbol} — target_hits is NULL in algo_trades. "
                f"Cannot evaluate exposure policy without target hit history. "
                f"Database schema or trade data corrupted. Cannot proceed with position evaluation."
            )
        target_hits = int(target_hits)

        # CRITICAL: Do NOT use entry_price as fallback for cur_price. This distorts risk evaluation.
        # cur_price must be valid; if missing, skip this position.
        if not cur_price:
            raise ValueError(
                f"CRITICAL: {symbol} — current_price is NULL in algo_positions. "
                f"Cannot evaluate exposure policy without live price. "
                f"Price data missing for open position. Cannot calculate current R-multiple or exit levels."
            )
        cur_price_float = float(cur_price)
        if cur_price_float <= 0:
            raise ValueError(
                f"CRITICAL: {symbol} — current_price={cur_price_float} <= 0. "
                f"Invalid price data in algo_positions. Cannot evaluate position risk. "
                f"Database integrity issue or price data corruption."
            )

        # R-multiple
        risk_per_share = entry_price - init_stop
        r_mult = ((cur_price_float - entry_price) / risk_per_share) if risk_per_share > 0 else 0

        # 1. CORRECTION TIER + force_exit_negative_r: cut losers
        if "force_exit_negative_r" not in tier:
            raise ValueError(
                f"Risk tier '{tier.get('name', 'UNKNOWN')}' missing required 'force_exit_negative_r' configuration. "
                "Cannot apply risk management without explicit force-exit policy."
            )
        force_exit_neg = tier["force_exit_negative_r"]
        if force_exit_neg and r_mult < 0:
            return {
                "trade_id": trade_id,
                "symbol": symbol,
                "position_id": position_id,
                "action": "force_exit",
                "reason": f"Tier '{tier['name']}': force-exit losers (R={r_mult:.2f})",
                "exit_fraction": 1.0,
                "new_stop": None,
                "r_multiple": r_mult,
                "tier": tier["name"],
            }

        # 2. force_partial_at_r: take partial profits when extended
        force_partial_threshold = tier.get("force_partial_at_r")
        if force_partial_threshold is not None and r_mult >= force_partial_threshold:
            # Only if not already hit a target at this level
            if target_hits < 2:  # haven't taken T2 yet
                return {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "position_id": position_id,
                    "action": "partial_exit",
                    "reason": (
                        f"Tier '{tier['name']}' force partial: R={r_mult:.2f} >= {force_partial_threshold}R threshold"
                    ),
                    "exit_fraction": 0.50,
                    "new_stop": max(active_stop, entry_price),  # raise to BE at minimum
                    "r_multiple": r_mult,
                    "tier": tier["name"],
                }

        # 3. tighten_winners_at_r: ratchet stop tighter on extended positions
        tighten_threshold = tier.get("tighten_winners_at_r")
        if tighten_threshold is not None and r_mult >= tighten_threshold:
            # Compute a tightened stop: midway between entry and current price
            # but never lower than current active stop
            tightened = entry_price + (cur_price - entry_price) * 0.50  # halfway
            tightened = max(active_stop, tightened)
            if tightened > active_stop * 1.005:  # only if meaningfully higher
                return {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "position_id": position_id,
                    "action": "tighten_stop",
                    "reason": (f"Tier '{tier['name']}' tighten: R={r_mult:.2f} >= {tighten_threshold}R, raise stop"),
                    "exit_fraction": 0.0,
                    "new_stop": round(tightened, 2),
                    "r_multiple": r_mult,
                    "tier": tier["name"],
                }

        return {"action": "hold", "symbol": symbol, "r_multiple": r_mult}

    def get_entry_constraints(self, eval_date: _date | None = None) -> dict[str, Any]:
        """Return current constraints for new entries.

        FAIL-FAST: When halt_new_entries=True, always includes halt_reason.
        Prevents silent missing reason if entries are halted.

        Raises:
            RuntimeError: If exposure data unavailable. Entry constraints are critical
            for position sizing policy — missing them violates risk management.
        """
        active = self.get_active_tier(eval_date)
        tier = active["tier"]

        # Build base constraints
        constraints = {
            "as_of_date": active["as_of_date"],
            "exposure_pct": active["exposure_pct"],
            "regime": active["regime"],
            "tier_name": tier["name"],
            "description": tier["description"],
            "risk_multiplier": tier["risk_multiplier"],
            "max_new_positions_today": tier["max_new_positions_today"],
            "min_swing_score": tier["min_swing_score"],
            "min_swing_grade": tier["min_swing_grade"],
            "halt_new_entries": tier["halt_new_entries"],
            "max_concentration_pct": tier["max_concentration_pct"],
        }

        # When halting entries, always include explicit reason
        if tier["halt_new_entries"]:
            constraints["halt_reason"] = (
                f"Market tier '{tier['name']}' halts new entries: {tier['description']} "
                f"(Exposure: {active['exposure_pct']}%)"
            )
        else:
            constraints["halt_reason"] = None

        return constraints


if __name__ == "__main__":
    p = ExposurePolicy()
    active = p.get_active_tier()
    logger.info("=" * 80)
    logger.info("MARKET EXPOSURE POLICY")
    logger.info("=" * 80)
    logger.info(f"\nAs of: {active['as_of_date']}")
    logger.info(f"Exposure: {active['exposure_pct']}%")
    logger.info(f"Regime:   {active['regime']}")
    if active.get("halt_reasons"):
        logger.info(f"HALT:     {active['halt_reasons']}")
    logger.info(
        f"\nActive Tier: {active['tier']['name']} ({active['tier']['min_pct']}-{active['tier']['max_pct']}%)"
    )
    logger.info(f"  {active['tier']['description']}")
    logger.info("\nEntry Constraints:")
    constraints = p.get_entry_constraints()
    for k, v in constraints.items():
        if k not in ("as_of_date", "tier_name", "description"):
            logger.info(f"  {k:30s} = {v}")

    actions = p.review_existing_positions()
    logger.info(f"\n\nPosition Review: {len(actions)} actions recommended")
    for a in actions:
        r_multiple = a.get("r_multiple")
        r_display = f"{r_multiple:+.2f}" if r_multiple is not None else "MISSING"
        logger.info(f"  {a['symbol']:6s} → {a['action'].upper():15s}  R={r_display}  {a['reason']}")
        if a.get("new_stop"):
            logger.info(f"            new_stop=${a['new_stop']:.2f}")

    logger.info("\n" + "=" * 80)
    logger.info("ALL TIER DEFINITIONS")
    logger.info("=" * 80)
    for tier in EXPOSURE_TIERS:
        logger.info(f"\n{tier['name'].upper():20s} {tier['min_pct']:>3}-{tier['max_pct']:>3}%")
        logger.info(f"  {tier['description']}")
        logger.info(
            f"  risk_mult={tier['risk_multiplier']}, max_new/day={tier['max_new_positions_today']}, "
            f"min_grade={tier['min_swing_grade']}"
        )
        if tier.get("tighten_winners_at_r"):
            logger.info(f"  tighten winners @ +{tier['tighten_winners_at_r']}R")
        if tier.get("force_partial_at_r"):
            logger.info(f"  force partial @ +{tier['force_partial_at_r']}R")
        if tier.get("halt_new_entries"):
            logger.info("  HALT NEW ENTRIES")
        if tier.get("force_exit_negative_r"):
            logger.info("  FORCE EXIT LOSERS")
