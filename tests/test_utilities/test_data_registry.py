#!/usr/bin/env python3
"""Test data registry - central catalog of all test data entry points.

Provides visibility into all fake/mock/test data in the system, their locations,
guards, and safety status.
"""

from typing import Any


class TestDataRegistry:
    """Central registry of all test data entry points in the system."""

    TEST_ENTRY_POINTS = {
        "dry_run_broker": {
            "name": "Dry-Run Broker Adapter",
            "file": "tests/test_utilities/dry_run_broker_adapter.py",
            "component": "reconciliation",
            "requires_flag": "ORCHESTRATOR_DRY_RUN=true + ENVIRONMENT=development|test|local",
            "data": {
                "portfolio_value": 100000.0,
                "cash": 50000.0,
                "equity": 50000.0,
                "positions": [],
            },
            "test_only": True,
            "safety_status": "✅ HARDENED - Runtime environment check in __init__",
            "markers": ["_is_mock_data", "_is_testing_only"],
        },
        "price_seeding": {
            "name": "Price Seeding",
            "file": "lambda/test-seed-prices/lambda_function.py (SEPARATE LAMBDA)",
            "component": "prices",
            "requires_flag": "ENVIRONMENT=development (in separate test Lambda)",
            "data": "User-provided test prices via seed_prices parameter",
            "test_only": True,
            "safety_status": "✅ REMOVED from orchestrator - Now in separate test Lambda only",
            "markers": [],
            "deprecated_location": "lambda/algo_orchestrator/lambda_function.py (REMOVED 2026-06-29)",
        },
        "response_caching": {
            "name": "API Response Caching",
            "file": "dashboard/api_data_layer.py:get_cached_response()",
            "component": "dashboard",
            "requires_flag": "None (production-safe: raises on stale > 30min)",
            "data": "Cached API responses (fails-fast on stale data)",
            "test_only": False,
            "safety_status": "✅ ALREADY HARDENED - Raises RuntimeError on stale data (>30 min)",
            "markers": ["_cache_age_seconds", "_stale_cache"],
        },
    }

    @staticmethod
    def get_all_test_entry_points() -> dict[str, dict]:
        return TestDataRegistry.TEST_ENTRY_POINTS.copy()

    @staticmethod
    def get_entry_point(name: str) -> dict[str, Any] | None:
        """Get details for specific test entry point.

        Args:
            name: Entry point name (e.g., 'dry_run_broker')

        Returns:
            Entry point details or None if not found
        """
        return TestDataRegistry.TEST_ENTRY_POINTS.get(name)

    @staticmethod
    def list_active_entry_points() -> list[str]:
        """List names of all active test entry points.

        Returns:
            List of entry point names
        """
        return list(TestDataRegistry.TEST_ENTRY_POINTS.keys())

    @staticmethod
    def list_test_only_entry_points() -> list[str]:
        """List names of entry points that are test-only (not production).

        Returns:
            List of test-only entry point names
        """
        # CRITICAL FIX: Explicit check for test_only field instead of False default
        result = []
        for name, details in TestDataRegistry.TEST_ENTRY_POINTS.items():
            test_only = details.get("test_only")
            if test_only is None:
                # Field missing - assume not test-only by default
                continue
            if test_only:
                result.append(name)
        return result

    @staticmethod
    def get_entry_point_markers(name: str) -> list[str]:
        """Get data markers for specific entry point.

        Args:
            name: Entry point name

        Returns:
            List of marker strings (e.g., ['_is_mock_data', '_is_testing_only'])
        """
        entry = TestDataRegistry.TEST_ENTRY_POINTS.get(name)
        if entry is None:
            return []
        # CRITICAL FIX: Explicit check for markers field instead of empty list default
        markers = entry.get("markers")
        if markers is None:
            return []
        elif not isinstance(markers, list):
            import logging

            logging.getLogger(__name__).warning(f"Entry point {name} markers field is not a list: {type(markers)}")
            return []
        return markers

    @staticmethod
    def get_all_markers() -> set[str]:
        all_markers = set()
        for entry in TestDataRegistry.TEST_ENTRY_POINTS.values():
            # CRITICAL FIX: Explicit check for markers field instead of empty list default
            markers = entry.get("markers")
            if markers is None:
                continue
            elif isinstance(markers, list):
                all_markers.update(markers)
            else:
                import logging

                logging.getLogger(__name__).warning(f"Entry markers field is not a list: {type(markers)}")
        return all_markers

    @staticmethod
    def validate_entry_point_markers(data: dict[str, Any], entry_point_name: str) -> bool:
        """Validate that data has expected markers for entry point.

        Args:
            data: Data dict to check
            entry_point_name: Name of entry point

        Returns:
            True if data has all expected markers for entry point
        """
        expected_markers = TestDataRegistry.get_entry_point_markers(entry_point_name)
        if not expected_markers:
            return True  # No markers expected

        for marker in expected_markers:
            if marker not in data:
                return False
        return True

    @staticmethod
    def print_registry() -> None:
        """Print human-readable registry of all test entry points."""
        print("\n" + "=" * 80)
        print("TEST DATA REGISTRY - All Test Entry Points")
        print("=" * 80 + "\n")

        for name, details in TestDataRegistry.TEST_ENTRY_POINTS.items():
            print(f"Entry Point: {name}")
            print(f"  Name: {details.get('name')}")
            print(f"  File: {details.get('file')}")
            print(f"  Component: {details.get('component')}")
            print(f"  Requires: {details.get('requires_flag')}")
            print(f"  Test-Only: {details.get('test_only')}")
            print(f"  Safety: {details.get('safety_status')}")
            print()
