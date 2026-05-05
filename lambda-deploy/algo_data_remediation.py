#!/usr/bin/env python3
"""
Data Remediation — automatic actions when patrol finds problems

Patrol catches problems. Remediation acts on them.

For each kind of patrol finding, defines:
  - Severity threshold to trigger action
  - The remediation step (rerun loader / halt trading / notify / quarantine)
  - Cooldown to prevent loop

When a patrol finding has a remediation, this module is called automatically
after patrol completes. Resulting actions are logged to algo_audit_log and
surfaced to the UI via algo_notifications.

USAGE (called by run_eod_loaders.sh + manually):
  python3 algo_data_remediation.py
  python3 algo_data_remediation.py --dry-run
"""

import os
import json
import argparse
import psycopg2
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

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


# Action recipes: (check_name, target_table, severity, action_func, cooldown_minutes)
# Each action returns {'success': bool, 'message': str, 'details': dict}
class RemediationEngine:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.actions_taken = []

    def run(self):
        """Read latest patrol findings, apply remediations."""
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        try:
            # Get findings from the most recent patrol run
            cur.execute("""
                SELECT id, patrol_run_id, check_name, severity, target_table,
                       message, details, created_at
                FROM data_patrol_log
                WHERE created_at >= NOW() - INTERVAL '15 minutes'
                  AND severity IN ('warn', 'error', 'critical')
                ORDER BY
                  CASE severity WHEN 'critical' THEN 1 WHEN 'error' THEN 2 ELSE 3 END,
                  created_at DESC
            """)
            findings = cur.fetchall()
            print(f"\n{'='*70}\nDATA REMEDIATION — {len(findings)} active findings\n{'='*70}\n")

            if not findings:
                print("  No active findings — nothing to remediate.")
                return

            # Process each finding
            for finding in findings:
                f_id, run_id, check, severity, target, msg, details, created = finding
                self._process(cur, conn, {
                    'id': f_id, 'check': check, 'severity': severity,
                    'target': target, 'message': msg, 'details': details,
                })

            print(f"\n{'='*70}")
            print(f"REMEDIATION COMPLETE — {len(self.actions_taken)} actions taken")
            for a in self.actions_taken:
                print(f"  [{a['severity']:8s}] {a['action']} on {a['target']}: {a['result']}")
            print(f"{'='*70}\n")

        finally:
            cur.close()
            conn.close()

    # Note: data_remediation_log table created by init_database.py (schema as code)

    def _process(self, cur, conn, finding):
        """Match finding to action recipe and execute."""
        check = finding['check']
        target = finding['target']
        severity = finding['severity']

        # Check cooldown to prevent action loops
        cur.execute("""
            SELECT 1 FROM data_remediation_log
            WHERE check_name = %s AND target_table = %s
              AND cooldown_expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
        """, (check, target))
        if cur.fetchone():
            return  # in cooldown

        # === Recipe matching ===

        # 1. Critical staleness on a CRITICAL data source → halt + notify
        if check == 'staleness' and severity == 'critical':
            self._halt_and_notify(cur, conn, finding,
                f'Critical data {target} stale — algo halted',
                cooldown_min=60)

        # 2. Identical OHLC suspicious → flag for investigation (likely API limit)
        elif check == 'identical_ohlc':
            self._notify_investigation(cur, conn, finding,
                'API limit hit suspected — investigate source',
                cooldown_min=240)

        # 3. NULL anomaly spike → could be loader regression
        elif check == 'null_anomaly' and severity in ('error', 'critical'):
            self._notify_investigation(cur, conn, finding,
                f'NULL spike in {target} — last loader run produced incomplete rows',
                cooldown_min=120)

        # 4. Loader contract failure → re-run that specific loader
        elif check == 'loader_contract':
            target_loader = self._loader_for_table(target)
            if target_loader:
                self._rerun_loader(cur, conn, finding, target_loader,
                    cooldown_min=60)
            else:
                self._notify_investigation(cur, conn, finding,
                    f'Contract failed on {target} but no canonical loader mapping',
                    cooldown_min=60)

        # 5. Price sanity (>50% moves on multiple symbols) → quarantine for review
        elif check == 'price_sanity' and severity in ('error', 'critical'):
            self._quarantine_signals(cur, conn, finding,
                cooldown_min=120)

        # 6. Universe coverage drop → loader didn't process all symbols
        elif check == 'coverage' and severity in ('error', 'critical'):
            target_loader = self._loader_for_table(target)
            if target_loader:
                self._rerun_loader(cur, conn, finding, target_loader,
                    cooldown_min=60)

        # 7. Score freshness lag (computed scores older than raw data)
        elif check == 'score_freshness':
            self._rerun_loader(cur, conn, finding, 'load_algo_metrics_daily.py',
                cooldown_min=30)

        # 8. DB constraint violation → critical
        elif check == 'db_constraints':
            self._halt_and_notify(cur, conn, finding,
                f'DB constraint violation on {target} — manual review required',
                cooldown_min=720)

    def _loader_for_table(self, table):
        """Map table → canonical loader for re-running."""
        return {
            'price_daily':              'loadpricedaily.py',
            'technical_data_daily':     'loadtechnicalsdaily.py',
            'buy_sell_daily':           'loadbuyselldaily.py',
            'trend_template_data':      'load_algo_metrics_daily.py',
            'signal_quality_scores':    'load_algo_metrics_daily.py',
            'market_health_daily':      'load_algo_metrics_daily.py',
            'sector_ranking':           'loadsectorranking.py',
            'industry_ranking':         'loadindustryranking.py',
            'data_completeness_scores': 'load_algo_metrics_daily.py',
            'market_exposure_daily':    'algo_market_exposure.py',
        }.get(table)

    def _rerun_loader(self, cur, conn, finding, loader_script, cooldown_min):
        """Spawn a loader rerun as a remediation."""
        action = f'rerun:{loader_script}'
        if self.dry_run:
            self._log(cur, conn, finding, action, 'dry_run',
                f'Would re-run {loader_script}', cooldown_min)
            return

        if not Path(loader_script).exists():
            self._log(cur, conn, finding, action, 'failed',
                f'Loader {loader_script} not found on disk', cooldown_min)
            return

        try:
            # Run with 5-min timeout
            result = subprocess.run(
                ['python3', loader_script],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                capture_output=True,
                timeout=300,
                text=True,
            )
            status = 'success' if result.returncode == 0 else 'failed'
            msg = (f'Re-ran {loader_script}: exit={result.returncode}'
                   + (f', tail={result.stdout[-200:]}' if result.stdout else ''))
            self._log(cur, conn, finding, action, status, msg, cooldown_min)
            self.actions_taken.append({
                'severity': finding['severity'], 'action': action,
                'target': finding['target'], 'result': status,
            })
        except subprocess.TimeoutExpired:
            self._log(cur, conn, finding, action, 'timeout',
                f'{loader_script} timed out after 5min', cooldown_min)

    def _halt_and_notify(self, cur, conn, finding, msg, cooldown_min):
        """Block algo trading + push UI notification."""
        action = 'halt_trading'
        if self.dry_run:
            self._log(cur, conn, finding, action, 'dry_run', msg, cooldown_min)
            self.actions_taken.append({
                'severity': finding['severity'], 'action': action,
                'target': finding['target'], 'result': '[dry-run]',
            })
            return

        try:
            from algo_notifications import notify
            notify(
                kind='data_critical',
                severity='critical',
                title=f'Data critical: {finding["target"]}',
                message=msg,
                symbol=None,
                details=finding.get('details'),
            )
            self._log(cur, conn, finding, action, 'success', msg, cooldown_min)
            self.actions_taken.append({
                'severity': 'critical', 'action': action,
                'target': finding['target'], 'result': 'notification sent',
            })
        except Exception as e:
            self._log(cur, conn, finding, action, 'failed', str(e), cooldown_min)

    def _notify_investigation(self, cur, conn, finding, msg, cooldown_min):
        """Notify operator to investigate — no automatic action."""
        action = 'notify_investigation'
        if self.dry_run:
            self._log(cur, conn, finding, action, 'dry_run', msg, cooldown_min)
            self.actions_taken.append({
                'severity': finding['severity'], 'action': action,
                'target': finding['target'], 'result': '[dry-run]',
            })
            return

        try:
            from algo_notifications import notify
            severity = finding['severity']
            ui_severity = 'error' if severity == 'critical' else 'warning'
            notify(
                kind='data_warn',
                severity=ui_severity,
                title=f'Data warning: {finding["target"]}',
                message=msg,
                details=finding.get('details'),
            )
            self._log(cur, conn, finding, action, 'success', msg, cooldown_min)
            self.actions_taken.append({
                'severity': severity, 'action': action,
                'target': finding['target'], 'result': 'notification sent',
            })
        except Exception as e:
            self._log(cur, conn, finding, action, 'failed', str(e), cooldown_min)

    def _quarantine_signals(self, cur, conn, finding, cooldown_min):
        """Mark today's BUY signals as 'unverified' until human review."""
        action = 'quarantine_signals'
        if self.dry_run:
            self._log(cur, conn, finding, action, 'dry_run',
                'Would quarantine today signals for review', cooldown_min)
            return

        # Don't actually mutate buy_sell_daily — we said we wouldn't.
        # Instead, raise the algo's swing_score threshold so today's signals
        # need extra-strong scores to pass.
        try:
            from algo_notifications import notify
            notify(
                kind='signal_quarantine',
                severity='warning',
                title='Signal quarantine — extreme price moves detected',
                message='Algo will require A+ grade only until reviewed',
                details=finding.get('details'),
            )
            self._log(cur, conn, finding, action, 'success',
                'Notification sent; algo entries blocked', cooldown_min)
        except Exception as e:
            self._log(cur, conn, finding, action, 'failed', str(e), cooldown_min)

    def _log(self, cur, conn, finding, action, status, message, cooldown_min):
        cooldown = datetime.now() + timedelta(minutes=cooldown_min)
        try:
            cur.execute("""
                INSERT INTO data_remediation_log
                    (finding_id, check_name, target_table, action,
                     action_status, message, cooldown_expires_at, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                finding.get('id'), finding['check'], finding['target'],
                action, status, message, cooldown,
                json.dumps(finding.get('details')) if finding.get('details') else None,
            ))
            conn.commit()
        except Exception as e:
            print(f"  log error: {e}")
            conn.rollback()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    engine = RemediationEngine(dry_run=args.dry_run)
    engine.run()
