#!/usr/bin/env python3
"""
Daily Reconciliation - Sync positions, calculate P&L, create snapshots

Tasks:
1. Fetch Alpaca account data
2. Compare with algo_positions
3. Calculate P&L and metrics
4. Create portfolio snapshots
5. Audit and log discrepancies
"""

from config.credential_helper import get_db_config
from config.credential_manager import get_credential_manager
import os
from utils.db_connection import get_db_connection

import requests
import logging
from pathlib import Path
from datetime import datetime
from utils.trade_status import TradeStatus, PositionStatus
from algo.algo_config import get_config
from algo.algo_notifications import notify

logger = logging.getLogger(__name__)

class DailyReconciliation:
    """Daily reconciliation and portfolio snapshot creation."""

    def __init__(self, config):
        self.config = config
        self.trading_client = None
        try:
            from alpaca_trade_api import REST
            credential_manager = get_credential_manager()
            creds = credential_manager.get_alpaca_credentials()
            if creds.get("key") and creds.get("secret"):
                base_url = os.getenv('APCA_API_BASE_URL')
                if not base_url:
                    raise ValueError("APCA_API_BASE_URL environment variable is required (e.g., https://api.alpaca.markets or https://paper-api.alpaca.markets)")
                self.trading_client = REST(
                    key_id=creds["key"],
                    secret_key=creds["secret"],
                    base_url=base_url,
                    api_version='v2',
                    raw_data=False
                )
        except Exception as e:
            logger.warning(f"Alpaca client initialization failed: {e}")
            self.trading_client = None
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = get_db_connection()
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def run_daily_reconciliation(self, reconcile_date=None):
        """Run full daily reconciliation."""
        if not reconcile_date:
            reconcile_date = datetime.now().date()

        self.connect()

        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"DAILY RECONCILIATION - {reconcile_date}")
            logger.info(f"{'='*70}\n")

            # 1. Fetch Alpaca account
            alpaca_data = self._fetch_alpaca_account()
            if not alpaca_data:
                logger.error("CRITICAL: Alpaca account fetch failed — cannot reconcile")
                try:
                    notify('critical', title='Alpaca Connection Failed',
                           message='Daily reconciliation cannot proceed without Alpaca account data')
                except Exception as e:
                    logger.warning(f"Failed to send Alpaca failure notification: {e} (proceeding with reconciliation halt)")
                    # Note: notification failure doesn't block reconciliation halt, but we log it
                return {'success': False, 'reason': 'Alpaca account fetch failed — reconciliation halted'}

            logger.info(f"1. Alpaca Account:")
            logger.info(f"   Portfolio Value: ${alpaca_data.get('portfolio_value', 0):,.2f}")
            logger.info(f"   Cash: ${alpaca_data.get('cash', 0):,.2f}")
            logger.info(f"   Equity: ${alpaca_data.get('equity', 0):,.2f}")

            # 1b. Sync Alpaca positions into our DB (imports any external positions)
            sync_result = self.sync_alpaca_positions()
            logger.info(f"\n1b. Position Sync:")
            logger.info(f"   {sync_result['message']}")
            if sync_result.get('orphan_symbols'):
                logger.info(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

            # 1c. Compute MAE/MFE metrics for recently closed trades (E3 analytics)
            mae_result = self.compute_closed_trade_metrics()
            logger.info(f"\n1c. MAE/MFE Metrics:")
            logger.info(f"   {mae_result['reason']}")

            # 1d. Compute analytics metrics: IC and expectancy (E4-E5)
            analytics = self.compute_analytics_metrics()
            logger.info(f"\n1d. Analytics Metrics:")
            if analytics['ic'].get('valid'):
                logger.info(f"   IC (Information Coefficient): {analytics['ic']['ic']:.4f} ({analytics['ic']['trade_count']} trades)")
                if analytics['ic']['alert']:
                    logger.info(f"   ⚠ {analytics['ic']['alert']}")
            if analytics['expectancy'].get('valid'):
                logger.info(f"   Expectancy: {analytics['expectancy']['expectancy']:+.4f}% (win rate {analytics['expectancy']['win_rate']:.1f}%)")
                logger.info(f"   Kelly Fraction (25% conservative): {analytics['expectancy']['kelly_fraction']:.4f}")
                if analytics['expectancy']['alert']:
                    logger.info(f"   [FAIL] {analytics['expectancy']['alert']}")

            self.cur.execute("""
                SELECT position_id, symbol, quantity, avg_entry_price, current_price, position_value
                FROM algo_positions
                WHERE status = %s
                ORDER BY symbol
            """, (PositionStatus.OPEN.value,))

            positions = self.cur.fetchall()
            logger.info(f"\n2. Database Positions: {len(positions)} open")

            total_position_value = 0.0
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0

            for pos_id, symbol, qty, entry, current, pos_value in positions:
                # Coerce all DB-returned Decimals to float to avoid mixed-type arithmetic
                qty_f = float(qty or 0)
                entry_f = float(entry or 0)
                current_f = float(current or entry_f)
                pos_value_f = float(pos_value or 0)
                pnl = (current_f - entry_f) * qty_f
                pnl_pct = ((current_f - entry_f) / entry_f * 100.0) if entry_f > 0 else 0.0
                total_position_value += pos_value_f
                unrealized_pnl += pnl

                logger.info(f"   {symbol}: {qty_f:.0f} @ ${entry_f:.2f} -> ${current_f:.2f} | {pnl:+,.2f} ({pnl_pct:+.2f}%)")

            # 3. Calculate metrics
            cash = alpaca_data.get('cash', 0)
            # Use Alpaca's authoritative portfolio_value for the snapshot (includes live prices).
            # Our DB position_value sum may lag — Alpaca is the ground truth for drawdown math.
            alpaca_portfolio_value = float(alpaca_data.get('portfolio_value', 0) or 0)
            # DB-computed total (kept for drift reporting)
            total_equity_db = cash + total_position_value
            # Prefer Alpaca's live value; fall back to DB sum only if Alpaca value is missing/zero
            total_equity = alpaca_portfolio_value if alpaca_portfolio_value > 0 else total_equity_db

            if total_equity_db > 0:
                drift_pct = ((alpaca_portfolio_value - total_equity_db) / total_equity_db) * 100
                if abs(drift_pct) > 1.0:
                    logger.warning(f"Position value drift: Alpaca ${alpaca_portfolio_value:,.2f} vs DB-computed ${total_equity_db:,.2f} ({drift_pct:+.1f}%)")

            if total_equity > 0:
                unrealized_pnl_pct = (unrealized_pnl / total_equity) * 100

            largest_position = float(max([p[5] for p in positions], default=0) or 0)
            max_concentration = (largest_position / total_equity * 100.0) if total_equity > 0 else 0.0

            avg_position_size = (total_position_value / len(positions)) if positions else 0.0

            self.cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)

            prev_snapshot = self.cur.fetchone()
            prev_value = float(prev_snapshot[0]) if prev_snapshot else total_equity
            daily_return = total_equity - prev_value
            daily_return_pct = (daily_return / prev_value * 100) if prev_value > 0 else 0

            self.cur.execute("""
                SELECT market_trend, distribution_days_4w
                FROM market_health_daily
                WHERE date <= %s
                ORDER BY date DESC LIMIT 1
            """, (reconcile_date,))

            market = self.cur.fetchone()
            market_trend = market[0] if market else 'unknown'
            dist_days = market[1] if market else 0

            self.cur.execute("SELECT snapshot_date FROM algo_portfolio_snapshots WHERE snapshot_date = %s", (reconcile_date,))
            existing_snapshot = self.cur.fetchone()
            if existing_snapshot:
                logger.warning(f"Portfolio snapshot already exists for {reconcile_date} — refusing overwrite to prevent data loss")
                logger.info(f"WARNING: Snapshot for {reconcile_date} already exists. Skipping insertion to prevent overwrite.")
            else:
                self.cur.execute("""
                    INSERT INTO algo_portfolio_snapshots (
                        snapshot_date, total_portfolio_value, total_cash, total_equity,
                        position_count, largest_position_pct, average_position_size_pct,
                        unrealized_pnl_total, unrealized_pnl_pct,
                        daily_return_pct, market_health_status, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                """, (
                    reconcile_date,
                    total_equity,
                    cash,
                    total_equity,
                    len(positions),
                    max_concentration,
                    (avg_position_size / total_equity * 100) if total_equity > 0 else 0,
                    unrealized_pnl,
                    unrealized_pnl_pct,
                    daily_return_pct,
                    market_trend
                ))

            self.conn.commit()

            logger.info(f"\n3. Portfolio Summary:")
            logger.info(f"   Total Value: ${total_equity:,.2f}")
            logger.info(f"   Position Value: ${total_position_value:,.2f}")
            logger.info(f"   Cash: ${cash:,.2f}")
            logger.info(f"   Unrealized P&L: {unrealized_pnl:+,.2f} ({unrealized_pnl_pct:+.2f}%)")
            logger.info(f"   Daily Return: {daily_return_pct:+.2f}%")
            logger.info(f"   Concentration: {max_concentration:.1f}%")

            logger.info(f"\n{'='*70}")
            logger.info(f"Reconciliation complete - snapshot created")
            logger.info(f"{'='*70}\n")

            return {
                'success': True,
                'portfolio_value': total_equity,
                'positions': len(positions),
                'unrealized_pnl': unrealized_pnl
            }

        except Exception as e:
            logger.error(f"Error in reconciliation: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            self.disconnect()

    def sync_alpaca_positions(self):
        """Pull live positions from Alpaca and import any not in algo_positions.

        Best practice: our DB should reflect what Alpaca actually holds.
        This catches:
          - Positions opened outside our algo (manual trades)
          - Positions we tracked but Alpaca never filled
          - Drift between systems

        For positions in Alpaca but not us → import as 'imported_external'
        For positions in us but not Alpaca → flag as orphaned (don't auto-close)
        """
        if not self.trading_client:
            return {'imported': 0, 'orphaned': 0, 'message': 'No Alpaca client'}
        try:
            import signal
            import threading

            alpaca_positions = None
            error_msg = None

            def fetch_positions():
                nonlocal alpaca_positions, error_msg
                try:
                    alpaca_positions = self.trading_client.list_positions()
                except Exception as e:
                    error_msg = str(e)

            # Run with 30-second timeout
            thread = threading.Thread(target=fetch_positions, daemon=True)
            thread.start()
            thread.join(timeout=30)

            if thread.is_alive():
                return {'imported': 0, 'orphaned': 0, 'message': 'Alpaca list_positions timed out after 30s'}

            if error_msg:
                return {'imported': 0, 'orphaned': 0, 'message': f'Fetch failed: {error_msg}'}

            if alpaca_positions is None:
                return {'imported': 0, 'orphaned': 0, 'message': 'No positions returned from Alpaca'}

        except Exception as e:
            return {'imported': 0, 'orphaned': 0, 'message': f'Fetch failed: {e}'}

        self.cur.execute("SELECT symbol FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
        our_symbols = {row[0] for row in self.cur.fetchall()}

        # Fetch actual portfolio value for position_size_pct calculation (not a hardcoded constant).
        self.cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        _pv_row = self.cur.fetchone()
        _portfolio_value_for_pct = float(_pv_row[0]) if _pv_row and _pv_row[0] else 0.0

        alpaca_symbols = {}  # symbol -> qty for drift detection
        imported = 0

        for ap in alpaca_positions:
            sym = ap.symbol
            qty = float(ap.qty)
            alpaca_symbols[sym] = qty

            if sym in our_symbols:
                self.cur.execute(
                    "SELECT quantity FROM algo_positions WHERE symbol = %s AND status = %s",
                    (sym, PositionStatus.OPEN.value)
                )
                row = self.cur.fetchone()
                if row:
                    db_qty = int(row[0] or 0)
                    if abs(db_qty - qty) > 0.1:  # Allow small rounding differences
                        try:
                            notify(
                                severity='critical',
                                title='CRITICAL: Quantity Mismatch',
                                message=f'{sym} has {qty:.0f} shares on Alpaca but '
                                        f'{db_qty} in DB. Manual intervention required.',
                                symbol=sym,
                                details={'symbol': sym, 'alpaca_qty': qty, 'db_qty': db_qty},
                            )
                        except Exception as e:
                            logger.warning(f"  Could not send quantity drift alert: {e}")
                continue  # already tracked

            # Import this Alpaca position as a manual/external one
            try:
                qty = float(getattr(ap, 'qty', 0) or 0)
                avg_entry = float(getattr(ap, 'avg_entry_price', 0) or 0)
                cur_price = float(getattr(ap, 'current_price', None) or avg_entry)
                pos_value = float(getattr(ap, 'market_value', None) or qty * cur_price)
                pnl = float(getattr(ap, 'unrealized_pl', 0) or 0)
                pnl_pct = float(getattr(ap, 'unrealized_plpc', 0) or 0) * 100

                if qty <= 0:
                    continue  # short or zero — skip

                position_id = f'EXT-{sym}-{datetime.now().strftime("%Y%m%d")}'
                trade_id = f'EXT-{sym}'

                # For imported positions, calculate realistic stops + targets using volatility
                # This replaces the hardcoded placeholder values (0.92, 1.10/1.20/1.30)
                stop_loss_price = None
                target_1 = None
                target_2 = None
                target_3 = None
                stop_loss_method = 'imported_no_risk_calc'

                try:
                    # Use pre-computed ATR from technical_data_daily (includes gap moves via
                    # max(H-L, |H-PC|, |L-PC|)). AVG(high-low) from price_daily underestimates
                    # true ATR for gap-prone stocks and sets stops too tight.
                    self.cur.execute("""
                        SELECT atr FROM technical_data_daily
                        WHERE symbol = %s AND atr IS NOT NULL
                        ORDER BY date DESC LIMIT 1
                    """, (sym,))
                    atr_row = self.cur.fetchone()
                    if atr_row and atr_row[0]:
                        atr = float(atr_row[0])
                        # Stop = 2 * ATR below entry (standard risk management)
                        stop_loss_price = max(0.01, avg_entry - (2 * atr))
                        stop_loss_method = 'imported_2x_atr'
                        # Targets = 1:2 and 1:3 reward/risk ratio
                        r = avg_entry - stop_loss_price
                        target_1 = avg_entry + (2 * r)  # 2R
                        target_2 = avg_entry + (3 * r)  # 3R
                        target_3 = avg_entry + (4 * r)  # 4R
                except Exception as e:
                    logger.debug(f"Failed to calculate stop/targets for imported {sym}: {e}")
                    # Fall through to defaults below

                # If risk calculation failed, use configured defaults
                if stop_loss_price is None:
                    config = get_config()
                    stop_loss_pct = config.get('imported_position_default_stop_loss_pct', 5.0)
                    stop_loss_price = avg_entry * (1.0 - stop_loss_pct / 100.0)
                    stop_loss_method = 'imported_conservative_default'
                if target_1 is None:
                    config = get_config()
                    target_1_pct = config.get('imported_position_default_target_1_pct', 5.0)
                    target_2_pct = config.get('imported_position_default_target_2_pct', 10.0)
                    target_3_pct = config.get('imported_position_default_target_3_pct', 15.0)
                    target_1 = avg_entry * (1.0 + target_1_pct / 100.0)
                    target_2 = avg_entry * (1.0 + target_2_pct / 100.0)
                    target_3 = avg_entry * (1.0 + target_3_pct / 100.0)

                self.cur.execute("""
                    INSERT INTO algo_trades (
                        trade_id, symbol, signal_date, trade_date,
                        entry_time, entry_price, entry_quantity, entry_reason,
                        stop_loss_price, stop_loss_method,
                        target_1_price, target_2_price, target_3_price,
                        status, execution_mode, alpaca_order_id,
                        position_size_pct, base_type, created_at
                    )
                    VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE, CURRENT_TIMESTAMP, %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_id) DO NOTHING
                """, (
                    trade_id, sym, avg_entry, int(qty),
                    'EXTERNAL: existing Alpaca position imported',
                    stop_loss_price,
                    stop_loss_method,
                    target_1, target_2, target_3,
                    PositionStatus.OPEN.value, 'external', f'ALPACA-EXT-{sym}',
                    (pos_value / _portfolio_value_for_pct * 100) if _portfolio_value_for_pct > 0 else 0.0,
                    'imported_external',
                ))

                # Insert position (use same stop as calculated in trade above)
                self.cur.execute("""
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, unrealized_pnl,
                        unrealized_pnl_pct, status, trade_ids_arr,
                        current_stop_price, target_levels_hit, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (position_id) DO NOTHING
                """, (
                    position_id, sym, int(qty), avg_entry, cur_price,
                    pos_value, pnl, pnl_pct, PositionStatus.OPEN.value, [trade_id],
                    stop_loss_price,  # use calculated stop, not hardcoded 8%
                ))
                imported += 1
            except Exception as e:
                logger.warning(f"  Failed to import {sym}: {e}")
                self.conn.rollback()

        # Find orphans (in our DB but not Alpaca)
        orphans = our_symbols - set(alpaca_symbols.keys())
        if orphans:
            for sym in orphans:
                self.cur.execute("""
                    UPDATE algo_positions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status = %s
                """, (PositionStatus.ORPHANED.value, sym, PositionStatus.OPEN.value))
                # Alert: position missing from Alpaca
                try:
                    notify(
                        severity='critical',
                        title='CRITICAL: Position Drift Detected',
                        message=f'{sym} shows as open in DB but not found in Alpaca. '
                                f'May indicate liquidation or external closure.',
                        symbol=sym,
                        details={'symbol': sym, 'drift_type': 'orphaned_in_db'},
                    )
                except Exception as e:
                    logger.warning(f"  Could not send orphan alert: {e}")

        self.conn.commit()
        return {
            'imported': imported,
            'orphaned': len(orphans),
            'alpaca_total': len(alpaca_positions),
            'orphan_symbols': list(orphans),
            'message': f'Imported {imported} external Alpaca positions, '
                       f'{len(orphans)} orphans flagged',
        }

    def compute_analytics_metrics(self):
        """E4+E5: Compute Information Coefficient and Expectancy metrics.

        E4: Weekly correlation of entry swing_score vs 5-day post-entry return.
        E5: After 30+ closed trades, compute Kelly fraction for position sizing alerts.
        """
        try:
            # E4: Information Coefficient (last 8 weeks of closed trades)
            self.cur.execute("""
                SELECT swing_score, profit_loss_pct, trade_duration_days
                FROM algo_trades
                WHERE status = %s
                  AND exit_date >= NOW()::date - INTERVAL '56 days'
                  AND swing_score IS NOT NULL
                  AND profit_loss_pct IS NOT NULL
                ORDER BY exit_date
            """, (TradeStatus.CLOSED.value,))

            trades = self.cur.fetchall()
            ic_result = {'valid': False, 'ic': None, 'alert': None}

            if len(trades) >= 10:  # Need min 10 trades for meaningful IC
                # Compute rank correlation (Spearman) between swing_score and 5d returns
                try:
                    import statistics
                    scores = [float(t[0]) for t in trades]
                    returns = [float(t[1]) for t in trades]

                    # Rank correlation manually (Spearman)
                    score_ranks = sorted(range(len(scores)), key=lambda i: scores[i])
                    return_ranks = sorted(range(len(returns)), key=lambda i: returns[i])
                    rank_scores = [0] * len(score_ranks)
                    rank_returns = [0] * len(return_ranks)
                    for i, idx in enumerate(score_ranks):
                        rank_scores[idx] = i
                    for i, idx in enumerate(return_ranks):
                        rank_returns[idx] = i

                    # Pearson correlation on ranks (= Spearman IC).
                    # Use n-1 denominator for both covariance and stdev (sample statistics).
                    # Using population cov (÷n) with sample stdev (÷n-1) produces a slightly-off IC.
                    mean_sr = statistics.mean(rank_scores)
                    mean_rr = statistics.mean(rank_returns)
                    n = len(rank_scores)
                    cov = sum((rank_scores[i] - mean_sr) * (rank_returns[i] - mean_rr) for i in range(n)) / (n - 1)
                    std_sr = statistics.stdev(rank_scores) if n > 1 else 1
                    std_rr = statistics.stdev(rank_returns) if len(rank_returns) > 1 else 1
                    ic = cov / (std_sr * std_rr) if (std_sr * std_rr) > 0 else 0

                    ic_result = {
                        'valid': True,
                        'ic': round(ic, 4),
                        'trade_count': len(trades),
                        'alert': 'IC < 0.05 (signal quality degraded)' if ic < 0.05 else None
                    }
                except Exception as e:
                    logger.warning(f"IC computation failed: {e}")

            # E5: Expectancy and Kelly sizing (all closed trades)
            self.cur.execute("""
                SELECT COUNT(*), SUM(profit_loss_pct), AVG(profit_loss_pct)
                FROM algo_trades
                WHERE status = %s AND profit_loss_pct IS NOT NULL
            """, (TradeStatus.CLOSED.value,))

            stats = self.cur.fetchone()
            expectancy_result = {'valid': False, 'expectancy': None, 'alert': None}

            if stats and stats[0] >= 30:  # Need 30+ trades
                total_trades = stats[0]
                total_pct = float(stats[1] or 0)
                avg_return = float(stats[2] or 0)

                # Count wins and losses
                self.cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) AS wins,
                           COUNT(*) FILTER (WHERE profit_loss_pct <= 0) AS losses,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct > 0) AS avg_win,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct <= 0) AS avg_loss
                    FROM algo_trades
                    WHERE status = %s
                """, (TradeStatus.CLOSED.value,))

                wr = self.cur.fetchone()
                wins = int(wr[0] or 0)
                losses = int(wr[1] or 0)
                avg_win = float(wr[2] or 0) if wr[2] else 1.0
                avg_loss = float(wr[3] or 0) if wr[3] else -1.0

                win_rate = wins / total_trades if total_trades > 0 else 0
                expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

                # Kelly fraction: f = (bp - q) / b where b=ratio, p=win%, q=loss%
                # Simplified: kelly = (wins/total * avg_win - losses/total * abs(avg_loss)) / max(abs(avg_win), abs(avg_loss))
                if avg_win > 0 or avg_loss < 0:
                    kelly_num = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
                    kelly_denom = max(abs(avg_win), abs(avg_loss))
                    kelly = kelly_num / kelly_denom if kelly_denom > 0 else 0
                else:
                    kelly = 0

                expectancy_result = {
                    'valid': True,
                    'expectancy': round(expectancy, 4),
                    'win_rate': round(win_rate * 100, 1),
                    'kelly_fraction': round(max(0, kelly * 0.25), 4),  # Conservative 25% Kelly
                    'alert': 'NEGATIVE EXPECTANCY (reduce position sizing)' if expectancy < 0 else None
                }

            return {
                'ic': ic_result,
                'expectancy': expectancy_result,
            }
        except Exception as e:
            logger.error(f"Error in compute_analytics_metrics: {e}")
            return {'ic': {'valid': False}, 'expectancy': {'valid': False}}

    def compute_closed_trade_metrics(self):
        """E3: Compute MAE/MFE for recently closed trades (last 30 days)."""
        try:
            # Find recently closed trades without MAE/MFE
            self.cur.execute("""
                SELECT id, symbol, trade_date, exit_date, entry_price, exit_price, exit_r_multiple
                FROM algo_trades
                WHERE status = %s
                  AND exit_date IS NOT NULL
                  AND exit_date >= NOW()::date - INTERVAL '30 days'
                  AND (mae_pct IS NULL OR mfe_pct IS NULL)
                ORDER BY exit_date DESC
            """, (TradeStatus.CLOSED.value,))

            trades_to_update = self.cur.fetchall()
            if not trades_to_update:
                return {'updated': 0, 'reason': 'No recently closed trades without MAE/MFE'}

            updates = 0
            for trade_id, symbol, entry_date, exit_date, entry_price, exit_price, r_mult in trades_to_update:
                try:
                    entry_price = float(entry_price)
                    exit_price = float(exit_price or entry_price)

                    self.cur.execute("""
                        SELECT high, low FROM price_daily
                        WHERE symbol = %s AND date >= %s AND date <= %s
                        ORDER BY date ASC
                    """, (symbol, entry_date, exit_date))

                    prices = self.cur.fetchall()
                    if not prices:
                        continue

                    highs = [float(p[0]) if p[0] is not None else entry_price for p in prices]
                    lows = [float(p[1]) if p[1] is not None else entry_price for p in prices]

                    # MAE: worst (lowest) price from entry
                    min_price = min(lows)
                    mae_pct = ((min_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    # MFE: best (highest) price from entry
                    max_price = max(highs)
                    mfe_pct = ((max_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    self.cur.execute("""
                        UPDATE algo_trades
                        SET mae_pct = %s, mfe_pct = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (round(mae_pct, 4), round(mfe_pct, 4), trade_id))

                    updates += 1
                except Exception as e:
                    logger.warning(f"Failed to compute MAE/MFE for trade {trade_id}: {e}")

            self.conn.commit()
            return {'updated': updates, 'reason': f'Computed MAE/MFE for {updates} closed trades'}
        except Exception as e:
            logger.error(f"Error in compute_closed_trade_metrics: {e}")
            return {'updated': 0, 'reason': f'Error: {e}'}

    def _fetch_alpaca_account(self):
        """Fetch account data from Alpaca using REST client with timeout."""
        try:
            if not self.trading_client:
                return None

            import threading

            account = None
            error_msg = None

            def fetch_account():
                nonlocal account, error_msg
                try:
                    account = self.trading_client.get_account()
                except Exception as e:
                    error_msg = str(e)

            # Run with 30-second timeout
            thread = threading.Thread(target=fetch_account, daemon=True)
            thread.start()
            thread.join(timeout=30)

            if thread.is_alive():
                logger.error("Alpaca get_account timed out after 30s")
                return None

            if error_msg:
                logger.warning(f"Could not fetch Alpaca account: {error_msg}")
                return None

            if account is None:
                logger.warning("No account data returned from Alpaca")
                return None

            return {
                'cash': float(account.cash),
                'equity': float(account.equity),
                'portfolio_value': float(account.portfolio_value),
                'buying_power': float(account.buying_power)
            }

        except Exception as e:
            logger.warning(f"Could not fetch Alpaca account (skipping): {e}")
            return None

if __name__ == "__main__":

    config = get_config()
    reconciliation = DailyReconciliation(config)

    result = reconciliation.run_daily_reconciliation()
    logger.info(f"Result: {result}")

