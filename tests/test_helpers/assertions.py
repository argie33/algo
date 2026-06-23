"""Strong assertion helpers for comprehensive test validation.

Provides utilities to write tests that verify correctness, not just "doesn't crash":
- Render Rich panels to text for testing
- Strong assertions for error/success states
- Test data factories for common scenarios
- Type coercion helpers
"""

from rich.console import Console
from typing import Any


def render_panel_to_text(panel: Any) -> str:
    """Render a Rich Panel to text string for assertion testing.

    Args:
        panel: Rich Panel object

    Returns:
        String containing the rendered panel content
    """
    console = Console()
    with console.capture() as capture:
        console.print(panel)
    return capture.get()


def assert_panel_error(panel_text: str, context: str = "") -> None:
    """Assert that a rendered panel shows an error state.

    Args:
        panel_text: Text from render_panel_to_text()
        context: Optional context for assertion message

    Raises:
        AssertionError: If panel doesn't show error indicators
    """
    error_indicators = ["validation failed", "ERROR", "⚠", "✗", "critical", "missing"]
    has_error = any(indicator in panel_text.lower() for indicator in error_indicators)

    assert has_error, (
        f"Expected error indicators in panel. {context}\n"
        f"Panel content:\n{panel_text}"
    )


def assert_panel_success(panel_text: str, expected_content: str | list[str] | None = None, context: str = "") -> None:
    """Assert that a rendered panel shows success state and expected content.

    Args:
        panel_text: Text from render_panel_to_text()
        expected_content: String or list of strings that should appear in panel
        context: Optional context for assertion message

    Raises:
        AssertionError: If panel shows error or missing expected content
    """
    error_indicators = ["validation failed", "ERROR", "⚠ N/A", "CRITICAL DATA MISSING"]
    has_error = any(indicator in panel_text for indicator in error_indicators)

    assert not has_error, (
        f"Expected success state but found error. {context}\n"
        f"Panel content:\n{panel_text}"
    )

    if expected_content:
        if isinstance(expected_content, str):
            expected_content = [expected_content]

        for expected_str in expected_content:
            assert expected_str in panel_text, (
                f"Expected '{expected_str}' in panel. {context}\n"
                f"Panel content:\n{panel_text}"
            )


def assert_panel_renders_without_crash(panel: Any, context: str = "") -> str:
    """Assert that a panel renders without crashing and return text.

    Args:
        panel: Rich Panel object
        context: Optional context for assertion message

    Returns:
        Rendered panel text

    Raises:
        AssertionError: If panel fails to render
    """
    try:
        text = render_panel_to_text(panel)
        assert text is not None and len(text) > 0, (
            f"Panel rendered to empty string. {context}"
        )
        return text
    except Exception as e:
        raise AssertionError(f"Panel failed to render. {context}\nError: {e}") from e


def assert_numeric_value_in_range(
    value: float | int | None,
    min_val: float | None = None,
    max_val: float | None = None,
    allow_none: bool = False,
    context: str = "",
) -> None:
    """Assert that a numeric value is in expected range.

    Args:
        value: Value to check
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        allow_none: Whether None is acceptable
        context: Optional context for assertion message

    Raises:
        AssertionError: If value is out of range
    """
    if value is None:
        assert allow_none, f"Value is None but not allowed. {context}"
        return

    assert isinstance(value, (int, float)), (
        f"Value {value} is not numeric. {context}"
    )

    if min_val is not None:
        assert value >= min_val, (
            f"Value {value} is below minimum {min_val}. {context}"
        )

    if max_val is not None:
        assert value <= max_val, (
            f"Value {value} is above maximum {max_val}. {context}"
        )


class TestDataFactory:
    """Factory for generating test data scenarios."""

    @staticmethod
    def well_formed_market_data() -> dict[str, Any]:
        """Generate well-formed market data for tests."""
        return {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": 450.25,
            "dist": "5",
            "stage": "Uptrend",
            "spy_chg": 1.5,
            "trend": "UP",
            "halts": [],
            "upvol": 62.5,
            "adr": 1.45,
            "nh": 500,
            "nl": 100,
            "pcr": 0.75,
            "bmom": 0.65,
            "ycs": 0.5,
            "fed": "Normal",
        }

    @staticmethod
    def well_formed_risk_data() -> dict[str, Any]:
        """Generate well-formed risk metrics for tests."""
        return {
            "var95": 2.5,
            "beta": 1.1,
            "cvar95": 3.2,
            "conc5": 28,
            "svar": 4.5,
        }

    @staticmethod
    def well_formed_health_data() -> list[dict[str, Any]]:
        """Generate well-formed health items for tests."""
        return [
            {
                "tbl": "prices",
                "age_hours": 2,
                "st": "ok",
                "role": "CRIT",
                "row_count": 10000,
            },
            {
                "tbl": "trades",
                "age_hours": 0.5,
                "st": "ok",
                "role": "IMP",
                "row_count": 5000,
            },
        ]

    @staticmethod
    def malformed_numeric_data() -> dict[str, Any]:
        """Generate common malformed numeric field variants."""
        return {
            "string_number": "123.45",
            "dict_number": {"value": 123.45},
            "list_number": [123.45],
            "bool_number": True,
            "none_number": None,
        }

    @staticmethod
    def malformed_list_data() -> dict[str, Any]:
        """Generate common malformed list field variants."""
        return {
            "string_list": "item1 item2",
            "dict_list": {"items": ["item1"]},
            "single_item": "item1",  # Not a list
            "none_list": None,
        }
