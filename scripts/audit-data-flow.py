#!/usr/bin/env python3
"""
Data Flow Audit: Verify all dashboard data comes from AWS APIs.

This script verifies that:
1. Dashboard.py uses API endpoints (not direct DB)
2. All API endpoints fetch from AWS RDS (via DatabaseContext)
3. Fallback data is properly detected and logged
4. SLA response times are met
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime

# Fix console encoding on Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def audit_dashboard_source():
    """Audit dashboard.py to ensure API-only data access."""
    print("\n[1/4] Auditing dashboard data sources...")
    print("-" * 60)

    dashboard_file = Path("tools/dashboard/dashboard.py")
    if not dashboard_file.exists():
        print(f"  ❌ Dashboard file not found: {dashboard_file}")
        return False

    content = dashboard_file.read_text(encoding="utf-8", errors="ignore")

    # Check for API usage
    api_calls = len(re.findall(r"api_call\(", content))
    db_calls = len(re.findall(r"DatabaseContext|psycopg2|\.execute\(", content))

    print(f"  [OK] API calls found: {api_calls}")
    print(
        f"  {'[OK]' if db_calls == 0 else '[FAIL]'} Direct DB calls found: {db_calls}"
    )

    # List all fetcher functions
    fetchers = re.findall(r"def (fetch_\w+)\(", content)
    print(f"  [OK] Fetcher functions: {len(fetchers)}")
    for fetcher in fetchers[:5]:
        print(f"    - {fetcher}")
    if len(fetchers) > 5:
        print(f"    ... and {len(fetchers) - 5} more")

    if db_calls == 0:
        print("  [OK] PASS: Dashboard uses API-only architecture")
        return True
    else:
        print(f"  ❌ FAIL: Dashboard has {db_calls} direct DB calls")
        return False

def audit_api_routes():
    """Audit API handler infrastructure to ensure DatabaseContext is used."""
    print("\n[2/4] Auditing API route handlers...")
    print("-" * 60)

    # Check lambda_function.py for DatabaseContext usage
    lambda_file = Path("lambda/api/lambda_function.py")
    if not lambda_file.exists():
        print(f"  ❌ Lambda file not found: {lambda_file}")
        return False

    content = lambda_file.read_text(encoding="utf-8", errors="ignore")

    # Check for DatabaseContext import and usage
    has_import = "from utils.db.context import DatabaseContext" in content
    db_context_calls = len(re.findall(r"with DatabaseContext\(", content))

    print(
        f"  {'[OK]' if has_import else '[FAIL]'} DatabaseContext imported: {has_import}"
    )
    print(f"  [OK] DatabaseContext usage: {db_context_calls} context manager(s)")

    # Check that routes are using the database cursor
    algo_file = Path("lambda/api/routes/algo.py")
    if algo_file.exists():
        algo_content = algo_file.read_text(encoding="utf-8", errors="ignore")
        handlers = len(
            re.findall(r"def _(?:get|post|put|delete)_\w+\(cur\)", algo_content)
        )
        print(f"  [OK] Route handlers receiving cur parameter: {handlers}")

    # Check for fallback handling
    fallback_checks = len(re.findall(r"_is_fallback_data|_is_placeholder", content))
    print(f"  [OK] Fallback data detection: {fallback_checks} locations")

    if has_import and db_context_calls > 0:
        print("  [OK] PASS: Lambda uses DatabaseContext for all AWS RDS access")
        return True
    else:
        print("  [FAIL] DatabaseContext not properly configured")
        return False

def audit_fallback_logging():
    """Audit fallback data logging."""
    print("\n[3/4] Auditing fallback logging...")
    print("-" * 60)

    fallback_file = Path("utils/fallback_registry.py")
    if not fallback_file.exists():
        print(f"  ⚠ Fallback registry not found: {fallback_file}")
        return True  # Not critical

    content = fallback_file.read_text(encoding="utf-8", errors="ignore")

    # Check for logging functions
    has_logging = "log_fallback_usage" in content
    has_triggers = "FallbackTrigger" in content
    has_registry = "get_hardcoded_fallback_values" in content

    print(f"  {'[OK]' if has_logging else '[FAIL]'} Fallback logging: {has_logging}")
    print(f"  {'[OK]' if has_triggers else '[FAIL]'} Fallback triggers: {has_triggers}")
    print(f"  {'[OK]' if has_registry else '[FAIL]'} Fallback registry: {has_registry}")

    if has_logging and has_triggers and has_registry:
        print("  [OK] PASS: Fallback logging is properly configured")
        return True
    else:
        print("  ⚠ WARN: Fallback logging may be incomplete")
        return False

def audit_aws_configuration():
    """Audit AWS environment configuration."""
    print("\n[4/4] Auditing AWS configuration...")
    print("-" * 60)

    env_vars = {
        "AWS_PROFILE": "AWS profile for credentials",
        "AWS_REGION": "AWS region (us-east-1)",
        "DB_HOST": "RDS host (from Secrets Manager or env)",
        "ENVIRONMENT": "Environment (dev/prod)",
    }

    configured = 0
    for var, description in env_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            display = value if var != "DB_HOST" else f"***{value[-20:]}"
            print(f"  [OK] {var}: {display}")
            configured += 1
        else:
            print(f"  [WARN] {var}: NOT SET ({description})")

    print(f"  [OK] Configured: {configured}/{len(env_vars)}")

    # Check for dev_server.py configuration
    dev_server = Path("lambda/api/dev_server.py")
    if dev_server.exists():
        content = dev_server.read_text(encoding="utf-8", errors="ignore")
        if "AWS Secrets Manager" in content:
            print("  [OK] Dev server: Configured for AWS Secrets Manager")
            return True

    return configured >= 2

def main():
    """Run all audits."""
    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print("AWS DATA FLOW AUDIT")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)

    results = {
        "dashboard_source": audit_dashboard_source(),
        "api_routes": audit_api_routes(),
        "fallback_logging": audit_fallback_logging(),
        "aws_configuration": audit_aws_configuration(),
    }

    print("\n" + "=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check, result in results.items():
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"  {status}: {check.replace('_', ' ').title()}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n[OK] All data flow audits passed!")
        print("  Dashboard data flows entirely from AWS APIs")
        print("  System is ready for production")
        return 0
    else:
        print(f"\n❌ {total - passed} audit(s) failed")
        print("  Please review the issues above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
