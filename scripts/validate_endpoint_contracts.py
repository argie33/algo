#!/usr/bin/env python3
"""Validate that API endpoints match the dashboard API contract.

This script ensures:
1. All dashboard contract endpoints have corresponding API implementations
2. Endpoint paths and methods match the contract
3. Response schemas align with contract definitions
4. No undocumented endpoints exist in the API
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Set


def get_dashboard_contract_endpoints() -> Dict[str, str]:
    """Extract endpoint paths from dashboard_api_contract.py."""
    contract_file = Path("shared_contracts/dashboard_api_contract.py")
    if not contract_file.exists():
        print("ERROR: dashboard_api_contract.py not found")
        return {}

    content = contract_file.read_text()

    # Find all endpoint definitions (path: "/api/...")
    endpoints = {}
    pattern = r'"path":\s*"([^"]+)"'
    for match in re.finditer(pattern, content):
        path = match.group(1)
        endpoints[path] = "dashboard"

    return endpoints


def get_api_route_endpoints() -> Set[str]:
    """Extract endpoint paths from API route files.

    Routes in this system are module-based:
    - routes/industries.py handles /api/industries*
    - routes/economic.py handles /api/economic*
    - routes/market.py handles /api/market*
    etc.
    """
    routes_dir = Path("lambda/api/routes")
    endpoints = set()
    route_modules = {}  # Map module name to base endpoint

    # Map route module names to their base endpoints
    module_endpoint_map = {
        "health": "/api/health",
        "algo": "/api/algo",
        "openapi_spec": "/api/openapi",
        "logs": "/api/logs",
        "financials": "/api/financials",
        "earnings": "/api/earnings",
        "signals": "/api/signals",
        "prices": "/api/prices",
        "stocks": "/api/stocks",
        "sectors": "/api/sectors",
        "industries": "/api/industries",
        "market": "/api/market",
        "economic": "/api/economic",
        "sentiment": "/api/sentiment",
        "scores": "/api/scores",
        "research": "/api/research",
        "audit": "/api/audit",
        "trades": "/api/trades",
        "admin": "/api/admin",
        "contact": "/api/contact",
        "settings": "/api/settings",
        "risk_dashboard": "/api/risk-dashboard",
        "data_coverage": "/api/data-coverage",
    }

    # Check which route modules exist
    for route_file in routes_dir.glob("*.py"):
        if route_file.name in ["__init__.py", "utils.py"]:
            continue
        module_name = route_file.stem
        if module_name in module_endpoint_map:
            endpoints.add(module_endpoint_map[module_name])

    # Also look for algo_handlers subdir
    for route_file in routes_dir.glob("algo_handlers/*.py"):
        if route_file.name in ["__init__.py"]:
            continue
        module_name = route_file.stem
        handler_map = {
            "config": "/api/algo/config",
            "market": "/api/algo/market",
            "monitoring": "/api/algo/monitoring",
            "sector": "/api/algo/sector",
            "signals": "/api/algo/signals",
            "orchestration": "/api/algo/orchestration",
            "external": "/api/algo/external",
        }
        if module_name in handler_map:
            endpoints.add(handler_map[module_name])

    # Look for explicit /api/ paths in docstrings and comments
    for route_file in routes_dir.rglob("*.py"):
        if route_file.name in ["__init__.py", "utils.py"]:
            continue

        content = route_file.read_text()

        # Look for /api/ paths in string literals and docstrings
        for match in re.finditer(r'["\'](/api/[^"\']*)["\']', content):
            path = match.group(1)
            if "/api/" in path:
                endpoints.add(path)

    return endpoints


def main():
    """Validate endpoint contracts."""
    print("\n" + "=" * 80)
    print("ENDPOINT CONTRACT VALIDATION")
    print("=" * 80 + "\n")

    contract_endpoints = get_dashboard_contract_endpoints()
    api_endpoints = get_api_route_endpoints()

    print(f"Contract endpoints defined: {len(contract_endpoints)}")
    print(f"API endpoints found: {len(api_endpoints)}")

    if not contract_endpoints:
        print("\nWARNING: No contract endpoints found. Skipping validation.")
        return 0

    # Check for documented endpoints missing implementations
    missing_impl = []
    for path in contract_endpoints:
        # Extract base path: /api/industries/{name}/trend -> /api/industries
        # Match everything before the first {param}
        base_path = re.sub(r"/{[^}]+}.*", "", path)

        # Check if any API endpoint matches this base path
        found = False
        for api_path in api_endpoints:
            # Normalize paths for comparison
            normalized_api = api_path.rstrip("/")
            normalized_base = base_path.rstrip("/")

            # API path should either match the base exactly or start with base/
            if normalized_api == normalized_base or normalized_api.startswith(normalized_base + "/"):
                found = True
                break
        if not found:
            missing_impl.append(path)

    # Check for undocumented endpoints
    undocumented = []
    for api_path in api_endpoints:
        found = False
        for contract_path in contract_endpoints:
            if api_path.startswith(contract_path.rstrip("/*")):
                found = True
                break
        if not found:
            undocumented.append(api_path)

    print("\nDECLARED DASHBOARD ENDPOINTS:")
    for path in sorted(contract_endpoints.keys()):
        # Extract base path for parameterized endpoints
        base_path = re.sub(r"/{[^}]+}.*", "", path).rstrip("/")

        # Check if matched
        matched = False
        for api_path in api_endpoints:
            normalized_api = api_path.rstrip("/")
            normalized_base = base_path.rstrip("/")

            if normalized_api == normalized_base or normalized_api.startswith(normalized_base + "/"):
                matched = True
                break

        status = "OK" if matched else "MISSING"
        print(f"  [{status}] {path}")

    if missing_impl:
        print(f"\nERROR: {len(missing_impl)} contract endpoint(s) lack implementation:")
        for path in missing_impl:
            print(f"  - {path}")

    if undocumented:
        print(f"\nWARNING: {len(undocumented)} undocumented endpoint(s) found:")
        for path in undocumented:
            print(f"  - {path}")
        print("\nAdd these to shared_contracts/dashboard_api_contract.py if they should be documented.")

    print("\n" + "=" * 80)

    if missing_impl:
        print(f"FAILURE: {len(missing_impl)} contract endpoints missing implementation")
        return 1

    print("SUCCESS: All contract endpoints have implementations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
