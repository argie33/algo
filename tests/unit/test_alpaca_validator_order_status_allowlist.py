"""Regression: validate_order_response()'s status allow-list listed "pending_new" twice
and was missing "new" entirely - Alpaca's standard initial status for a freshly-accepted
order. order_manager.py's own polling loop already treats "new" as a valid in-flight
status (send_bracket_order's status-check), but this validator, called immediately after
every entry-order submission, rejected it - so a real, successfully-submitted bracket
order (entry + stop-loss + take-profit legs all live at the broker) could be reported as
a failed submission, leaving a real, stop-loss-protected position completely untracked
in algo_trades/algo_positions.
"""

from utils.validation.alpaca import AlpacaResponseValidator


def test_new_status_is_a_valid_order_response_status():
    result = AlpacaResponseValidator.validate_order_response(
        {"id": "order-123", "status": "new", "order_class": "simple"}
    )
    assert result["valid"] is True, result["errors"]
    assert result["status"] == "new"


def test_genuinely_invalid_status_is_still_rejected():
    result = AlpacaResponseValidator.validate_order_response(
        {"id": "order-123", "status": "totally_bogus_status", "order_class": "simple"}
    )
    assert result["valid"] is False
    assert any("Invalid status value" in e for e in result["errors"])
