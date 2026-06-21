#!/usr/bin/env python3
"""Validate that all Lambda API routes have proper response validation.

This script:
1. Scans all API route files
2. Identifies endpoints that should validate responses (dashboard endpoints)
3. Reports which routes are missing ResponseValidator imports/calls
4. Fails CI if critical endpoints lack validation
"""

import re
import sys
from pathlib import Path


def get_all_routes() -> dict[str, Path]:
    """Get all Python files in lambda/api/routes."""
    routes = {}
    routes_dir = Path("lambda/api/routes")
    for file in routes_dir.rglob("*.py"):
        if file.name.startswith("__"):
            continue
        rel_path = file.relative_to(routes_dir)
        routes[str(rel_path)] = file
    return routes


def read_file(path: Path) -> str:
    """Read file content safely."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Cannot read {path}: {e}")
        return ""


def has_response_validator_import(content: str) -> bool:
    """Check if file imports ResponseValidator."""
    return "ResponseValidator" in content or "response_validator" in content


def has_validate_endpoint_response_call(content: str) -> bool:
    """Check if file calls validate_endpoint_response."""
    return "validate_endpoint_response" in content


def get_handle_function_signature(content: str) -> tuple[bool, bool]:
    """Check if handle() function exists and what it returns.

    Returns: (has_handle_func, returns_dict)
    """
    # Look for handle() function definition
    handle_pattern = r"def handle\s*\("
    has_handle = bool(re.search(handle_pattern, content))

    # Check if function returns a dict (most likely case)
    # Look for return statements in the handle function
    if has_handle:
        # Extract the handle function
        match = re.search(r"def handle\s*\([^)]*\)[^:]*:(.+?)(?=\ndef |\Z)", content, re.DOTALL)
        if match:
            func_body = match.group(1)
            # Check for dict-like returns
            return_patterns = [
                r"return\s*{",  # return {...}
                r"return\s*\w+_response\(",  # return json_response(...), error_response(...), etc
                r"return\s*list_response\(",
                r"return.*dict",
            ]
            returns_dict = any(re.search(p, func_body) for p in return_patterns)
            return has_handle, returns_dict

    return has_handle, False


def is_dashboard_endpoint(file_path: str) -> bool:
    """Determine if route is a dashboard endpoint that needs validation."""
    # Dashboard endpoints are documented in CLAUDE.md and dashboard_api_contract.py
    dashboard_routes = {
        "algo_handlers/config.py",  # /api/algo/config
        "algo_handlers/market.py",  # /api/algo/market
        "algo_handlers/monitoring.py",  # /api/algo/monitoring
        "algo_handlers/sector.py",  # /api/algo/sector
        "algo_handlers/signals.py",  # /api/algo/signals
        "economic.py",  # /api/economic/*
        "health.py",  # /api/health
        "industries.py",  # /api/industries/*
        "market.py",  # /api/market
        "positions.py",  # /api/positions
        "trades.py",  # /api/trades
        "prices.py",  # /api/prices
        "stocks.py",  # /api/stocks
        "signals.py",  # /api/signals
        "scores.py",  # /api/scores
        "sectors.py",  # /api/sectors
        "sentiment.py",  # /api/sentiment
        "financials.py",  # /api/financials
        "earnings.py",  # /api/earnings
    }

    normalized_path = file_path.replace("\\", "/")
    return any(normalized_path.endswith(route) for route in dashboard_routes)


def main():
    """Audit API response validation."""
    print("\n" + "=" * 80)
    print("API RESPONSE VALIDATION AUDIT")
    print("=" * 80)

    routes = get_all_routes()
    missing_validation: list[str] = []

    print(f"\nScanning {len(routes)} route files...\n")

    dashboard_endpoints_found = 0
    dashboard_endpoints_validated = 0

    for route_name in sorted(routes.keys()):
        if route_name == "utils.py":
            continue

        route_path = routes[route_name]
        content = read_file(route_path)

        is_dashboard = is_dashboard_endpoint(route_name)
        has_handle, returns_dict = get_handle_function_signature(content)
        has_import = has_response_validator_import(content)
        has_call = has_validate_endpoint_response_call(content)

        if is_dashboard:
            dashboard_endpoints_found += 1
            status_emoji = "[FAIL]" if not (has_import and has_call) else "[PASS]"
            print(f"{status_emoji} {route_name}")

            if has_import and has_call:
                dashboard_endpoints_validated += 1
                print("       - Has ResponseValidator")
            else:
                missing_validation.append(route_name)
                if not has_import:
                    print("       - Missing ResponseValidator import")
                if not has_call:
                    print("       - Missing validate_endpoint_response() call")
        else:
            # Non-dashboard routes
            if has_handle and returns_dict and has_import and not has_call:
                print(f"[?] {route_name} (non-dashboard, has ResponseValidator import but no validation call)")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print("\nDashboard Endpoints:")
    print(f"  Found: {dashboard_endpoints_found}")
    print(f"  Validated: {dashboard_endpoints_validated}")
    print(f"  Missing: {len(missing_validation)}")

    if missing_validation:
        print("\nMissing Validation:")
        for route in missing_validation:
            print(f"  - {route}")
        print(f"\nFAILURE: {len(missing_validation)} dashboard endpoints lack response validation")
        return 1

    print("\n[SUCCESS] All dashboard endpoints have response validation in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
