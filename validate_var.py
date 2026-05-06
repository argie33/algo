#!/usr/bin/env python3
"""
Phase 8: VaR/CVaR Validation Script

Verifies that VaR calculations are correct by:
1. Computing historical VaR manually from portfolio snapshots
2. Comparing to VaR computed by algo_var.py
3. Validating under crisis scenarios

Ensures risk metrics are accurate before using for position sizing.
"""

import os
import psycopg2
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from datetime import date, timedelta
from typing import Dict, Any, Optional

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


class VaRValidator:
    """Validate VaR/CVaR calculations."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def validate_all(self) -> Dict[str, Any]:
        """Run all VaR validation tests."""
        print(f"\n{'='*80}")
        print(f"VaR/CVaR VALIDATION")
        print(f"{'='*80}\n")

        self.connect()
        try:
            results = {
                'historical_var': self._validate_historical_var(),
                'cvar': self._validate_cvar(),
                'stressed_var': self._validate_stressed_var(),
                'crisis_scenario': self._validate_crisis_scenario(),
            }
        finally:
            self.disconnect()

        return self._summarize(results)

    def _validate_historical_var(self) -> Dict[str, Any]:
        """Validate 95% confidence VaR calculation."""
        print(f"TEST 1: Historical VaR (95% confidence)")
        print(f"  Computing daily returns from portfolio snapshots...")

        self.cur.execute("""
            SELECT snapshot_date, total_portfolio_value
            FROM algo_portfolio_snapshots
            WHERE snapshot_date >= CURRENT_DATE - INTERVAL '252 days'
            ORDER BY snapshot_date
        """)
        rows = self.cur.fetchall()

        if len(rows) < 30:
            print(f"  [SKIP] Insufficient data (need ≥30 days, have {len(rows)})")
            return {'status': 'SKIP', 'reason': 'insufficient_data'}

        values = [float(row[1]) for row in rows]
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

        # Compute 95% VaR (loss at 5th percentile)
        var_percentile = np.percentile(returns, 5)
        current_value = values[-1]
        var_dollars = current_value * abs(var_percentile)
        var_pct = abs(var_percentile) * 100

        # Compare to database record
        self.cur.execute("""
            SELECT var_95_pct FROM algo_risk_daily
            WHERE report_date = CURRENT_DATE
        """)
        db_row = self.cur.fetchone()
        db_var_pct = float(db_row[0]) if db_row and db_row[0] else None

        passed = False
        if db_var_pct:
            # Allow 5% tolerance
            tolerance = db_var_pct * 0.05
            passed = abs(var_pct - db_var_pct) <= tolerance
            print(f"  Manual Calculation: {var_pct:.3f}%")
            print(f"  Database Record: {db_var_pct:.3f}%")
            print(f"  Tolerance: {tolerance:.3f}%")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            print(f"  Manual Calculation: {var_pct:.3f}%")
            print(f"  Database Record: None")
            print(f"  Status: [SKIP] No database record\n")

        return {
            'status': 'PASS' if passed else ('SKIP' if not db_var_pct else 'FAIL'),
            'manual_var_pct': round(var_pct, 3),
            'database_var_pct': round(db_var_pct, 3) if db_var_pct else None,
        }

    def _validate_cvar(self) -> Dict[str, Any]:
        """Validate Conditional VaR (Expected Shortfall)."""
        print(f"TEST 2: Conditional VaR (Expected Shortfall)")
        print(f"  Computing CVaR from tail returns...")

        self.cur.execute("""
            SELECT snapshot_date, total_portfolio_value
            FROM algo_portfolio_snapshots
            WHERE snapshot_date >= CURRENT_DATE - INTERVAL '252 days'
            ORDER BY snapshot_date
        """)
        rows = self.cur.fetchall()

        if len(rows) < 30:
            print(f"  [SKIP] Insufficient data")
            return {'status': 'SKIP', 'reason': 'insufficient_data'}

        values = [float(row[1]) for row in rows]
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

        # CVaR = mean of losses worse than VaR threshold
        var_threshold = np.percentile(returns, 5)
        tail_losses = [r for r in returns if r <= var_threshold]

        if tail_losses:
            cvar_pct = abs(np.mean(tail_losses)) * 100
            current_value = values[-1]
            cvar_dollars = current_value * abs(np.mean(tail_losses))

            self.cur.execute("""
                SELECT cvar_95_pct FROM algo_risk_daily
                WHERE report_date = CURRENT_DATE
            """)
            db_row = self.cur.fetchone()
            db_cvar_pct = float(db_row[0]) if db_row and db_row[0] else None

            passed = False
            if db_cvar_pct:
                tolerance = db_cvar_pct * 0.05
                passed = abs(cvar_pct - db_cvar_pct) <= tolerance
                print(f"  Manual Calculation: {cvar_pct:.3f}%")
                print(f"  Database Record: {db_cvar_pct:.3f}%")
                print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
            else:
                print(f"  Manual Calculation: {cvar_pct:.3f}%")
                print(f"  Database Record: None")
                print(f"  Status: [SKIP] No database record\n")

            return {
                'status': 'PASS' if passed else ('SKIP' if not db_cvar_pct else 'FAIL'),
                'manual_cvar_pct': round(cvar_pct, 3),
                'database_cvar_pct': round(db_cvar_pct, 3) if db_cvar_pct else None,
            }
        else:
            print(f"  [SKIP] No tail losses found\n")
            return {'status': 'SKIP', 'reason': 'no_tail_losses'}

    def _validate_stressed_var(self) -> Dict[str, Any]:
        """Validate stressed VaR using worst 12-month window."""
        print(f"TEST 3: Stressed VaR (99% confidence, worst 12m window)")
        print(f"  Finding worst 12-month period in history...")

        self.cur.execute("""
            SELECT snapshot_date, total_portfolio_value
            FROM algo_portfolio_snapshots
            WHERE snapshot_date >= CURRENT_DATE - INTERVAL '5 years'
            ORDER BY snapshot_date
        """)
        rows = self.cur.fetchall()

        if len(rows) < 365:
            print(f"  [SKIP] Insufficient history (need 5+ years)")
            return {'status': 'SKIP', 'reason': 'insufficient_history'}

        values = [float(row[1]) for row in rows]
        returns = np.array([(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))])

        worst_var = 0
        worst_start_idx = 0

        for start_idx in range(len(returns) - 252):
            window_returns = returns[start_idx:start_idx + 252]
            var_thresh = np.percentile(window_returns, 1.0)  # 1% = 99% confidence
            if abs(var_thresh) > abs(worst_var):
                worst_var = var_thresh
                worst_start_idx = start_idx

        current_value = values[-1]
        stressed_var_pct = abs(worst_var) * 100

        self.cur.execute("""
            SELECT stressed_var_99_pct FROM algo_risk_daily
            WHERE report_date = CURRENT_DATE
        """)
        db_row = self.cur.fetchone()
        db_stressed_pct = float(db_row[0]) if db_row and db_row[0] else None

        passed = False
        if db_stressed_pct:
            tolerance = db_stressed_pct * 0.10  # 10% tolerance for stressed
            passed = abs(stressed_var_pct - db_stressed_pct) <= tolerance
            print(f"  Manual Calculation: {stressed_var_pct:.3f}%")
            print(f"  Database Record: {db_stressed_pct:.3f}%")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            print(f"  Manual Calculation: {stressed_var_pct:.3f}%")
            print(f"  Database Record: None")
            print(f"  Status: [SKIP]\n")

        return {
            'status': 'PASS' if passed else ('SKIP' if not db_stressed_pct else 'FAIL'),
            'manual_stressed_var_pct': round(stressed_var_pct, 3),
            'database_stressed_var_pct': round(db_stressed_pct, 3) if db_stressed_pct else None,
        }

    def _validate_crisis_scenario(self) -> Dict[str, Any]:
        """Validate VaR during crisis scenario (2020 COVID)."""
        print(f"TEST 4: Crisis Scenario (2020 COVID Crash)")
        print(f"  Computing VaR during Feb-Apr 2020 drawdown...")

        self.cur.execute("""
            SELECT snapshot_date, total_portfolio_value
            FROM algo_portfolio_snapshots
            WHERE snapshot_date >= '2020-02-01' AND snapshot_date <= '2020-04-30'
            ORDER BY snapshot_date
        """)
        rows = self.cur.fetchall()

        if len(rows) < 10:
            print(f"  [SKIP] Insufficient COVID period data")
            return {'status': 'SKIP', 'reason': 'insufficient_data'}

        values = [float(row[1]) for row in rows]
        returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]

        crisis_var = np.percentile(returns, 5)
        crisis_var_pct = abs(crisis_var) * 100
        max_dd = min(returns) * 100

        print(f"  COVID Period VaR (95%): {crisis_var_pct:.3f}%")
        print(f"  Worst Day Loss: {max_dd:.3f}%")
        print(f"  Status: [DATA] Crisis period validation\n")

        return {
            'status': 'DATA',
            'crisis_var_pct': round(crisis_var_pct, 3),
            'worst_day_loss_pct': round(max_dd, 3),
        }

    def _summarize(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize validation results."""
        print(f"{'='*80}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*80}\n")

        passed = 0
        skipped = 0
        failed = 0

        for test_name, result in results.items():
            status = result.get('status', 'UNKNOWN')
            if status == 'PASS':
                passed += 1
                print(f"  [PASS] {test_name}")
            elif status == 'SKIP':
                skipped += 1
                print(f"  [SKIP] {test_name} ({result.get('reason', 'N/A')})")
            else:
                failed += 1
                print(f"  [FAIL] {test_name}")

        print(f"\n  Result: {passed} passed, {skipped} skipped, {failed} failed")

        if failed == 0:
            print(f"\n  [OK] VaR/CVaR calculations validated")
        else:
            print(f"\n  [WARN] Some VaR tests failed - check calculations")

        print(f"{'='*80}\n")

        return {
            'status': 'PASS' if failed == 0 else 'FAIL',
            'passed': passed,
            'skipped': skipped,
            'failed': failed,
            'details': results,
        }


if __name__ == '__main__':
    validator = VaRValidator()
    result = validator.validate_all()
    print(f"Final Result: {result['status']}")
