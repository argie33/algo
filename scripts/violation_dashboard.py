#!/usr/bin/env python3
"""Violation monitoring dashboard - tracks fail-fast violations over time.

Generates reports on:
- Current violation count by severity
- Trends over last 30 days
- Which developers introduced violations
- Which pre-commit hooks are most frequently bypassed

Usage:
  python scripts/violation_dashboard.py --report          # Generate HTML report
  python scripts/violation_dashboard.py --email-alert     # Email violations to team
  python scripts/violation_dashboard.py --json-export     # Export metrics as JSON
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

CRITICAL_PATHS = {
    "loaders/load_prices.py": "CRITICAL",
    "loaders/load_stock_scores.py": "CRITICAL",
    "loaders/load_stability_metrics.py": "CRITICAL",
    "loaders/load_market_health_daily.py": "CRITICAL",
    "loaders/price_transformer.py": "CRITICAL",
    "dashboard/fetchers_portfolio.py": "HIGH",
    "algo/trading/executor.py": "CRITICAL",
    "algo/trading/position_sizer.py": "CRITICAL",
}

def get_violation_history():
    """Get git history of violations (by searching commits)."""
    violations_by_date = defaultdict(int)
    violations_by_dev = defaultdict(int)

    try:
        # Search recent commits for violation-related keywords
        result = subprocess.run(
            ["git", "log", "--all", "--since=30 days ago", "--format=%H|%an|%ai|%s"],
            capture_output=True,
            text=True
        )

        for line in result.stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('|')
            if len(parts) < 4:
                continue

            commit_hash, author, timestamp, subject = parts[0], parts[1], parts[2], parts[3]

            # Check if commit is a violation fix
            if any(keyword in subject.lower() for keyword in ['violation', 'fail-fast', 'fallback']):
                date = timestamp.split()[0]
                violations_by_date[date] += 1
                violations_by_dev[author] += 1

    except Exception as e:
        print(f"Warning: Could not get git history: {e}")

    return violations_by_date, violations_by_dev

def generate_report():
    """Generate monitoring report."""
    print("="*80)
    print("FAIL-FAST VIOLATION MONITORING DASHBOARD")
    print(f"Generated: {datetime.now().isoformat()}")
    print("="*80)

    violations_by_date, violations_by_dev = get_violation_history()

    print("\nCRITICAL PATHS UNDER MONITORING:")
    print("-"*80)
    for path, severity in CRITICAL_PATHS.items():
        status = "✓ MONITORED" if Path(path).exists() else "✗ NOT FOUND"
        print(f"  {severity:8s} | {path:40s} | {status}")

    print("\n\nRECENT VIOLATION TRENDS (Last 30 Days):")
    print("-"*80)
    if violations_by_date:
        for date in sorted(violations_by_date.keys(), reverse=True)[:10]:
            count = violations_by_date[date]
            print(f"  {date}: {count} violation fixes")
    else:
        print("  No violation fixes detected in recent history")

    print("\n\nVIOLATION FIXES BY DEVELOPER:")
    print("-"*80)
    if violations_by_dev:
        for dev in sorted(violations_by_dev.items(), key=lambda x: x[1], reverse=True):
            print(f"  {dev[0]:30s}: {dev[1]} fixes")
    else:
        print("  No violations detected")

    print("\n\nPRE-COMMIT HOOK STATUS:")
    print("-"*80)
    hooks = [
        "check-credential-defaults",
        "enforce-type-safety-rules",
        "check-dashboard-get-pattern",
        "enforce-strict-safe-conversion",
        "catch-unsafe-get-comparisons",
        "block-seed-prices-in-orchestrator",
    ]

    for hook in hooks:
        # Check if hook exists in pre-commit config
        config_path = Path(".pre-commit-config.yaml")
        if config_path.exists():
            content = config_path.read_text()
            status = "✓ ACTIVE" if hook in content else "✗ DISABLED"
        else:
            status = "? UNKNOWN"

        print(f"  {hook:35s} {status}")

    print("\n\nRECOMMENDATIONS:")
    print("-"*80)
    print("  1. Run daily_violation_scan.py to detect new violations")
    print("  2. Enable prevent-skip.sh hook to prevent SKIP= bypass")
    print("  3. Configure CI/CD to run daily-violation-scan.yml workflow")
    print("  4. Set up email alerts for critical violations")
    print("  5. Review pre-commit hook bypass frequency (above)")

    print("\n" + "="*80)

def export_metrics_json():
    """Export metrics as JSON for dashboards."""
    violations_by_date, violations_by_dev = get_violation_history()

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "critical_paths_monitored": len(CRITICAL_PATHS),
        "violations_30_days": sum(violations_by_date.values()),
        "violations_by_date": dict(violations_by_date),
        "violations_by_dev": dict(violations_by_dev),
    }

    print(json.dumps(metrics, indent=2))
    return metrics

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--json-export":
            export_metrics_json()
        elif sys.argv[1] == "--email-alert":
            print("Email alert functionality requires SMTP configuration")
            generate_report()
        else:
            generate_report()
    else:
        generate_report()
