#!/usr/bin/env python3

from config.credential_manager import get_credential_manager
from config.alpaca_config import get_alpaca_base_url
import os
from utils.database_context import DatabaseContext

import logging
import requests
from datetime import datetime, timezone, timedelta, date as _date_type
from utils.trade_status import TradeStatus, PositionStatus
from algo.algo_config import get_config, get_api_timeout
from algo.algo_notifications import notify

logger = logging.getLogger(__name__)

class DailyReconciliation:
    """Daily reconciliation and portfolio snapshot creation."""

    def __init__(self, config):
        self.config = config
        self.trading_client = None  # Kept for backward compat; HTTP calls used directly
        try:
            import requests as _req
            credential_manager = get_credential_manager()
            creds = credential_manager.get_alpaca_credentials()
            self._alpaca_key = creds.get("key")
            self._alpaca_secret = creds.get("secret")
            self._alpaca_base_url = get_alpaca_base_url()
            if self._alpaca_key and self._alpaca_secret:
                self.trading_client = True  # Signals credentials are available
        except Exception as e:
            logger.warning(f"Alpaca client initialization failed: {e}")
            self._alpaca_key = None
            self._alpaca_secret = None
            self._alpaca_base_url = None

    def run_daily_reconciliation(self, reconcile_date=None):
        """Run full daily reconciliation."""
        if not reconcile_date:
            reconcile_date = datetime.now(timezone.utc).date()
        elif isinstance(reconcile_date, str):
            reconcile_date = datetime.strptime(reconcile_date, '%Y-%m-%d').date()
        elif hasattr(reconcile_date, 'date') and not isinstance(reconcile_date, _date_type):
            reconcile_date = reconcile_date.date()

        try:
            logger.info(f"\n{'='*70}")
            logger.info(f"DAILY RECONCILIATION - {reconcile_date}")
            logger.info(f"{'='*70}\n")

            # 1. Fetch Alpaca account (required - no fallback to stale DB data)
            alpaca_data = self._fetch_alpaca_account()
            if not alpaca_data:
                logger.critical("Alpaca account fetch failed — reconciliation cannot proceed without live account data")
                try:
                    notify('critical', title='Reconciliation Halted',
                           message='Alpaca unavailable. Reconciliation requires live account data — cannot use stale DB cache.')
                except Exception as e:
                    logger.warning(f"Failed to send notification: {e}")
                raise ValueError("Alpaca account data required for reconciliation — cannot proceed with DB-only fallback")
            else:
                logger.info(f"1. Alpaca Account:")
                logger.info(f"   Portfolio Value: ${alpaca_data.get('portfolio_value', 0):,.2f}")
                logger.info(f"   Cash: ${alpaca_data.get('cash', 0):,.2f}")
                logger.info(f"   Equity: ${alpaca_data.get('equity', 0):,.2f}")

            with DatabaseContext('write') as cur:
                # 1b. Sync Alpaca positions into our DB (imports any external positions)
                sync_result = self.sync_alpaca_positions(cur)
                logger.info(f"\n1b. Position Sync:")
                logger.info(f"   {sync_result['message']}")
                if sync_result.get('orphan_symbols'):
                    logger.info(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

                # 1b2. Reconcile actual Alpaca fill prices with DB exit records
                fill_result = self.reconcile_exit_fills(cur, reconcile_date)
                logger.info(f"\n1b2. Exit Fill Reconciliation:")
                logger.info(f"   {fill_result['message']}")

                # 1b3. Check for trades pending Phase 7 price reconciliation
                pending_result = self.check_pending_reconciliations(cur)
                if pending_result.get('pending_count', 0) > 0:
                    logger.info(f"\n1b3. Pending Reconciliations:")
                    logger.info(f"   {pending_result['message']}")
                    if pending_result.get('stuck_count', 0) > 0:
                        for p in pending_result.get('pending', [])[:5]:
                            logger.warning(
                                f"   STUCK: {p['symbol']} {p['trade_id']} "
                                f"(Est: ${p['estimated_price']:.2f} vs ${p['current_exit_price']:.2f}, "
                                f"{p['days_pending']}d pending)"
                            )

                # 1c. Compute MAE/MFE metrics for recently closed trades (E3 analytics)
                mae_result = self.compute_closed_trade_metrics(cur)
                logger.info(f"\n1c. MAE/MFE Metrics:")
                logger.info(f"   {mae_result['reason']}")

                # 1d. Compute analytics metrics: IC and expectancy (E4-E5)
                analytics = self.compute_analytics_metrics(cur)
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

                # FIXED: Read from algo_trades (source of truth) instead of algo_positions (stale).
                # algo_positions drifts over time; algo_trades is authoritative for open positions.
                # CRITICAL: Do NOT fall back to entry_price when current_price is missing.
                # When price_daily has no entry, current_price must be NULL to indicate missing data.
                # This prevents position_value from being calculated incorrectly (showing 0% gain/loss).
                cur.execute("""
                    WITH open_trades AS (
                        SELECT DISTINCT ON (at.symbol)
                            at.symbol, at.entry_quantity as quantity, at.entry_price as avg_entry_price,
                            lp.current_price,
                            (at.entry_quantity * lp.current_price) as position_value
                        FROM algo_trades at
                        LEFT JOIN (
                            SELECT DISTINCT ON (symbol) symbol, close as current_price
                            FROM price_daily
                            WHERE symbol IN (
                                SELECT DISTINCT symbol FROM algo_trades
                                WHERE status IN ('open', 'filled', 'active', 'partially_filled')
                                  AND exit_date IS NULL
                            )
                            ORDER BY symbol, date DESC
                        ) lp ON at.symbol = lp.symbol
                        WHERE at.status IN ('open', 'filled', 'active', 'partially_filled')
                          AND at.exit_date IS NULL
                        ORDER BY at.symbol, at.trade_date DESC
                    )
                    SELECT symbol, quantity, avg_entry_price, current_price, position_value
                    FROM open_trades
                    ORDER BY symbol
                """)

                positions = cur.fetchall()
                logger.info(f"\n2. Database Positions: {len(positions)} open")

                total_position_value = 0.0
                unrealized_pnl = 0.0
                unrealized_pnl_pct = 0.0
                positions_with_prices = 0

                for symbol, qty, entry, current, pos_value in positions:
                    # Coerce all DB-returned Decimals to float to avoid mixed-type arithmetic
                    qty_f = float(qty or 0)
                    entry_f = float(entry or 0)

                    # CRITICAL: Do NOT fall back to entry_f when current is None.
                    # If current is None, it means price data is missing. Skip position value calculation.
                    if current is None:
                        logger.warning(f"   {symbol}: {qty_f:.0f} @ ${entry_f:.2f} -> PRICE MISSING (cannot compute P&L)")
                        continue

                    current_f = float(current)
                    pos_value_f = float(pos_value or 0)
                    pnl = (current_f - entry_f) * qty_f
                    pnl_pct = ((current_f - entry_f) / entry_f * 100.0) if entry_f > 0 else 0.0
                    total_position_value += pos_value_f
                    unrealized_pnl += pnl
                    positions_with_prices += 1

                    logger.info(f"   {symbol}: {qty_f:.0f} @ ${entry_f:.2f} -> ${current_f:.2f} | {pnl:+,.2f} ({pnl_pct:+.2f}%)")

                # 3. Calculate metrics
                cash_val = alpaca_data.get('cash')
                cash = float(cash_val) if cash_val is not None else None
                if cash is None or cash == 0:
                    cur.execute("SELECT total_cash FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
                    prev_cash_row = cur.fetchone()
                    if prev_cash_row and prev_cash_row[0]:
                        cash = float(prev_cash_row[0])
                        logger.info(f"   Cash (from prior snapshot): ${cash:,.2f}")
                # Use Alpaca's authoritative portfolio_value for the snapshot (includes live prices).
                # Our DB position_value sum may lag — Alpaca is the ground truth for drawdown math.
                pv = alpaca_data.get('portfolio_value')
                alpaca_portfolio_value = float(pv) if pv is not None else 0.0
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

                largest_position = float(max([p[4] for p in positions], default=0) or 0)
                max_concentration = (largest_position / total_equity * 100.0) if total_equity > 0 else 0.0

                avg_position_size = (total_position_value / len(positions)) if positions else 0.0

                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)

                prev_snapshot = cur.fetchone()
                prev_value = float(prev_snapshot[0]) if prev_snapshot else total_equity
                daily_return = total_equity - prev_value
                daily_return_pct = (daily_return / prev_value * 100) if prev_value > 0 else 0

                cur.execute("""
                    SELECT market_trend, distribution_days_4w
                    FROM market_health_daily
                    WHERE date <= %s
                    ORDER BY date DESC LIMIT 1
                """, (reconcile_date,))

                market = cur.fetchone()
                market_trend = market[0] if market else 'unknown'
                dist_days = market[1] if market else 0

                # Calculate additional metrics
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                        COALESCE(SUM(profit_loss_dollars) FILTER (WHERE DATE(exit_date) = %s::date), 0) as realized_pnl_today,
                        COALESCE(SUM(profit_loss_dollars), 0) as cumulative_pnl
                    FROM algo_trades
                    WHERE status = %s
                """, (str(reconcile_date), 'closed'))
                win_count, loss_count, realized_pnl_today, cumulative_pnl = cur.fetchone() or (0, 0, 0.0, 0.0)
                win_count = int(win_count or 0)
                loss_count = int(loss_count or 0)
                realized_pnl_today = float(realized_pnl_today or 0)
                cumulative_pnl = float(cumulative_pnl or 0)

                # Get cumulative return (normalize to actual initial capital from Alpaca account history)
                try:
                    initial_capital = self._fetch_initial_capital(cur)
                    cumulative_return_pct = (cumulative_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
                    logger.info(f"   Cumulative Return: {cumulative_return_pct:+.2f}% (on initial capital ${initial_capital:,.2f})")
                except ValueError as e:
                    logger.error(f"CRITICAL: {e} — cannot calculate cumulative return")
                    raise

                # Calculate max drawdown from historical snapshots
                max_drawdown_pct = 0.0
                cur.execute("""
                    SELECT
                        MAX(total_portfolio_value) as peak,
                        MIN(total_portfolio_value) as trough
                    FROM algo_portfolio_snapshots
                """)
                peak_row = cur.fetchone()
                if peak_row and peak_row[0] and peak_row[1]:
                    peak_val = float(peak_row[0])
                    trough_val = float(peak_row[1])
                    if peak_val > 0:
                        max_drawdown_pct = ((peak_val - trough_val) / peak_val) * 100.0

                # Calculate Sharpe ratio: mean_return / std_dev * sqrt(252)
                sharpe_ratio = 0.0
                cur.execute("""
                    SELECT daily_return_pct FROM algo_portfolio_snapshots
                    WHERE daily_return_pct IS NOT NULL
                    ORDER BY snapshot_date DESC LIMIT 252
                """)
                returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
                if len(returns) > 1:
                    import statistics
                    try:
                        std_dev = statistics.stdev(returns)
                        mean_return = statistics.mean(returns)
                        sharpe_ratio = (mean_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0.0
                    except Exception as e:
                        logger.warning(f"Exception: {e}")
                        sharpe_ratio = 0.0

                cur.execute("""
                    INSERT INTO algo_portfolio_snapshots (
                        snapshot_date, total_portfolio_value, total_cash, total_equity,
                        position_count, largest_position_pct, average_position_size_pct,
                        concentration_risk_pct,
                        realized_pnl_today, unrealized_pnl_total, unrealized_pnl_pct,
                        win_count_today, loss_count_today,
                        daily_return_pct, cumulative_return_pct, max_drawdown_pct,
                        sharpe_ratio, market_health_status, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (snapshot_date) DO UPDATE SET
                        total_portfolio_value = EXCLUDED.total_portfolio_value,
                        total_cash = EXCLUDED.total_cash,
                        total_equity = EXCLUDED.total_equity,
                        position_count = EXCLUDED.position_count,
                        largest_position_pct = EXCLUDED.largest_position_pct,
                        average_position_size_pct = EXCLUDED.average_position_size_pct,
                        concentration_risk_pct = EXCLUDED.concentration_risk_pct,
                        realized_pnl_today = EXCLUDED.realized_pnl_today,
                        unrealized_pnl_total = EXCLUDED.unrealized_pnl_total,
                        unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                        win_count_today = EXCLUDED.win_count_today,
                        loss_count_today = EXCLUDED.loss_count_today,
                        daily_return_pct = EXCLUDED.daily_return_pct,
                        cumulative_return_pct = EXCLUDED.cumulative_return_pct,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        market_health_status = EXCLUDED.market_health_status
                """, (
                    reconcile_date,
                    total_equity,
                    cash,
                    total_equity,
                    len(positions),
                    max_concentration,
                    (avg_position_size / total_equity * 100) if total_equity > 0 else 0,
                    max_concentration,
                    realized_pnl_today,
                    unrealized_pnl,
                    unrealized_pnl_pct,
                    win_count,
                    loss_count,
                    daily_return_pct,
                    cumulative_return_pct,
                    max_drawdown_pct,
                    sharpe_ratio,
                    market_trend
                ))

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
            return {'success': False, 'error': str(e)}

    def reconcile_exit_fills(self, cur, reconcile_date) -> dict:
        """Update DB trade exit prices with actual Alpaca fill prices.

        Phase 4 marks trades 'closed' immediately using the last known market price
        when placing market exit orders before market open. This reconciles those
        estimated prices with actual Alpaca fill prices after market opens.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return {'updated': 0, 'message': 'No Alpaca credentials'}
        try:
            import requests
            from algo.algo_config import get_api_timeout

            since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
            resp = requests.get(
                f'{self._alpaca_base_url}/v2/orders',
                params={'status': 'closed', 'side': 'sell', 'after': since,
                        'direction': 'desc', 'limit': 500},
                headers={'APCA-API-KEY-ID': self._alpaca_key,
                         'APCA-API-SECRET-KEY': self._alpaca_secret},
                timeout=get_api_timeout(),
            )
            if resp.status_code != 200:
                return {'updated': 0, 'message': f'Alpaca orders API {resp.status_code}'}

            orders = resp.json()
            if not isinstance(orders, list):
                return {'updated': 0, 'message': 'Unexpected Alpaca response format'}

            updated = 0
            two_days_ago = reconcile_date - timedelta(days=2)

            for order in orders:
                if order.get('status') != 'filled' or order.get('side') != 'sell':
                    continue
                symbol = order.get('symbol')
                filled_price_str = order.get('filled_avg_price')
                if not symbol or not filled_price_str:
                    continue
                try:
                    filled_price = float(filled_price_str)
                except (TypeError, ValueError):
                    continue
                if filled_price <= 0:
                    continue

                cur.execute("SAVEPOINT reconcile_fill")
                try:
                    cur.execute("""
                        SELECT trade_id, entry_price, stop_loss_price, entry_quantity
                        FROM algo_trades
                        WHERE symbol = %s
                          AND status = 'closed'
                          AND exit_date >= %s
                          AND exit_date <= %s
                        ORDER BY exit_date DESC LIMIT 1
                    """, (symbol, two_days_ago, reconcile_date))

                    row = cur.fetchone()
                    if not row:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        continue

                    trade_id, entry_price, stop_loss_price, entry_qty = row
                    entry_price = float(entry_price or 0)
                    stop_loss_price = float(stop_loss_price or 0)
                    entry_qty = int(entry_qty or 0)
                    if entry_price <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        continue

                    pnl_pct = (filled_price - entry_price) / entry_price * 100.0
                    pnl_dollars = (filled_price - entry_price) * entry_qty
                    risk = entry_price - stop_loss_price
                    exit_r_multiple = ((filled_price - entry_price) / risk) if risk > 0 else 0.0

                    # Check if this trade had an estimated exit price (Phase 4 pre-market exit)
                    cur.execute(
                        "SELECT estimated_exit_price FROM algo_trades WHERE trade_id = %s",
                        (trade_id,)
                    )
                    est_row = cur.fetchone()
                    estimated_price = float(est_row[0]) if est_row and est_row[0] else None

                    # Calculate reconciliation note with variance if estimated price exists
                    reconciliation_note = None
                    if estimated_price and estimated_price > 0:
                        variance_pct = ((filled_price - estimated_price) / estimated_price * 100.0)
                        reconciliation_note = f"Actual: ${filled_price:.2f} vs Estimated: ${estimated_price:.2f} ({variance_pct:+.2f}%)"

                    cur.execute("""
                        UPDATE algo_trades
                        SET exit_price = %s, profit_loss_pct = %s,
                            profit_loss_dollars = %s, exit_r_multiple = %s,
                            exit_price_reconciled_at = CURRENT_TIMESTAMP,
                            reconciliation_note = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE trade_id = %s
                    """, (filled_price, pnl_pct, pnl_dollars, exit_r_multiple, reconciliation_note, trade_id))

                    cur.execute("RELEASE SAVEPOINT reconcile_fill")
                    updated += 1
                    logger.info(f"   Exit fill reconciled: {symbol} {trade_id} @ ${filled_price:.2f} ({pnl_pct:.1f}%)")
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT reconcile_fill")
                    logger.warning(f"   Exit fill reconcile failed for {symbol}: {e}")

            return {'updated': updated, 'message': f'Reconciled {updated} exit fills with actual Alpaca prices'}
        except Exception as e:
            logger.warning(f'Exit fill reconciliation error: {e}')
            return {'updated': 0, 'message': f'Error: {e}'}

    def audit_stale_estimated_prices(self, cur) -> dict:
        """Audit for trades with estimated exit prices that haven't been reconciled.

        CRITICAL: If Phase 7 reconciliation doesn't run or fails, estimated prices
        remain permanent with no way to distinguish them from actual prices.
        This audit detects stale estimated prices > 1 day old that are stuck.

        Returns: dict with stale_count, stale_trades list, alert message if any found
        """
        try:
            # Find trades with estimated prices that should have been reconciled by now
            # Trades closed yesterday or earlier with NO reconciliation timestamp
            cur.execute("""
                SELECT trade_id, symbol, exit_date, estimated_exit_price, exit_price,
                       exit_price_reconciled_at
                FROM algo_trades
                WHERE estimated_exit_price IS NOT NULL
                  AND exit_price_reconciled_at IS NULL
                  AND exit_date < CURRENT_DATE
                ORDER BY exit_date ASC
                LIMIT 100
            """)
            stale_trades = cur.fetchall()

            if stale_trades:
                alert_msg = (
                    f"CRITICAL: {len(stale_trades)} trades have estimated exit prices "
                    f"that were not reconciled. Phase 7 reconciliation may have failed. "
                    f"First stale trade: {stale_trades[0][1]} closed {stale_trades[0][2]}"
                )
                logger.critical(alert_msg)
                try:
                    notify('critical', title='Exit Price Reconciliation Failed',
                           message=alert_msg)
                except Exception as e:
                    logger.warning(f"Failed to send reconciliation alert: {e}")
                return {
                    'status': 'STALE_ESTIMATED_PRICES',
                    'stale_count': len(stale_trades),
                    'stale_trades': [
                        {'trade_id': t[0], 'symbol': t[1], 'exit_date': t[2],
                         'estimated': float(t[3]), 'actual': float(t[4])}
                        for t in stale_trades
                    ],
                    'message': alert_msg
                }
            return {'status': 'OK', 'stale_count': 0, 'message': 'All estimated prices reconciled'}
        except Exception as e:
            logger.error(f"Stale price audit failed: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def sync_alpaca_positions(self, cur):
        """Pull live positions from Alpaca and sync with algo_trades (single source of truth).

        Best practice: our DB should reflect what Alpaca actually holds.
        This catches:
          - Positions opened outside our algo (manual trades)
          - Positions we tracked but Alpaca never filled
          - Drift between systems

        Since algo_trades is the single source of truth for the dashboard:
        - Compare Alpaca positions against algo_trades (not algo_positions)
        - Mark positions in algo_trades that don't exist in Alpaca as closed
        - Import new Alpaca positions as external trades
        """
        if not self._alpaca_key or not self._alpaca_secret:
            return {'imported': 0, 'orphaned': 0, 'message': 'No Alpaca credentials'}
        try:
            import requests
            from algo.algo_config import get_api_timeout
            resp = requests.get(
                f'{self._alpaca_base_url}/v2/positions',
                headers={'APCA-API-KEY-ID': self._alpaca_key,
                         'APCA-API-SECRET-KEY': self._alpaca_secret},
                timeout=get_api_timeout(),
            )
            if resp.status_code != 200:
                return {'imported': 0, 'orphaned': 0, 'message': f'Alpaca /v2/positions HTTP {resp.status_code}'}
            raw_positions = resp.json()
            # Wrap raw dicts to match expected attribute access pattern
            class _Pos:
                def __init__(self, d):
                    self.__dict__.update(d)
            alpaca_positions = [_Pos(p) for p in raw_positions]
        except Exception as e:
            return {'imported': 0, 'orphaned': 0, 'message': f'Fetch failed: {e}'}

        # Check both algo_positions and algo_trades for open positions
        cur.execute("SELECT symbol FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
        our_symbols = {row[0] for row in cur.fetchall()}

        # Also check algo_trades (the actual source of truth)
        cur.execute("""
            SELECT DISTINCT symbol FROM algo_trades
            WHERE status IN ('open', 'filled', 'partially_filled', 'active')
        """)
        algo_trades_symbols = {row[0] for row in cur.fetchall()}
        our_symbols.update(algo_trades_symbols)

        # Fetch actual portfolio value for position_size_pct calculation (not a hardcoded constant).
        cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        _pv_row = cur.fetchone()
        _portfolio_value_for_pct = float(_pv_row[0]) if _pv_row and _pv_row[0] else 0.0

        alpaca_symbols = {}  # symbol -> qty for drift detection
        imported = 0

        for ap in alpaca_positions:
            sym = ap.symbol
            qty = float(ap.qty)
            alpaca_symbols[sym] = qty

            if sym in our_symbols:
                cur.execute(
                    "SELECT quantity FROM algo_positions WHERE symbol = %s AND status = %s",
                    (sym, PositionStatus.OPEN.value)
                )
                row = cur.fetchone()
                if row:
                    db_qty = int(row[0] or 0)
                    # Shares should be integers; only allow rounding error on tiny positions (<1 share)
                    qty_int = int(round(qty))
                    if abs(db_qty - qty_int) > 0:
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

                position_id = f'EXT-{sym}-{datetime.now(timezone.utc).strftime("%Y%m%d")}'
                trade_id = f'EXT-{sym}'

                # For imported positions, calculate realistic stops + targets using volatility
                # This replaces the hardcoded placeholder values (0.92, 1.10/1.20/1.30)
                stop_loss_price = None
                target_1 = None
                target_2 = None
                target_3 = None
                stop_loss_method = 'imported_no_risk_calc'

                cur.execute("SAVEPOINT import_sp")
                try:
                    # Use pre-computed ATR from technical_data_daily (includes gap moves via
                    # max(H-L, |H-PC|, |L-PC|)). AVG(high-low) from price_daily underestimates
                    # true ATR for gap-prone stocks and sets stops too tight.
                    cur.execute("""
                        SELECT atr FROM technical_data_daily
                        WHERE symbol = %s AND atr IS NOT NULL
                        ORDER BY date DESC LIMIT 1
                    """, (sym,))
                    atr_row = cur.fetchone()
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

                cur.execute("""
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
                cur.execute("""
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
                cur.execute("ROLLBACK TO SAVEPOINT import_sp")

        # Find pending orders that haven't been filled yet (don't show in /v2/positions)
        # These should NOT be marked as orphaned, as they may still fill
        pending_symbols = set()
        if alpaca_positions:  # Only check if we successfully fetched positions
            try:
                resp = requests.get(
                    f'{self._alpaca_base_url}/v2/orders?status=pending&status=accepted&status=held',
                    headers={'APCA-API-KEY-ID': self._alpaca_key,
                             'APCA-API-SECRET-KEY': self._alpaca_secret},
                    timeout=get_api_timeout(),
                )
                if resp.status_code == 200:
                    pending_orders = resp.json() if isinstance(resp.json(), list) else []
                    pending_symbols = {order.get('symbol') for order in pending_orders if order.get('symbol')}
                    logger.debug(f"Found {len(pending_symbols)} symbols with pending orders: {pending_symbols}")
            except Exception as e:
                logger.warning(f"Could not fetch pending orders: {e}")

        # Find orphans (in our DB but not in Alpaca positions AND not pending)
        orphans = (our_symbols - set(alpaca_symbols.keys())) - pending_symbols
        if orphans:
            for sym in orphans:
                # Mark as orphaned in algo_positions (legacy)
                cur.execute("""
                    UPDATE algo_positions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status = %s
                """, (PositionStatus.ORPHANED.value, sym, PositionStatus.OPEN.value))

                # Also close positions in algo_trades (single source of truth for dashboard)
                # This ensures the dashboard doesn't show positions that don't exist in Alpaca
                # Close both: trades with no exit_date AND trades with old exit_date but wrong status
                cur.execute("""
                    UPDATE algo_trades
                    SET status = 'closed', exit_date = COALESCE(exit_date, CURRENT_DATE), updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status IN ('open', 'filled', 'partially_filled', 'active')
                """, (sym,))

                # Alert: position missing from Alpaca
                try:
                    notify(
                        severity='critical',
                        title='CRITICAL: Position Drift Detected',
                        message=f'{sym} shows as open in DB but not found in Alpaca. '
                                f'Position closed in DB to match Alpaca reality. Manual verification recommended.',
                        symbol=sym,
                        details={'symbol': sym, 'drift_type': 'orphaned_in_db', 'action': 'closed_to_sync'},
                    )
                except Exception as e:
                    logger.warning(f"  Could not send orphan alert: {e}")

        return {
            'imported': imported,
            'orphaned': len(orphans),
            'alpaca_total': len(alpaca_positions),
            'orphan_symbols': list(orphans),
            'message': f'Imported {imported} external Alpaca positions, '
                       f'{len(orphans)} orphans flagged',
        }

    def compute_analytics_metrics(self, cur):
        """E4+E5: Compute Information Coefficient and Expectancy metrics.

        E4: Weekly correlation of entry swing_score vs 5-day post-entry return.
        E5: After 30+ closed trades, compute Kelly fraction for position sizing alerts.

        Args:
            cur: Database cursor from DatabaseContext
        """
        try:
            # E4: Information Coefficient (last 8 weeks of closed trades)
            cur.execute("""
                SELECT swing_score, profit_loss_pct, trade_duration_days
                FROM algo_trades
                WHERE status = %s
                  AND exit_date >= NOW()::date - INTERVAL '56 days'
                  AND swing_score IS NOT NULL
                  AND profit_loss_pct IS NOT NULL
                ORDER BY exit_date
            """, (TradeStatus.CLOSED.value,))

            trades = cur.fetchall()
            ic_result = {'valid': False, 'ic': None, 'alert': None}

            if len(trades) >= 10:  # Need min 10 trades for meaningful IC
                # Compute rank correlation (Spearman) between swing_score and 5d returns
                try:
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
                    n = len(rank_scores)
                    if n < 2:
                        # Not enough data points for IC calculation
                        ic_result = {'valid': False, 'ic': 0, 'trade_count': len(trades), 'reason': 'Insufficient trades for IC'}
                    else:
                        mean_sr = statistics.mean(rank_scores)
                        mean_rr = statistics.mean(rank_returns)
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
            cur.execute("""
                SELECT COUNT(*), SUM(profit_loss_pct), AVG(profit_loss_pct)
                FROM algo_trades
                WHERE status = %s AND profit_loss_pct IS NOT NULL
            """, (TradeStatus.CLOSED.value,))

            stats = cur.fetchone()
            expectancy_result = {'valid': False, 'expectancy': None, 'alert': None}

            if stats and stats[0] >= 30:  # Need 30+ trades
                total_trades = stats[0]
                total_pct = float(stats[1] or 0)
                avg_return = float(stats[2] or 0)

                # Count wins and losses
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) AS wins,
                           COUNT(*) FILTER (WHERE profit_loss_pct <= 0) AS losses,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct > 0) AS avg_win,
                           AVG(profit_loss_pct) FILTER (WHERE profit_loss_pct <= 0) AS avg_loss
                    FROM algo_trades
                    WHERE status = %s
                """, (TradeStatus.CLOSED.value,))

                wr = cur.fetchone()
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

    def compute_closed_trade_metrics(self, cur):
        """E3: Compute MAE/MFE for recently closed trades (last 30 days)."""
        try:
            # Find recently closed trades without MAE/MFE
            cur.execute("""
                SELECT trade_id, symbol, trade_date, exit_date, entry_price, exit_price, exit_r_multiple
                FROM algo_trades
                WHERE status = %s
                  AND exit_date IS NOT NULL
                  AND exit_date >= NOW()::date - INTERVAL '30 days'
                  AND (mae_pct IS NULL OR mfe_pct IS NULL)
                ORDER BY exit_date DESC
            """, (TradeStatus.CLOSED.value,))

            trades_to_update = cur.fetchall()
            if not trades_to_update:
                return {'updated': 0, 'reason': 'No recently closed trades without MAE/MFE'}

            updates = 0
            for trade_id, symbol, entry_date, exit_date, entry_price, exit_price, r_mult in trades_to_update:
                try:
                    cur.execute("SAVEPOINT mae_mfe_update")
                    entry_price = float(entry_price)
                    exit_price = float(exit_price or entry_price)

                    cur.execute("""
                        SELECT high, low FROM price_daily
                        WHERE symbol = %s AND date >= %s AND date <= %s
                        ORDER BY date ASC
                    """, (symbol, entry_date, exit_date))

                    prices = cur.fetchall()
                    if not prices:
                        cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                        continue

                    # CRITICAL: Never use entry_price as fallback for high/low.
                    # Entry price is worst-case fill price, using it masks actual market excursion.
                    # Example: stop-loss hit at -5%, entry used as high/low → MAE shows -0.01% (entry price ≈ high/low).
                    # This corrupts strategy evaluation and makes losing trades appear safer.
                    # Instead: skip MAE/MFE if price data incomplete (leave NULL in DB).
                    highs = [float(p[0]) for p in prices if p[0] is not None]
                    lows = [float(p[1]) for p in prices if p[1] is not None]

                    # Only compute MAE/MFE if we have complete high/low data for the period
                    if not highs or not lows:
                        logger.warning(
                            f"Incomplete OHLCV data for trade {trade_id} ({symbol}) {entry_date} to {exit_date}: "
                            f"skipping MAE/MFE computation to avoid fallback-induced corruption"
                        )
                        cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                        continue

                    # MAE: worst (lowest) price from entry
                    min_price = min(lows)
                    mae_pct = ((min_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    # MFE: best (highest) price from entry
                    max_price = max(highs)
                    mfe_pct = ((max_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0

                    cur.execute("""
                        UPDATE algo_trades
                        SET mae_pct = %s, mfe_pct = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE trade_id = %s
                    """, (round(mae_pct, 4), round(mfe_pct, 4), trade_id))

                    cur.execute("RELEASE SAVEPOINT mae_mfe_update")
                    updates += 1
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT mae_mfe_update")
                    logger.warning(f"Failed to compute MAE/MFE for trade {trade_id}: {e}")

            return {'updated': updates, 'reason': f'Computed MAE/MFE for {updates} closed trades'}
        except Exception as e:
            logger.error(f"Error in compute_closed_trade_metrics: {e}")
            return {'updated': 0, 'reason': f'Error: {e}'}

    def check_pending_reconciliations(self, cur) -> dict:
        """Identify and report on trades pending Phase 7 price reconciliation.

        Trades with estimated exit prices (Phase 4 pre-market exits) that haven't
        been reconciled with actual Alpaca fill prices. Helps diagnose Phase 7
        failures or delays that leave estimated prices permanent.
        """
        try:
            cur.execute("""
                SELECT trade_id, symbol, exit_date, exit_price, estimated_exit_price,
                       exit_price_reconciled_at, reconciliation_note
                FROM algo_trades
                WHERE estimated_exit_price IS NOT NULL
                  AND exit_price_reconciled_at IS NULL
                ORDER BY exit_date DESC
            """)
            pending = cur.fetchall()

            if not pending:
                return {'pending_count': 0, 'message': 'No pending reconciliations'}

            pending_list = []
            for trade_id, symbol, exit_date, exit_price, est_price, recon_at, note in pending:
                variance_pct = ((float(exit_price or 0) - float(est_price or 0)) / float(est_price or 1) * 100) if est_price else 0
                pending_list.append({
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'exit_date': exit_date,
                    'estimated_price': float(est_price) if est_price else None,
                    'current_exit_price': float(exit_price) if exit_price else None,
                    'variance_pct': variance_pct,
                    'note': note,
                    'days_pending': (datetime.now(timezone.utc).date() - exit_date).days if exit_date else None
                })

            # Log critical alert if any reconciliations are stuck (> 1 day old)
            stuck = [p for p in pending_list if p['days_pending'] and p['days_pending'] > 1]
            if stuck:
                stuck_examples = ', '.join(['{} {}'.format(p['symbol'], p['trade_id']) for p in stuck[:3]])
                logger.critical(
                    f"RECONCILIATION STUCK: {len(stuck)} trades with estimated exit prices "
                    f"stuck > 1 day without Alpaca price reconciliation. "
                    f"Examples: {stuck_examples}"
                )

            return {
                'pending_count': len(pending_list),
                'stuck_count': len(stuck),
                'pending': pending_list,
                'message': f'{len(pending_list)} trades pending reconciliation ({len(stuck)} stuck > 1d)'
            }
        except Exception as e:
            logger.warning(f"Failed to check pending reconciliations: {e}")
            return {'pending_count': 0, 'message': f'Error: {e}'}

    def _fetch_alpaca_account(self):
        """Fetch account data from Alpaca via direct HTTP REST call."""
        if not self._alpaca_key or not self._alpaca_secret:
            return None
        try:
            import requests
            resp = requests.get(
                f'{self._alpaca_base_url}/v2/account',
                headers={'APCA-API-KEY-ID': self._alpaca_key,
                         'APCA-API-SECRET-KEY': self._alpaca_secret},
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                data = resp.json()
                cash_val = data.get('cash')
                equity_val = data.get('equity')
                portfolio_value_val = data.get('portfolio_value') or data.get('equity')
                buying_power_val = data.get('buying_power')
                return {
                    'cash': float(cash_val) if cash_val is not None else None,
                    'equity': float(equity_val) if equity_val is not None else None,
                    'portfolio_value': float(portfolio_value_val) if portfolio_value_val is not None else None,
                    'buying_power': float(buying_power_val) if buying_power_val is not None else None,
                }
            logger.warning(f"Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:100]}")
            return None
        except Exception as e:
            logger.warning(f"Could not fetch Alpaca account (skipping): {e}")
            return None

    def _fetch_initial_capital(self, cur):
        """Get the actual initial capital from Alpaca account history.

        Returns the oldest portfolio value from Alpaca portfolio history.
        Falls back to the oldest algo_portfolio_snapshots entry if Alpaca history unavailable.
        Raises ValueError if initial capital cannot be determined.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            logger.warning("No Alpaca credentials; checking database for initial capital")
            try:
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0]:
                    val = float(row[0])
                    if val > 0:
                        logger.info(f"Using oldest database snapshot as initial capital: ${val:,.2f}")
                        return val
            except Exception as e:
                logger.warning(f"Could not query database for initial capital: {e}")
            raise ValueError("Cannot determine initial capital: no Alpaca credentials and no database history")

        try:
            import requests
            resp = requests.get(
                f'{self._alpaca_base_url}/v2/account/portfolio/history',
                params={'period': 'all'},
                headers={'APCA-API-KEY-ID': self._alpaca_key,
                         'APCA-API-SECRET-KEY': self._alpaca_secret},
                timeout=get_api_timeout(),
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and 'equity' in data:
                    equity_list = data.get('equity', [])
                    if equity_list and len(equity_list) > 0:
                        initial_val = float(equity_list[0])
                        if initial_val > 0:
                            logger.info(f"Initial capital from Alpaca history: ${initial_val:,.2f}")
                            return initial_val
            logger.warning(f"Alpaca portfolio history unavailable (HTTP {resp.status_code}); checking database")
        except Exception as e:
            logger.warning(f"Could not fetch Alpaca portfolio history: {e}; checking database")

        try:
            cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date ASC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row[0]:
                val = float(row[0])
                if val > 0:
                    logger.info(f"Using oldest database snapshot as initial capital: ${val:,.2f}")
                    return val
        except Exception as e:
            logger.warning(f"Could not query database for initial capital: {e}")

        raise ValueError("Cannot determine initial capital: Alpaca history unavailable and no database snapshots found")

if __name__ == "__main__":

    config = get_config()
    reconciliation = DailyReconciliation(config)

    result = reconciliation.run_daily_reconciliation()
    logger.info(f"Result: {result}")

