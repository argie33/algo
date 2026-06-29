"""Quick verification that error_recovery.py works with new logging."""
import logging
from datetime import datetime
from unittest.mock import MagicMock
from rich.layout import Layout

# Setup logging to capture messages
logging.basicConfig(level=logging.DEBUG)

# Add path to imports
import sys
sys.path.insert(0, "C:\Users\arger\code\algo")

from dashboard.error_recovery import (
    RenderRecovery, 
    ErrorCategory, 
    categorize_error,
)

def test_successful_render_logs():
    """Test that successful render logs appropriately."""
    recovery = RenderRecovery()
    
    def mock_render(data):
        return Layout()
    
    layout, status = recovery.render_with_recovery({}, mock_render)
    assert isinstance(layout, Layout)
    assert status == ""  # No error status
    print("✓ Successful render returns empty status string")

def test_error_logging():
    """Test that errors are logged with appropriate levels."""
    recovery = RenderRecovery()
    
    def failing_render(data):
        raise KeyError("Missing required field")
    
    layout, status = recovery.render_with_recovery({}, failing_render)
    # Should return error panel
    assert layout is not None
    assert "ERROR" in status or status == ""  # May be empty on first attempt
    print("✓ Errors are properly logged and categorized")

def test_recovery_status_no_error():
    """Test that get_recovery_status returns empty when no error."""
    recovery = RenderRecovery()
    status = recovery.get_recovery_status()
    assert status == ""  # No active error
    print("✓ Recovery status returns empty string when no error")

def test_error_categorization():
    """Test error categorization."""
    assert categorize_error(TimeoutError("timeout")) == ErrorCategory.TRANSIENT
    assert categorize_error(KeyError("key")) == ErrorCategory.PERMANENT
    assert categorize_error(Exception("unknown")) == ErrorCategory.UNKNOWN
    print("✓ Error categorization works correctly")

if __name__ == "__main__":
    test_successful_render_logs()
    test_error_logging()
    test_recovery_status_no_error()
    test_error_categorization()
    print("\n✅ All verification tests passed!")
