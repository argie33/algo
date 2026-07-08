#!/usr/bin/env python3
"""Test data detector - identify and prevent test/mock data in production paths.

Provides runtime detection of mock data markers to prevent accidental
usage of fake data in production trading paths.
"""

from typing import Any


class TestDataDetector:
    """Detect and flag test/mock data in objects."""

    # All possible test data markers
    MOCK_DATA_MARKERS = {
        "_is_mock_data",
        "_is_testing_only",
        "_is_test_mode",
        "_mock_portfolio_value",
        "_mock_cash",
        "_mock_positions",
        "_marked_at",
        "_test_mode_source",
    }

    @staticmethod
    def is_test_data(obj: Any) -> bool:
        """Check if object contains test data markers.

        Args:
            obj: Object to check (typically dict)

        Returns:
            True if object contains any test data markers
        """
        if not isinstance(obj, dict):
            return False
        return any(marker in obj for marker in TestDataDetector.MOCK_DATA_MARKERS)

    @staticmethod
    def get_test_data_markers(obj: Any) -> set[str]:
        """Get set of test markers found in object.

        Args:
            obj: Object to scan (typically dict)

        Returns:
            Set of marker strings found
        """
        if not isinstance(obj, dict):
            return set()
        return {k for k in obj.keys() if k in TestDataDetector.MOCK_DATA_MARKERS}

    @staticmethod
    def has_marker(obj: Any, marker: str) -> bool:
        """Check if object has specific marker.

        Args:
            obj: Object to check
            marker: Marker name to check for

        Returns:
            True if marker present
        """
        if not isinstance(obj, dict):
            return False
        return marker in obj

    @staticmethod
    def assert_not_test_data(obj: Any, location: str = "unknown") -> None:
        """Assert that object does not contain test data markers.

        Used in production critical paths to ensure test data never reaches
        position sizing, order execution, or other trading logic.

        Args:
            obj: Object to validate (typically data dict)
            location: Location/function name for error messages

        Raises:
            RuntimeError: If test data markers detected
        """
        markers = TestDataDetector.get_test_data_markers(obj)
        if markers:
            raise RuntimeError(
                f"[TEST_DATA_DETECTED_IN_PRODUCTION] {location} received data with test markers. "
                f"Test data must not reach production trading paths. "
                f"Markers found: {markers}. "
                f"This is a critical safety violation."
            )

    @staticmethod
    def filter_test_data(items: list[Any]) -> list[Any]:
        """Filter out test data items from list.

        Args:
            items: List of items to filter

        Returns:
            List with test data items removed
        """
        return [item for item in items if not TestDataDetector.is_test_data(item)]

    @staticmethod
    def summarize_markers(obj: Any) -> str:
        """Get human-readable summary of markers in object.

        Args:
            obj: Object to summarize

        Returns:
            String describing found markers
        """
        markers = TestDataDetector.get_test_data_markers(obj)
        if not markers:
            return "No test markers found"
        return f"Test markers found: {', '.join(sorted(markers))}"
