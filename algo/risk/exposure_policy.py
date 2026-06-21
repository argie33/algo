#!/usr/bin/env python3

import logging
import math
from datetime import date as _date
from typing import Any

import psycopg2

from utils.db import DatabaseContext
from utils.safe_data_conversion import safe_float, safe_int


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


def tier_for_exposure(exposure_pct):
    """Return the active policy tier for a given exposure %.

    Upper bounds are exclusive so exact boundary values (e.g. 70.0) land in the
    higher (more aggressive) tier, matching the >= thresholds in algo_market_exposure.py.
    NaN or None defaults to correction (fail-closed).
    """
    if exposure_pct is None or (isinstance(exposure_pct, float) and math.isnan(exposure_pct)):
        return EXPOSURE_TIERS[-1]

    for i, tier in enumerate(EXPOSURE_TIERS):
        is_last = i == len(EXPOSURE_TIERS) - 1
        upper_ok = exposure_pct <= tier["max_pct"] if is_last else exposure_pct < tier["max_pct"]
        if tier["min_pct"] <= exposure_pct and upper_ok:
            return tier

    return EXPOSURE_TIERS[-1] if exposure_pct < 0 else EXPOSURE_TIERS[0]


class ExposurePolicy:
    """Apply market exposure tier policies to portfolio state."""

    def __init__(self):
        pass

    def get_active_tier(self, eval_date=None) -> dict:
        """Look up the most recent exposure score and return its policy tier.

        Returns: dict with tier, exposure_pct, regime, halt_reasons

        Raises:
            RuntimeError: If no market exposure data available (fail-fast, no silent None)
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
                        f"No market exposure data available for {eval_date}. "
                        "Market regime and exposure policy cannot proceed without market_exposure_daily data. "
                        "Verify market_exposure_daily loader has run successfully."
                    )
                exposure = safe_float(row[1], default=0.0, context="row[1]")
                tier = tier_for_exposure(exposure)
                return {
                    "as_of_date": row[0].isoformat(),
                    "exposure_pct": exposure,
                    "regime": row[2],
                    "halt_reasons": row[3],
                    "tier": tier,
                }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def review_existing_positions(self, eval_date=None):
        """Apply tier policy to all open positions.

        Returns list of recommended actions per position:
          { trade_id, symbol, action, reason, new_stop, exit_fraction }

        Actions are recommendations — orchestrator decides whether to execute.
        """
        active = self.get_active_tier(eval_date)
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
                    if action and action["action"] not in ("hold", "skip"):
                        actions.append(action)
                return actions
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Position review failed: {e}") from e

    def _evaluate_position(self, row, tier) -> dict | None:
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

        entry_price = safe_float(entry_price, default=None, context="entry_price")
        init_stop = safe_float(init_stop, default=None, context="init_stop")
        if entry_price is None or init_stop is None:
            logger.warning(f"SKIP {symbol}: entry_price or init_stop missing/invalid. Cannot evaluate exposure policy.")
            return {
                "symbol": symbol,
                "position_id": row[8] if len(row) > 8 else None,
                "trade_id": row[0] if len(row) > 0 else None,
                "action": "skip",
                "reason": f"Missing critical price data (entry={entry_price}, stop={init_stop})",
            }
        active_stop = safe_float(cur_stop, default=init_stop, context="cur_stop") if cur_stop else init_stop

        # CRITICAL: target_hits configuration must be present. Do not mask missing config with fallback to 0.
        if target_hits is None:
            logger.warning(f"SKIP {symbol}: target_hits configuration missing (NULL). Cannot evaluate exposure policy.")
            return {
                "symbol": symbol,
                "position_id": position_id,
                "trade_id": trade_id,
                "action": "skip",
                "reason": "Missing target_hits configuration in algo_positions",
            }
        target_hits = safe_int(target_hits, default=0, context="target_hits")

        # CRITICAL: Do NOT use entry_price as fallback for cur_price. This distorts risk evaluation.
        # cur_price must be valid; if missing, skip this position.
        cur_price_float = safe_float(cur_price, default=None, context="cur_price")
        if cur_price_float is None or cur_price_float <= 0:
            logger.warning(f"SKIP {symbol}: No valid current price in algo_positions. Cannot evaluate exposure policy.")
            return {
                "symbol": symbol,
                "position_id": position_id,
                "trade_id": trade_id,
                "action": "skip",
                "reason": f"No valid current price ({cur_price})",
            }

        cur_price = cur_price_float

        # R-multiple
        risk_per_share = entry_price - init_stop
        r_mult = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0

        # 1. CORRECTION TIER + force_exit_negative_r: cut losers
        if tier.get("force_exit_negative_r") and r_mult < 0:
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
        if tier.get("force_partial_at_r") and r_mult >= tier["force_partial_at_r"]:
            # Only if not already hit a target at this level
            if target_hits < 2:  # haven't taken T2 yet
                return {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "position_id": position_id,
                    "action": "partial_exit",
                    "reason": (
                        f"Tier '{tier['name']}' force partial: R={r_mult:.2f} >= "
                        f"{tier['force_partial_at_r']}R threshold"
                    ),
                    "exit_fraction": 0.50,
                    "new_stop": max(active_stop, entry_price),  # raise to BE at minimum
                    "r_multiple": r_mult,
                    "tier": tier["name"],
                }

        # 3. tighten_winners_at_r: ratchet stop tighter on extended positions
        if tier.get("tighten_winners_at_r") and r_mult >= tier["tighten_winners_at_r"]:
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
                    "reason": (
                        f"Tier '{tier['name']}' tighten: R={r_mult:.2f} >= {tier['tighten_winners_at_r']}R, raise stop"
                    ),
                    "exit_fraction": 0.0,
                    "new_stop": round(tightened, 2),
                    "r_multiple": r_mult,
                    "tier": tier["name"],
                }

        return {"action": "hold", "symbol": symbol, "r_multiple": r_mult}

    def get_entry_constraints(self, eval_date=None):
        """Return current constraints for new entries."""
        active = self.get_active_tier(eval_date)
        if not active:
            return None
        tier = active["tier"]
        return {
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


if __name__ == "__main__":
    p = ExposurePolicy()
    active = p.get_active_tier()
    logger.info("=" * 80)
    logger.info("MARKET EXPOSURE POLICY")
    logger.info("=" * 80)
    if active:
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
    else:
        logger.info("\nNo market exposure data — run algo_market_exposure.py first")

    actions = p.review_existing_positions()
    logger.info(f"\n\nPosition Review: {len(actions)} actions recommended")
    for a in actions:
        logger.info(f"  {a['symbol']:6s} → {a['action'].upper():15s}  R={a.get('r_multiple', 0):+.2f}  {a['reason']}")
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
