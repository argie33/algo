#!/usr/bin/env python3
"""
Trade Executor - Execute trades via Alpaca and track positions

Features:
- Idempotent entry (no duplicate trades for same symbol on same day)
- Atomic DB transactions for entry/exit
- Partial exits with weighted-cost-basis P&L (T1 = 50%, T2 = 25%, T3 = 25%)
- R-multiple computed against actual stop loss (not a placeholder)
- Trailing stop adjustments after profit-taking levels
- Paper, dry, review, and auto execution modes
"""

import os
import psycopg2
import uuid
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import requests

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class TradeExecutor:
    """Execute trades via Alpaca and track in database."""

    def __init__(self, config):
        self.config = config
        self.alpaca_key = os.getenv('APCA_API_KEY_ID')
        self.alpaca_secret = os.getenv('APCA_API_SECRET_KEY')
        self.alpaca_base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    # ---------- Entry ----------

    def execute_trade(self, symbol, entry_price, shares, stop_loss_price,
                      target_1_price=None, target_2_price=None, target_3_price=None,
                      signal_date=None, sqs=None, trend_score=None,
                      # New reasoning metadata for transparency:
                      swing_score=None, swing_grade=None,
                      base_type=None, base_quality=None, stage_phase=None,
                      sector=None, industry=None, rs_percentile=None,
                      market_exposure_at_entry=None, exposure_tier_at_entry=None,
                      stop_method=None, stop_reasoning=None,
                      swing_components=None, advanced_components=None):
        """Execute a new entry trade.

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str,
            'duplicate': bool (only when blocked by idempotency)
        }
        """
        if not signal_date:
            signal_date = datetime.now().date()

        # Compute targets if missing — based on R-multiples from actual stop
        risk_per_share = entry_price - stop_loss_price
        if risk_per_share <= 0:
            return {
                'success': False, 'trade_id': '', 'status': 'invalid',
                'message': 'Invalid stop (>= entry)'
            }
        if target_1_price is None:
            t1_r = float(self.config.get('t1_target_r_multiple', 1.5))
            target_1_price = round(entry_price + (risk_per_share * t1_r), 2)
        if target_2_price is None:
            t2_r = float(self.config.get('t2_target_r_multiple', 3.0))
            target_2_price = round(entry_price + (risk_per_share * t2_r), 2)
        if target_3_price is None:
            t3_r = float(self.config.get('t3_target_r_multiple', 4.0))
            target_3_price = round(entry_price + (risk_per_share * t3_r), 2)

        self.connect()
        try:
            # ---- Idempotency: skip if we already have an open position for this symbol
            #     OR an entry trade for this symbol on this signal_date ----
            self.cur.execute(
                "SELECT 1 FROM algo_positions WHERE symbol = %s AND status = 'open' LIMIT 1",
                (symbol,),
            )
            if self.cur.fetchone():
                return {
                    'success': False, 'trade_id': '', 'status': 'duplicate', 'duplicate': True,
                    'message': f'Already have open position in {symbol}'
                }

            self.cur.execute(
                """
                SELECT trade_id FROM algo_trades
                WHERE symbol = %s AND signal_date = %s AND status IN ('filled','active','pending')
                LIMIT 1
                """,
                (symbol, signal_date),
            )
            existing = self.cur.fetchone()
            if existing:
                return {
                    'success': False, 'trade_id': existing[0], 'status': 'duplicate', 'duplicate': True,
                    'message': f'Trade already exists for {symbol} on {signal_date}'
                }

            execution_mode = self.config.get('execution_mode', 'paper')
            trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"

            if execution_mode in ('paper', 'dry'):
                alpaca_order_id = f'LOCAL-{trade_id}'
                order_status = 'filled'
                executed_price = entry_price
            elif execution_mode == 'review':
                alpaca_order_id = f'PENDING-{trade_id}'
                order_status = 'pending_review'
                executed_price = entry_price
            else:  # 'auto' — actually send to Alpaca as BRACKET ORDER
                order_result = self._send_alpaca_order(
                    symbol, shares, entry_price,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=target_1_price,  # T1 as take-profit leg
                    order_class='bracket',
                )
                if not order_result['success']:
                    return {
                        'success': False, 'trade_id': trade_id, 'status': 'failed',
                        'message': order_result.get('message', 'Order failed')
                    }
                alpaca_order_id = order_result['order_id']
                order_status = order_result.get('status', 'pending')
                executed_price = order_result.get('executed_price', entry_price)

            # Compute initial position size pct using live or snapshot portfolio value
            portfolio_value = self._get_portfolio_value() or 100000.0
            position_size_pct = (shares * executed_price / portfolio_value * 100) if portfolio_value > 0 else 0

            # Build comprehensive entry reason
            entry_reason_parts = ['Algo signal — all tiers passed']
            if swing_grade:
                entry_reason_parts.append(f'swing_grade={swing_grade}')
            if base_type:
                entry_reason_parts.append(f'base={base_type}')
            if stage_phase:
                entry_reason_parts.append(f'phase={stage_phase}')
            if exposure_tier_at_entry:
                entry_reason_parts.append(f'exposure={exposure_tier_at_entry}')
            entry_reason = ' | '.join(entry_reason_parts)

            # Insert with FULL reasoning
            self.cur.execute(
                """
                INSERT INTO algo_trades (
                    trade_id, symbol, signal_date, trade_date,
                    entry_price, entry_quantity, entry_reason,
                    stop_loss_price, stop_loss_method,
                    target_1_price, target_1_r_multiple,
                    target_2_price, target_2_r_multiple,
                    target_3_price, target_3_r_multiple,
                    status, execution_mode, alpaca_order_id,
                    position_size_pct, signal_quality_score, trend_template_score,
                    swing_score, swing_grade,
                    base_type, base_quality, stage_phase,
                    sector, industry, rs_percentile,
                    market_exposure_at_entry, exposure_tier_at_entry,
                    stop_method, stop_reasoning,
                    swing_components, advanced_components, bracket_order,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    CURRENT_TIMESTAMP
                )
                """,
                (
                    trade_id, symbol, signal_date, datetime.now().date(),
                    executed_price, shares, entry_reason,
                    stop_loss_price, stop_method or 'minervini_break_or_swing_low',
                    target_1_price, float(self.config.get('t1_target_r_multiple', 1.5)),
                    target_2_price, float(self.config.get('t2_target_r_multiple', 3.0)),
                    target_3_price, float(self.config.get('t3_target_r_multiple', 4.0)),
                    order_status, execution_mode, alpaca_order_id,
                    position_size_pct,
                    int(sqs) if sqs is not None else None,
                    int(trend_score) if trend_score is not None else None,
                    swing_score, swing_grade,
                    base_type, base_quality, stage_phase,
                    sector, industry, rs_percentile,
                    market_exposure_at_entry, exposure_tier_at_entry,
                    stop_method, stop_reasoning,
                    json.dumps(swing_components) if swing_components else None,
                    json.dumps(advanced_components) if advanced_components else None,
                    execution_mode == 'auto',  # bracket_order = True only in auto mode
                ),
            )

            # Insert / open position record
            if order_status == 'filled':
                position_id = f'POS-{trade_id}'
                position_value = shares * executed_price
                self.cur.execute(
                    """
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, status,
                        trade_ids, current_stop_price, target_levels_hit,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, 'open',
                        %s, %s, 0, CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        position_id, symbol, shares, executed_price,
                        executed_price, position_value,
                        trade_id, stop_loss_price,
                    ),
                )

            self.conn.commit()
            return {
                'success': True,
                'trade_id': trade_id,
                'alpaca_order_id': alpaca_order_id,
                'status': order_status,
                'message': f'{shares} sh {symbol} @ ${executed_price:.2f} (stop ${stop_loss_price:.2f})',
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {
                'success': False, 'trade_id': '', 'status': 'error',
                'message': f'{type(e).__name__}: {e}'
            }
        finally:
            self.disconnect()

    # ---------- Exit (full or partial) ----------

    def exit_trade(self, trade_id, exit_price, exit_reason, exit_fraction=1.0,
                   exit_stage=None, new_stop_price=None):
        """Exit all or part of a position.

        Args:
            trade_id: trade to exit
            exit_price: execution price for the exit
            exit_reason: reason text (logged in algo_trades + algo_audit_log)
            exit_fraction: 0 < f <= 1 (1.0 = full exit)
            exit_stage: optional 'target_1' | 'target_2' | 'target_3' | 'stop' | 'time' | 'distribution'
            new_stop_price: if provided, raise the stop on the residual shares (trailing stop)

        Returns: { success, trade_id, shares_exited, profit_loss_dollars, profit_loss_pct, message }
        """
        if not (0 < exit_fraction <= 1.0):
            return {'success': False, 'message': f'Invalid exit_fraction {exit_fraction}'}

        self.connect()
        try:
            self.cur.execute(
                """
                SELECT t.symbol, t.entry_price, t.entry_quantity, t.stop_loss_price,
                       p.position_id, p.quantity, p.target_levels_hit
                FROM algo_trades t
                LEFT JOIN algo_positions p ON p.trade_ids LIKE '%%' || t.trade_id || '%%'
                                         AND p.status = 'open'
                WHERE t.trade_id = %s
                """,
                (trade_id,),
            )
            row = self.cur.fetchone()
            if not row:
                return {'success': False, 'message': f'Trade {trade_id} not found'}
            symbol, entry_price, entry_qty, stop_loss_price, position_id, current_qty, target_hits = row

            entry_price = float(entry_price)
            entry_qty = int(entry_qty)
            stop_loss_price = float(stop_loss_price)
            current_qty = int(current_qty) if current_qty else 0
            target_hits = int(target_hits) if target_hits else 0

            if current_qty <= 0 and not position_id:
                return {'success': False, 'message': f'No open position for {trade_id}'}

            # Shares to exit
            shares_to_exit = max(1, int(current_qty * exit_fraction))
            shares_to_exit = min(shares_to_exit, current_qty)
            full_exit = shares_to_exit >= current_qty

            # Profit calc against actual entry
            risk_per_share = entry_price - stop_loss_price
            r_multiple = ((exit_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0
            pnl_per_share = exit_price - entry_price
            pnl_dollars = pnl_per_share * shares_to_exit
            pnl_pct = (pnl_per_share / entry_price * 100) if entry_price > 0 else 0

            # In auto mode, send the exit order to Alpaca
            execution_mode = self.config.get('execution_mode', 'paper')
            if execution_mode == 'auto':
                self._send_alpaca_exit(symbol, shares_to_exit)

            # Update the trade record
            if full_exit:
                self.cur.execute(
                    """
                    UPDATE algo_trades
                    SET exit_date = CURRENT_DATE,
                        exit_price = %s,
                        exit_reason = %s,
                        exit_r_multiple = %s,
                        profit_loss_dollars = %s,
                        profit_loss_pct = %s,
                        status = 'closed'
                    WHERE trade_id = %s
                    """,
                    (exit_price, exit_reason, r_multiple, pnl_dollars, pnl_pct, trade_id),
                )
            else:
                # Partial exit — append to exit log column, keep status active
                self.cur.execute(
                    """
                    UPDATE algo_trades
                    SET partial_exits_log = COALESCE(partial_exits_log, '') ||
                            CASE WHEN partial_exits_log IS NULL OR partial_exits_log = '' THEN '' ELSE '; ' END ||
                            %s,
                        partial_exit_count = COALESCE(partial_exit_count, 0) + 1,
                        last_partial_exit_date = CURRENT_DATE,
                        status = 'active'
                    WHERE trade_id = %s
                    """,
                    (
                        f"{shares_to_exit}sh @ ${exit_price:.2f} ({exit_reason}, {r_multiple:.2f}R)",
                        trade_id,
                    ),
                )

            # Update the position
            new_qty = current_qty - shares_to_exit
            if full_exit or new_qty <= 0:
                self.cur.execute(
                    """
                    UPDATE algo_positions
                    SET status = 'closed', quantity = 0, closed_at = CURRENT_TIMESTAMP
                    WHERE position_id = %s
                    """,
                    (position_id,),
                )
            else:
                # New stop (trailing) and incremented target_levels_hit
                effective_stop = new_stop_price if new_stop_price is not None else stop_loss_price
                self.cur.execute(
                    """
                    UPDATE algo_positions
                    SET quantity = %s,
                        position_value = %s * current_price,
                        target_levels_hit = COALESCE(target_levels_hit, 0) + 1,
                        current_stop_price = %s
                    WHERE position_id = %s
                    """,
                    (new_qty, new_qty, effective_stop, position_id),
                )

            # Audit log
            try:
                import json
                self.cur.execute(
                    """
                    INSERT INTO algo_audit_log (action_type, symbol, action_date,
                                                details, actor, status, created_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"exit_{exit_stage or 'manual'}", symbol,
                        json.dumps({
                            'trade_id': trade_id,
                            'shares_exited': shares_to_exit,
                            'exit_price': float(exit_price),
                            'r_multiple': float(r_multiple),
                            'pnl_dollars': float(pnl_dollars),
                            'pnl_pct': float(pnl_pct),
                            'reason': exit_reason,
                            'full_exit': full_exit,
                        }),
                        'algo_executor',
                        'success',
                    ),
                )
            except Exception:
                pass  # audit best-effort

            self.conn.commit()
            return {
                'success': True,
                'trade_id': trade_id,
                'shares_exited': shares_to_exit,
                'profit_loss_dollars': pnl_dollars,
                'profit_loss_pct': pnl_pct,
                'r_multiple': r_multiple,
                'full_exit': full_exit,
                'message': (
                    f'Exited {shares_to_exit}sh of {symbol} @ ${exit_price:.2f} '
                    f'({pnl_pct:+.2f}%, {r_multiple:+.2f}R)'
                ),
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            return {'success': False, 'message': f'{type(e).__name__}: {e}'}
        finally:
            self.disconnect()

    # ---------- Helpers ----------

    def _get_portfolio_value(self):
        """Live Alpaca equity, fall back to latest snapshot."""
        if self.alpaca_key and self.alpaca_secret:
            try:
                resp = requests.get(
                    f'{self.alpaca_base_url}/v2/account',
                    headers={'APCA-API-KEY-ID': self.alpaca_key,
                             'APCA-API-SECRET-KEY': self.alpaca_secret},
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    pv = data.get('portfolio_value') or data.get('equity')
                    if pv is not None:
                        return float(pv)
            except Exception:
                pass
        try:
            self.cur.execute(
                "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
                "ORDER BY snapshot_date DESC LIMIT 1"
            )
            row = self.cur.fetchone()
            if row and row[0]:
                return float(row[0])
        except Exception:
            pass
        return None

    def _send_alpaca_order(self, symbol, shares, entry_price, stop_loss_price=None,
                           take_profit_price=None, order_class='bracket'):
        """Send a BRACKET order to Alpaca — entry + stop loss + take profit.

        This is the institutional best practice: even if our system goes down,
        Alpaca enforces the stop loss and take profit. No naked positions.

        Bracket order: parent buy fills, then OCO (one-cancels-other) of:
          - Stop loss order (executes if price drops to stop)
          - Take profit limit order (executes if price hits target)

        Falls back to simple limit order if bracket can't be sent (no stop).
        """
        if not self.alpaca_key or not self.alpaca_secret:
            return {'success': False, 'message': 'Alpaca credentials not configured'}
        try:
            # Build order payload
            order_data = {
                'symbol': symbol,
                'qty': shares,
                'side': 'buy',
                'type': 'limit',
                'time_in_force': 'day',
                'limit_price': str(round(entry_price, 2)),
                'extended_hours': False,
            }

            # If we have a stop, send as bracket order with stop loss
            if stop_loss_price and stop_loss_price > 0 and order_class == 'bracket':
                order_data['order_class'] = 'bracket'
                order_data['stop_loss'] = {
                    'stop_price': str(round(stop_loss_price, 2)),
                }
                # Take profit: if provided, use it; else use first target (1.5R)
                if take_profit_price and take_profit_price > entry_price:
                    order_data['take_profit'] = {
                        'limit_price': str(round(take_profit_price, 2)),
                    }
                else:
                    # Default: T1 at 1.5R as the take-profit leg
                    risk = entry_price - stop_loss_price
                    if risk > 0:
                        tp = entry_price + (1.5 * risk)
                        order_data['take_profit'] = {
                            'limit_price': str(round(tp, 2)),
                        }

            response = requests.post(
                f'{self.alpaca_base_url}/v2/orders',
                json=order_data,
                headers={'APCA-API-KEY-ID': self.alpaca_key,
                         'APCA-API-SECRET-KEY': self.alpaca_secret},
                timeout=10,
            )
            if response.status_code in (200, 201):
                data = response.json()
                return {
                    'success': True,
                    'order_id': data.get('id', 'unknown'),
                    'order_class': data.get('order_class', 'simple'),
                    'status': data.get('status', 'pending'),
                    'executed_price': entry_price,
                    'legs': data.get('legs', []),  # bracket child orders
                }
            return {'success': False, 'message': f'Alpaca {response.status_code}: {response.text[:200]}'}
        except Exception as e:
            return {'success': False, 'message': f'Request failed: {e}'}

    def _send_alpaca_exit(self, symbol, shares):
        """Send a sell order to Alpaca (best effort)."""
        if not self.alpaca_key or not self.alpaca_secret:
            return None
        try:
            requests.post(
                f'{self.alpaca_base_url}/v2/orders',
                json={
                    'symbol': symbol,
                    'qty': shares,
                    'side': 'sell',
                    'type': 'market',
                    'time_in_force': 'day',
                },
                headers={'APCA-API-KEY-ID': self.alpaca_key,
                         'APCA-API-SECRET-KEY': self.alpaca_secret},
                timeout=10,
            )
        except Exception:
            pass


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    executor = TradeExecutor(config)
    result = executor.execute_trade(
        symbol='AAPL', entry_price=150.00, shares=100, stop_loss_price=142.50,
    )
    print(f"Trade Execution Test:")
    print(f"  Success: {result['success']}")
    print(f"  Trade ID: {result['trade_id']}")
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}")
