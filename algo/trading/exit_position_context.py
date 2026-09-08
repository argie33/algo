"""PositionContext (per-position exit-check evaluation) for exit_engine.py, extracted from
algo/trading/exit_engine.py (2026-09-05, file-size ratchet: that file is a Tier-2 bloater
flagged for decomposition). Body is verbatim, no logic changed - only moved file. ExitEngine
(still in exit_engine.py) constructs and calls these check_* methods, each taking `engine:
ExitEngine` as an explicit parameter rather than depending on module state directly.

`DatabaseContext` is accessed via the exit_engine module object at call time (not imported by
name here) because several existing tests patch `algo.trading.exit_engine.DatabaseContext`
expecting that to affect check_climax_exhaustion's audit-log write - a plain import here would
silently stop seeing that patch. `algo.trading.exit_engine` itself imports this module at load
time, so the reference is resolved lazily (inside the method body, not at import time) to avoid
a circular-import failure. `ExitEngine` itself is only referenced in type hints (deferred via
`from __future__ import annotations`), imported under TYPE_CHECKING to avoid the same cycle.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.trading.exit_engine as _ee

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig
    from algo.trading.exit_engine import ExitEngine

logger = logging.getLogger(__name__)


class PositionContext:
    """Context for position exit evaluation with integrated check methods."""

    def __init__(
        self,
        symbol: str,
        current_date: _date,
        cur_price: Decimal,
        prev_close: Decimal | None,
        entry_price: Decimal,
        active_stop: Decimal,
        init_stop: Decimal,
        t1_price: Decimal | None,
        t2_price: Decimal | None,
        t3_price: Decimal | None,
        target_hits: int,
        days_held: int,
        dist_days_today: int | None,
        config: AlgoConfig | dict[str, Any],
        cur: PsycopgCursor[Any] | None = None,
        t1_hit_time: datetime | None = None,
        t2_hit_time: datetime | None = None,
        t3_hit_time: datetime | None = None,
        last_partial_exit_date: _date | None = None,
        partial_exits_log: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.current_date = current_date
        self.cur_price = cur_price
        self.prev_close = prev_close
        self.entry_price = entry_price
        self.active_stop = active_stop
        self.init_stop = init_stop
        if t1_price is None or t2_price is None or t3_price is None:
            missing = [f"T{i}" for i, p in enumerate([t1_price, t2_price, t3_price], 1) if p is None]
            raise ValueError(
                f"CRITICAL: {symbol} position loaded without target prices: {', '.join(missing)}. "
                "Cannot execute position without exit plan."
            )
        self.t1_price = t1_price
        self.t2_price = t2_price
        self.t3_price = t3_price
        self.target_hits = target_hits
        self.days_held = days_held
        self.dist_days_today = dist_days_today
        self.t1_hit_time = t1_hit_time
        self.t2_hit_time = t2_hit_time
        self.t3_hit_time = t3_hit_time
        self.last_partial_exit_date = last_partial_exit_date
        self.partial_exits_log = partial_exits_log
        self.config = config
        self.cur = cur
        self._validate_exit_config()

    def _validate_exit_config(self) -> None:
        """Validate critical exit rule config keys are present at initialization.

        Only validates fields that are actually used in this position's exit checks.
        Fail-fast on missing required config rather than during individual rule checks.
        """
        # Minimal required config - fields used by all exit checks
        required_config_keys = {
            "exit_on_rs_line_break_50dma": bool,
            "max_hold_days": int,
            "eight_week_rule_threshold_pct": float,
            "eight_week_rule_window_days": int,
        }

        missing_keys = []
        for key, expected_type in required_config_keys.items():
            if key not in self.config:
                missing_keys.append(f"'{key}' ({expected_type.__name__})")
            elif not isinstance(self.config[key], expected_type):
                actual_type = type(self.config[key]).__name__
                missing_keys.append(f"'{key}' has type {actual_type}, expected {expected_type.__name__}")

        if missing_keys:
            raise ValueError(
                f"[{self.symbol}] CRITICAL: Exit rule config incomplete. Missing: {', '.join(missing_keys)}. "
                f"Position cannot be monitored without complete exit parameters. "
                f"Check orchestrator config validation."
            )

    def check_minervini_break(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Minervini break: DISABLED (0% win rate in backtest 2026-08-05).

        This exit was disabled due to poor performance. Keeping method signature for
        backwards compatibility but always returns False (exit disabled).
        To re-enable: add exit_on_minervini_break=true to algo_config.
        """
        return False, None

    def check_rs_line_break(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """RS line break: relative strength deterioration vs SPY.

        TUNING FIX (2026-08-02): Only exit on RS line breaks if position is a LOSER.
        Winners were being exited when sector weakened, destroying profits.
        Now: RS line break only exits positions with R <= 0.5 (losers only).
        """
        if "exit_on_rs_line_break_50dma" not in self.config:
            raise ValueError(
                "CRITICAL: 'exit_on_rs_line_break_50dma' config missing. "
                "Cannot proceed with exit rules  - risk controls undefined."
            )
        if self.config["exit_on_rs_line_break_50dma"]:
            if engine._rs_line_breaking(self.cur, self.symbol, self.current_date):
                # TUNING FIX: Calculate current R-multiple to check if position is a loser
                # R = (current_price - entry_price) / (entry_price - stop_loss)
                # Only exit if R <= 0.5 (loser), never exit winners when sector weakens
                risk_per_share = self.entry_price - self.init_stop
                if risk_per_share <= 0:
                    logger.warning(f"[EXIT] {self.symbol}: RS line break check skipped - invalid risk_per_share")
                    return False, None

                current_r = (self.cur_price - self.entry_price) / risk_per_share
                if current_r <= 0.5:
                    # LOSER: Sector weakness + down money = exit cleanly
                    return (
                        True,
                        {
                            "stage": "stop",
                            "fraction": 1.0,
                            "reason": f"RS line broke below 50-DMA (loser: R={float(current_r):.2f})",
                        },
                    )
                else:
                    # WINNER: Sector weakness but position profitable - DO NOT EXIT
                    logger.debug(
                        f"[EXIT] {self.symbol}: RS line break ignored (winner: R={float(current_r):.2f}, "
                        f"price=${float(self.cur_price):.2f}, entry=${float(self.entry_price):.2f})"
                    )
                    return False, None
        return False, None

    def check_time_exit(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Time-based exit with O'Neil 8-week rule override.

        CRITICAL FIX SESSION 41: Time-based exits are discretionary (not capital preservation),
        so they respect min_hold_days gate. This prevents same-day time exits while still allowing
        hard stops, targets, and distribution exits that reduce exposure immediately.
        """
        min_hold_val = self.config.get("min_hold_days")
        if min_hold_val is None:
            raise ValueError("CRITICAL: min_hold_days config missing. Cannot enforce minimum holding period.")

        min_hold_days = int(min_hold_val)
        # CRITICAL FIX: Clamp negative days_held to 0 (data corruption safeguard)
        # Negative values block all exits - treat same-day entries as 0 days, not negative
        days_held_for_check = max(0, self.days_held)
        if days_held_for_check < min_hold_days:
            return False, None

        max_hold_val = self.config.get("max_hold_days")
        if max_hold_val is None:
            raise ValueError("CRITICAL: max_hold_days config missing. Cannot enforce maximum holding period.")

        max_hold = int(max_hold_val)
        if self.days_held >= max_hold:
            eight_wk_val = self.config.get("eight_week_rule_threshold_pct")
            if eight_wk_val is None:
                raise ValueError("CRITICAL: eight_week_rule_threshold_pct config missing.")

            eight_wk_threshold = float(eight_wk_val)
            eight_wk_window_val = self.config.get("eight_week_rule_window_days")
            if eight_wk_window_val is None:
                raise ValueError("CRITICAL: eight_week_rule_window_days config missing.")

            eight_wk_window = int(eight_wk_window_val)
            eight_wk_ext = engine._eight_week_rule_active(
                self.cur,
                self.symbol,
                self.current_date,
                float(self.entry_price),
                self.days_held,
                eight_wk_threshold,
                eight_wk_window,
            )

            if eight_wk_ext and self.days_held < 56:
                return False, None

            return (
                True,
                {
                    "stage": "time",
                    "fraction": 1.0,
                    "reason": f"TIME exit: {self.days_held} days >= {max_hold} max",
                },
            )
        return False, None

    def _was_target_hit_today(self, hit_time: datetime | None) -> bool:
        if hit_time is None:
            return False
        hit_date = hit_time.date() if isinstance(hit_time, datetime) else hit_time
        return hit_date == self.current_date

    def _was_distribution_reduced_today(self) -> bool:
        """Guard against check_distribution firing repeatedly on every exit-engine pass
        while dist_days_today stays above max_dd, which - unlike the T1/T2/T3 checks - has no
        per-day dedup of its own. Confirmed live 2026-07-27: 7 positions were each reduced by
        50% THREE separate times in the same single day (all three logged under the same
        last_partial_exit_date), compounding down to ~12.5% of their original size from one
        ongoing market condition instead of a single one-time de-risking action."""
        if self.last_partial_exit_date is None or self.partial_exits_log is None:
            return False
        last_exit_date = (
            self.last_partial_exit_date.date()
            if isinstance(self.last_partial_exit_date, datetime)
            else self.last_partial_exit_date
        )
        if last_exit_date != self.current_date:
            return False
        last_log_entry = self.partial_exits_log.rsplit("; ", 1)[-1]
        return "Market distribution" in last_log_entry

    def _target_r_label(self, config_key: str) -> str:
        """Format the configured R-multiple for a target-hit reason string.

        BUG FOUND 2026-08-25 (real-money-readiness goal session, config-sanity spot check):
        check_target_t1/t2/t3's reason strings used to hardcode "(1.5R)"/"(3R)"/"(4R)"
        literally, instead of reading the actual configured t1/t2/t3_target_r_multiple. Live-
        confirmed the drift already happened for real: algo_config.t1_target_r_multiple is
        currently 2.5 (not the 1.5 hardcoded in the old string and still documented as the
        schema default in config_schema.py/trading_config.py) - every real T1 exit today would
        have recorded "(1.5R)" in algo_trades.exit_reason while the actual price threshold used
        2.5R math, a permanent, wrong label in the audit trail. T2/T3 (3R/4R) happened to still
        match their current config values by coincidence, but were equally hardcoded and
        equally exposed to the same drift the moment either config value changes - this system
        already has regime-based R-multiple adjustment machinery (regime_manager.py multiplies
        the base value per market regime), so these values are not static by design. Falls back
        to "target" (no numeric claim) rather than raising - this is a display label on an
        exit that's already firing, not a risk gate; a missing/malformed config value here must
        not be the thing that crashes a real exit in progress.
        """
        r_mult = self.config.get(config_key)
        if r_mult is None:
            return "target"
        try:
            return f"{float(r_mult):g}R"
        except (TypeError, ValueError):
            return "target"

    def check_target_t1(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """T1 target exit (2026-08-25: R-multiple in the reason string is read live from
        config, not hardcoded - see _target_r_label): 50% position reduction.

        GATED OFF BY DEFAULT since 2026-09-07 (exit-strategy literature review + validation
        backtest, scripts/backtest_exit_strategy_comparison_20260907.py): trend-following
        literature (Covel, Faber-style momentum research) argues scaling out at fixed
        R-multiples lowers blended expectancy vs. a pure trail by capping the fat-tail winners
        a trend system's edge depends on. Validated against our own data, not just literature
        (the user's explicit bar for changing this): a paired backtest replaying the real
        price-technical BUY entry trigger (buy_signal_generator.py's swing-pivot breakout)
        across 2,885 symbols with 10+ years of price_daily history (471,972 paired trades,
        1962-2026) found the pure-trail design (chandelier + breakeven floor, no scale-out)
        beat this T1/T2/T3 chain on mean R-multiple (+0.096 vs +0.085), geometric per-trade
        growth (+0.088% vs +0.079% at 1% risk/trade), and tail capture (57.5% vs 52.7% of
        total profit from the top decile of trades) - paired mean-R difference -0.0114, 95%
        bootstrap CI [-0.0132, -0.0096], excludes zero. Gating T1 alone is sufficient for every
        NEW trade opened while this is off: check_target_t2/t3 require target_hits==1/2, which
        only a real T1 (then T2) fire ever sets, so with T1 gated off target_hits never leaves
        0 and T2/T3 go naturally inert - deliberately NOT gating T2/T3 themselves means a
        position that already recorded target_hits=1 BEFORE this was deployed (a real T1 sale
        under the old default) still completes T2/T3 normally instead of being stranded
        half-exited by the config change. Controlled by `use_scale_out_targets` (schema default True, matching every other
        exit-rule config's schema-default-vs-live-value split already in this file; live
        algo_config value False per this backtest - see the migration seeding it). Required
        config, no implicit default here (matches this whole file's fail-fast convention) -
        existing test fixtures were updated to set it explicitly True so their T1/T2/T3
        coverage keeps exercising the (still fully intact) scale-out machinery. Re-enable by
        setting use_scale_out_targets=true in algo_config if a future backtest finds the
        opposite on a larger/different sample - nothing here is deleted, just gated.
        """
        if "use_scale_out_targets" not in self.config:
            raise ValueError(
                "CRITICAL: 'use_scale_out_targets' config missing. "
                "Cannot proceed with target exits without explicit configuration."
            )
        if not bool(self.config["use_scale_out_targets"]):
            return False, None
        if self.target_hits == 0 and self.cur_price >= self.t1_price:
            if self._was_target_hit_today(self.t1_hit_time):
                return False, None
            if "require_target_pullback" not in self.config:
                raise ValueError(
                    "Exit engine config missing 'require_target_pullback' flag. "
                    "Cannot proceed with target exits without explicit configuration."
                )
            require_pb = bool(self.config["require_target_pullback"])
            if not require_pb or engine._is_pulling_back(self.cur, self.symbol, self.current_date):
                return (
                    True,
                    {
                        "stage": "target_1",
                        "fraction": 0.50,
                        "reason": f"T1 exit: ${float(self.cur_price):.2f} >= ${float(self.t1_price):.2f} ({self._target_r_label('t1_target_r_multiple')})",
                        "new_stop": float(max(self.active_stop, self.entry_price)),
                    },
                )
        return False, None

    def check_target_t2(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """T2 target exit (3R): 25% position reduction with stop raise to T1."""
        if self.target_hits == 1 and self.cur_price >= self.t2_price:
            if self._was_target_hit_today(self.t2_hit_time):
                return False, None
            if "require_target_pullback" not in self.config:
                raise ValueError(
                    "Exit engine config missing 'require_target_pullback' flag. "
                    "Cannot proceed with target exits without explicit configuration."
                )
            require_pb = bool(self.config["require_target_pullback"])
            if not require_pb or engine._is_pulling_back(self.cur, self.symbol, self.current_date):
                stop_for_t2 = max(self.active_stop, self.t1_price)
                return (
                    True,
                    {
                        "stage": "target_2",
                        "fraction": 0.50,
                        "reason": f"T2 exit: ${float(self.cur_price):.2f} >= ${float(self.t2_price):.2f} ({self._target_r_label('t2_target_r_multiple')})",
                        "new_stop": float(stop_for_t2),
                    },
                )
        return False, None

    def check_target_t3(self) -> tuple[bool, dict[str, Any] | None]:
        """T3 target exit (4R): final 25% position reduction."""
        if self.target_hits == 2 and self.cur_price >= self.t3_price:
            if not self._was_target_hit_today(self.t3_hit_time):
                return (
                    True,
                    {
                        "stage": "target_3",
                        "fraction": 1.0,
                        "reason": f"T3 target hit: ${float(self.cur_price):.2f} >= ${float(self.t3_price):.2f} ({self._target_r_label('t3_target_r_multiple')}) - FINAL EXIT",
                    },
                )
        return False, None

    def check_move_to_breakeven(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Raise stop to breakeven once price reaches move_be_at_r (config, default 1.0R).

        FIXED 2026-09-07 (real-money-readiness audit): move_be_at_r was required by
        ExitEngine._validate_config (fail-fast if missing) but never actually read anywhere -
        pure dead config. The only existing breakeven-raise logic was hardcoded to other
        strategies' own thresholds (T1's configured r_multiple, or a hardcoded 0.5R gate on
        TD Sequential/first-red-day/climax-exhaustion, all of which additionally require
        target_hits >= 1 or a specific technical pattern before ever running) - so a position
        that ran up past move_be_at_r's intended trigger with none of those conditions met kept
        its original (below-entry) stop the whole way back down. This closes that gap directly:
        independent check, no gating on target_hits or any other exit condition, fraction=0.0
        (stop-raise only, never forces an exit - see ExitStrategyChain.evaluate's docstring for
        why a fraction==0.0 signal doesn't short-circuit real exits from lower-priority checks).
        """
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        move_be_at_r = self.config.get("move_be_at_r")
        if move_be_at_r is None:
            raise ValueError("CRITICAL: move_be_at_r config missing.")

        if r_mult >= Decimal(str(move_be_at_r)) and self.active_stop < self.entry_price:
            return (
                True,
                {
                    "stage": "raise_stop_breakeven",
                    "fraction": 0.0,
                    "reason": f"Breakeven stop raise at {float(r_mult):.2f}R >= move_be_at_r={move_be_at_r}",
                    "new_stop": float(self.entry_price),
                },
            )
        return False, None

    def check_chandelier_trail(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Chandelier/EMA trailing stop: tightens stop after 1R profit."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        chandelier_enabled = self.config.get("use_chandelier_trail")
        if chandelier_enabled is None:
            raise ValueError("CRITICAL: use_chandelier_trail config missing.")

        if bool(chandelier_enabled) and r_mult >= Decimal(1):
            chand_stop = engine._chandelier_or_ema_stop(self.cur, self.symbol, self.current_date, self.days_held)
            if chand_stop and Decimal(str(chand_stop)) > self.active_stop:
                # BUG FOUND 2026-08-23 (goal session: real-money-readiness audit, same
                # technique that found position_monitor.py's parallel
                # _compute_trailing_stop() gap): both _chandelier_or_ema_stop() branches
                # derive the new stop from lagging EOD reference data (price_daily/
                # technical_data_daily's highest-high/ATR, or the 21-EMA of daily closes) -
                # neither is bounded by self.cur_price, a live intraday quote that can have
                # already gapped down well below what that stale reference data implies.
                # Unlike position_monitor.py's parallel "hard stop" implementation (which
                # has its own defensive `if proposed_stop > cur_price: clamp` right after
                # calling its equivalent function), NOTHING in this chain -
                # check_chandelier_trail -> execute_exit -> executor_exit_handler.py's
                # _raise_stop_only - ever compares the new stop against current price;
                # _raise_stop_only only checks it's higher than the EXISTING stop. An
                # above-market stop written to algo_positions.current_stop_price would
                # make the very next evaluation's `cur_price <= active_stop` check fire
                # immediately, force-exiting the position without any further adverse
                # price movement. Clamp here, at the same point position_monitor.py's
                # equivalent check lives, rather than deep in the DB-write layer.
                cur_price_dec = Decimal(str(self.cur_price))
                if Decimal(str(chand_stop)) >= cur_price_dec:
                    logger.error(
                        f"[EXIT_ENGINE] {self.symbol}: Chandelier/EMA stop ${chand_stop:.2f} >= "
                        f"current price ${self.cur_price:.2f} - clamping to just under market "
                        f"instead of writing an above-market stop."
                    )
                    chand_stop = float((cur_price_dec - Decimal("0.01")).quantize(Decimal("0.01"), ROUND_HALF_UP))
                return (
                    True,
                    {
                        "stage": "raise_stop_trail",
                        "fraction": 0.0,
                        "reason": f"Chandelier/EMA trail tightens stop to ${chand_stop:.2f}",
                        "new_stop": chand_stop,
                    },
                )
        return False, None

    def check_td_sequential(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """TD Sequential exhaustion: 9-count (50%) or 13-count (100%) exit."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        td_seq_enabled = self.config.get("exit_on_td_sequential")
        if td_seq_enabled is None:
            raise ValueError("CRITICAL: exit_on_td_sequential config missing.")

        if bool(td_seq_enabled) and self.target_hits >= 1:
            if r_mult >= Decimal("0.5"):
                td_state = engine._get_td_state(self.cur, self.symbol, self.current_date)
                # FAIL-FAST: Validate critical TD Sequential fields present before using
                required_fields = ["combo_13_complete", "completed_9", "setup_type"]
                missing = [f for f in required_fields if f not in td_state]
                if missing:
                    raise ValueError(
                        f"[TD_SEQUENTIAL] {self.symbol}: TD state missing critical fields {missing}. "
                        f"Cannot make exit decision without complete TD data. Available: {list(td_state.keys())}"
                    )
                if td_state["combo_13_complete"] and td_state["setup_type"] == "sell":
                    return (
                        True,
                        {
                            "stage": "td_combo_13",
                            "fraction": 1.0,
                            "reason": f"TD Combo 13-count exhaustion (FULL EXIT, R={float(r_mult):.2f})",
                        },
                    )
                if td_state["completed_9"] and td_state["setup_type"] == "sell":
                    return (
                        True,
                        {
                            "stage": "td_exhaustion",
                            "fraction": 0.50,
                            "reason": f"TD Sequential 9-count exhaustion (R={float(r_mult):.2f})",
                            "new_stop": float(max(self.active_stop, self.entry_price)),
                        },
                    )
        return False, None

    def check_first_red_day(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """First red day: institutional distribution after parabolic run."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        if r_mult >= Decimal("2.5") and self.prev_close is not None and self.prev_close > 0:
            down_pct = float(
                (
                    (Decimal(str(self.prev_close)) - Decimal(str(self.cur_price)))
                    / Decimal(str(self.prev_close))
                    * Decimal(100)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            if down_pct >= 1.5:
                vol_check = engine._check_volume_spike(self.cur, self.symbol, self.current_date, 1.5)
                if vol_check:
                    return (
                        True,
                        {
                            "stage": "first_red_day",
                            "fraction": 0.50,
                            "reason": f"First Red Day: down {down_pct:.2f}% on heavy volume (R={float(r_mult):.2f})",
                            "new_stop": float(max(self.active_stop, self.entry_price)),
                        },
                    )
        return False, None

    def check_climax_exhaustion(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Climax run exhaustion: parabolic move climax after 5R+ gain in 10d."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        if self.days_held > 30 and r_mult >= Decimal("5.0"):
            gain_10d = engine._compute_gain_last_n_days(self.cur, self.symbol, self.current_date, 10)
            if gain_10d is not None and gain_10d >= 20.0:
                return (
                    True,
                    {
                        "stage": "climax_exhaustion",
                        "fraction": 0.50,
                        "reason": f"Climax run exhaustion: gained {gain_10d:.1f}% in last 10d (R={float(r_mult):.2f})",
                        "new_stop": float(max(self.active_stop, self.entry_price)),
                    },
                )
        return False, None

    def check_distribution(self) -> tuple[bool, dict[str, Any] | None]:
        """Distribution day: market distribution day count exceeded."""
        dist_enabled = self.config.get("exit_on_distribution_day")
        if dist_enabled is None:
            raise ValueError("CRITICAL: exit_on_distribution_day config missing.")

        if bool(dist_enabled) and self.dist_days_today is not None:
            max_dd_val = self.config.get("max_distribution_days")
            if max_dd_val is None:
                raise ValueError("CRITICAL: max_distribution_days config missing.")

            max_dd = int(max_dd_val)
            if self.dist_days_today > max_dd and not self._was_distribution_reduced_today():
                # CRITICAL FIX: Prevent stop from being raised above current price for underwater positions
                # The bug (2026-07-27): check_distribution() raised stop to entry_price even for positions
                # below entry_price, guaranteeing stop-out on the next pass (underwater positions would exit
                # 50% AND immediately stop-out the remaining half, cascading into circuit breaker halt).
                # Distribution market conditions justify reducing exposure (50% exit), but we must ensure
                # the protective stop does NOT go above the current price (which would guarantee immediate stop-out).
                at_or_above_breakeven = self.cur_price >= self.entry_price
                if at_or_above_breakeven:
                    # Position is at or above breakeven - safe to raise stop to entry price to lock in gains
                    new_stop = max(self.active_stop, self.entry_price)
                    reason = f"Market distribution: {self.dist_days_today} dist days > {max_dd}  - reducing 50% of profitable position, stop raised to breakeven"
                else:
                    # Position is underwater - reduce exposure but keep stop at current level
                    # to avoid creating a guaranteed stop-out on the remaining half
                    new_stop = self.active_stop
                    reason = f"Market distribution: {self.dist_days_today} dist days > {max_dd}  - reducing 50% of position to manage market distribution risk (stop stays at {float(self.active_stop):.2f})"

                return (
                    True,
                    {
                        "stage": "distribution",
                        "fraction": 0.5,
                        "new_stop": new_stop,
                        "reason": reason,
                    },
                )
        return False, None


def _persist_exit_check_error(
    error_date: _date,
    trade_id: Any,
    position_id: Any,
    symbol: str,
    error_type: str,
    error_message: str,
) -> None:
    """Best-effort audit write for a failed exit check, on its own connection.

    2026-08-03: two live runs (LOCAL-AFTERNOON-...-100833, ...-101518) each recorded real
    trade_errors in orchestrator_execution_log with zero corresponding rows in
    algo_exit_check_errors for that date - the alert's "see algo_exit_check_errors for
    detail" pointer was a dead end. A same-day mitigation upgraded the failure-path
    logging to CRITICAL with pgcode/pgerror/diag/traceback, but the underlying INSERT
    still ran as a nested SAVEPOINT on the *same* connection/transaction that had just
    failed - direct DB reproduction that day ruled out a broken INSERT statement, a
    full-batch rollback, and a plain SERIALIZABLE conflict as causes, without finding the
    real one. Rather than keep guessing at what state the shared connection could be in,
    this now writes the audit row on a brand-new DatabaseContext connection, decoupling
    audit-trail durability from whatever happened to the main exit-check transaction -
    whatever the original failure mode was, it cannot also break an unrelated connection.
    """
    try:
        with _ee.DatabaseContext("write") as audit_cur:  # type: ignore[attr-defined]
            audit_cur.execute(
                """INSERT INTO algo_exit_check_errors
                   (error_date, trade_id, position_id, symbol, error_type, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (error_date, trade_id, position_id, symbol, error_type, error_message[:2000]),
            )
    except Exception as audit_err:
        diag_detail = ""
        if isinstance(audit_err, psycopg2.Error):
            diag_detail = (
                f" pgcode={getattr(audit_err, 'pgcode', None)} "
                f"pgerror={getattr(audit_err, 'pgerror', None)} "
                f"diag={getattr(getattr(audit_err, 'diag', None), 'message_detail', None)}"
            )
        logger.critical(
            f"[AUDIT] Failed to persist exit-check error for {symbol} (trade {trade_id}, "
            f"error_type={error_type}) to algo_exit_check_errors on an isolated connection: "
            f"{type(audit_err).__name__}: {audit_err}.{diag_detail} "
            f"algo_exit_check_errors will NOT have a row for this failure. "
            f"Original error: {error_message}",
            exc_info=audit_err,
        )
