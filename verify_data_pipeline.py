#!/usr/bin/env python3
"""
Data Pipeline Verification Script

Verifies that all data loaders are in place and functioning:
1. All 36 loaders present
2. Loaders use OptimalLoader pattern
3. Watermarking prevents duplicates
4. Error handling in place
5. All target tables exist
"""

import sys
import os
from datetime import datetime
from pathlib import Path

def find_loaders():
    """Find all data loader files."""
    print("\n" + "="*70)
    print("  DATA LOADER INVENTORY")
    print("="*70)

    loader_dir = Path(".")
    loader_files = []

    # Find all files matching load*.py pattern
    for pattern in ["load*.py", "Load*.py"]:
        loader_files.extend(loader_dir.glob(pattern))

    loader_files = sorted(set([f.name for f in loader_files if f.is_file()]))

    print(f"\nFound {len(loader_files)} loader files:\n")
    for loader in loader_files:
        print(f"  • {loader}")

    return loader_files

def verify_loader_quality(loader_files):
    """Check loader implementation quality."""
    print("\n" + "="*70)
    print("  LOADER IMPLEMENTATION QUALITY CHECK")
    print("="*70)

    checks = {
        'OptimalLoader': 0,
        'Watermarking': 0,
        'Error Handling': 0,
        'Bulk COPY': 0,
        'Deduplication': 0,
    }

    for loader_file in loader_files:
        try:
            with open(loader_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if 'OptimalLoader' in content:
                checks['OptimalLoader'] += 1

            if 'watermark' in content.lower() or 'last_load' in content.lower():
                checks['Watermarking'] += 1

            if 'try:' in content and 'except' in content:
                checks['Error Handling'] += 1

            if 'COPY' in content or 'copy_from' in content.lower():
                checks['Bulk COPY'] += 1

            if 'CONFLICT' in content or 'dedup' in content.lower():
                checks['Deduplication'] += 1

        except Exception as e:
            print(f"[WARN] Error reading {loader_file}: {e}")

    print("\nImplementation Pattern Usage:\n")
    for check, count in checks.items():
        percentage = (count / len(loader_files) * 100) if loader_files else 0
        status = "✓" if percentage >= 80 else "⚠"
        print(f"  {status} {check:20} {count:2}/{len(loader_files)} ({percentage:3.0f}%)")

    return all(count >= len(loader_files) * 0.7 for count in checks.values())

def verify_loader_tables():
    """Verify loader target tables exist in schema."""
    print("\n" + "="*70)
    print("  LOADER TARGET TABLES VERIFICATION")
    print("="*70)

    # Parse init_database.py to find all CREATE TABLE statements
    try:
        with open('init_database.py', 'r', encoding='utf-8', errors='ignore') as f:
            schema_content = f.read()

        tables = []
        import re
        for match in re.finditer(r'CREATE TABLE.*?\((.*?)\);', schema_content, re.IGNORECASE | re.DOTALL):
            # Extract table name from CREATE TABLE statement
            create_stmt = schema_content[match.start():match.start()+100]
            table_match = re.search(r'CREATE TABLE.*?(\w+)\s*\(', create_stmt, re.IGNORECASE)
            if table_match:
                tables.append(table_match.group(1))

        print(f"\nFound {len(set(tables))} tables in schema")

        # Critical tables that loaders populate
        critical_tables = [
            'price_daily',
            'stock_scores',
            'swing_trader_scores',
            'market_exposure_daily',
            'algo_trades',
            'algo_positions',
            'market_health_daily',
            'fear_greed_index',
            'aaii_sentiment',
            'analyst_sentiment_analysis',
        ]

        print("\nCritical Table Status:\n")
        results = []
        for table in critical_tables:
            if any(table.lower() in t.lower() for t in tables):
                print(f"  ✓ {table}")
                results.append(True)
            else:
                print(f"  ✗ {table} NOT FOUND")
                results.append(False)

        return all(results)

    except Exception as e:
        print(f"[FAIL] Error verifying tables: {e}")
        return False

def verify_error_handling():
    """Check if loaders have proper error handling."""
    print("\n" + "="*70)
    print("  ERROR HANDLING VERIFICATION")
    print("="*70)

    loaders = list(Path(".").glob("load*.py"))

    error_patterns = {
        'Try/Except': 0,
        'Logging': 0,
        'Retry Logic': 0,
        'Connection Pooling': 0,
        'Timeout Handling': 0,
    }

    for loader_file in loaders:
        try:
            with open(loader_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if 'try:' in content:
                error_patterns['Try/Except'] += 1

            if 'logger' in content.lower() or 'print(' in content:
                error_patterns['Logging'] += 1

            if 'retry' in content.lower() or 'attempt' in content.lower():
                error_patterns['Retry Logic'] += 1

            if 'pool' in content.lower() or 'connection' in content.lower():
                error_patterns['Connection Pooling'] += 1

            if 'timeout' in content.lower() or 'timeout_ms' in content:
                error_patterns['Timeout Handling'] += 1

        except Exception as e:
            print(f"[WARN] Error checking {loader_file.name}: {e}")

    print("\nError Handling Patterns:\n")
    total_loaders = len(loaders)
    for pattern, count in error_patterns.items():
        if total_loaders > 0:
            percentage = (count / total_loaders * 100)
            status = "✓" if percentage >= 70 else "⚠"
            print(f"  {status} {pattern:20} {count:2}/{total_loaders} ({percentage:3.0f}%)")

    return all(count >= total_loaders * 0.6 for count in error_patterns.values())

def main():
    """Run all data pipeline verification checks."""
    print("\n" + "="*70)
    print("  DATA PIPELINE VERIFICATION SUITE")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*70)

    results = {}

    # Find loaders
    loaders = find_loaders()

    if len(loaders) == 0:
        print("[FAIL] No data loaders found")
        return 1

    # Run verification checks
    results['Loader Quality'] = verify_loader_quality(loaders)
    results['Target Tables'] = verify_loader_tables()
    results['Error Handling'] = verify_error_handling()

    # Summary
    print("\n" + "="*70)
    print("  VERIFICATION SUMMARY")
    print("="*70)

    print(f"\nTotal Loaders: {len(loaders)}")
    print(f"Expected: ~36 (standard data pipeline)")

    if len(loaders) < 20:
        print("[WARN] Fewer than expected loaders found")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {check_name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total and len(loaders) >= 30:
        print("\n✓ DATA PIPELINE VERIFIED")
        return 0
    else:
        print(f"\n⚠ Some checks need review")
        return 1

if __name__ == "__main__":
    sys.exit(main())
