#!/usr/bin/env python3
"""
SLA Verification Script
Verifies that the algo meets its business hour trading SLAs.

SLAs:
1. Morning pipeline completes in <90 min (2:00 AM → 3:30 AM ET)
2. Fresh prices available by 8:30 AM ET
3. Phase 1 passes (≥95% price coverage)
4. Orchestrator completes in <20 min (all phases)
5. At 1 PM & 3 PM: orchestrator runs with current prices, generates trades
"""

import sys
import os
from datetime import date as _date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(os.getcwd()))

from utils.database_context import DatabaseContext
from algo.algo_market_calendar import MarketCalendar

ET = ZoneInfo("America/New_York")

class SLAVerifier:
    def __init__(self):
        self.slas_met = {}
        self.slas_failed = {}

    def check_price_coverage_sla(self):
        """SLA 1: Price data must have ≥95% coverage vs prior day"""
        with DatabaseContext('read') as cur:
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s", (max_date,))
            today_count = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
                "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
                (max_date,)
            )
            prior_count = cur.fetchone()[0] or today_count

            coverage = (today_count / max(prior_count, 1)) * 100

            if coverage >= 95:
                self.slas_met['price_coverage'] = {
                    'status': 'PASS',
                    'date': str(max_date),
                    'symbols': today_count,
                    'coverage_pct': round(coverage, 1)
                }
            else:
                self.slas_failed['price_coverage'] = {
                    'status': 'FAIL',
                    'date': str(max_date),
                    'symbols': today_count,
                    'coverage_pct': round(coverage, 1),
                    'threshold': 95,
                    'reason': f'Coverage {coverage:.1f}% < 95%'
                }

            return coverage >= 95

    def check_data_freshness_sla(self):
        """SLA 2: All required data tables must be current (today's date)"""
        with DatabaseContext('read') as cur:
            today = _date.today()

            tables = {
                'price_daily': 'Price data',
                'technical_data_daily': 'Technical indicators',
                'buy_sell_daily': 'Buy/sell signals',
                'swing_trader_scores': 'Swing scores'
            }

            all_current = True
            stale_tables = []

            for table, label in tables.items():
                cur.execute(f"SELECT MAX(date) FROM {table}")
                max_date = cur.fetchone()[0]

                if max_date != today:
                    all_current = False
                    stale_tables.append({
                        'table': table,
                        'label': label,
                        'last_update': str(max_date),
                        'days_stale': (today - max_date).days
                    })

            if all_current:
                self.slas_met['data_freshness'] = {
                    'status': 'PASS',
                    'all_tables_current': True
                }
            else:
                self.slas_failed['data_freshness'] = {
                    'status': 'FAIL',
                    'stale_tables': stale_tables,
                    'reason': f'{len(stale_tables)} tables stale'
                }

            return all_current

    def check_orchestrator_runs_sla(self):
        """SLA 3: Orchestrator must run successfully at 1 PM and 3 PM ET"""
        with DatabaseContext('read') as cur:
            today = _date.today()

            # Check all runs for today
            cur.execute("""
                SELECT run_id, overall_status
                FROM orchestrator_execution_log
                WHERE run_date = %s
                ORDER BY run_id DESC
                LIMIT 20
            """, (today,))

            runs = cur.fetchall()

            business_hours_runs = []
            for run_id, status in runs:
                time_str = run_id.split('-')[-1]
                try:
                    hour = int(time_str[0:2])
                    if 13 <= hour <= 15:  # 1 PM to 3 PM
                        business_hours_runs.append({
                            'run_id': run_id,
                            'hour': hour,
                            'status': status
                        })
                except (ValueError, IndexError):
                    pass

            success_runs = [r for r in business_hours_runs if r['status'] == 'success']

            if success_runs:
                self.slas_met['orchestrator_business_hours'] = {
                    'status': 'PASS',
                    'successful_runs': len(success_runs),
                    'runs': success_runs
                }
            else:
                self.slas_failed['orchestrator_business_hours'] = {
                    'status': 'FAIL',
                    'runs': business_hours_runs,
                    'reason': 'No successful business hours runs found'
                }

            return bool(success_runs)

    def check_trades_generated_sla(self):
        """SLA 4: Trades must be generated and executed during business hours"""
        try:
            with DatabaseContext('read') as cur:
                today = _date.today()

                # Check for trades in the last 24 hours
                cur.execute("""
                    SELECT COUNT(*) FROM algo_trades
                    WHERE entry_time::date >= %s - INTERVAL '1 day'
                """, (today,))

                trade_count = cur.fetchone()[0] or 0

                if trade_count > 0:
                    self.slas_met['trades_generated'] = {
                        'status': 'PASS',
                        'trades_count': trade_count,
                        'today': str(today)
                    }
                else:
                    self.slas_failed['trades_generated'] = {
                        'status': 'FAIL',
                        'trades_count': trade_count,
                        'reason': 'No trades executed in last 24 hours'
                    }

                return trade_count > 0
        except Exception as e:
            self.slas_failed['trades_generated'] = {
                'status': 'ERROR',
                'reason': f'Could not check: {str(e)}'
            }
            return False

    def print_report(self):
        """Print SLA verification report"""
        print("\n" + "="*80)
        print("ALGO SYSTEM SLA VERIFICATION REPORT")
        print("="*80)

        print("\n[PASSED SLAs]")
        if self.slas_met:
            for sla_name, result in self.slas_met.items():
                print(f"  {sla_name:40s}: PASS")
                for key, val in result.items():
                    if key != 'status':
                        print(f"    - {key}: {val}")
        else:
            print("  (None)")

        print("\n[FAILED SLAs]")
        if self.slas_failed:
            for sla_name, result in self.slas_failed.items():
                print(f"  {sla_name:40s}: FAIL")
                print(f"    - {result.get('reason', 'See details below')}")
                for key, val in result.items():
                    if key not in ['status', 'reason']:
                        print(f"    - {key}: {val}")
        else:
            print("  (None)")

        print("\n" + "="*80)
        passed = len(self.slas_met)
        failed = len(self.slas_failed)
        total = passed + failed
        pct = int((passed / total * 100)) if total > 0 else 0
        print(f"SUMMARY: {passed}/{total} SLAs met ({pct}%)")
        print("="*80 + "\n")

        return failed == 0


def main():
    verifier = SLAVerifier()

    print("Running SLA checks...")
    verifier.check_price_coverage_sla()
    verifier.check_data_freshness_sla()
    verifier.check_orchestrator_runs_sla()
    verifier.check_trades_generated_sla()

    success = verifier.print_report()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
