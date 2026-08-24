#!/usr/bin/env python3

import logging
import math
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

import psycopg2

from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


@dataclass
class ExposurePolicyConstraints:
    """Type-safe constraints for Phase 5→8 handoff.

    All constraints required and validated before trading.
    Static type checking catches missing/wrong fields at commit time, not runtime.
    """

    halt_new_entries: bool
    max_new_positions_today: int
    max_concentration_pct: float
    regime: Literal["confirmed_uptrend", "uptrend_under_pressure", "caution", "correction"]
    tier_name: str
    description: str
    risk_multiplier: float
    min_composite_score: float
    as_of_date: str
    exposure_pct: float
    halt_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """For backwards compatibility with code expecting dict."""
        result = {
            "halt_new_entries": self.halt_new_entries,
            "max_new_positions_today": self.max_new_positions_today,
            "max_concentration_pct": self.max_concentration_pct,
            "regime": self.regime,
            "tier_name": self.tier_name,
            "description": self.description,
            "risk_multiplier": self.risk_multiplier,
            "min_composite_score": self.min_composite_score,
            "as_of_date": self.as_of_date,
            "exposure_pct": self.exposure_pct,
            "halt_reason": self.halt_reason,
        }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExposurePolicyConstraints":
        """Create from dict for temporary compatibility during migration."""
        return cls(
            halt_new_entries=data["halt_new_entries"],
            max_new_positions_today=data["max_new_positions_today"],
            max_concentration_pct=data["max_concentration_pct"],
            regime=data["regime"],
            tier_name=data["tier_name"],
            description=data["description"],
            risk_multiplier=data["risk_multiplier"],
            min_composite_score=data["min_composite_score"],
            as_of_date=data["as_of_date"],
            exposure_pct=data["exposure_pct"],
            halt_reason=data.get("halt_reason"),
        )


# Four tiers aligned with RegimeManager vocabulary so both systems speak the same language.
# Ranges mirror the regime thresholds in algo_market_exposure.py:
#   confirmed_uptrend    >= 70%
#   uptrend_under_pressure 45-70%
#   caution              25-45%
#   correction           < 25%
#
# Upper bounds are exclusive (except the top tier) - no boundary overlap.
#
# REDESIGNED 2026-08-24 (user-directed): tighten_winners_at_r/force_partial_at_r/
# force_exit_negative_r are permanently None/False/False across every tier now - exposure
# is a lever on future buying (halt_new_entries, max_new_positions_today,
# max_concentration_pct at entry, plus position_sizer.py's continuous exposure_pct/100
# sizing multiplier), never a reason to trim or exit a position already held. An existing
# position's own stop-loss/exit logic (exit_engine.py's 11-step hierarchy - initial/trailed
# stop, Minervini trend break, time exit, T1/T2/T3 targets, chandelier trail, TD Sequential
# exhaustion, first-red-day, climax exhaustion, and market-distribution-day count) is what
# decides whether THAT position gets sold, independent of the broad market's exposure
# score - a stock's own price/volume action can stay bullish while the market-wide exposure
# score drops (or vice versa), and forcing an exit on a good position because a portfolio-
# level dial moved was exactly the bug: correction tier's force_exit_negative_r used to
# force-exit ANY red position the moment exposure crossed below 25%, and
# uptrend_under_pressure/caution's tighten_winners_at_r/force_partial_at_r used to ratchet
# stops and take partial profits off winners on the same exposure-score trigger - both
# regardless of what that specific position's own stop/target/trend-break logic said. This
# was live-confirmed as the actual behavior (Phase 5 generated these actions every run,
# Phase 6 executed them as real force_exit/partial_exit/tighten_stop orders), not merely a
# theoretical risk. The 4 tiers below still differ on entry-side risk (fewer/no new
# positions, smaller ones, tighter concentration caps) as market conditions worsen - that
# part of "exposure = lever" is unchanged and correct. Sector-concentration rebalancing
# (phase6_exit_execution.py's separate _check_sector_concentration(), a diversification
# control, not an exposure-score one) is untouched by this change - it generates its own
# force_exit actions independently of this class.
#
# TUNING (2026-08-24, user-directed - "buy the best stocks, don't load up on shitty stocks",
# floor of 60 minimum, tighten further above that): min_composite_score raised 50/60/70/80 ->
# 60/65/70/75 (a first pass at +2/tier was rejected by the user as too timid and replaced with
# this).
#
# RE-APPLIED (2026-08-24, same day, real-money-readiness /goal session): this exact change
# had already landed once earlier the same day but was found reverted back to 50/60/70/80 in
# both the working tree and git history - EXPOSURE_TIERS has no database backing (unlike
# phase7_min_composite_score below, which survived only because migration 1224's DB row
# protected it), so a concurrent session's edit/race silently dropped it with nothing to
# catch the loss. Landed a THIRD time (found reverted again mid-session by a new regression
# test written specifically to catch this - see
# tests/unit/test_exposure_tiers_min_composite_score_values_20260824.py) via an isolated git
# worktree to avoid the same race a fourth time.
#
# Basis: composite_score itself has no historical per-trade record (stock_scores is
# overwritten every run; stock_scores_history, migration 1221, only started 2026-08-24), so it
# can't be backtested directly yet. As a proxy, rs_percentile - a real input to composite_score's
# momentum pillar (loaders/load_stock_scores.py) - DOES have history via algo_trades, and shows
# a real, monotonic relationship between score and outcome across the 96 closed trades on
# record: top-quintile RS entries (80-99.6) average +0.47% P&L / 44.9% win rate (n=69) vs. the
# 40-59 RS band at -0.48 to -0.70% / 25-29% win rate (n=11). Small sample and a proxy metric,
# not composite_score itself - re-validate against real composite_score-at-entry once
# stock_scores_history has enough days accumulated.
#
# Thresholds anchored to the live composite_score distribution (local `stocks` DB, 2026-08-24
# universe snapshot, n=5122, max ever observed=75.08): 60~=p90 (471/5122 qualify), 65~=p99
# (95/5122), 70~=top 12/5122, 75 = the current all-time max (1/5122) - deliberately at the edge
# of reachable, not beyond it. A uniform +10 shift (60/70/80/90) was considered and rejected:
# composite_score is a 6-factor weighted blend (quality/growth/value/positioning/stability/
# momentum, load_stock_scores.py) that empirically never exceeds ~75, so 80 and 90 would be
# permanently unreachable by any stock - that would silently make the caution and correction
# tiers behave identically to a permanent halt without saying so, which is different from "more
# selective." caution (70) and correction (75, moot regardless since halt_new_entries=True
# already blocks it) both land at genuinely rare-but-reachable levels instead.
EXPOSURE_TIERS: list[dict[str, Any]] = [
    {
        "name": "confirmed_uptrend",
        "min_pct": 70,
        "max_pct": 100,
        "description": "Confirmed bull market - full deployment",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 4,
        "min_composite_score": 60.0,
        "tighten_winners_at_r": None,
        "force_partial_at_r": None,
        "halt_new_entries": False,
        "force_exit_negative_r": False,
        "max_concentration_pct": 28.0,  # TUNING FIX (2026-08-02): Raised from 20% to 28%. Was forcing exits at winners. -2.43% avg return on forced exits.
        "color": "green",
    },
    {
        "name": "uptrend_under_pressure",
        "min_pct": 45,
        "max_pct": 70,
        "description": "Uptrend intact but weakening - reduced position size",
        "risk_multiplier": 0.65,
        "max_new_positions_today": 3,
        "min_composite_score": 65.0,
        "tighten_winners_at_r": None,
        "force_partial_at_r": None,
        "halt_new_entries": False,
        "force_exit_negative_r": False,
        "max_concentration_pct": 22.0,  # TUNING FIX (2026-08-02): Raised from 16% to 22%. Better scaling for winners under market pressure.
        "color": "yellow",
    },
    {
        "name": "caution",
        "min_pct": 25,
        "max_pct": 45,
        "description": "Market under significant stress - reduced position size",
        "risk_multiplier": 0.35,
        "max_new_positions_today": 2,
        "min_composite_score": 70.0,
        "tighten_winners_at_r": None,
        "force_partial_at_r": None,
        "halt_new_entries": False,
        "force_exit_negative_r": False,
        "max_concentration_pct": 12.0,
        "color": "orange",
    },
    {
        "name": "correction",
        "min_pct": 0,
        "max_pct": 25,
        "description": "Market correction - preserve capital, no new entries",
        "risk_multiplier": 0.0,
        "max_new_positions_today": 0,
        "min_composite_score": 75.0,
        "tighten_winners_at_r": None,
        "force_partial_at_r": None,
        "halt_new_entries": True,
        "force_exit_negative_r": False,
        "max_concentration_pct": 10.0,
        "color": "red",
    },
]


def tier_for_exposure(exposure_pct: float | None) -> dict[str, Any]:
    """Return the active policy tier for a given exposure %.

    Upper bounds are exclusive so exact boundary values (e.g. 70.0) land in the
    higher (more aggressive) tier, matching the >= thresholds in algo_market_exposure.py.
    CRITICAL: Fails fast (raises) if exposure_pct is None or NaN - never silently defaults.
    Missing market exposure indicates Phase 4 failure; trading must halt to prevent stale data usage.
    """
    # BUG FOUND 2026-08-11 (via fuzzing with pathological inputs): this NaN guard only
    # checked isinstance(exposure_pct, float) - a Decimal("NaN") (real column type is
    # `double precision`/float today, per market_exposure_daily's schema, so not currently
    # reachable from either live call site, but exposure_pct's own type hint is `float |
    # None` with nothing enforcing that at runtime) would skip this guard entirely and then
    # blow up with a raw, undiagnosed decimal.InvalidOperation deep in the tier-matching
    # comparisons below - Decimal NaN comparisons raise, unlike float NaN which just
    # returns False (same distinction already documented in position_sizer.py's
    # calculate_position_size). Widened to catch both, so a future caller that passes a
    # Decimal still gets this function's own clean, diagnostic RuntimeError.
    is_nan = (isinstance(exposure_pct, float) and math.isnan(exposure_pct)) or (
        isinstance(exposure_pct, Decimal) and exposure_pct.is_nan()
    )
    if exposure_pct is None or is_nan:
        msg = (
            f"[EXPOSURE POLICY CRITICAL] Market exposure percentage is missing or invalid ({exposure_pct}). "
            f"Phase 4 market exposure calculation must succeed for position sizing. "
            f"Cannot proceed with trading when risk tier cannot be determined. "
            f"Check: (1) Is Phase 4 market exposure loader running? (2) Does market_exposure_daily have today's data? "
            f"(3) Is Phase 4 computation returning valid values?"
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    # The inclusive upper bound must belong to whichever tier holds the true ceiling
    # (max_pct == 100, confirmed_uptrend) - not whichever tier happens to be LAST in this
    # list. EXPOSURE_TIERS is ordered highest-to-lowest, so "last iterated" was actually
    # `correction` (max_pct=25), leaving confirmed_uptrend's max_pct=100 exclusive. Since
    # exposure_pct=100.0 is reachable (all factors maxed, no vetoes), that crashed tier
    # lookup - and therefore position sizing/entry checks - on exactly the most bullish,
    # fully-valid reading instead of the intended out-of-range/corrupted-data case.
    ceiling = max(tier["max_pct"] for tier in EXPOSURE_TIERS)
    for tier in EXPOSURE_TIERS:
        is_ceiling_tier = tier["max_pct"] == ceiling
        upper_ok = exposure_pct <= tier["max_pct"] if is_ceiling_tier else exposure_pct < tier["max_pct"]
        if tier["min_pct"] <= exposure_pct and upper_ok:
            return tier

    # If no tier matched, the exposure_pct is outside the defined range. This indicates either
    # a bug in tier definitions (gaps) or data corruption (exposure_pct > 100% or < 0%).
    # Never silently fallback-raise error to surface the problem.
    tier_ranges = [f"{t['min_pct']}-{t['max_pct']}%" for t in EXPOSURE_TIERS]
    msg = (
        f"[EXPOSURE POLICY] Exposure percentage {exposure_pct:.1f}% does not match any tier. "
        f"Defined tier ranges: {', '.join(tier_ranges)}. "
        f"Cannot apply policy to unknown exposure level. Check exposure calculation logic."
    )
    logger.critical(msg)
    raise RuntimeError(msg)


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
            # Eastern Time, not system-local date.today() - eval_date drives an exact
            # date-boundary query (WHERE date <= %s ORDER BY date DESC) below. The only
            # production caller (phase5_exposure_policy.py) always passes run_date
            # explicitly, so this default isn't live-reachable today, but fixed defensively
            # to match every other eval_date default in this codebase (2026-07-21 audit).
            eval_date = datetime.now(EASTERN_TZ).date()

        try:
            with DatabaseContext("read") as cur:
                # GOVERNANCE: Check data_unavailable flag before using market exposure data
                # If marked unavailable, caller must not proceed with position management
                cur.execute(
                    """SELECT date, exposure_pct, regime, halt_reasons, data_unavailable, reason
                       FROM market_exposure_daily
                       WHERE date <= %s ORDER BY date DESC LIMIT 1""",
                    (eval_date,),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"CRITICAL: No market exposure data available for {eval_date}. "
                        "Phase 4 must compute daily market exposure. Cannot apply entry/exit policies without it."
                    )
                # GOVERNANCE ENFORCEMENT: Fail-fast if data marked unavailable
                date_val, exposure_pct, regime, halt_reasons, data_unavailable, reason = row
                if data_unavailable:
                    raise RuntimeError(
                        f"CRITICAL: Market exposure data marked unavailable for {date_val}: {reason or 'no reason provided'}. "
                        "Cannot apply position policies without valid market exposure assessment."
                    )
                exposure = float(exposure_pct)
                tier = tier_for_exposure(exposure)
                return {
                    "as_of_date": date_val.isoformat(),
                    "exposure_pct": exposure,
                    "regime": regime,
                    "halt_reasons": halt_reasons,
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

        REDESIGNED 2026-08-24: every tier's tighten_winners_at_r/force_partial_at_r/
        force_exit_negative_r is now None/False/False (see EXPOSURE_TIERS), so
        _evaluate_position() always returns {"action": "hold", ...} and this always
        returns []. Kept (not deleted) as the real, tested seam Phase 5/6 call through -
        exposure tier should only ever gate NEW entries, never trim/exit a position
        already held (that's exit_engine.py's job, independent of the market-wide
        exposure score) - so if a future tier config ever re-adds a non-None/True value
        here, this method's existing plumbing and Phase 6 execution path are still
        correct and ready to use, without reintroducing the removed exposure-driven
        selling as new code.

        Actions are recommendations - orchestrator decides whether to execute.
        """
        active = self.get_active_tier(eval_date)
        if not active:
            raise RuntimeError(
                f"No active exposure policy tier for {eval_date} - cannot generate position recommendations"
            )

        tier = active["tier"]
        if eval_date is None:
            eval_date = datetime.now(EASTERN_TZ).date()

        try:
            # CRITICAL FIX: `t.status IN ('open','pending')` never matches a live
            # (execution_mode=auto) filled order, which writes status='filled'/'partially_filled'
            # literally (see algo/trading/exit_engine.py's identical fix and executor_entry_handler.py).
            # Without this, exposure-tier stop-tightening/partial-exit/force-exit recommendations
            # would never be generated for real live positions.
            open_statuses = TradeStatus.all_open()
            status_placeholders = ", ".join(["%s"] * len(open_statuses))
            with DatabaseContext("read") as cur:
                cur.execute(
                    f"""
                    SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                           t.target_1_price, t.target_2_price, t.target_3_price,
                           t.trade_date,
                           p.id, p.quantity, p.target_levels_hit,
                           p.current_stop_price, p.current_price,
                           p.unrealized_pnl_pct
                    FROM algo_positions p
                    CROSS JOIN LATERAL UNNEST(p.trade_ids_arr) AS tid(id)
                    JOIN algo_trades t ON t.trade_id::text = tid.id::text
                    WHERE t.status IN ({status_placeholders}) AND p.status = 'open' AND p.quantity > 0
                    """,
                    tuple(open_statuses),
                )
                positions = cur.fetchall()
                actions = []
                for row in positions:
                    try:
                        action = self._evaluate_position(row, tier)
                    except ValueError as e:
                        # One position with corrupted/invalid trade data must not block
                        # stop-tightening, partial-exits, or force-exits for the rest of
                        # the open book. Log loudly and continue.
                        logger.error(f"[EXPOSURE_POLICY] Skipping position, evaluation failed: {e}")
                        continue
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
        if not cur_stop:
            raise ValueError(
                f"CRITICAL: {symbol} - current_stop_price is NULL in algo_trades. "
                f"Cannot evaluate exposure policy without live stop loss. "
                f"Position tracking or database integrity compromised."
            )
        active_stop = float(cur_stop)

        # CRITICAL: target_hits configuration must be present. Do not mask missing config with fallback to 0.
        if target_hits is None:
            raise ValueError(
                f"CRITICAL: {symbol} - target_hits is NULL in algo_trades. "
                f"Cannot evaluate exposure policy without target hit history. "
                f"Database schema or trade data corrupted. Cannot proceed with position evaluation."
            )
        target_hits = int(target_hits)

        # CRITICAL: Do NOT use entry_price as fallback for cur_price. This distorts risk evaluation.
        # cur_price must be valid; if missing, skip this position.
        if not cur_price:
            raise ValueError(
                f"CRITICAL: {symbol} - current_price is NULL in algo_positions. "
                f"Cannot evaluate exposure policy without live price. "
                f"Price data missing for open position. Cannot calculate current R-multiple or exit levels."
            )
        cur_price_float = float(cur_price)
        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<= 0` never catches NaN - gates
        # force_exit_negative_r and other tier-based risk decisions for a real open position.
        if math.isnan(cur_price_float) or math.isinf(cur_price_float) or cur_price_float <= 0:
            raise ValueError(
                f"CRITICAL: {symbol} - current_price={cur_price_float} <= 0. "
                f"Invalid price data in algo_positions. Cannot evaluate position risk. "
                f"Database integrity issue or price data corruption."
            )

        # R-multiple
        risk_per_share = entry_price - init_stop
        if math.isnan(risk_per_share) or math.isinf(risk_per_share) or risk_per_share <= 0:
            raise ValueError(
                f"CRITICAL: {symbol} - invalid risk/reward setup: entry={entry_price}, stop={init_stop} "
                f"(stop >= entry). Cannot evaluate exposure policy with corrupted stop loss data."
            )
        r_mult = (cur_price_float - entry_price) / risk_per_share

        # 1. CORRECTION TIER + force_exit_negative_r: cut losers
        if "force_exit_negative_r" not in tier:
            raise ValueError(
                f"Risk tier '{tier['name']}' missing required 'force_exit_negative_r' configuration. "
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
            tightened = entry_price + (cur_price_float - entry_price) * 0.50  # halfway
            tightened = max(active_stop, tightened)
            if tightened > active_stop * 1.005:  # only if meaningfully higher
                return {
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "position_id": position_id,
                    "action": "tighten_stop",
                    "reason": (f"Tier '{tier['name']}' tighten: R={r_mult:.2f} >= {tighten_threshold}R, raise stop"),
                    "exit_fraction": 0.0,
                    # Decimal.quantize(ROUND_HALF_UP), not round() - same binary-float
                    # representation trap fixed 2026-07-21 in order_manager.py's price
                    # rounding (round(2.675, 2) == 2.67 due to 2.675 not being exactly
                    # representable). new_stop feeds phase6_exit_execution.py's stop-price
                    # update, the same "price value on its way to changing what the system
                    # actually does with a position" category as the order-submission fix.
                    "new_stop": float(Decimal(str(tightened)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "r_multiple": r_mult,
                    "tier": tier["name"],
                }

        return {"action": "hold", "symbol": symbol, "r_multiple": r_mult}

    def get_entry_constraints(self, eval_date: _date | None = None) -> ExposurePolicyConstraints:
        """Return current constraints for new entries.

        FAIL-FAST: When halt_new_entries=True, always includes halt_reason.
        Prevents silent missing reason if entries are halted.

        Returns:
            ExposurePolicyConstraints: Type-safe constraint dataclass with all required fields.

        Raises:
            RuntimeError: If exposure data unavailable. Entry constraints are critical
            for position sizing policy - missing them violates risk management.
        """
        active = self.get_active_tier(eval_date)
        tier = active["tier"]

        # When halting entries, always include explicit reason
        halt_reason = None
        if tier["halt_new_entries"]:
            halt_reason = (
                f"Market tier '{tier['name']}' halts new entries: {tier['description']} "
                f"(Exposure: {active['exposure_pct']}%)"
            )

        return ExposurePolicyConstraints(
            halt_new_entries=tier["halt_new_entries"],
            max_new_positions_today=tier["max_new_positions_today"],
            max_concentration_pct=tier["max_concentration_pct"],
            regime=active["regime"],
            tier_name=tier["name"],
            description=tier["description"],
            risk_multiplier=tier["risk_multiplier"],
            min_composite_score=tier["min_composite_score"],
            as_of_date=active["as_of_date"],
            exposure_pct=active["exposure_pct"],
            halt_reason=halt_reason,
        )


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
    logger.info(f"\nActive Tier: {active['tier']['name']} ({active['tier']['min_pct']}-{active['tier']['max_pct']}%)")
    logger.info(f"  {active['tier']['description']}")
    logger.info("\nEntry Constraints:")
    constraints = p.get_entry_constraints()
    for k, v in constraints.to_dict().items():
        if k not in ("as_of_date", "tier_name", "description"):
            logger.info(f"  {k:30s} = {v}")

    actions = p.review_existing_positions()
    logger.info(f"\n\nPosition Review: {len(actions)} actions recommended")
    for a in actions:
        r_multiple = a.get("r_multiple")
        r_display = f"{r_multiple:+.2f}" if r_multiple is not None else "MISSING"
        logger.info(f"  {a['symbol']:6s} -> {a['action'].upper():15s}  R={r_display}  {a['reason']}")
        new_stop = a.get("new_stop")
        if new_stop is not None:
            logger.info(f"            new_stop=${new_stop:.2f}")

    logger.info("\n" + "=" * 80)
    logger.info("ALL TIER DEFINITIONS")
    logger.info("=" * 80)
    for tier in EXPOSURE_TIERS:
        logger.info(f"\n{tier['name'].upper():20s} {tier['min_pct']:>3}-{tier['max_pct']:>3}%")
        logger.info(f"  {tier['description']}")
        logger.info(
            f"  risk_mult={tier['risk_multiplier']}, max_new/day={tier['max_new_positions_today']}, "
            f"min_composite={tier['min_composite_score']}"
        )
        tighten_r = tier.get("tighten_winners_at_r")
        if tighten_r is not None:
            logger.info(f"  tighten winners @ +{tighten_r}R")
        force_partial_r = tier.get("force_partial_at_r")
        if force_partial_r is not None:
            logger.info(f"  force partial @ +{force_partial_r}R")
        if tier.get("halt_new_entries"):
            logger.info("  HALT NEW ENTRIES")
        if tier.get("force_exit_negative_r"):
            logger.info("  FORCE EXIT LOSERS")
