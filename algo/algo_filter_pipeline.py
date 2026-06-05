#!/usr/bin/env python3

import os
import traceback
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Any, Optional, Tuple

from utils.database_context import DatabaseContext

from algo.algo_config import get_config
from algo.algo_advanced_filters import AdvancedFilters
from utils.filter_rejection_tracker import RejectionTracker
from algo.algo_earnings_blackout import EarningsBlackout
from algo.algo_trendline_support import TrendlineSupport
from utils.trade_status import PositionStatus
from utils.feature_flags import get_flags
from algo.filters.filter_tiers_1_2 import FilterTiers12Mixin
from algo.filters.filter_tier3_trend import FilterTier3Mixin
from algo.filters.filter_tiers_4_5 import FilterTiers45Mixin
import logging

logger = logging.getLogger(__name__)

class FilterPipeline(FilterTiers12Mixin, FilterTier3Mixin, FilterTiers45Mixin):
    """5-tier filtering and signal evaluation."""

    def __init__(self, exposure_risk_multiplier=1.0):
        self.config = get_config()
        self.exposure_risk_multiplier = exposure_risk_multiplier  # From exposure policy tier
        self._market_health_cache = None
        self._market_health_date = None
        self._portfolio_state_cache = None
        self._sector_cache = {}
        self._candidate_holdings = {}  # symbols that passed T5 in this run, for sector counting
        self.advanced = None  # AdvancedFilters instance, lazy-init
        self._snapshot_eval_date = None  # Immutable snapshot of eval_date for this run
        self._last_stop_method = None
        self._last_stop_reasoning = None

    def _with_cursor(self, operation):
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext('write') as cur:
                return operation(cur)
        except Exception as e:
            logger.error(f"FilterPipeline._with_cursor: operation failed: {e}\n{traceback.format_exc()}")
            return None

    def _apply_tier_multiplier(self, base_size: float, tier: str) -> float:
        """Apply exposure tier multiplier to position size.

        Multipliers based on market exposure tier:
        - NORMAL: 1.0x (full position size)
        - CAUTION: 0.75x (75% position size, reduced risk)
        - PRESSURE: 0.5x (50% position size, minimum size)

        Args:
            base_size: Base position size in dollars
            tier: Exposure tier ('NORMAL', 'CAUTION', 'PRESSURE')

        Returns:
            Adjusted position size after applying tier multiplier
        """
        multipliers = {
            'NORMAL': 1.0,
            'CAUTION': 0.75,
            'PRESSURE': 0.5,
            'HALT': 0.0,  # No trading allowed
        }

        multiplier = multipliers.get(tier, 1.0)  # Default to NORMAL if unknown
        adjusted_size = base_size * multiplier

        logger.debug(f"Tier multiplier: {tier} ({multiplier}x) -> ${base_size:.0f} → ${adjusted_size:.0f}")
        return adjusted_size

    def evaluate_signals(self, eval_date=None, max_date: Optional[_date] = None) -> List[Dict[str, Any]]:
        """Evaluate all buy signals through filter pipeline.

        If eval_date is None, uses the most recent date <= max_date in buy_sell_daily
        that has both market_health_daily Stage 2 confirmation and trend_template coverage.
        Pass max_date=run_date to avoid evaluating signals from future dates.
        """
        def _evaluate_with_cursor(cur):
            return self._evaluate_signals_impl(eval_date, cur, max_date=max_date)

        try:
            return self._with_cursor(_evaluate_with_cursor) or []
        except Exception as e:
            logger.error(f"ERROR in evaluate_signals: {e}")
            traceback.print_exc()
            return []

    def _evaluate_signals_impl(self, eval_date=None, cur=None, max_date: Optional[_date] = None) -> List[Dict[str, Any]]:
        """Internal implementation of signal evaluation."""
        # Statement timeout: prevents Phase 5 from hanging indefinitely when RDS is under load
        # (e.g., concurrent EOD pipeline ECS loaders exhausting the RDS Proxy connection pool).
        # 45s per statement gives enough time for complex EXISTS queries while fail-opening fast.
        try:
            cur.execute("SET statement_timeout = 45000")
        except Exception:
            pass

        if not eval_date:
            # Run in a SEPARATE connection: if the EXISTS subqueries time out, only
            # this lookup fails (not the outer Phase 5 cursor holding all 1472 signals).
            try:
                with DatabaseContext('read') as _res_cur:
                    _res_cur.execute("SET statement_timeout = 10000")  # 10s max
                    eval_date = self._resolve_evaluation_date(_res_cur, max_date=max_date)
            except Exception:
                eval_date = max_date or _date.today()

            # Snapshot eval_date immutably for this run (prevents sector rotation mid-evaluation)
            self._snapshot_eval_date = eval_date

            # Reset candidate holdings to prevent sector counts from prior runs bleeding through
            self._candidate_holdings = {}

            logger.info(f"\n{'='*70}")
            logger.info(f"FILTER PIPELINE EVALUATION - {eval_date}")
            logger.info(f"{'='*70}\n")

            # Pre-fetch all swing scores for today's BUY signals in one bulk query.
            # Primary sort: swing_score DESC (best-scored candidates first).
            # Fallback sort: minervini_trend_score DESC when swing scores are all zero
            # (pipeline failure — signal_quality_scores or swing_trader_scores timeout).
            # Symbols without any scores default last (alphabetical).
            cur.execute(
                """
                SELECT b.symbol, b.date, b.signal_type,
                       COALESCE(s.score, 0) as swing_score,
                       COALESCE(tt.minervini_trend_score, 0) as trend_score_fallback
                FROM buy_sell_daily b
                LEFT JOIN swing_trader_scores s ON b.symbol = s.symbol AND b.date = s.date
                LEFT JOIN trend_template_data tt ON b.symbol = tt.symbol AND b.date = tt.date
                WHERE b.date = %s AND b.signal_type = 'BUY'
                ORDER BY COALESCE(s.score, 0) DESC,
                         COALESCE(tt.minervini_trend_score, 0) DESC,
                         b.symbol
                """,
                (eval_date,),
            )
            rows = cur.fetchall()
            # Convert to list of (symbol, date, signal_type) tuples for loop compatibility
            signals = [(r[0], r[1], r[2]) for r in rows]
            signal_swing_scores = {r[0]: r[3] for r in rows}  # Cache for later lookups

            # Detect empty/stale swing_trader_scores and warn — if <10% of signals have
            # non-zero scores the table is likely empty due to pipeline timeout.
            non_zero_scores = sum(1 for r in rows if r[3] > 0)
            if rows and non_zero_scores < max(1, len(rows) * 0.10):
                logger.warning(
                    f"[SWING SCORES] Only {non_zero_scores}/{len(rows)} BUY signals have non-zero "
                    f"swing scores for {eval_date}. swing_trader_scores may be empty or stale "
                    f"(signal_quality_scores timeout or pipeline step failure). "
                    f"Falling back to minervini_trend_score sort — check Step Functions logs."
                )

            logger.info(f"Found {len(signals)} BUY signals to evaluate from {eval_date}")
            if not signals:
                logger.warning(f"[CRITICAL] No BUY signals found in buy_sell_daily for {eval_date} — signal generation will return 0 trades")
            logger.info("")

            if self.advanced is None:
                self.advanced = AdvancedFilters(self.config)
            ctx = self.advanced.load_market_context(eval_date)
            logger.info(f"Market context: top sectors = {ctx['strong_sectors']}")
            if ctx['market_breadth']:
                logger.info(f"  AAII bull/bear spread: {ctx['market_breadth']['bull_bear_spread']:+.1f}")

            # Pre-fetch portfolio value ONCE to avoid one Alpaca HTTP call per stock in Tier 5.
            # PositionSizer.get_portfolio_value() calls paper-api.alpaca.markets for every
            # stock that reaches Tier 5 — with 100+ candidates that's 100+ HTTP round-trips.
            # Cache here and pass via self._cached_portfolio_value for FilterTiers45Mixin to use.
            self._cached_portfolio_value = None
            try:
                from algo.algo_position_sizer import PositionSizer as _PSizer
                self._cached_portfolio_value = _PSizer(self.config).get_portfolio_value()
                logger.info(f"  Portfolio value (cached for Tier 5 sizing): ${self._cached_portfolio_value:,.0f}")
            except Exception as _pv_err:
                logger.warning(f"  Could not pre-fetch portfolio value: {_pv_err} — will fetch per-stock (slower)")

            tier_pass_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            advanced_passed = 0
            advanced_blocked = 0
            passed_all_tiers = []

            # Track pre-tier rejections for comprehensive rejection logging
            pre_tier_rejections = {
                'earnings_blackout': 0,
                'signal_age': 0,
                'stage_not_2': 0,
                'close_quality': 0,
                'volume': 0,
                'no_trend_data': 0,
                'no_entry_price': 0,
            }

            tracker = RejectionTracker()

            earnings_blackout = EarningsBlackout(self.config)
            trendline = TrendlineSupport()

            today = _date.today()

            # Compute the most recent expected trading day (yesterday or earlier) once, outside the loop.
            # Signal age is measured from this reference — not from date.today() — so a Friday signal
            # evaluated on Tuesday after a 4-day holiday weekend reads as 0 days old (not 4).
            # Hardcoding today as the reference causes false rejections after any multi-day holiday.
            _expected_recent = today - timedelta(days=1)
            try:
                from algo.algo_market_calendar import MarketCalendar
                for _ in range(10):
                    if MarketCalendar.is_trading_day(_expected_recent):
                        break
                    _expected_recent -= timedelta(days=1)
            except Exception as cal_e:
                logger.debug(f"MarketCalendar check failed, falling back to weekday check: {cal_e}")
                while _expected_recent.weekday() >= 5:
                    _expected_recent -= timedelta(days=1)

            # Hard time budget: stop evaluating after 240s to fit in Lambda's 600s budget.
            # Phase 5 evaluates BUY signals sorted by swing_score (best first). With 5000+ stocks
            # × per-symbol DB queries, unconstrained evaluation can take 5-10 minutes. The 240s
            # budget is 40% of the 600s Lambda limit, leaving 360s for other phases and exits.
            import time as _time
            _phase5_start = _time.time()
            _phase5_budget_secs = 240
            _tier_eval_times = []  # Track per-symbol evaluation times

            for symbol, signal_date, _signal in signals:
                _sym_start = _time.time()
                if _time.time() - _phase5_start > _phase5_budget_secs:
                    logger.warning(f"Phase 5 evaluation stopped after {_phase5_budget_secs}s "
                                   f"({len(passed_all_tiers)} candidates found so far)")
                    break

                blackout_check = earnings_blackout.run(symbol, signal_date)
                if not blackout_check['pass']:
                    logger.info(f"  SKIP {symbol}: {blackout_check['reason']}")
                    pre_tier_rejections['earnings_blackout'] += 1
                    tracker.log_pre_tier_rejection(eval_date, symbol, f"earnings_blackout: {blackout_check['reason']}")
                    continue

                # A1: Signal Age Gate — reject signals older than max_signal_age_days.
                # Age is measured from the most recent expected trading day (not today) so that
                # holiday weekends do not inflate calendar-day counts and falsely reject fresh signals.
                max_signal_age_days = int(self.config.get('max_signal_age_days', 3))
                signal_age = (_expected_recent - signal_date).days
                if signal_age > max_signal_age_days:
                    logger.info(f"  SKIP {symbol}: Signal {signal_age}d old vs last trading day (max {max_signal_age_days}d)")
                    pre_tier_rejections['signal_age'] += 1
                    tracker.log_pre_tier_rejection(eval_date, symbol, f"signal_age: {signal_age}d old vs last trading day (max {max_signal_age_days}d)")
                    continue

                # Fetch stage, trend score, and price data for signal date.
                # volume_ma_50 from technical_data_daily replaces the correlated subquery
                # AVG(volume) FROM price_daily (50-day window scan per symbol = too slow).
                row = None
                try:
                    cur.execute("SAVEPOINT stage_query")
                    cur.execute(
                        """SELECT t.weinstein_stage, p.volume, p.high, p.low, p.close,
                                  td.volume_ma_50 AS avg_vol_50d
                           FROM trend_template_data t
                           LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                           LEFT JOIN technical_data_daily td ON t.symbol = td.symbol AND t.date = td.date
                           WHERE t.symbol = %s AND t.date = %s LIMIT 1""",
                        (symbol, signal_date),
                    )
                    row = cur.fetchone()  # fetch BEFORE RELEASE (DDL clears result buffer)
                    cur.execute("RELEASE SAVEPOINT stage_query")
                except Exception as _sq_err:
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT stage_query")
                        cur.execute("RELEASE SAVEPOINT stage_query")
                    except Exception:
                        pass
                    logger.warning(f"  SKIP {symbol}: stage query failed ({_sq_err})")
                    continue
                if row:
                    stage_number, volume, day_high, day_low, close, avg_vol_50d = row

                    # A1: Stage 2 check (configurable bypass for force-testing end-to-end)
                    require_stage_2 = not bool(self.config.get('bypass_stage_2_filter', False))
                    if require_stage_2 and stage_number != 2:
                        logger.info(f"  SKIP {symbol}: Stage {stage_number} (need Stage 2)")
                        pre_tier_rejections['stage_not_2'] += 1
                        tracker.log_pre_tier_rejection(eval_date, symbol, f"stage_not_2: Stage {stage_number} (need Stage 2)")
                        continue

                    # A2: Close Quality Gate — close must be in upper N% of day's range
                    if day_high and day_low and close is not None and day_high > day_low:
                        min_close_quality_pct = float(self.config.get('min_close_quality_pct', 60.0))
                        day_range = day_high - day_low
                        close_pct_of_range = ((close - day_low) / day_range * 100) if day_range > 0 else 0
                        if close_pct_of_range < min_close_quality_pct:
                            logger.info(f"  SKIP {symbol}: Close at {close_pct_of_range:.0f}% of range (need >{min_close_quality_pct:.0f}%)")
                            pre_tier_rejections['close_quality'] += 1
                            tracker.log_pre_tier_rejection(eval_date, symbol, f"close_quality: Close at {close_pct_of_range:.0f}% of range (need >{min_close_quality_pct:.0f}%)")
                            continue

                    # A3: Volume Hard Gate — min breakout volume ratio
                    min_vol_ratio = float(self.config.get('min_breakout_volume_ratio', 1.25))
                    if volume and avg_vol_50d and avg_vol_50d > 0:
                        vol_ratio = volume / avg_vol_50d
                        if vol_ratio < min_vol_ratio:
                            logger.info(f"  SKIP {symbol}: Vol {vol_ratio:.2f}x 50-day avg (need >{min_vol_ratio}x)")
                            pre_tier_rejections['volume'] += 1
                            tracker.log_pre_tier_rejection(eval_date, symbol, f"volume: Vol {vol_ratio:.2f}x 50-day avg (need >{min_vol_ratio}x)")
                            continue
                else:
                    logger.info(f"  SKIP {symbol}: No trend or price data for {signal_date}")
                    pre_tier_rejections['no_trend_data'] += 1
                    tracker.log_pre_tier_rejection(eval_date, symbol, f"no_trend_data: No trend or price data for {signal_date}")
                    continue

                # Fetch fresh market close for entry date (Day 1: signal_date or next trading day)
                entry_date = self._get_next_trading_day(signal_date, cur)
                entry_price = self._get_market_close(symbol, entry_date, cur)
                if entry_price is None:
                    pre_tier_rejections['no_entry_price'] += 1
                    tracker.log_pre_tier_rejection(eval_date, symbol, f"no_entry_price: No market close for {entry_date}")
                    continue

                trendline_check = trendline.validate_entry_near_trendline(symbol, signal_date, float(entry_price))
                if not trendline_check['near_trendline']:
                    logger.info(f"  WARN {symbol}: {trendline_check['reason']}")
                    # Note: This is a soft check (warn, not skip) - trendline is optional confluence

                result = self.evaluate_signal(symbol, signal_date, float(entry_price), cur)
                for t in (1, 2, 3, 4, 5):
                    if result['tiers'][t]['pass']:
                        tier_pass_counts[t] += 1

                if result['passed_all_tiers']:
                    # Get sector info (needed for swing score and results)
                    sector_info = self._get_sector_info(symbol, cur) or {'sector': '', 'industry': ''}

                    # Run advanced filters (if enabled)
                    enable_advanced = bool(self.config.get('enable_advanced_filters', True))
                    if enable_advanced:
                        try:
                            # SAVEPOINT guards against statement-timeout-induced transaction aborts.
                            # Without this, a timeout inside evaluate_candidate() puts the whole
                            # transaction in aborted state, causing all subsequent symbols to fail
                            # with "current transaction is aborted, commands ignored".
                            cur.execute("SAVEPOINT adv_filter")
                            adv = self.advanced.evaluate_candidate(
                                symbol, signal_date, float(entry_price),
                                sector_info['sector'], sector_info['industry'],
                            )
                            cur.execute("RELEASE SAVEPOINT adv_filter")
                            result['advanced'] = adv
                        except Exception as e:
                            try:
                                cur.execute("ROLLBACK TO SAVEPOINT adv_filter")
                                cur.execute("RELEASE SAVEPOINT adv_filter")
                            except Exception as rollback_err:
                                if "current transaction is aborted" in str(rollback_err).lower():
                                    logger.critical(f"Transaction aborted for {symbol}, cannot recover. Stopping Phase 5 early.")
                                    break
                                pass
                            logger.warning(f"Advanced filters failed for {symbol}: {e} (using default)")
                            adv = {'pass': True, 'reason': 'Advanced filters unavailable', 'composite_score': 50.0, 'components': {}, 'grade': 'C'}
                            result['advanced'] = adv
                    else:
                        # Advanced filters disabled
                        adv = {'pass': True, 'reason': 'Advanced filters disabled', 'composite_score': 50.0, 'components': {}, 'grade': 'C'}
                        result['advanced'] = adv

                    if adv['pass']:
                        advanced_passed += 1

                        # Use pre-fetched swing scores from the bulk query above (no per-symbol lookup)
                        try:
                            cur.execute("SAVEPOINT swing_score")
                            cur.execute(
                                "SELECT score, components FROM swing_trader_scores WHERE symbol = %s AND date = %s LIMIT 1",
                                (symbol, signal_date)
                            )
                            swing_row = cur.fetchone()
                            cur.execute("RELEASE SAVEPOINT swing_score")
                            if swing_row:
                                swing_score_from_db, swing_comp_json = swing_row
                                import json as _json
                                if isinstance(swing_comp_json, dict):
                                    swing_components = swing_comp_json
                                elif swing_comp_json:
                                    swing_components = _json.loads(swing_comp_json)
                                else:
                                    swing_components = {}
                                # Use score from pre-fetch cache
                                swing_score_val = signal_swing_scores.get(symbol, 0.0)
                                # Compute grade from score
                                def score_to_grade(score):
                                    if score >= 85: return 'A+'
                                    elif score >= 75: return 'A'
                                    elif score >= 65: return 'B'
                                    elif score >= 55: return 'C'
                                    elif score >= 45: return 'D'
                                    else: return 'F'
                                computed_grade = score_to_grade(float(swing_score_val))
                                swing = {'pass': True, 'reason': 'precomputed', 'swing_score': float(swing_score_val), 'grade': computed_grade, 'components': swing_components}
                            else:
                                swing_score_val = signal_swing_scores.get(symbol, 0.0)
                                logger.debug(f"No grade/components for {symbol} on {signal_date}, using cached score {swing_score_val}")
                                swing = {'pass': True, 'reason': 'score_unavailable', 'swing_score': float(swing_score_val), 'grade': 'F', 'components': {}}
                        except Exception as e:
                            try:
                                cur.execute("ROLLBACK TO SAVEPOINT swing_score")
                                cur.execute("RELEASE SAVEPOINT swing_score")
                            except Exception as rollback_err:
                                if "current transaction is aborted" in str(rollback_err).lower():
                                    logger.critical(f"Transaction aborted for {symbol} during swing score lookup. Stopping Phase 5 early.")
                                    break
                                pass
                            swing_score_val = signal_swing_scores.get(symbol, 0.0)
                            logger.warning(f"Error fetching swing trader metadata for {symbol}: {e}")
                            swing = {'pass': True, 'reason': 'lookup_error', 'swing_score': float(swing_score_val), 'grade': 'F', 'components': {}}

                        # Hard gate: swing score gate relaxed for production (use component scoring for filtering)
                        # min_swing check disabled to allow all candidates through for ranking
                        if not swing['pass']:
                            result['swing_block_reason'] = swing['reason']
                            logger.debug(f"  Swing gate failed {symbol}: {swing['reason']} (proceeding with soft pass)")
                            # Convert failed swing to soft-pass with 0 score so it doesn't block ranking
                            swing = {'pass': True, 'reason': 'swing gate failed', 'swing_score': 0.0, 'grade': 'F', 'components': {}}

                        # Always add to passed_all_tiers for ranking (swing_score=0 will rank low)
                        passed_all_tiers.append({
                                'symbol': symbol,
                                'signal_date': signal_date,
                                'entry_date': entry_date,
                                'entry_price': float(entry_price),
                                'stop_loss_price': result.get('stop_loss_price'),
                                'sqs': result.get('sqs', 0),
                                'trend_score': result.get('trend_score', 0),
                                'completeness_pct': result.get('completeness_pct', 0),
                                'shares': result.get('shares', 0),
                                'risk_dollars': result.get('risk_dollars', 0.0),
                                'composite_score': adv['composite_score'],
                                'swing_score': swing['swing_score'],
                                'swing_grade': swing['grade'],
                                'swing_components': swing['components'],
                                'sector': sector_info['sector'],
                                'industry': sector_info['industry'],
                                'advanced_components': adv['components'],
                                'all_tiers_pass': True,
                                # Capture per-signal stop metadata here (not after the loop) so
                                # each trade records its own stop method, not the last signal's.
                                'stop_method': getattr(self, '_last_stop_method', 'unknown'),
                                'stop_reasoning': getattr(self, '_last_stop_reasoning', 'No reasoning recorded'),
                            })
                    else:
                        advanced_blocked += 1
                        result['advanced_block_reason'] = adv['reason']

                # NEW: Log rejection if not passed (Phase 3 integration)
                if not result.get('passed_all_tiers', False):
                    tier_results = {}
                    for t in [1, 2, 3, 4, 5]:
                        tier_results[t] = {
                            'pass': result['tiers'][t].get('pass', False),
                            'reason': result['tiers'][t].get('reason', '')
                        }
                    adv_result = {'reason': result.get('advanced_block_reason', '')} if 'advanced_block_reason' in result else None
                    tracker.log_rejection(eval_date, symbol, float(entry_price), tier_results, adv_result)

                self._log_signal_evaluation(result)
                # Use SAVEPOINT so a persist failure never aborts the outer transaction
                try:
                    cur.execute("SAVEPOINT persist_eval")
                    self._persist_signal_evaluation(result, eval_date, cur)
                    cur.execute("RELEASE SAVEPOINT persist_eval")
                except Exception as e_persist:
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT persist_eval")
                        cur.execute("RELEASE SAVEPOINT persist_eval")
                    except Exception:
                        pass
                    logger.debug(f"Signal evaluation persist failed for {result.get('symbol','?')}: {e_persist}")

                # Track per-symbol timing for performance diagnostics
                _sym_elapsed = _time.time() - _sym_start
                _tier_eval_times.append((_sym_elapsed, symbol))
                if _sym_elapsed > 1.0:  # Log signals taking >1s individually
                    logger.debug(f"[TIMING] {symbol}: {_sym_elapsed:.2f}s evaluation")

            # Timing statistics
            _total_eval = _time.time() - _phase5_start
            if _tier_eval_times:
                _avg_time = sum(t[0] for t in _tier_eval_times) / len(_tier_eval_times)
                _slowest_10 = sorted(_tier_eval_times, reverse=True)[:10]
                logger.info(f"\n{'='*70}")
                logger.info(f"PERFORMANCE TIMING (Phase 5 signal evaluation):")
                logger.info(f"{'='*70}")
                logger.info(f"  Total evaluation time: {_total_eval:.1f}s")
                logger.info(f"  Symbols evaluated:    {len(_tier_eval_times)}")
                logger.info(f"  Average per symbol:   {_avg_time:.3f}s")
                logger.info(f"  Slowest 10 symbols:")
                for elapsed, sym in _slowest_10:
                    logger.info(f"    {sym:8s}: {elapsed:.2f}s")

            logger.info(f"\n{'='*70}")
            logger.info("FILTER REJECTION ANALYSIS:")
            logger.info(f"{'='*70}")

            # Pre-tier rejections
            total_pre_tier = sum(pre_tier_rejections.values())
            if total_pre_tier > 0:
                logger.info("PRE-TIER REJECTIONS (before tier evaluation):")
                for reason, count in sorted(pre_tier_rejections.items(), key=lambda x: -x[1]):
                    if count > 0:
                        logger.info(f"  {reason:20s}: {count:3d} signals")
                logger.info(f"  {'TOTAL PRE-TIER':20s}: {total_pre_tier:3d} signals")

            # Tier pass-through
            logger.info("\nTIER PASS-THROUGH ANALYSIS:")
            logger.info(f"  T1 Data Quality:     {tier_pass_counts[1]:3d}/{len(signals)}")
            logger.info(f"  T2 Market Health:    {tier_pass_counts[2]:3d}/{len(signals)}")
            logger.info(f"  T3 Trend Template:   {tier_pass_counts[3]:3d}/{len(signals)}")
            logger.info(f"  T4 Signal Quality:   {tier_pass_counts[4]:3d}/{len(signals)}")
            logger.info(f"  T5 Portfolio:        {tier_pass_counts[5]:3d}/{len(signals)}")

            # Advanced filters
            logger.info(f"\nADVANCED FILTER RESULTS:")
            logger.info(f"  Passed all tiers:    {len(passed_all_tiers):3d}")
            logger.info(f"  Advanced passed:     {advanced_passed:3d} (of {tier_pass_counts[5]})")
            logger.info(f"  Advanced blocked:    {advanced_blocked:3d} (of {tier_pass_counts[5]})")

            # Summary
            qualified = len(passed_all_tiers)
            logger.info(f"\nFINAL RESULTS:")
            logger.info(f"  Input signals:       {len(signals):3d}")
            logger.info(f"  Pre-tier rejected:   {total_pre_tier:3d}")
            logger.info(f"  Tier-level rejected: {len(signals) - total_pre_tier - qualified:3d}")
            logger.info(f"  QUALIFIED FOR TRADE: {qualified:3d}")
            logger.info(f"{'='*70}")

            # Detect swing score data outage: if <10% of evaluated signals have non-zero scores,
            # the swing_trader_scores loader likely didn't run for today's eval_date.
            # In that case, bypass the min_swing_score gate entirely and fall back to ranking by
            # minervini_trend_score so good setups still surface instead of 0 trades.
            evaluated_count = len(passed_all_tiers)
            non_zero_passed = sum(1 for t in passed_all_tiers if t.get('swing_score', 0) > 0)
            swing_scores_available = evaluated_count == 0 or non_zero_passed >= max(1, evaluated_count * 0.10)

            if not swing_scores_available:
                logger.warning(
                    f"[SWING FALLBACK] Only {non_zero_passed}/{evaluated_count} qualified candidates "
                    f"have non-zero swing scores — swing_trader_scores may be stale or empty. "
                    f"Bypassing min_swing_score gate and ranking by minervini_trend_score instead."
                )
                # Re-rank by trend score when swing data is unavailable
                for t in passed_all_tiers:
                    t['final_score'] = t.get('trend_score', 0)
                passed_all_tiers.sort(key=lambda x: x['final_score'], reverse=True)
                max_positions = int(self.config.get('max_positions', 12))
                final_trades = passed_all_tiers[:max_positions]
                # Skip to target price calculation (jump past regime/swing filter below)
                swing_fallback_active = True
            else:
                swing_fallback_active = False

            # Regime-aware min_swing_score filter (from RegimeManager)
            # Config can explicitly override with a lower value (e.g., for testing):
            # set 'disable_regime_swing_floor' = True in config_overrides to skip regime override
            if not swing_fallback_active:
                config_min_swing = self.config.get('min_swing_score', 55)
                min_swing_score = config_min_swing
                disable_regime = bool(self.config.get('disable_regime_swing_floor', False))
                if not disable_regime:
                    try:
                        from algo.algo_regime_manager import RegimeManager
                        regime_mgr = RegimeManager()
                        regime_params = regime_mgr.get_regime_params(eval_date)
                        regime_min = regime_params.get('min_swing_score', config_min_swing)
                        # Regime can raise the floor but never below config's explicit setting
                        min_swing_score = max(config_min_swing, regime_min) if config_min_swing > 0 else regime_min
                        regime = regime_mgr.get_current_regime(eval_date)
                        logger.info(f"Regime: {regime}, min_swing_score threshold: {min_swing_score}")
                    except Exception as e:
                        logger.debug(f"Could not load regime min_swing_score: {e}. Using config default {min_swing_score}.")
                else:
                    logger.info(f"Regime override disabled (disable_regime_swing_floor=True); using config min_swing_score: {min_swing_score}")

                # Apply regime-aware minimum swing score filter
                passed_all_tiers = [t for t in passed_all_tiers if t.get('swing_score', 0) >= min_swing_score]
                logger.info(f"After regime min_swing_score filter ({min_swing_score}): {len(passed_all_tiers)} qualified")

                # PRIMARY RANKING: swing_score (research-weighted, swing-specific)
                for t in passed_all_tiers:
                    t['final_score'] = t.get('swing_score', 0)

                passed_all_tiers.sort(key=lambda x: x['final_score'], reverse=True)
                max_positions = int(self.config.get('max_positions', 12))
                final_trades = passed_all_tiers[:max_positions]

            # Calculate target prices for all final trades (R-multiple based)
            # Read R-multiples from config
            t1_r = float(self.config.get('t1_target_r_multiple', 1.5))
            t2_r = float(self.config.get('t2_target_r_multiple', 3.0))
            t3_r = float(self.config.get('t3_target_r_multiple', 4.0))

            for trade in final_trades:
                entry = trade.get('entry_price', 0)
                stop = trade.get('stop_loss_price', 0)
                if entry > 0 and stop > 0 and stop < entry:
                    r = entry - stop  # Risk per share
                    trade['target_1_price'] = round(entry + t1_r * r, 2)
                    trade['target_2_price'] = round(entry + t2_r * r, 2)
                    trade['target_3_price'] = round(entry + t3_r * r, 2)
                else:
                    trade['target_1_price'] = None
                    trade['target_2_price'] = None
                    trade['target_3_price'] = None

                # stop_method and stop_reasoning are captured per-signal inside the evaluation loop above.

            try:
                def _comp_pts(v):
                    if isinstance(v, dict):
                        return float(v.get('pts', 0))
                    return float(v) if isinstance(v, (int, float)) else 0.0

                logger.info(f"\nFinal Trades (Top {max_positions} by swing_score):")
                logger.info("=" * 100)
                logger.info(f"{'#':<3}{'Sym':<8}{'Grade':<6}{'Score':>6}  {'Entry':>9}{'Stop':>9}{'Setup':>6}"
                            f"{'Trend':>6}{'Mom':>5}{'Vol':>5}{'Fund':>5}{'Sec':>5}{'MTF':>5}  {'Sector':<20}")
                logger.info("-" * 100)
                for i, trade in enumerate(final_trades, 1):
                    comp = trade.get('swing_components', {}) or {}
                    gr = trade.get('swing_grade', 'D')
                    logger.info(
                        f"{i:<3d}{trade['symbol']:<8}{gr:<6}{trade['final_score']:>6.1f}  "
                        f"${trade['entry_price']:>8.2f}${trade['stop_loss_price']:>8.2f}"
                        f"{_comp_pts(comp.get('setup_quality', 0)):>6.1f}"
                        f"{_comp_pts(comp.get('trend_quality', 0)):>6.1f}"
                        f"{_comp_pts(comp.get('momentum_rs', 0)):>5.1f}"
                        f"{_comp_pts(comp.get('volume', 0)):>5.1f}"
                        f"{_comp_pts(comp.get('fundamentals', 0)):>5.1f}"
                        f"{_comp_pts(comp.get('sector_industry', 0)):>5.1f}"
                        f"{_comp_pts(comp.get('multi_timeframe', 0)):>5.1f}  "
                        f"{(trade.get('sector') or 'N/A')[:20]:<20}"
                    )
                if not final_trades:
                    logger.info("(no qualifying trades — gates too strict for current market)")
                logger.info(f"\n{'='*70}\n")
            except Exception as _disp_err:
                logger.warning(f"Trade table display error (non-fatal): {_disp_err}")

            return final_trades

    def _resolve_evaluation_date(self, cur, max_date: Optional[_date] = None) -> _date:
        """Pick the most recent date <= max_date with BUY signals + market health + trend data.

        max_date defaults to today. Passing run_date prevents evaluating signals from
        future dates when the orchestrator is run with a historical date.
        """
        if max_date is None:
            max_date = _date.today()
        cur.execute(
            """
            SELECT bs.date
            FROM buy_sell_daily bs
            WHERE bs.signal_type = 'BUY'
              AND bs.date <= %s
              AND EXISTS (SELECT 1 FROM market_health_daily mh WHERE mh.date = bs.date)
              AND EXISTS (SELECT 1 FROM trend_template_data tt WHERE tt.date = bs.date)
            GROUP BY bs.date
            ORDER BY bs.date DESC
            LIMIT 1
            """,
            (max_date,)
        )
        row = cur.fetchone()
        resolved = row[0] if row else max_date

        if resolved < max_date:
            gap_days = (max_date - resolved).days
            # Warn when falling back >1 calendar day — 3 days is the max allowed by signal_age gate
            level = logger.warning if gap_days <= 3 else logger.critical
            level(
                f"[EVAL DATE] Resolved to {resolved} (max_date={max_date}, gap={gap_days}d). "
                f"Check that buy_sell_daily, market_health_daily, and trend_template_data all "
                f"have data for {max_date} — the most recent missing table causes the fallback."
            )
            if gap_days > 3:
                logger.critical(f"[EVAL DATE] Gap exceeds signal_age limit — signals are {gap_days}d stale and will be rejected by T1 data-age gate")

        return resolved

    def evaluate_signal(self, symbol, signal_date, entry_price, cur) -> Dict[str, Any]:
        """Evaluate single signal through all 5 tiers (short-circuits on first failure)."""
        flags = get_flags()
        result = {
            'symbol': symbol,
            'signal_date': signal_date,
            'entry_price': entry_price,
            'tiers': {i: {'pass': False, 'reason': ''} for i in (1, 2, 3, 4, 5)},
            'passed_all_tiers': False,
            'sqs': 0,
            'trend_score': 0,
            'completeness_pct': 0,
            'stop_loss_price': None,
            'shares': 0,
            'risk_dollars': 0.0,
            'position_size_pct': 0.0,
        }

        # Tier 1 (Data Quality)
        if not flags.is_enabled("signal_tier_1_enabled", default=True):
            result['tiers'][1] = {'pass': True, 'reason': 'Tier 1 disabled by feature flag'}
            logger.info(f"    T1 disabled by feature flag (pass-through)")
        else:
            t1 = self._tier1_data_quality(symbol, cur)
            result['tiers'][1] = t1
            result['completeness_pct'] = t1.get('completeness_pct', 0)
            if not t1['pass']:
                return result

        # Tier 2 (market health uses signal_date, falls back to most recent within 5 days)
        if not flags.is_enabled("signal_tier_2_enabled", default=True):
            result['tiers'][2] = {'pass': True, 'reason': 'Tier 2 disabled by feature flag'}
            logger.info(f"    T2 disabled by feature flag (pass-through)")
        else:
            t2 = self._tier2_market_health(signal_date, cur)
            result['tiers'][2] = t2
            if not t2['pass']:
                return result

        # Tier 3 (trend template)
        if not flags.is_enabled("signal_tier_3_enabled", default=True):
            result['tiers'][3] = {'pass': True, 'reason': 'Tier 3 disabled by feature flag', 'trend_score': 0}
            logger.info(f"    T3 disabled by feature flag (pass-through)")
        else:
            t3 = self._tier3_trend_template(symbol, signal_date, cur)
            result['tiers'][3] = t3
            result['trend_score'] = t3.get('trend_score', 0)
            result['stop_loss_price'] = t3.get('stop_loss_price')
            result['stop_method'] = t3.get('stop_method', self._last_stop_method)
            result['stop_reasoning'] = t3.get('stop_reasoning', self._last_stop_reasoning)
            if not t3['pass']:
                return result

        # Tier 4 (signal quality)
        if not flags.is_enabled("signal_tier_4_enabled", default=True):
            result['tiers'][4] = {'pass': True, 'reason': 'Tier 4 disabled by feature flag', 'sqs': 0}
            logger.info(f"    T4 disabled by feature flag (pass-through)")
        else:
            t4 = self._tier4_signal_quality(symbol, signal_date, cur)
            result['tiers'][4] = t4
            result['sqs'] = t4.get('sqs', 0)
            if not t4['pass']:
                return result

        # Tier 5 (portfolio health)
        if not flags.is_enabled("signal_tier_5_enabled", default=True):
            result['tiers'][5] = {'pass': True, 'reason': 'Tier 5 disabled by feature flag', 'shares': 0, 'risk_dollars': 0.0}
            logger.info(f"    T5 disabled by feature flag (pass-through)")
        else:
            t5 = self._tier5_portfolio_health(symbol, entry_price, result['stop_loss_price'], cur, signal_date)
            result['tiers'][5] = t5
            result['shares'] = t5.get('shares', 0)
            result['risk_dollars'] = t5.get('risk_dollars', 0.0)
            result['position_size_pct'] = t5.get('position_size_pct', 0.0)
            result['passed_all_tiers'] = t5['pass']
            return result

        result['passed_all_tiers'] = True
        return result

    # ---------- Tier implementations ----------

    def _tier1_data_quality(self, symbol, cur) -> Dict[str, Any]:
        try:
            cur.execute(
                """
                SELECT composite_completeness_pct, is_tradeable
                FROM data_completeness_scores WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()
            completeness = 0
            if row and row[0] is not None:
                completeness = float(row[0])
                min_required = float(self.config.get('min_completeness_score', 70))
                if completeness < min_required:
                    return {
                        'pass': False,
                        'reason': f'Completeness {completeness:.0f}% < {min_required:.0f}%',
                        'completeness_pct': completeness,
                    }

            cur.execute(
                "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            price_row = cur.fetchone()
            if not price_row or price_row[0] is None:
                return {'pass': False, 'reason': 'No price data', 'completeness_pct': completeness}

            price = float(price_row[0])
            min_price = float(self.config.get('min_stock_price', 5.0))
            if price < min_price:
                return {
                    'pass': False,
                    'reason': f'Price ${price:.2f} < ${min_price:.2f}',
                    'completeness_pct': completeness,
                }

            return {
                'pass': True,
                'reason': f'Completeness {completeness:.0f}%, Price ${price:.2f}',
                'completeness_pct': completeness,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'completeness_pct': 0}

    def _tier2_market_health(self, signal_date, cur) -> Dict[str, Any]:
        """Market health for the signal's date, with 5-day fallback."""
        try:
            if self._market_health_date == signal_date:
                # Use cached result (even if None — no market health data for this date)
                row = self._market_health_cache
            else:
                cur.execute(
                    """
                    SELECT date, market_stage, distribution_days_4w, vix_level, market_trend
                    FROM market_health_daily
                    WHERE date <= %s AND date >= %s::date - INTERVAL '5 days'
                    ORDER BY date DESC LIMIT 1
                    """,
                    (signal_date, signal_date),
                )
                row = cur.fetchone()
                self._market_health_cache = row
                self._market_health_date = signal_date

            if not row:
                return {'pass': False, 'reason': 'No market health data near signal date'}

            _d, stage, dist_days, vix, trend = row
            stage = stage or 0
            dist_days = dist_days or 0
            vix = float(vix) if vix is not None else 0.0

            max_vix = float(self.config.get('vix_max_threshold', 35.0))
            if vix > max_vix:
                return {'pass': False, 'reason': f'VIX {vix:.1f} > {max_vix:.1f}'}

            max_dd = int(self.config.get('max_distribution_days', 4))
            if dist_days > max_dd:
                return {'pass': False, 'reason': f'Distribution days {dist_days} > {max_dd}'}

            require_stage_2 = bool(self.config.get('require_stage_2_market', False))
            if require_stage_2 and stage != 2:
                return {'pass': False, 'reason': f'Market Stage {stage} != 2 (trend={trend})'}

            return {
                'pass': True,
                'reason': f'Stage {stage}, DD {dist_days}, VIX {vix:.1f}, {trend}',
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}

    def _check_volume_decay(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """Minervini warning: declining volume into breakout signals false breakout.

        Checks if 10-day average volume is declining relative to 50-day average.
        A breakout with declining volume = weak accumulation = false setup.
        """
        try:
            cur.execute(
                """
                SELECT volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, signal_date),
            )
            rows = cur.fetchall()
            if len(rows) < 50:
                return {'pass': True, 'reason': 'Insufficient volume history'}

            volumes = [float(r[0]) for r in rows if r[0]]
            if len(volumes) < 50:
                return {'pass': True, 'reason': 'No volume data'}

            # 10-day vs 50-day average volume (use exactly 50 bars for the baseline)
            vol_10d_avg = sum(volumes[:10]) / 10.0
            vol_50d_avg = sum(volumes[:50]) / 50.0

            if vol_10d_avg > 0 and vol_50d_avg > 0:
                vol_decline_pct = ((vol_50d_avg - vol_10d_avg) / vol_50d_avg) * 100.0

                # If 10-day avg is >15% below 50-day avg, volume is declining (red flag)
                if vol_decline_pct > 15.0:
                    return {
                        'pass': False,
                        'reason': f'Volume declining: 10d avg {vol_decline_pct:.1f}% below 50d (sign of weak setup)',
                    }

            return {'pass': True, 'reason': 'Volume OK'}
        except Exception as e:
            logger.debug(f'Volume decay check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'Volume check error (continuing)'}

    def _check_rs_line_strength(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """Minervini rule: RS-line (stock vs SPY) should be strong (at/near new highs).

        Checks if the 60-day RS-line (stock close / SPY close) is within the configured
        threshold of its 60-day peak. Uses a 60-day reference window (not 52-week) so
        recent relative strength matters more than a stale prior-year high.
        If RS-line is weak/broken, it's a warning even if price looks good.
        """
        try:
            cur.execute(
                """
                SELECT s.close, spy.close
                FROM price_daily s
                JOIN price_daily spy ON s.date = spy.date
                WHERE s.symbol = %s AND spy.symbol = 'SPY'
                  AND s.date <= %s
                ORDER BY s.date DESC LIMIT 250
                """,
                (symbol, signal_date),
            )
            rows = cur.fetchall()
            if len(rows) < 60:
                return {'pass': True, 'reason': 'Insufficient data for RS check'}

            # Compute RS-line (stock/SPY ratio) for last 60 and all available
            rs_line = [float(r[0]) / float(r[1]) for r in rows if r[0] and r[1]]
            if len(rs_line) < 60:
                return {'pass': True, 'reason': 'Insufficient RS history'}

            current_rs = rs_line[0]  # Most recent
            rs_60day_high = max(rs_line[:60])  # 60-day high (recent peak)

            # RS should be within threshold of 60-day high (use recent peak, not stale 52-week peak)
            rs_pct_from_high = ((rs_60day_high - current_rs) / rs_60day_high * 100.0) if rs_60day_high > 0 else 0
            max_rs_pct = float(self.config.get('max_rs_pct_from_60d_high', 15.0))

            if rs_pct_from_high > max_rs_pct:
                return {
                    'pass': False,
                    'reason': f'RS-line {rs_pct_from_high:.1f}% below 60d high (need <{max_rs_pct:.0f}% to trade)',
                }

            return {'pass': True, 'reason': f'RS-line strong: {rs_pct_from_high:.1f}% from high'}
        except Exception as e:
            logger.debug(f'RS-line check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'RS check error (continuing)'}

    def _check_weekly_stage_2(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """A4: Weekly Chart Hard Gate — Require weekly chart Stage 2.

        Even if daily is Stage 2, entering when weekly is Stage 3/4 is dangerous.
        Weekly chart shows the longer-term trend.
        """
        try:
            cur.execute(
                """
                SELECT signal FROM buy_sell_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            weekly_signal_row = cur.fetchone()
            if weekly_signal_row:
                weekly_signal = weekly_signal_row[0]
                if weekly_signal == 'SELL':
                    return {
                        'pass': False,
                        'reason': 'Weekly chart in SELL mode (avoid entries in Stage 3/4)',
                    }

            cur.execute(
                """
                SELECT pw.close,
                       AVG(pw.close) OVER (ORDER BY pw.date ASC ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as sma_30w
                FROM price_weekly pw
                WHERE pw.symbol = %s AND pw.date <= %s
                ORDER BY pw.date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = cur.fetchone()
            if row and row[0] and row[1]:
                close = float(row[0])
                sma_30w = float(row[1])
                if close < sma_30w:
                    return {
                        'pass': False,
                        'reason': f'Weekly price below 30-week MA (Stage 3/4, not Stage 2)',
                    }

            return {'pass': True, 'reason': 'Weekly chart Stage 2 OK'}
        except Exception as e:
            logger.debug(f'Weekly Stage 2 check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'Weekly check error (continuing)'}

    def _check_rs_line_slope(self, symbol, signal_date, cur) -> Dict[str, Any]:
        """A5: RS Line Trending Up — RS line must have positive slope over last N days.

        Currently the system checks if RS line is within 5% of its 52-week high.
        This adds a direction check: is the RS line trending UP, not just consolidating near the high?
        """
        try:
            slope_days = int(self.config.get('min_rs_line_slope_days', 10))

            cur.execute(
                """
                SELECT s.close, spy.close, s.date
                FROM price_daily s
                JOIN price_daily spy ON s.date = spy.date
                WHERE s.symbol = %s AND spy.symbol = 'SPY'
                  AND s.date <= %s
                ORDER BY s.date DESC LIMIT %s
                """,
                (symbol, signal_date, slope_days + 5),
            )
            rows = cur.fetchall()
            if len(rows) < slope_days:
                return {'pass': True, 'reason': f'Insufficient data for {slope_days}d slope'}

            # Compute RS-line (stock/SPY ratio) for the period
            rs_line_with_dates = []
            for r in rows:
                if r[0] and r[1]:
                    rs = float(r[0]) / float(r[1])
                    rs_line_with_dates.append((r[2], rs))

            if len(rs_line_with_dates) < slope_days:
                return {'pass': True, 'reason': 'Insufficient RS data'}

            rs_line_values = [x[1] for x in rs_line_with_dates[:slope_days]]
            rs_line_values.reverse()  # Fix: make oldest first so slope calculation is correct
            x_values = list(range(slope_days))

            # Simple linear regression: slope = sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)
            x_mean = sum(x_values) / len(x_values)
            y_mean = sum(rs_line_values) / len(rs_line_values)

            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, rs_line_values))
            denominator = sum((x - x_mean) ** 2 for x in x_values)

            slope = numerator / denominator if denominator != 0 else 0

            if slope <= 0:
                return {
                    'pass': False,
                    'reason': f'RS line slope {slope:.4f} not trending up (need positive slope)',
                }

            return {'pass': True, 'reason': f'RS line trending up: slope {slope:.4f}'}
        except Exception as e:
            logger.debug(f'RS-line slope check failed for {symbol}: {e}')
            return {'pass': True, 'reason': 'RS slope check error (continuing)'}

    # ---------- Market Data Helpers ----------

    def _get_next_trading_day(self, from_date, cur) -> _date:
        """Get the next trading day after from_date (first day with price data).

        For entry purposes, this gives us Day 1 to confirm the signal on real market data.
        """
        cur.execute(
            """
            SELECT date FROM price_daily
            WHERE symbol = 'SPY' AND date > %s
            ORDER BY date ASC LIMIT 1
            """,
            (from_date,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        # Fallback: add 1 day and hope it's a trading day
        return from_date + timedelta(days=1)

    def _get_market_close(self, symbol, date, cur) -> Optional[float]:
        """Get market close price for a symbol on a given date.

        Returns the actual market close from price_daily table.
        If the requested date has no data (e.g., future date), falls back to
        most recent available price to avoid rejecting same-day signals.
        This is appropriate for paper/sim trading.
        """
        cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date = %s
            """,
            (symbol, date),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])

        # Fallback: use most recent price <= requested date (for same-day signal evaluation)
        cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol, date),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
        return None

if __name__ == "__main__":
    pipeline = FilterPipeline()
    final_trades = pipeline.evaluate_signals()
    logger.info(f"\nFinal trade count: {len(final_trades)}")
