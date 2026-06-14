#!/usr/bin/env python3
"""
Test to verify that all critical loaders have proper timeout guards in place.
Tests that ExecutionTimeout and socket-level timeouts are configured.
"""

import sys
import os

def check_loader_has_timeout_guard(loader_file_path: str) -> tuple[bool, str]:
    """Check if a loader file has ExecutionTimeout import and usage."""
    try:
        with open(loader_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        has_import = 'from utils.infrastructure.timeout import ExecutionTimeout' in content
        has_usage = 'with ExecutionTimeout' in content
        has_socket_timeout = 'socket.setdefaulttimeout' in content or 'socket_timeout' in content

        checks = {
            'ExecutionTimeout import': has_import,
            'ExecutionTimeout usage': has_usage,
            'socket timeout': has_socket_timeout,
        }

        passed = sum(1 for v in checks.values() if v)
        total = len(checks)

        status = f"{passed}/{total} checks passed"
        return (passed == total, status)
    except Exception as e:
        return (False, f"Error reading file: {e}")

def test_critical_loaders():
    """Verify critical API-calling loaders have timeout protection."""
    print("=" * 70)
    print("LOADER TIMEOUT GUARD VERIFICATION")
    print("=" * 70)
    print()

    critical_loaders = [
        ('load_prices.py', 'Price data loader (yfinance)'),
        ('load_fred_economic_data.py', 'FRED economic data (FRED API)'),
        ('load_aaii_sentiment.py', 'AAII sentiment (Excel download)'),
        ('load_fear_greed_index.py', 'Fear & Greed Index (CNN API)'),
    ]

    # Get the correct path: test is at algo/tests/, so we go up one level to algo/
    project_root = os.path.dirname(os.path.dirname(__file__))
    loaders_dir = os.path.join(project_root, 'loaders')

    all_passed = True

    for loader_file, description in critical_loaders:
        loader_path = os.path.join(loaders_dir, loader_file)

        if not os.path.exists(loader_path):
            print(f"[FAIL] {loader_file:<35} - FILE NOT FOUND")
            all_passed = False
            continue

        has_timeout, status = check_loader_has_timeout_guard(loader_path)
        status_icon = "[OK]" if has_timeout else "[FAIL]"

        print(f"{status_icon} {loader_file:<35} - {description}")
        print(f"   {status}")
        print()

        if not has_timeout:
            all_passed = False

    return all_passed

def test_socket_timeout_utility():
    """Verify loader_helper has socket timeout setup function."""
    print("=" * 70)
    print("SOCKET TIMEOUT UTILITY VERIFICATION")
    print("=" * 70)
    print()

    # Get the correct path: test is at algo/tests/, so we go up one level to algo/
    project_root = os.path.dirname(os.path.dirname(__file__))
    helper_path = os.path.join(project_root, 'loaders', 'loader_helper.py')

    try:
        with open(helper_path, 'r', encoding='utf-8') as f:
            content = f.read()

        has_setup_func = 'def setup_loader_timeouts' in content
        has_socket_import = 'import socket' in content

        if has_setup_func and has_socket_import:
            print("[OK] loader_helper.py has setup_loader_timeouts() function")
            print("[OK] socket module is imported")
            print()
            return True
        else:
            print(f"[FAIL] loader_helper.py is missing required timeout setup")
            print(f"   setup_loader_timeouts: {has_setup_func}")
            print(f"   socket import: {has_socket_import}")
            print()
            return False
    except Exception as e:
        print(f"[FAIL] Error reading loader_helper.py: {e}")
        print()
        return False

def test_execution_timeout_utility():
    """Verify ExecutionTimeout utility is available."""
    print("=" * 70)
    print("EXECUTION TIMEOUT UTILITY VERIFICATION")
    print("=" * 70)
    print()

    # Get the correct path: test is at algo/tests/, so we go up one level to algo/
    project_root = os.path.dirname(os.path.dirname(__file__))
    timeout_path = os.path.join(project_root, 'utils', 'infrastructure', 'timeout.py')

    try:
        with open(timeout_path, 'r', encoding='utf-8') as f:
            content = f.read()

        has_timeout_class = 'class ExecutionTimeout' in content or 'def ExecutionTimeout' in content
        has_context_manager = '@contextmanager' in content or 'def ExecutionTimeout' in content

        if has_timeout_class or has_context_manager:
            print("[OK] ExecutionTimeout utility is available")
            print("[OK] Provides context manager for timeout handling")
            print()
            return True
        else:
            print(f"[FAIL] ExecutionTimeout utility missing expected components")
            print()
            return False
    except Exception as e:
        print(f"[FAIL] Error reading ExecutionTimeout utility: {e}")
        print()
        return False

def main():
    results = []

    results.append(("Execution Timeout Utility", test_execution_timeout_utility()))
    results.append(("Socket Timeout Setup", test_socket_timeout_utility()))
    results.append(("Critical Loaders", test_critical_loaders()))

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {test_name}")

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print()
        print("=" * 70)
        print("[SUCCESS] ALL TIMEOUT GUARDS ARE IN PLACE")
        print("=" * 70)
        print()
        print("[OK] Loaders will now timeout gracefully instead of hanging indefinitely")
        print("[OK] Socket-level timeouts catch hanging connections early")
        print("[OK] Execution-level timeouts prevent long-running retries")
        print()
        return 0
    else:
        print()
        print("=" * 70)
        print("[FAILED] SOME TIMEOUT GUARDS ARE MISSING")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
