#!/usr/bin/env python3
"""Test request validation for POST endpoints - Issue #8 fix.

Tests that Pydantic models correctly validate:
- /api/algo/preview
- /api/algo/pre-trade-impact
- /api/contact/submit
"""

import sys
from pathlib import Path

import pytest


# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))

from models.requests import (
    ContactSubmissionRequest,
    ManualTradeRequest,
    PositionUpdateRequest,
    PreTradeImpactRequest,
    TradePreviewRequest,
    VerifyUserEmailRequest,
)
from pydantic import ValidationError


class TestTradePreviewRequest:
    """Test POST /api/algo/preview request validation."""

    def test_valid_minimal_request(self):
        """Valid request with required fields only."""
        req = TradePreviewRequest(symbol="AAPL", entry_price=150.50)
        assert req.symbol == "AAPL"
        assert req.entry_price == 150.50
        assert req.stop_loss_price is None

    def test_valid_full_request(self):
        """Valid request with all fields."""
        req = TradePreviewRequest(
            symbol="MSFT", entry_price=300.00, stop_loss_price=295.00
        )
        assert req.symbol == "MSFT"
        assert req.entry_price == 300.00
        assert req.stop_loss_price == 295.00

    def test_symbol_normalized_to_uppercase(self):
        """Symbol is normalized to uppercase."""
        req = TradePreviewRequest(symbol="aapl", entry_price=150.00)
        assert req.symbol == "AAPL"

    def test_missing_symbol_rejected(self):
        """Missing symbol is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(entry_price=150.50)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "symbol" for err in errors)

    def test_missing_entry_price_rejected(self):
        """Missing entry_price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(symbol="AAPL")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "entry_price" for err in errors)

    def test_negative_entry_price_rejected(self):
        """Negative entry_price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(symbol="AAPL", entry_price=-150.50)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "entry_price" for err in errors)

    def test_zero_entry_price_rejected(self):
        """Zero entry_price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(symbol="AAPL", entry_price=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "entry_price" for err in errors)

    def test_stop_loss_must_be_below_entry(self):
        """Stop loss price must be below entry price."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(
                symbol="AAPL", entry_price=150.00, stop_loss_price=150.00
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_stop_loss_above_entry_rejected(self):
        """Stop loss price above entry price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(
                symbol="AAPL", entry_price=150.00, stop_loss_price=155.00
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_symbol_too_long_rejected(self):
        """Symbol longer than 10 chars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(symbol="TOOLONGSYMBOL", entry_price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "symbol" for err in errors)

    def test_symbol_with_invalid_chars_rejected(self):
        """Symbol with invalid characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TradePreviewRequest(symbol="A@PL", entry_price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "symbol" for err in errors)

    def test_valid_symbols_with_special_chars(self):
        """Valid symbols with dash and caret are accepted."""
        req1 = TradePreviewRequest(symbol="BRK-B", entry_price=150.00)
        assert req1.symbol == "BRK-B"

        req2 = TradePreviewRequest(symbol="SPY^X", entry_price=400.00)
        assert req2.symbol == "SPY^X"


class TestPreTradeImpactRequest:
    """Test POST /api/algo/pre-trade-impact request validation."""

    def test_valid_symbol_only(self):
        """Valid request with symbol only."""
        req = PreTradeImpactRequest(symbol="AAPL")
        assert req.symbol == "AAPL"
        assert req.entry_price is None
        assert req.position_dollars is None
        assert req.position_pct is None

    def test_valid_with_entry_price(self):
        """Valid request with entry price."""
        req = PreTradeImpactRequest(symbol="MSFT", entry_price=300.00)
        assert req.symbol == "MSFT"
        assert req.entry_price == 300.00

    def test_valid_with_position_dollars(self):
        """Valid request with position dollars."""
        req = PreTradeImpactRequest(symbol="AAPL", position_dollars=10000)
        assert req.position_dollars == 10000

    def test_valid_with_position_pct(self):
        """Valid request with position percentage."""
        req = PreTradeImpactRequest(symbol="AAPL", position_pct=5.0)
        assert req.position_pct == 5.0

    def test_valid_with_all_optional_fields(self):
        """Valid request with all optional fields."""
        req = PreTradeImpactRequest(
            symbol="AAPL", entry_price=150.00, position_dollars=10000, position_pct=5.0
        )
        assert req.symbol == "AAPL"
        assert req.entry_price == 150.00
        assert req.position_dollars == 10000
        assert req.position_pct == 5.0

    def test_missing_symbol_rejected(self):
        """Missing symbol is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(entry_price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "symbol" for err in errors)

    def test_negative_entry_price_rejected(self):
        """Negative entry price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(symbol="AAPL", entry_price=-150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "entry_price" for err in errors)

    def test_zero_position_dollars_rejected(self):
        """Zero position dollars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(symbol="AAPL", position_dollars=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_dollars" for err in errors)

    def test_negative_position_pct_rejected(self):
        """Negative position percentage is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(symbol="AAPL", position_pct=-5.0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_pct" for err in errors)

    def test_position_pct_over_100_rejected(self):
        """Position percentage > 100 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(symbol="AAPL", position_pct=150.0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_pct" for err in errors)

    def test_position_pct_equal_100_accepted(self):
        """Position percentage = 100 is accepted."""
        req = PreTradeImpactRequest(symbol="AAPL", position_pct=100.0)
        assert req.position_pct == 100.0

    def test_zero_position_pct_rejected(self):
        """Position percentage = 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PreTradeImpactRequest(symbol="AAPL", position_pct=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_pct" for err in errors)


class TestContactSubmissionRequest:
    """Test POST /api/contact request validation."""

    def test_valid_minimal_request(self):
        """Valid request with required fields only."""
        req = ContactSubmissionRequest(
            name="John Doe", email="john@example.com", message="This is a test message"
        )
        assert req.name == "John Doe"
        assert req.email == "john@example.com"
        assert req.message == "This is a test message"
        assert req.subject is None
        assert req.phone is None

    def test_valid_full_request(self):
        """Valid request with all fields."""
        req = ContactSubmissionRequest(
            name="Jane Doe",
            email="jane@example.com",
            subject="Test Subject",
            message="This is a test message",
            phone="+1-800-555-0123",
        )
        assert req.name == "Jane Doe"
        assert req.email == "jane@example.com"
        assert req.subject == "Test Subject"
        assert req.message == "This is a test message"
        assert req.phone == "+1-800-555-0123"

    def test_name_whitespace_stripped(self):
        """Name whitespace is stripped."""
        req = ContactSubmissionRequest(
            name="  John Doe  ", email="john@example.com", message="Test"
        )
        assert req.name == "John Doe"

    def test_missing_name_rejected(self):
        """Missing name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(email="john@example.com", message="Test")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "name" for err in errors)

    def test_empty_name_rejected(self):
        """Empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(name="", email="john@example.com", message="Test")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "name" for err in errors)

    def test_missing_email_rejected(self):
        """Missing email is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(name="John Doe", message="Test")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "email" for err in errors)

    def test_invalid_email_rejected(self):
        """Invalid email is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(
                name="John Doe", email="invalid-email", message="Test"
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "email" for err in errors)

    def test_missing_message_rejected(self):
        """Missing message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(name="John Doe", email="john@example.com")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "message" for err in errors)

    def test_empty_message_rejected(self):
        """Empty message is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(
                name="John Doe", email="john@example.com", message=""
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "message" for err in errors)

    def test_xss_in_message_rejected(self):
        """XSS attempts in message are rejected."""
        xss_payloads = [
            '<script>alert("xss")</script>',
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<iframe src=evil.com></iframe>",
            'onclick="alert(1)"',
        ]
        for payload in xss_payloads:
            with pytest.raises(ValidationError):
                ContactSubmissionRequest(
                    name="John Doe", email="john@example.com", message=payload
                )

    def test_xss_in_name_rejected(self):
        """XSS attempts in name are rejected."""
        with pytest.raises(ValidationError):
            ContactSubmissionRequest(
                name="John<script>alert(1)</script>",
                email="john@example.com",
                message="Test",
            )

    def test_xss_in_subject_rejected(self):
        """XSS attempts in subject are rejected."""
        with pytest.raises(ValidationError):
            ContactSubmissionRequest(
                name="John Doe",
                email="john@example.com",
                message="Test",
                subject="<img src=x onerror=alert(1)>",
            )

    def test_sql_patterns_in_message_allowed(self):
        """SQL patterns in message are allowed (parameterized queries prevent injection)."""
        sql_like_messages = [
            "'; DROP TABLE users; --",
            "UNION SELECT * FROM users",
            "DELETE FROM users WHERE 1=1",
            "How do I write queries like SELECT * FROM table?",
        ]
        for message in sql_like_messages:
            req = ContactSubmissionRequest(
                name="John Doe", email="john@example.com", message=message
            )
            assert req.message == message

    def test_valid_phone_formats(self):
        """Valid phone formats are accepted."""
        valid_phones = [
            "+1-800-555-0123",
            "(800) 555-0123",
            "800-555-0123",
            "8005550123",
            "+1 800 555 0123",
        ]
        for phone in valid_phones:
            req = ContactSubmissionRequest(
                name="John Doe", email="john@example.com", message="Test", phone=phone
            )
            assert req.phone == phone

    def test_invalid_phone_rejected(self):
        """Invalid phone format is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContactSubmissionRequest(
                name="John Doe", email="john@example.com", message="Test", phone="123"
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "phone" for err in errors)

    def test_name_max_length(self):
        """Name respects max length of 100 chars."""
        with pytest.raises(ValidationError):
            ContactSubmissionRequest(
                name="x" * 101, email="john@example.com", message="Test"
            )

    def test_message_max_length(self):
        """Message respects max length of 5000 chars."""
        with pytest.raises(ValidationError):
            ContactSubmissionRequest(
                name="John Doe", email="john@example.com", message="x" * 5001
            )

    def test_subject_optional(self):
        """Subject is optional."""
        req = ContactSubmissionRequest(
            name="John Doe", email="john@example.com", message="Test"
        )
        assert req.subject is None

    def test_phone_optional(self):
        """Phone is optional."""
        req = ContactSubmissionRequest(
            name="John Doe", email="john@example.com", message="Test"
        )
        assert req.phone is None


class TestVerifyUserEmailRequest:
    """Test POST /api/admin/verify-user-email request validation."""

    def test_valid_request(self):
        """Valid request with username."""
        req = VerifyUserEmailRequest(username="testuser")
        assert req.username == "testuser"

    def test_valid_with_email_format(self):
        """Username can be in email format."""
        req = VerifyUserEmailRequest(username="user@example.com")
        assert req.username == "user@example.com"

    def test_valid_with_special_chars(self):
        """Username can contain dots, dashes, underscores, +."""
        req1 = VerifyUserEmailRequest(username="test.user")
        assert req1.username == "test.user"

        req2 = VerifyUserEmailRequest(username="test-user")
        assert req2.username == "test-user"

        req3 = VerifyUserEmailRequest(username="test_user")
        assert req3.username == "test_user"

        req4 = VerifyUserEmailRequest(username="test+user")
        assert req4.username == "test+user"

    def test_missing_username_rejected(self):
        """Missing username is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            VerifyUserEmailRequest()
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "username" for err in errors)

    def test_empty_username_rejected(self):
        """Empty username is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            VerifyUserEmailRequest(username="")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "username" for err in errors)

    def test_username_with_invalid_chars_rejected(self):
        """Username with invalid characters is rejected."""
        invalid_usernames = [
            "test!user",
            "test#user",
            "test$user",
            "test%user",
            "test&user",
        ]
        for username in invalid_usernames:
            with pytest.raises(ValidationError):
                VerifyUserEmailRequest(username=username)


class TestManualTradeRequest:
    """Test POST /api/trades/manual request validation."""

    def test_valid_minimal_request(self):
        """Valid request with required fields only."""
        req = ManualTradeRequest(symbol="AAPL", quantity=100, price=150.50)
        assert req.symbol == "AAPL"
        assert req.quantity == 100
        assert req.price == 150.50
        assert req.trade_type == "buy"
        assert req.execution_date is None
        assert req.stop_loss_price is None

    def test_valid_full_request(self):
        """Valid request with all fields."""
        req = ManualTradeRequest(
            symbol="MSFT",
            trade_type="sell",
            quantity=50,
            price=300.00,
            execution_date="2026-06-14",
            stop_loss_price=295.00,
        )
        assert req.symbol == "MSFT"
        assert req.trade_type == "sell"
        assert req.quantity == 50
        assert req.price == 300.00
        assert req.execution_date == "2026-06-14"
        assert req.stop_loss_price == 295.00

    def test_symbol_normalized_to_uppercase(self):
        """Symbol is normalized to uppercase."""
        req = ManualTradeRequest(symbol="aapl", quantity=100, price=150.00)
        assert req.symbol == "AAPL"

    def test_trade_type_normalized_to_lowercase(self):
        """Trade type is normalized to lowercase."""
        req = ManualTradeRequest(
            symbol="AAPL", trade_type="BUY", quantity=100, price=150.00
        )
        assert req.trade_type == "buy"

    def test_missing_symbol_rejected(self):
        """Missing symbol is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(quantity=100, price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "symbol" for err in errors)

    def test_missing_quantity_rejected(self):
        """Missing quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_missing_price_rejected(self):
        """Missing price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", quantity=100)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "price" for err in errors)

    def test_zero_quantity_rejected(self):
        """Zero quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", quantity=0, price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_negative_quantity_rejected(self):
        """Negative quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", quantity=-100, price=150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_zero_price_rejected(self):
        """Zero price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", quantity=100, price=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "price" for err in errors)

    def test_negative_price_rejected(self):
        """Negative price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(symbol="AAPL", quantity=100, price=-150.00)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "price" for err in errors)

    def test_invalid_trade_type_rejected(self):
        """Invalid trade type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(
                symbol="AAPL", trade_type="invalid", quantity=100, price=150.00
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "trade_type" for err in errors)

    def test_invalid_execution_date_format_rejected(self):
        """Invalid execution date format is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(
                symbol="AAPL", quantity=100, price=150.00, execution_date="06-14-2026"
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "execution_date" for err in errors)

    def test_valid_execution_date_format(self):
        """Valid YYYY-MM-DD execution date is accepted."""
        req = ManualTradeRequest(
            symbol="AAPL", quantity=100, price=150.00, execution_date="2026-06-14"
        )
        assert req.execution_date == "2026-06-14"

    def test_zero_stop_loss_rejected(self):
        """Zero stop loss is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(
                symbol="AAPL", quantity=100, price=150.00, stop_loss_price=0
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_negative_stop_loss_rejected(self):
        """Negative stop loss is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ManualTradeRequest(
                symbol="AAPL", quantity=100, price=150.00, stop_loss_price=-10.00
            )
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_positive_stop_loss_accepted(self):
        """Positive stop loss is accepted."""
        req = ManualTradeRequest(
            symbol="AAPL", quantity=100, price=150.00, stop_loss_price=145.00
        )
        assert req.stop_loss_price == 145.00

    def test_stop_loss_can_be_above_price(self):
        """Stop loss can be above entry price (for short selling scenarios)."""
        req = ManualTradeRequest(
            symbol="AAPL",
            trade_type="sell",
            quantity=100,
            price=150.00,
            stop_loss_price=155.00,
        )
        assert req.stop_loss_price == 155.00


class TestPositionUpdateRequest:
    """Test POST /api/position/update request validation."""

    def test_valid_minimal_request(self):
        """Valid request with required position_id only."""
        req = PositionUpdateRequest(position_id=1)
        assert req.position_id == 1
        assert req.quantity is None
        assert req.stop_loss_price is None

    def test_valid_quantity_update(self):
        """Valid request updating quantity."""
        req = PositionUpdateRequest(position_id=1, quantity=100)
        assert req.position_id == 1
        assert req.quantity == 100

    def test_valid_stop_loss_update(self):
        """Valid request updating stop loss."""
        req = PositionUpdateRequest(position_id=1, stop_loss_price=145.50)
        assert req.position_id == 1
        assert req.stop_loss_price == 145.50

    def test_valid_target_prices_update(self):
        """Valid request updating target prices."""
        req = PositionUpdateRequest(
            position_id=1,
            target_1_price=155.00,
            target_2_price=165.00,
            target_3_price=175.00,
        )
        assert req.target_1_price == 155.00
        assert req.target_2_price == 165.00
        assert req.target_3_price == 175.00

    def test_missing_position_id_rejected(self):
        """Missing position_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(quantity=100)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_id" for err in errors)

    def test_zero_position_id_rejected(self):
        """Zero position_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_id" for err in errors)

    def test_negative_position_id_rejected(self):
        """Negative position_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=-1)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_id" for err in errors)

    def test_zero_quantity_rejected(self):
        """Zero quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, quantity=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_negative_quantity_rejected(self):
        """Negative quantity is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, quantity=-100)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_unreasonably_large_quantity_rejected(self):
        """Quantity over 1,000,000 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, quantity=1_000_001)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "quantity" for err in errors)

    def test_valid_large_quantity_accepted(self):
        """Quantity up to 1,000,000 is accepted."""
        req = PositionUpdateRequest(position_id=1, quantity=1_000_000)
        assert req.quantity == 1_000_000

    def test_zero_stop_loss_rejected(self):
        """Zero stop loss price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, stop_loss_price=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_negative_stop_loss_rejected(self):
        """Negative stop loss price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, stop_loss_price=-10.50)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_unreasonably_large_stop_loss_rejected(self):
        """Stop loss price over $1M is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, stop_loss_price=1_000_001)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "stop_loss_price" for err in errors)

    def test_zero_target_price_rejected(self):
        """Zero target price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, target_1_price=0)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "target_1_price" for err in errors)

    def test_negative_target_price_rejected(self):
        """Negative target price is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, target_2_price=-100)
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "target_2_price" for err in errors)

    def test_stop_loss_vs_entry_validation_long(self):
        """For long positions, stop loss must be below entry price."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            stop_loss_price=155.00,
            position_type="buy",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_stop_loss_vs_entry()
        assert "must be below" in str(exc_info.value)

    def test_stop_loss_vs_entry_validation_short(self):
        """For short positions, stop loss must be above entry price."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            stop_loss_price=145.00,
            position_type="sell",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_stop_loss_vs_entry()
        assert "must be above" in str(exc_info.value)

    def test_stop_loss_too_close_to_entry_long(self):
        """Stop loss too close to entry price (long) is rejected."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            stop_loss_price=149.995,
            position_type="long",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_stop_loss_vs_entry()
        assert "too close" in str(exc_info.value)

    def test_valid_stop_loss_for_long(self):
        """Valid stop loss below entry for long position."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            stop_loss_price=145.00,
            position_type="buy",
        )
        req.validate_stop_loss_vs_entry()  # Should not raise

    def test_valid_stop_loss_for_short(self):
        """Valid stop loss above entry for short position."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            stop_loss_price=155.00,
            position_type="short",
        )
        req.validate_stop_loss_vs_entry()  # Should not raise

    def test_targets_must_be_above_entry_long(self):
        """For long positions, targets must be above entry price."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            target_1_price=145.00,
            position_type="buy",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_targets_vs_entry()
        assert "must be above" in str(exc_info.value)

    def test_targets_must_be_below_entry_short(self):
        """For short positions, targets must be below entry price."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            target_2_price=155.00,
            position_type="sell",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_targets_vs_entry()
        assert "must be below" in str(exc_info.value)

    def test_valid_targets_for_long(self):
        """Valid targets above entry for long position."""
        req = PositionUpdateRequest(
            position_id=1,
            entry_price=150.00,
            target_1_price=155.00,
            target_2_price=165.00,
            target_3_price=175.00,
            position_type="buy",
        )
        req.validate_targets_vs_entry()  # Should not raise

    def test_targets_must_be_ordered_ascending_long(self):
        """For long positions, targets must be in ascending order."""
        req = PositionUpdateRequest(
            position_id=1,
            target_1_price=170.00,
            target_2_price=160.00,
            target_3_price=180.00,
            position_type="long",
        )
        with pytest.raises(ValueError) as exc_info:
            req.validate_targets_ordered()
        assert "ascending order" in str(exc_info.value)

    def test_valid_targets_ordered(self):
        """Valid targets in correct order."""
        req = PositionUpdateRequest(
            position_id=1,
            target_1_price=155.00,
            target_2_price=165.00,
            target_3_price=175.00,
            position_type="long",
        )
        req.validate_targets_ordered()  # Should not raise

    def test_position_type_normalized_to_lowercase(self):
        """Position type is normalized to lowercase."""
        req = PositionUpdateRequest(position_id=1, position_type="BUY")
        assert req.position_type == "buy"

    def test_invalid_position_type_rejected(self):
        """Invalid position type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PositionUpdateRequest(position_id=1, position_type="invalid")
        errors = exc_info.value.errors()
        assert any(err["loc"][0] == "position_type" for err in errors)

    def test_position_type_sell_valid(self):
        """Position type 'sell' is valid."""
        req = PositionUpdateRequest(position_id=1, position_type="sell")
        assert req.position_type == "sell"

    def test_position_type_short_valid(self):
        """Position type 'short' is valid."""
        req = PositionUpdateRequest(position_id=1, position_type="short")
        assert req.position_type == "short"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
