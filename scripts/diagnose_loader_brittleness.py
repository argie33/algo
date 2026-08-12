#!/usr/bin/env python3
"""Comprehensive diagnostic for loader brittleness issues.

Identifies root causes of Monday failures and cascade issues.
"""

import sys
from datetime import datetime
from collections import defaultdict

from utils.db.connection import get_db_connection
from utils.infrastructure.timezone import EASTERN_TZ

def get_loader_status_summary():
    """Get comprehensive loader status and failure analysis."""
    conn = get_db_connection()
    cur = conn.cursor()

    print("=" * 80)
    print("LOADER BRITTLENESS DIAGNOSTIC")
    print("=" * 80)

    # 1. Status distribution
    print("\n1. LOADER STATUS DISTRIBUTION")
    print("-" * 80)
    cur.execute("""
        SELECT status, COUNT(*) as count
        FROM data_loader_status
        GROUP BY status
        ORDER BY CASE status
            WHEN 'FAILED' THEN 1
            WHEN 'RUNNING' THEN 2
            WHEN 'INCOMPLETE' THEN 3
            ELSE 4 END
    """)

    for status, count in cur.fetchall():
        print(f"  {status:15s}: {count:3d}")

    # 2. Failed loaders
    print("\n2. FAILED LOADERS (Root causes for cascade)")
    print("-" * 80)
    cur.execute("""
        SELECT
            table_name,
            consecutive_failures,
            last_updated,
            error_message,
            last_success_at
        FROM data_loader_status
        WHERE status = 'FAILED'
        ORDER BY consecutive_failures DESC
    """)

    failed_loaders = {}
    for row in cur.fetchall():
        table_name, failures, updated, error, last_success = row
        failed_loaders[table_name] = {
            'failures': failures,
            'error': error,
            'updated': updated,
            'last_success': last_success
        }
        print(f"  {table_name:30s} failures={failures}")
        if error:
            lines = error.split('\n')[:2]
            for line in lines:
                print(f"    | {line[:75]}")

    # 3. Dependency analysis - what depends on failed loaders
    print("\n3. DEPENDENCY IMPACT ANALYSIS")
    print("-" * 80)

    # Build dependency map from local_loader_scheduler
    dependencies = {
        "financial_statements": ["company_info"],
        "value_quality_growth": ["financial_statements", "valuations", "analyst_earnings_estimates"],
        "enhanced_quality_growth": ["value_quality_growth"],
        "segment_metrics": ["segment_info"],
        "buy_sell": ["prices", "technical"],
        "scores": ["value_quality_growth", "enhanced_quality_growth", "stability_metrics"],
        "signal_quality": ["buy_sell"],
        "algo": ["signal_quality", "scores"],
        "profile": ["company_info"],
        "valuations": ["company_info"],
        "earnings_sec": ["company_info"],
        "insider_holdings": ["company_info"],
        "insider_velocity": ["insider_holdings"],
        "positioning": ["company_info"],
        "institutional": ["company_info"],
    }

    # Find all loaders impacted by each failed loader
    affected_map = defaultdict(set)

    def find_dependents(loader, deps_map):
        """Recursively find all loaders that depend on this one."""
        dependents = set()
        for target, sources in deps_map.items():
            if loader in sources:
                dependents.add(target)
                dependents.update(find_dependents(target, deps_map))
        return dependents

    for failed_loader in failed_loaders.keys():
        affected = find_dependents(failed_loader, dependencies)
        for dependent in affected:
            affected_map[dependent].add(failed_loader)

    if affected_map:
        for affected_loader in sorted(affected_map.keys()):
            failed_deps = affected_map[affected_loader]
            print(f"  {affected_loader:30s} blocked by: {', '.join(sorted(failed_deps))}")
    else:
        print("  (No cascade dependencies identified)")

    # 4. Timeout analysis
    print("\n4. TIMEOUT ANALYSIS (Local Scheduler Timeouts)")
    print("-" * 80)

    timeouts = {
        "prices": 600 * 60,
        "technical": 30 * 60,
        "company_info": 180 * 60,
        "financial_statements": 240 * 60,
        "analyst_sentiment": 30 * 60,
        "analyst_earnings_estimates": 30 * 60,
        "analyst_upgrades": 40 * 60,
        "insider_holdings": 30 * 60,
        "valuations": 45 * 60,
        "sec_valuations": 45 * 60,
    }

    # Check if failed loaders have inadequate timeouts
    print("  Critical loaders with tight timeouts:")
    for loader_name, timeout_sec in sorted(timeouts.items(), key=lambda x: x[1]):
        if loader_name in failed_loaders:
            timeout_min = timeout_sec // 60
            print(f"    {loader_name:30s} timeout={timeout_min:3d}min [FAILED with this timeout]")

    # 5. Recent stale RUNNING loaders
    print("\n5. STALE RUNNING LOADERS (Auto-failed by Phase 1)")
    print("-" * 80)
    cur.execute("""
        SELECT
            table_name,
            status,
            last_updated,
            last_success_at
        FROM data_loader_status
        WHERE status = 'RUNNING'
            AND last_updated < NOW() - INTERVAL '5 minutes'
        ORDER BY last_updated ASC
    """)

    stale_running = cur.fetchall()
    if stale_running:
        for table_name, status, updated, last_success in stale_running:
            age_minutes = int((datetime.now(EASTERN_TZ) - updated.replace(tzinfo=EASTERN_TZ)).total_seconds() / 60)
            print(f"  {table_name:30s} age={age_minutes:4d}min (will auto-fail in 5min if still RUNNING)")
    else:
        print("  (None - Phase 1 stale-reaper working correctly)")

    # 6. Failure pattern analysis
    print("\n6. FAILURE PATTERNS")
    print("-" * 80)

    # Group failures by error type
    error_types = defaultdict(list)
    for table, info in failed_loaders.items():
        error_msg = info['error'] or '(unknown)'
        # Simplify error message for grouping
        if 'stuck RUNNING' in error_msg:
            error_type = 'STUCK_RUNNING'
        elif 'rate limit' in error_msg.lower() or '429' in error_msg:
            error_type = 'RATE_LIMIT'
        elif 'timeout' in error_msg.lower():
            error_type = 'TIMEOUT'
        elif 'connection' in error_msg.lower():
            error_type = 'CONNECTION'
        else:
            error_type = 'OTHER'
        error_types[error_type].append(table)

    for error_type, loaders in sorted(error_types.items()):
        print(f"  {error_type:15s}: {len(loaders):2d} loaders - {', '.join(loaders[:3])}")
        if len(loaders) > 3:
            print(f"                      {', '.join(loaders[3:])}")

    # 7. Age of last successful run
    print("\n7. DATA FRESHNESS (Last successful load date)")
    print("-" * 80)
    cur.execute("""
        SELECT
            table_name,
            last_success_at,
            status
        FROM data_loader_status
        WHERE last_success_at IS NOT NULL
        ORDER BY last_success_at ASC
        LIMIT 15
    """)

    for table, last_success, status in cur.fetchall():
        if last_success:
            # Handle both datetime and date objects
            if hasattr(last_success, 'date'):
                last_success_date = last_success.date()
            else:
                last_success_date = last_success
            days_old = (datetime.now(EASTERN_TZ).date() - last_success_date).days
            status_tag = f"[{status}]" if status != 'HEALTHY' else "[OK]"
            print(f"  {table:30s} {days_old:2d} days old {status_tag}")

    conn.close()

    # 8. Recommendations
    print("\n8. ROOT CAUSE SUMMARY & RECOMMENDATIONS")
    print("-" * 80)

    if 'STUCK_RUNNING' in error_types:
        print("  [!] PRIMARY ISSUE: Loaders stuck in RUNNING status")
        print("     → Loaders timeout or crash, but don't get marked FAILED properly")
        print("     → Phase 1 detects & auto-fails after 5 min, but cascade continues")
        print("     → ROOT CAUSE: Timeouts too tight for full universe @ rate limits")

    if 'RATE_LIMIT' in error_types:
        print("  [*] SECONDARY ISSUE: SEC API rate limiting (429 errors)")
        print("     → Happens when multiple loaders hit SEC @ 2 req/sec cap")
        print("     → company_info_sec, valuations, earnings_sec all hit SEC API")
        print("     → ROOT CAUSE: No sequential gating between SEC loaders locally")

    print("\n  ACTION ITEMS:")
    print("  1. Review timeout configuration in scripts/local_loader_scheduler.py")
    print("  2. Verify actual loader runtimes vs. budget")
    print("  3. Check if rate limiting is hitting multiple SEC loaders in parallel")
    print("  4. Run local metrics pipeline to measure real runtimes:")
    print("     python scripts/local_loader_scheduler.py --now metrics")

if __name__ == "__main__":
    try:
        get_loader_status_summary()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
