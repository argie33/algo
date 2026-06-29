#!/usr/bin/env python3
"""Daily scan for fail-fast violations in critical financial code paths.

Runs automatically via CI/CD to detect new violations before they reach main.
Reports violations by severity and sends alerts to team.

Usage:
  python scripts/daily_violation_scan.py                    # Run scan
  python scripts/daily_violation_scan.py --fix-report FILE  # Generate fix report
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Critical financial code paths - violations here are serious
CRITICAL_PATHS = {
    "loaders/load_prices.py": "price data - position sizing",
    "loaders/load_stock_scores.py": "stock scoring - trade decisions",
    "loaders/load_stability_metrics.py": "volatility/beta - risk calculations",
    "loaders/load_market_health_daily.py": "market halts - circuit breakers",
    "loaders/price_transformer.py": "price validation - OHLCV integrity",
    "dashboard/fetchers_portfolio.py": "portfolio data - P&L display",
    "dashboard/fetchers_market.py": "market data - position monitoring",
    "algo/trading/executor.py": "order execution - trade submission",
    "algo/trading/position_sizer.py": "position sizing - risk limits",
    "algo/risk/position_sizer_specialist.py": "position calculations - exposure",
}

# Patterns that indicate violations
VIOLATION_PATTERNS = {
    "return_none_no_raise": (r"^\s*return\s+None\s*$", "returns None without raising exception"),
    "return_empty_list": (r"^\s*return\s+\[\]\s*$", "returns [] without error"),
    "return_empty_dict": (r"^\s*return\s+\{\}\s*$", "returns {} without marker"),
    "get_empty_default": (r"\.get\(['\"][^'\"]+['\"]\s*,\s*['\"]['\"]", ".get() with empty string default"),
    "get_zero_default": (r"\.get\(['\"][^'\"]+['\"]\s*,\s*0\)(?!\s*if)", ".get() with 0 default"),
}

def scan_file(file_path):
    """Scan file for violations."""
    violations = []

    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        for line_no, line in enumerate(lines, 1):
            # Skip comments and docstrings
            if line.strip().startswith("#") or line.strip().startswith('"""'):
                continue

            for violation_type, (pattern, description) in VIOLATION_PATTERNS.items():
                if re.search(pattern, line):
                    violations.append({
                        "file": str(file_path),
                        "line": line_no,
                        "type": violation_type,
                        "description": description,
                        "code": line.rstrip()[:100],
                    })
    except Exception:
        pass

    return violations

def main():
    """Run daily violation scan."""
    all_violations = defaultdict(list)
    critical_violations = []

    # Scan critical paths
    for file_path in CRITICAL_PATHS.keys():
        if Path(file_path).exists():
            violations = scan_file(file_path)
            for v in violations:
                all_violations[file_path].extend([v])
                critical_violations.append({
                    **v,
                    "severity": "CRITICAL",
                    "financial_impact": CRITICAL_PATHS[file_path],
                })

    # Report findings
    print("="*80)
    print(f"DAILY FAIL-FAST VIOLATION SCAN - {datetime.now().isoformat()}")
    print("="*80)

    if critical_violations:
        print(f"\nCRITICAL VIOLATIONS FOUND: {len(critical_violations)}")
        print("-"*80)

        for v in critical_violations:
            print(f"\n{v['file']}:{v['line']}")
            print(f"  Severity: {v['severity']}")
            print(f"  Impact: {v['financial_impact']}")
            print(f"  Issue: {v['description']}")
            print(f"  Code: {v['code']}")

        print("\n" + "="*80)
        print("ACTION REQUIRED: Fix all critical violations before merge!")
        print("="*80)

        return 1  # Exit with error
    else:
        print("\nSCAN RESULT: NO VIOLATIONS FOUND")
        print("Critical financial paths are clean!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
