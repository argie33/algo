#!/usr/bin/env python3
"""
Position Reconciliation — Verify DB matches Alpaca account state

Nightly check: query Alpaca API for all open positions and compare against
DB algo_positions. Alert on any divergence (missing position, qty mismatch,
symbol not held, etc). Catches cases where orders were filled outside our
workflow or positions were closed in Alpaca but marked open in DB.
"""

import os
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

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


class PositionReconciler:
    """Compare DB positions with Alpaca account state."""

    def __init__(self):
        self.conn = None
        self.cur = None
        try:
            from alpaca.trading.client import TradingClient
            self.trading_client = TradingClient(
                api_key=os.getenv('APCA_API_KEY_ID'),
                secret_key=os.getenv('APCA_API_SECRET_KEY'),
            )
        except Exception as e:
            print(f"  [WARN] Alpaca client init failed: {e}")
            self.trading_client = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def reconcile(self):
        """Run full reconciliation. Returns dict with findings."""
        if not self.trading_client:
            print("  [WARN] Alpaca client unavailable — skipping reconciliation")
            return {'status': 'skipped', 'reason': 'no_alpaca_client'}

        self.connect()
        try:
            print("\n" + "="*70)
            print("POSITION RECONCILIATION")
            print("="*70)

            # Get DB positions
            self.cur.execute("""
                SELECT symbol, quantity, position_id
                FROM algo_positions
                WHERE status = 'open' AND quantity > 0
                ORDER BY symbol
            """)
            db_positions = {row[0]: {'qty': row[1], 'position_id': row[2]}
                            for row in self.cur.fetchall()}

            # Get Alpaca positions
            try:
                alpaca_positions = {pos.symbol: int(pos.qty) for pos in self.trading_client.get_all_positions()}
            except Exception as e:
                print(f"  [ERROR] Could not query Alpaca positions: {e}")
                return {'status': 'error', 'reason': str(e)}

            issues = []

            # Check 1: DB positions not in Alpaca (likely closed without updating DB)
            for symbol, db_info in db_positions.items():
                if symbol not in alpaca_positions:
                    issues.append({
                        'type': 'MISSING_IN_ALPACA',
                        'symbol': symbol,
                        'db_qty': db_info['qty'],
                        'alpaca_qty': 0,
                        'severity': 'ERROR',
                    })
                    print(f"  [ERROR] {symbol}: DB open {db_info['qty']} shares but Alpaca shows 0")
                elif alpaca_positions[symbol] != db_info['qty']:
                    issues.append({
                        'type': 'QTY_MISMATCH',
                        'symbol': symbol,
                        'db_qty': db_info['qty'],
                        'alpaca_qty': alpaca_positions[symbol],
                        'severity': 'WARN',
                    })
                    print(f"  [WARN] {symbol}: DB {db_info['qty']} vs Alpaca {alpaca_positions[symbol]}")
                else:
                    print(f"  [OK] {symbol}: {db_info['qty']} shares")

            # Check 2: Alpaca positions not in DB (likely filled outside our workflow)
            for symbol, alpaca_qty in alpaca_positions.items():
                if symbol not in db_positions:
                    issues.append({
                        'type': 'MISSING_IN_DB',
                        'symbol': symbol,
                        'db_qty': 0,
                        'alpaca_qty': alpaca_qty,
                        'severity': 'CRITICAL',  # Untracked position is dangerous
                    })
                    print(f"  [CRITICAL] {symbol}: Alpaca has {alpaca_qty} but DB has no record")

            # Log reconciliation to DB
            self._log_reconciliation(issues)

            print(f"\n{'='*70}")
            print(f"Summary: {len(db_positions)} DB, {len(alpaca_positions)} Alpaca, {len(issues)} issues")
            print(f"{'='*70}\n")

            return {
                'status': 'complete',
                'db_positions': len(db_positions),
                'alpaca_positions': len(alpaca_positions),
                'issues': issues,
                'critical_count': sum(1 for i in issues if i['severity'] == 'CRITICAL'),
                'error_count': sum(1 for i in issues if i['severity'] == 'ERROR'),
            }

        finally:
            self.disconnect()

    def _log_reconciliation(self, issues):
        """Write reconciliation results to audit log."""
        try:
            critical = sum(1 for i in issues if i['severity'] == 'CRITICAL')
            error = sum(1 for i in issues if i['severity'] == 'ERROR')
            warn = sum(1 for i in issues if i['severity'] == 'WARN')

            self.cur.execute("""
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES ('position_reconciliation', CURRENT_TIMESTAMP, %s, 'reconciler',
                        %s, CURRENT_TIMESTAMP)
            """,
            (
                json.dumps({
                    'total_issues': len(issues),
                    'critical': critical,
                    'error': error,
                    'warn': warn,
                    'issues': issues,
                }),
                'HALT' if critical > 0 else ('ERROR' if error > 0 else 'OK'),
            ))
            self.conn.commit()
        except Exception as e:
            print(f"  [WARN] Could not log reconciliation: {e}")


if __name__ == '__main__':
    reconciler = PositionReconciler()
    result = reconciler.reconcile()
    print(json.dumps(result, indent=2))

    import sys
    sys.exit(0 if result.get('critical_count', 0) == 0 else 1)
