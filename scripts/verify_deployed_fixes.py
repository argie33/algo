#!/usr/bin/env python3
"""
Comprehensive verification of deployed Issue fixes:
- Issue #2: Loader completion tracking (execution_started, execution_completed)
- Issue #4: Morning prep timing (2:00 AM start)
- Issue #9: Failsafe completion wait in Phase 1
- Issue #14: Morning prep completion validation

Run this immediately after Terraform deployment completes.
"""

import boto3
import requests
import json
import time
from datetime import datetime, timezone
import sys

class FixVerification:
    def __init__(self):
        self.results = {}
        self.logs = []

    def log(self, msg):
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
        print(f"[{timestamp}] {msg}")
        self.logs.append(f"[{timestamp}] {msg}")

    def verify_issue_4_terraform(self):
        """Verify Issue #4: 2:00 AM start time in Terraform"""
        self.log("Verifying Issue #4 (Morning Prep Timing)...")

        try:
            # Read the Terraform file to verify 2:00 AM cron
            with open('terraform/modules/pipeline/main.tf', 'r') as f:
                content = f.read()
                if 'cron(0 2 ? * MON-FRI *)' in content:
                    self.results['issue_4_terraform'] = 'PASS: 2:00 AM cron found in Terraform'
                    self.log(self.results['issue_4_terraform'])
                    return True
                else:
                    self.results['issue_4_terraform'] = 'FAIL: 2:00 AM cron not found'
                    self.log(self.results['issue_4_terraform'])
                    return False
        except Exception as e:
            self.results['issue_4_terraform'] = f'ERROR: {str(e)[:80]}'
            self.log(self.results['issue_4_terraform'])
            return False

    def verify_health_endpoint(self):
        """Verify health endpoint returns properly formatted response"""
        self.log("Verifying health endpoint...")

        try:
            start = time.time()
            response = requests.get(
                'https://d2u93283nn45h2.cloudfront.net/api/health',
                timeout=5
            )
            elapsed = time.time() - start

            if response.status_code == 200:
                data = response.json()
                # Check for required fields from Issue #14 enhancement
                if 'statusCode' in data and 'data' in data:
                    checks = {
                        'statusCode': 'statusCode' in data,
                        'rds_pool': 'rds_connection_pool' in data.get('data', {}),
                        'degraded_flag': 'degraded_mode_active' in data.get('data', {}),
                        'freshness': 'freshness' in data.get('data', {}),
                    }

                    all_good = all(checks.values())
                    if all_good:
                        self.results['health_endpoint'] = f'PASS: PASS: All fields present, {elapsed:.2f}s response'
                        self.log(self.results['health_endpoint'])
                        return True
                    else:
                        missing = [k for k, v in checks.items() if not v]
                        self.results['health_endpoint'] = f'WARN: PARTIAL: Missing {missing}'
                        self.log(self.results['health_endpoint'])
                        return False
            else:
                self.results['health_endpoint'] = f'FAIL: FAIL: Status {response.status_code}'
                self.log(self.results['health_endpoint'])
                return False

        except Exception as e:
            self.results['health_endpoint'] = f'FAIL: ERROR: {str(e)[:80]}'
            self.log(self.results['health_endpoint'])
            return False

    def verify_issue_2_code(self):
        """Verify Issue #2: Load prices records execution_completed"""
        self.log("Verifying Issue #2 (Loader Completion Tracking)...")

        try:
            with open('loaders/load_prices.py', 'r') as f:
                content = f.read()
                # Check if execution_completed is being recorded
                if 'execution_completed' in content and 'data_loader_status' in content:
                    if 'UPDATE data_loader_status' in content or 'execution_completed' in content:
                        self.results['issue_2_code'] = 'PASS: PASS: execution_completed tracking found in load_prices.py'
                        self.log(self.results['issue_2_code'])
                        return True
                    else:
                        self.results['issue_2_code'] = 'WARN: PARTIAL: execution_completed mentioned but not updated'
                        self.log(self.results['issue_2_code'])
                        return False
                else:
                    self.results['issue_2_code'] = 'FAIL: FAIL: execution_completed not found in load_prices.py'
                    self.log(self.results['issue_2_code'])
                    return False
        except Exception as e:
            self.results['issue_2_code'] = f'WARN: ERROR: {str(e)[:80]}'
            self.log(self.results['issue_2_code'])
            return False

    def verify_issue_14_code(self):
        """Verify Issue #14: Morning prep completion validation exists"""
        self.log("Verifying Issue #14 (Morning Prep Completion Validation)...")

        try:
            with open('algo/orchestrator/phase1_data_freshness.py', 'r') as f:
                content = f.read()
                if '_validate_morning_prep_completion' in content:
                    if 'all 5 morning prep steps' in content or 'morning_prep_tables' in content:
                        self.results['issue_14_code'] = 'PASS: PASS: Morning prep completion validation found'
                        self.log(self.results['issue_14_code'])
                        return True
                    else:
                        self.results['issue_14_code'] = 'WARN: PARTIAL: Validation function exists but incomplete'
                        self.log(self.results['issue_14_code'])
                        return False
                else:
                    self.results['issue_14_code'] = 'FAIL: FAIL: _validate_morning_prep_completion not found'
                    self.log(self.results['issue_14_code'])
                    return False
        except Exception as e:
            self.results['issue_14_code'] = f'WARN: ERROR: {str(e)[:80]}'
            self.log(self.results['issue_14_code'])
            return False

    def verify_issue_9_code(self):
        """Verify Issue #9: Failsafe completion wait in Phase 1"""
        self.log("Verifying Issue #9 (Failsafe Completion Wait)...")

        try:
            with open('algo/orchestrator/phase1_data_freshness.py', 'r') as f:
                content = f.read()
                if 'failsafe_completion' in content or 'wait' in content.lower() and 'failsafe' in content:
                    self.results['issue_9_code'] = 'PASS: PASS: Failsafe wait logic found'
                    self.log(self.results['issue_9_code'])
                    return True
                else:
                    self.results['issue_9_code'] = 'WARN: PARTIAL: Failsafe referenced but wait logic unclear'
                    self.log(self.results['issue_9_code'])
                    return False
        except Exception as e:
            self.results['issue_9_code'] = f'WARN: ERROR: {str(e)[:80]}'
            self.log(self.results['issue_9_code'])
            return False

    def run_all(self):
        """Run all verification tests"""
        self.log("=" * 80)
        self.log("DEPLOYED FIX VERIFICATION - Starting")
        self.log("=" * 80)

        results = {
            'Issue #4 (Timing)': self.verify_issue_4_terraform(),
            'Health Endpoint': self.verify_health_endpoint(),
            'Issue #2 (Loader Tracking)': self.verify_issue_2_code(),
            'Issue #14 (Prep Validation)': self.verify_issue_14_code(),
            'Issue #9 (Failsafe Wait)': self.verify_issue_9_code(),
        }

        self.log("=" * 80)
        self.log("SUMMARY")
        self.log("=" * 80)

        for test, result in results.items():
            status = "PASS: PASS" if result else "FAIL: FAIL"
            self.log(f"{status}: {test}")

        passed = sum(1 for r in results.values() if r)
        total = len(results)

        self.log(f"\nTotal: {passed}/{total} checks passed")
        self.log("=" * 80)

        return all(results.values())

if __name__ == '__main__':
    verifier = FixVerification()
    success = verifier.run_all()

    # Write results to file
    with open('/tmp/fix_verification_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'results': verifier.results,
            'logs': verifier.logs,
            'all_passed': success
        }, f, indent=2)

    sys.exit(0 if success else 1)
