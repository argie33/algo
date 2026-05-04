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

import os
import psycopg2
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import json

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

class DailyReconciliation:
    """Daily reconciliation and portfolio snapshot creation."""

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

    def run_daily_reconciliation(self, reconcile_date=None):
        """Run full daily reconciliation."""
        if not reconcile_date:
            reconcile_date = datetime.now().date()

        self.connect()

        try:
            print(f"\n{'='*70}")
            print(f"DAILY RECONCILIATION - {reconcile_date}")
            print(f"{'='*70}\n")

            # 1. Fetch Alpaca account
            alpaca_data = self._fetch_alpaca_account()
            if not alpaca_data:
                alpaca_data = {'cash': 100000, 'equity': 100000, 'portfolio_value': 100000}

            print(f"1. Alpaca Account:")
            print(f"   Portfolio Value: ${alpaca_data.get('portfolio_value', 0):,.2f}")
            print(f"   Cash: ${alpaca_data.get('cash', 0):,.2f}")
            print(f"   Equity: ${alpaca_data.get('equity', 0):,.2f}")

            # 1b. Sync Alpaca positions into our DB (imports any external positions)
            sync_result = self.sync_alpaca_positions()
            print(f"\n1b. Position Sync:")
            print(f"   {sync_result['message']}")
            if sync_result.get('orphan_symbols'):
                print(f"   Orphans flagged: {', '.join(sync_result['orphan_symbols'][:5])}")

            # 2. Get open positions from database
            self.cur.execute("""
                SELECT position_id, symbol, quantity, avg_entry_price, current_price, position_value
                FROM algo_positions
                WHERE status = 'open'
                ORDER BY symbol
            """)

            positions = self.cur.fetchall()
            print(f"\n2. Database Positions: {len(positions)} open")

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

                print(f"   {symbol}: {qty_f:.0f} @ ${entry_f:.2f} -> ${current_f:.2f} | {pnl:+,.2f} ({pnl_pct:+.2f}%)")

            # 3. Calculate metrics
            cash = alpaca_data.get('cash', 100000)
            total_equity = cash + total_position_value

            if total_equity > 0:
                unrealized_pnl_pct = (unrealized_pnl / total_equity) * 100

            largest_position = float(max([p[5] for p in positions], default=0) or 0)
            max_concentration = (largest_position / total_equity * 100.0) if total_equity > 0 else 0.0

            avg_position_size = (total_position_value / len(positions)) if positions else 0.0

            # 4. Get previous snapshot for daily return
            self.cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)

            prev_snapshot = self.cur.fetchone()
            prev_value = float(prev_snapshot[0]) if prev_snapshot else total_equity
            daily_return = total_equity - prev_value
            daily_return_pct = (daily_return / prev_value * 100) if prev_value > 0 else 0

            # 5. Get market health
            self.cur.execute("""
                SELECT market_trend, distribution_days_4w
                FROM market_health_daily
                WHERE date = %s
            """, (reconcile_date,))

            market = self.cur.fetchone()
            market_trend = market[0] if market else 'unknown'
            dist_days = market[1] if market else 0

            # 6. Create portfolio snapshot
            self.cur.execute("""
                INSERT INTO algo_portfolio_snapshots (
                    snapshot_date, total_portfolio_value, total_cash, total_equity,
                    position_count, largest_position_pct, average_position_size_pct,
                    unrealized_pnl_total, unrealized_pnl_pct,
                    daily_return_pct, market_health_status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (snapshot_date) DO UPDATE SET
                    total_portfolio_value = EXCLUDED.total_portfolio_value,
                    total_equity = EXCLUDED.total_equity,
                    unrealized_pnl_total = EXCLUDED.unrealized_pnl_total
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

            print(f"\n3. Portfolio Summary:")
            print(f"   Total Value: ${total_equity:,.2f}")
            print(f"   Position Value: ${total_position_value:,.2f}")
            print(f"   Cash: ${cash:,.2f}")
            print(f"   Unrealized P&L: {unrealized_pnl:+,.2f} ({unrealized_pnl_pct:+.2f}%)")
            print(f"   Daily Return: {daily_return_pct:+.2f}%")
            print(f"   Concentration: {max_concentration:.1f}%")

            print(f"\n{'='*70}")
            print(f"Reconciliation complete - snapshot created")
            print(f"{'='*70}\n")

            return {
                'success': True,
                'portfolio_value': total_equity,
                'positions': len(positions),
                'unrealized_pnl': unrealized_pnl
            }

        except Exception as e:
            print(f"Error in reconciliation: {e}")
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
        if not self.alpaca_key or not self.alpaca_secret:
            return {'imported': 0, 'orphaned': 0, 'message': 'No Alpaca creds'}
        try:
            r = requests.get(
                f'{self.alpaca_base_url}/v2/positions',
                headers={'APCA-API-KEY-ID': self.alpaca_key,
                         'APCA-API-SECRET-KEY': self.alpaca_secret},
                timeout=10,
            )
            if r.status_code != 200:
                return {'imported': 0, 'orphaned': 0, 'message': f'Alpaca {r.status_code}'}
            alpaca_positions = r.json()
        except Exception as e:
            return {'imported': 0, 'orphaned': 0, 'message': f'Fetch failed: {e}'}

        # Get current symbols in our DB
        self.cur.execute("SELECT symbol FROM algo_positions WHERE status = 'open'")
        our_symbols = {row[0] for row in self.cur.fetchall()}

        alpaca_symbols = {}  # symbol -> qty for drift detection
        imported = 0

        for ap in alpaca_positions:
            sym = ap.get('symbol')
            qty = float(ap.get('qty', 0))
            alpaca_symbols[sym] = qty

            if sym in our_symbols:
                # Check for quantity drift
                self.cur.execute(
                    "SELECT quantity FROM algo_positions WHERE symbol = %s AND status = 'open'",
                    (sym,)
                )
                row = self.cur.fetchone()
                if row:
                    db_qty = int(row[0] or 0)
                    if abs(db_qty - qty) > 0.1:  # Allow small rounding differences
                        try:
                            from algo_notifications import notify
                            notify(
                                kind='position_drift',
                                severity='critical',
                                title='CRITICAL: Quantity Mismatch',
                                message=f'{sym} has {qty:.0f} shares on Alpaca but '
                                        f'{db_qty} in DB. Manual intervention required.',
                                details={'symbol': sym, 'alpaca_qty': qty, 'db_qty': db_qty},
                            )
                        except Exception as e:
                            print(f"  Warning: Could not send quantity drift alert: {e}")
                continue  # already tracked

            # Import this Alpaca position as a manual/external one
            try:
                qty = float(ap.get('qty', 0))
                avg_entry = float(ap.get('avg_entry_price', 0))
                cur_price = float(ap.get('current_price', avg_entry))
                pos_value = float(ap.get('market_value', qty * cur_price))
                pnl = float(ap.get('unrealized_pl', 0))
                pnl_pct = float(ap.get('unrealized_plpc', 0)) * 100

                if qty <= 0:
                    continue  # short or zero — skip

                position_id = f'EXT-{sym}-{datetime.now().strftime("%Y%m%d")}'
                trade_id = f'EXT-{sym}'

                # Insert a placeholder trade for tracking
                self.cur.execute("""
                    INSERT INTO algo_trades (
                        trade_id, symbol, signal_date, trade_date,
                        entry_price, entry_quantity, entry_reason,
                        stop_loss_price, stop_loss_method,
                        target_1_price, target_2_price, target_3_price,
                        status, execution_mode, alpaca_order_id,
                        position_size_pct, base_type, created_at
                    )
                    VALUES (%s, %s, CURRENT_DATE, CURRENT_DATE, %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, 'filled', 'external', %s,
                            %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (trade_id) DO NOTHING
                """, (
                    trade_id, sym, avg_entry, int(qty),
                    'EXTERNAL: existing Alpaca position imported',
                    avg_entry * 0.92,  # placeholder 8% stop
                    'imported_no_stop',
                    avg_entry * 1.10, avg_entry * 1.20, avg_entry * 1.30,  # placeholders
                    f'ALPACA-EXT-{sym}',
                    pos_value / 100000.0 * 100,  # rough %
                    'imported_external',
                ))

                # Insert position
                self.cur.execute("""
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, unrealized_pnl,
                        unrealized_pnl_pct, status, trade_ids_arr,
                        current_stop_price, target_levels_hit, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              'open', %s, %s, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (position_id) DO NOTHING
                """, (
                    position_id, sym, int(qty), avg_entry, cur_price,
                    pos_value, pnl, pnl_pct, [trade_id],
                    avg_entry * 0.92,  # placeholder 8% stop
                ))
                imported += 1
            except Exception as e:
                print(f"  Failed to import {sym}: {e}")
                self.conn.rollback()

        # Find orphans (in our DB but not Alpaca)
        orphans = our_symbols - alpaca_symbols
        if orphans:
            for sym in orphans:
                self.cur.execute("""
                    UPDATE algo_positions
                    SET status = 'orphaned', updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status = 'open'
                """, (sym,))
                # Alert: position missing from Alpaca
                try:
                    from algo_notifications import notify
                    notify(
                        kind='position_drift',
                        severity='critical',
                        title='CRITICAL: Position Drift Detected',
                        message=f'{sym} shows as open in DB but not found in Alpaca. '
                                f'May indicate liquidation or external closure.',
                        details={'symbol': sym, 'drift_type': 'orphaned_in_db'},
                    )
                except Exception as e:
                    print(f"  Warning: Could not send orphan alert: {e}")

        self.conn.commit()
        return {
            'imported': imported,
            'orphaned': len(orphans),
            'alpaca_total': len(alpaca_positions),
            'orphan_symbols': list(orphans),
            'message': f'Imported {imported} external Alpaca positions, '
                       f'{len(orphans)} orphans flagged',
        }

    def _fetch_alpaca_account(self):
        """Fetch account data from Alpaca."""
        try:
            if not self.alpaca_key or not self.alpaca_secret:
                return None

            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret
            }

            response = requests.get(
                f'{self.alpaca_base_url}/v2/account',
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'cash': float(data.get('cash', 0)),
                    'equity': float(data.get('equity', 0)),
                    'portfolio_value': float(data.get('portfolio_value', 0)),
                    'buying_power': float(data.get('buying_power', 0))
                }
            else:
                return None

        except Exception as e:
            print(f"Warning: Could not fetch Alpaca account: {e}")
            return None

if __name__ == "__main__":
    from algo_config import get_config

    config = get_config()
    reconciliation = DailyReconciliation(config)

    result = reconciliation.run_daily_reconciliation()
    print(f"Result: {result}")
