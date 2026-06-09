#!/usr/bin/env python3

"""Filter Tier 4 & 5 implementations — signal quality and portfolio health."""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class FilterTiers45Mixin:
    """Tier 4 & 5 filtering logic."""

    def _tier4_signal_quality(self, symbol, signal_date, cur) -> Dict[str, Any]:
        try:
            cur.execute(
                """
                SELECT composite_sqs FROM signal_quality_scores
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, signal_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                # No SQS data for this symbol (table empty or loader hasn't run yet).
                # Pass-through rather than reject — signal_quality_scores is observe-only
                # per Phase 1 policy and may not be populated on fresh deployments.
                logger.debug(f"  [T4] {symbol}: No SQS data — passing through (observe-only)")
                return {'pass': True, 'reason': 'SQS N/A (no data)', 'sqs': 0}
            sqs = float(row[0])
            min_sqs = float(self.config.get('min_signal_quality_score', 60))
            if sqs < min_sqs:
                return {'pass': False, 'reason': f'SQS {sqs:.0f} < {min_sqs:.0f}', 'sqs': sqs}
            return {'pass': True, 'reason': f'SQS {sqs:.0f}', 'sqs': sqs}
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'sqs': 0}

    def _tier5_portfolio_health(self, symbol, entry_price, stop_loss_price, cur, signal_date=None) -> Dict[str, Any]:
        """Portfolio health check + actual share calculation using PositionSizer."""
        try:
            # Production safeguards (Phase 1)
            if signal_date:
                try:
                    from algo.algo_liquidity_checks import LiquidityChecks
                    lq = LiquidityChecks(self.config)
                    lq_passed, lq_reason = lq.run_all(symbol, entry_price, signal_date)
                    if not lq_passed:
                        return {'pass': False, 'reason': f'Liquidity: {lq_reason}', 'shares': 0}
                except Exception as e:
                    logger.warning(f'Liquidity check error for {symbol}: {e}')

            state = self._load_portfolio_state(cur)
            existing_symbols = state['symbols']

            # No duplicate position in same symbol
            if symbol in existing_symbols:
                return {
                    'pass': False,
                    'reason': f'Already have open position in {symbol}',
                    'shares': 0,
                }

            # Sector / industry concentration limits (PositionSizer doesn't check these)
            new_sector_info = self._get_sector_info(symbol, cur)
            if new_sector_info and (existing_symbols or self._candidate_holdings):
                sector_count, industry_count = self._count_sector_industry_overlap(
                    new_sector_info, existing_symbols, cur
                )
                max_per_sector = int(self.config.get('max_positions_per_sector', 8))
                max_per_industry = int(self.config.get('max_positions_per_industry', 5))
                if sector_count >= max_per_sector:
                    return {
                        'pass': False,
                        'reason': f'Sector "{new_sector_info["sector"]}" already has {sector_count} positions (max {max_per_sector})',
                        'shares': 0,
                    }
                if industry_count >= max_per_industry:
                    return {
                        'pass': False,
                        'reason': f'Industry "{new_sector_info["industry"]}" already has {industry_count} positions (max {max_per_industry})',
                        'shares': 0,
                    }

            # Correlation check: prevent entering if highly correlated with existing positions (>0.80 correlation)
            if existing_symbols:
                try:
                    corr_check = self._check_correlation_with_holdings(symbol, existing_symbols, cur)
                    if not corr_check['pass']:
                        return {
                            'pass': False,
                            'reason': corr_check['reason'],
                            'shares': 0,
                        }
                except Exception as e:
                    logger.warning(f'Correlation check failed for {symbol}: {e} (continuing without check)')

            # Use PositionSizer for all risk calculations (includes drawdown cascade, exposure mult, phase mult)
            if not stop_loss_price or stop_loss_price >= entry_price:
                # Stop calculation failed. Use fallback: 2x ATR from entry (if ATR available), else 5% stop.
                # Compute ATR fresh from price data
                atr_value = None
                try:
                    cur.execute(
                        """SELECT atr FROM technical_data_daily WHERE symbol = %s AND date = %s""",
                        (symbol, signal_date)
                    )
                    atr_row = cur.fetchone()
                    if atr_row and atr_row[0]:
                        atr_value = float(atr_row[0])
                except Exception as e:
                    logger.debug(f"Exception (expected): {e}")
                    pass

                if atr_value and atr_value > 0:
                    atr_stop = entry_price - (2.0 * atr_value)
                    # If ATR is huge, use % fallback instead (prevent unprotected position)
                    if atr_stop < entry_price * 0.85:
                        stop_loss_price = entry_price * 0.95
                        logger.warning(f'[T5] Stop calculation failed for {symbol}; ATR {atr_value:.2f} too large, using 5% fallback: {stop_loss_price:.2f}')
                    else:
                        stop_loss_price = max(0.01, atr_stop)
                        logger.warning(f'[T5] Stop calculation failed for {symbol}; using 2x ATR fallback: {stop_loss_price:.2f} (ATR={atr_value:.2f})')
                else:
                    stop_loss_price = entry_price * 0.95  # Conservative 5% fallback when ATR missing
                    logger.warning(f'[T5] Stop calculation FAILED for {symbol}; using 5% emergency fallback: {stop_loss_price:.2f} (no ATR available) — RISK INFLATED')

            from algo.algo_position_sizer import PositionSizer
            sizer = PositionSizer(self.config)
            cached_pv = getattr(self, '_cached_portfolio_value', None)
            result = sizer.calculate_position_size(symbol, entry_price, stop_loss_price, signal_date,
                                                   portfolio_value=cached_pv)

            if result['status'] != 'ok':
                return {
                    'pass': False,
                    'reason': result.get('reason', f'Sizing failed: {result["status"]}'),
                    'shares': 0,
                }

            # Apply exposure tier risk multiplier (e.g., PRESSURE tier = 0.5)
            if self.exposure_risk_multiplier != 1.0:
                adjusted_shares = round(result['shares'] * self.exposure_risk_multiplier)
                if adjusted_shares <= 0 and result['shares'] > 0:
                    return {
                        'pass': False,
                        'reason': f'Exposure tier multiplier {self.exposure_risk_multiplier} reduces position to 0 shares',
                        'shares': 0,
                    }
                result['shares'] = adjusted_shares
                result['risk_dollars'] *= self.exposure_risk_multiplier
                result['position_size_pct'] *= self.exposure_risk_multiplier
                result['reason'] = f'{adjusted_shares} sh @ ${entry_price:.2f} (risk ${result["risk_dollars"]:.0f}, {result["position_size_pct"]:.1f}% after tier mult={self.exposure_risk_multiplier})'

            # Mark candidate as "claimed" for sector/industry counting in this run
            if new_sector_info:
                self._candidate_holdings[symbol] = new_sector_info

            return {
                'pass': True,
                'reason': result['reason'],
                'shares': result['shares'],
                'risk_dollars': result['risk_dollars'],
                'position_size_pct': result['position_size_pct'],
            }
        except RuntimeError as e:
            # PositionSizer.get_portfolio_value() now returns a default instead of raising.
            # This branch is a safety net in case a RuntimeError surfaces from elsewhere.
            logger.warning(f"[T5] {symbol}: Portfolio sizing failed ({e}) — skipping stock")
            return {
                'pass': False, 'reason': f'Portfolio sizing error: {str(e)[:100]}',
                'shares': 0, 'risk_dollars': 0.0, 'position_size_pct': 0.0,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'shares': 0}

    def _get_sector_info(self, symbol, cur) -> Dict[str, Any]:
        try:
            cur.execute(
                "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            return {'sector': row[0], 'industry': row[1] or ''}
        except Exception as e:
            logger.warning(f"Exception: {e}")
            return None

    def _count_sector_industry_overlap(self, new_info, existing_symbols, cur) -> int:
        """Count how many open positions + same-run candidates share sector/industry with new_info.

        Checks both existing open positions AND candidates already approved in this run so
        sector limits are enforced within a single daily run (not just across days).
        """
        sector_count = 0
        industry_count = 0

        # Existing open positions
        for sym in existing_symbols:
            info = self._sector_cache.get(sym)
            if info is None:
                info = self._get_sector_info(sym, cur)
                self._sector_cache[sym] = info
            if not info:
                continue
            if info['sector'] == new_info['sector']:
                sector_count += 1
            if info['industry'] == new_info['industry']:
                industry_count += 1

        # Also count candidates already approved in this run
        for sym, info in self._candidate_holdings.items():
            if not info:
                continue
            if info['sector'] == new_info['sector']:
                sector_count += 1
            if info['industry'] == new_info['industry']:
                industry_count += 1

        return sector_count, industry_count

    def _load_portfolio_state(self, cur) -> Dict[str, Any]:
        """Cache portfolio state for the run (positions, value, drawdown)."""
        if self._portfolio_state_cache is not None:
            return self._portfolio_state_cache

        # Open positions
        from utils.trade_status import PositionStatus
        cur.execute(
            "SELECT symbol, position_value FROM algo_positions WHERE status = %s",
            (PositionStatus.OPEN.value,)
        )
        rows = cur.fetchall()
        position_count = len(rows)
        symbols = {r[0] for r in rows}
        positions_value = sum(float(r[1] or 0) for r in rows)

        # Portfolio value: prefer latest snapshot
        cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        snap = cur.fetchone()
        if not snap or not snap[0]:
            raise RuntimeError("Cannot apply exposure filter - portfolio value unavailable (no snapshot)")
        portfolio_value = float(snap[0])

        # Drawdown adjustment from peak
        cur.execute(
            "SELECT MAX(total_portfolio_value) FROM algo_portfolio_snapshots"
        )
        peak_row = cur.fetchone()
        peak = float(peak_row[0]) if peak_row and peak_row[0] else portfolio_value
        drawdown_pct = max(0.0, (peak - portfolio_value) / peak * 100.0) if peak > 0 else 0.0

        if drawdown_pct >= 20:
            risk_adjustment = 0.0
        elif drawdown_pct >= 15:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_15', 0.25))
        elif drawdown_pct >= 10:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_10', 0.50))
        elif drawdown_pct >= 5:
            risk_adjustment = float(self.config.get('risk_reduction_at_minus_5', 0.75))
        else:
            risk_adjustment = 1.0

        self._portfolio_state_cache = {
            'position_count': position_count,
            'symbols': symbols,
            'positions_value': positions_value,
            'portfolio_value': portfolio_value,
            'drawdown_pct': drawdown_pct,
            'risk_adjustment': risk_adjustment,
        }
        return self._portfolio_state_cache

    def _check_correlation_with_holdings(self, new_symbol, existing_symbols, cur) -> Dict[str, Any]:
        """Check if new symbol is highly correlated (>0.80) with existing open positions.

        Returns {'pass': bool, 'reason': str, 'highest_correlation': float}
        """
        if not existing_symbols:
            return {'pass': True, 'reason': 'No existing positions'}

        try:
            # Fetch 60-day price history for new symbol and each existing symbol
            symbols_to_check = [new_symbol] + list(existing_symbols)
            # Build placeholders dynamically: %s, %s, %s, ... one for each symbol
            placeholders = ','.join(['%s'] * len(symbols_to_check))
            cur.execute(
                f"""
                SELECT symbol, date, close FROM price_daily
                WHERE symbol IN ({placeholders})
                  AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY symbol, date
                """,
                tuple(symbols_to_check)
            )
            rows = cur.fetchall()
            if not rows:
                return {'pass': True, 'reason': 'Insufficient price data'}

            # Build price dataframe
            import pandas as pd
            df = pd.DataFrame(rows, columns=['symbol', 'date', 'close'])
            df['date'] = pd.to_datetime(df['date'])

            # Pivot to get prices by symbol
            pivot = df.pivot(index='date', columns='symbol', values='close')
            if pivot.empty or new_symbol not in pivot.columns:
                return {'pass': True, 'reason': 'Insufficient data for correlation check'}

            # Compute 60-day returns
            returns = pivot.pct_change()
            rows_before = len(returns)
            returns = returns.dropna()
            rows_after = len(returns)
            dropped = rows_before - rows_after
            if dropped > 0:
                logger.debug(
                    f"{new_symbol}: Dropped {dropped} row(s) with NaN returns during correlation check "
                    f"({rows_after} valid rows remain)"
                )

            if len(returns) < 20:
                logger.warning(f'Insufficient data for correlation check {new_symbol}: {len(returns)} days')
                return {'pass': True, 'reason': 'Insufficient history'}

            # Compute correlations with existing holdings
            # Only positive correlation creates concentration risk; negative correlation = hedging (desirable)
            new_returns = returns[new_symbol]
            max_corr = 0.0
            most_correlated = None
            for existing in existing_symbols:
                if existing in returns.columns:
                    corr = new_returns.corr(returns[existing])
                    if corr > max_corr:  # track only positive correlation
                        max_corr = corr
                        most_correlated = existing

            # Halt only if positively correlated > 0.80 (concentrated risk)
            if max_corr > 0.80:
                return {
                    'pass': False,
                    'reason': f'Correlated {max_corr:.2f} with {most_correlated} (60d, threshold 0.80)',
                    'highest_correlation': round(max_corr, 3),
                }
            return {
                'pass': True,
                'reason': f'Max correlation {max_corr:.2f} with portfolio',
                'highest_correlation': round(max_corr, 3),
            }
        except Exception as e:
            logger.debug(f'Correlation check failed: {e}')
            return {'pass': True, 'reason': 'Correlation check error (continuing)'}

    def _log_signal_evaluation(self, result) -> None:
        symbol = result['symbol']
        tiers = result['tiers']
        passed = ''.join(['1' if tiers[t]['pass'] else '.' for t in (1, 2, 3, 4, 5)])
        first_fail_reason = ''
        for t in (1, 2, 3, 4, 5):
            if not tiers[t]['pass']:
                first_fail_reason = f"T{t}: {tiers[t]['reason']}"
                break
        if not first_fail_reason:
            first_fail_reason = (
                f"PASS — SQS {result['sqs']}, Stop ${result['stop_loss_price']:.2f}, "
                f"{result['shares']} sh"
            )
        log_fn = logger.info if passed else logger.debug
        log_fn(f"{symbol:6s} | [{passed}] | {first_fail_reason}")

    def _persist_signal_evaluation(self, result, eval_date, cur) -> bool:
        """Persist evaluation result to algo_signals_evaluated for audit / dashboard."""
        try:
            tiers = result['tiers']
            # Build a concise reason summary
            first_fail = ''
            for t in (1, 2, 3, 4, 5):
                if not tiers[t]['pass']:
                    first_fail = f"T{t}: {tiers[t]['reason']}"
                    break
            reason = first_fail or f"PASS — {tiers[5]['reason']}"

            cur.execute(
                """
                INSERT INTO algo_signals_evaluated (
                    signal_date, symbol, source_table, source_timeframe,
                    raw_signal, entry_price,
                    filter_tier_1_pass, filter_tier_2_pass, filter_tier_3_pass,
                    filter_tier_4_pass, filter_tier_5_pass,
                    final_signal_quality_score, final_risk_score,
                    evaluated_at, evaluation_reason, created_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s,
                    CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (signal_date, symbol, source_timeframe) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price,
                    filter_tier_1_pass = EXCLUDED.filter_tier_1_pass,
                    filter_tier_2_pass = EXCLUDED.filter_tier_2_pass,
                    filter_tier_3_pass = EXCLUDED.filter_tier_3_pass,
                    filter_tier_4_pass = EXCLUDED.filter_tier_4_pass,
                    filter_tier_5_pass = EXCLUDED.filter_tier_5_pass,
                    final_signal_quality_score = EXCLUDED.final_signal_quality_score,
                    final_risk_score = EXCLUDED.final_risk_score,
                    evaluated_at = CURRENT_TIMESTAMP,
                    evaluation_reason = EXCLUDED.evaluation_reason
                """,
                (
                    eval_date, result['symbol'], 'buy_sell_daily', 'daily',
                    'BUY', result['entry_price'],
                    tiers[1]['pass'], tiers[2]['pass'], tiers[3]['pass'],
                    tiers[4]['pass'], tiers[5]['pass'],
                    int(result['sqs']) if result['sqs'] else 0,
                    result['risk_dollars'],
                    reason[:1000],
                ),
            )
        except Exception as e:
            # Don't fail the pipeline because of audit logging
            logger.info(f"  (audit log skipped for {result['symbol']}: {e})")
