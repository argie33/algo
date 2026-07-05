"""Pydantic models for API request bodies - single source of truth for request validation."""


from __future__ import annotations

import logging
import re
from typing import Any, cast

from pydantic import BaseModel, Field, ValidationInfo, field_validator

# Import security validators - handle both test (sys.path based) and Lambda (package based) contexts
try:
    from ..security_validators import (
        ValidationError,
        validate_email,
        validate_symbol,
    )
except (ImportError, ValueError):
    # Fallback for test context where lambda/api is added to sys.path
    from security_validators import (  # type: ignore[no-redef]
        ValidationError,
        validate_email,
        validate_symbol,
    )

logger = logging.getLogger(__name__)

XSS_PATTERNS = [
    r"<script",
    r"<iframe",
    r"<embed",
    r"<object",
    r"<img[\s/]",
    r"<svg\s+[^>]*on",
    r"javascript:",
    r"vbscript:",
    r"data:text/html",
    r"on\w+[\s/]*=",
]


class TradePreviewRequest(BaseModel):
    """Request model for POST /api/algo/preview - Calculate position preview before trade entry."""

    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)", min_length=1, max_length=10)
    entry_price: float = Field(..., description="Proposed entry price for position", gt=0)
    stop_loss_price: float | None = Field(None, description="Stop loss price level")

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, v: str) -> str:
        try:
            return validate_symbol(v)
        except ValidationError as e:
            raise ValueError(str(e)) from None

    @field_validator("stop_loss_price")
    @classmethod
    def validate_stop_loss(cls, v: Any, info: ValidationInfo) -> float | None:
        if v is not None and "entry_price" in info.data:
            entry_price = info.data["entry_price"]
            if v >= entry_price:
                raise ValueError("Stop loss price must be below entry price")
        return cast(float | None, v)


class ContactSubmissionRequest(BaseModel):
    """Request model for POST /api/contact - Submit contact form."""

    name: str = Field(..., description="Contact name", min_length=1, max_length=100)
    email: str = Field(..., description="Contact email address", min_length=5, max_length=200)
    subject: str | None = Field(None, description="Message subject", max_length=200)
    message: str = Field(..., description="Message body", min_length=1, max_length=5000)
    phone: str | None = Field(None, description="Phone number (optional)", max_length=20)

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: Any) -> str:
        try:
            return validate_email(v)
        except ValidationError as e:
            raise ValueError(str(e)) from None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format.

        Returns:
            str: Valid phone number if non-empty and matches pattern
            None: If phone is None or empty string (phone is optional field)
        """
        if v is not None and v.strip():
            # Pattern: +1-800-555-0123, (800) 555-0123, etc.
            if not re.match(r"^\+?[\d\s\-\(\)]{10,15}$", v):
                raise ValueError("Phone number format invalid")
            return v
        logger.debug("validate_phone: phone is None or empty (optional field not provided)")
        return None

    @field_validator("name", "message", "subject")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
        return v

    @field_validator("message", "name", "subject")
    @classmethod
    def check_dangerous_content(cls, v: Any, info: ValidationInfo) -> str | None:
        """Check for XSS patterns (plaintext input that will be rendered as HTML)."""
        if v is None:
            return None

        field_name = info.field_name
        for pattern in XSS_PATTERNS:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError(f"{field_name} contains invalid content")

        return cast(str, v)


class VerifyUserEmailRequest(BaseModel):
    """Request model for POST /api/admin/verify-user-email - Verify user email in Cognito."""

    username: str = Field(..., description="Cognito username to verify", min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Any) -> str:
        # Allow email format or standard username format
        if not re.match(r"^[a-zA-Z0-9._\-@+]+$", v):
            raise ValueError("Username must contain only alphanumeric characters, dots, underscores, dashes, @ or +")
        return cast(str, v)


class PreTradeImpactRequest(BaseModel):
    """Request model for POST /api/algo/pre-trade-impact - Estimate impact of a potential trade."""

    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)", min_length=1, max_length=10)
    entry_price: float | None = Field(None, description="Proposed entry price for position", gt=0)
    position_dollars: float | None = Field(None, description="Position size in dollars (if specified)", gt=0)
    position_pct: float | None = Field(None, description="Position size as % of portfolio (0-100)", gt=0, le=100)

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, v: str) -> str:
        try:
            return validate_symbol(v)
        except ValidationError as e:
            raise ValueError(str(e)) from None


class ManualTradeRequest(BaseModel):
    """Request model for POST /api/trades/manual - Manually log a trade entry."""

    symbol: str = Field(..., description="Stock ticker symbol (1-10 chars)", min_length=1, max_length=10)
    trade_type: str = Field(default="buy", description="Trade type: buy or sell")
    quantity: int = Field(..., description="Trade quantity (must be positive)", gt=0)
    price: float = Field(..., description="Trade price per share (must be positive)", gt=0)
    execution_date: str | None = Field(None, description="Trade execution date (YYYY-MM-DD format, defaults to today)")
    stop_loss_price: float | None = Field(None, description="Stop loss price (optional)")

    @field_validator("symbol")
    @classmethod
    def validate_symbol_field(cls, v: str) -> str:
        try:
            return validate_symbol(v)
        except ValidationError as e:
            raise ValueError(str(e)) from None

    @field_validator("trade_type")
    @classmethod
    def validate_trade_type(cls, v: str) -> str:
        v_lower = v.lower()
        if v_lower not in ("buy", "sell"):
            raise ValueError('Trade type must be "buy" or "sell"')
        return v_lower

    @field_validator("execution_date")
    @classmethod
    def validate_execution_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                # Validate it's a valid date format (YYYY-MM-DD)
                from datetime import datetime

                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Execution date must be in YYYY-MM-DD format") from None
        return v

    @field_validator("stop_loss_price")
    @classmethod
    def validate_stop_loss(cls, v: Any, info: ValidationInfo) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("Stop loss price must be greater than 0")
        return cast(float | None, v)


class PositionUpdateRequest(BaseModel):
    """Request model for POST/PUT /api/position/update - Update position parameters."""

    position_id: int = Field(..., description="Position ID to update")
    quantity: int | None = Field(None, description="Updated quantity (must be positive if provided)", gt=0)
    stop_loss_price: float | None = Field(None, description="Updated stop loss price (must be > 0 and make sense)")
    target_1_price: float | None = Field(None, description="Target 1 price (must be > entry_price for buys)")
    target_2_price: float | None = Field(None, description="Target 2 price (must be > entry_price for buys)")
    target_3_price: float | None = Field(None, description="Target 3 price (must be > entry_price for buys)")
    entry_price: float | None = Field(None, description="Entry price (used for validation of stop loss and targets)")
    position_type: str | None = Field(None, description="Position type: 'buy' or 'sell' (used for validation)")

    @field_validator("position_id")
    @classmethod
    def validate_position_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Position ID must be a positive integer")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int | None) -> int | None:
        if v is not None:
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError("Quantity must be an integer")
            if v <= 0:
                raise ValueError("Quantity must be positive")
            if v > 1_000_000:
                raise ValueError("Quantity is unreasonably large (max 1,000,000)")
        return v

    @field_validator("stop_loss_price")
    @classmethod
    def validate_stop_loss_price(cls, v: float | None) -> float | None:
        if v is not None:
            if v <= 0:
                raise ValueError("Stop loss price must be greater than 0")
            if v > 1_000_000:
                raise ValueError("Stop loss price is unreasonably large (max $1M)")
        return v

    @field_validator("target_1_price", "target_2_price", "target_3_price")
    @classmethod
    def validate_target_price(cls, v: float | None) -> float | None:
        if v is not None:
            if v <= 0:
                raise ValueError("Target price must be greater than 0")
            if v > 1_000_000:
                raise ValueError("Target price is unreasonably large (max $1M)")
        return v

    @field_validator("entry_price")
    @classmethod
    def validate_entry_price(cls, v: float | None) -> float | None:
        if v is not None:
            if v <= 0:
                raise ValueError("Entry price must be greater than 0")
            if v > 1_000_000:
                raise ValueError("Entry price is unreasonably large (max $1M)")
        return v

    @field_validator("position_type")
    @classmethod
    def validate_position_type(cls, v: str | None) -> str | None:
        """Validate position type field.

        Returns:
            str: Lowercase position type ("buy", "sell", "long", "short")
            None: If position_type is None (optional field not provided)
        """
        if v is not None:
            v_lower = v.lower()
            if v_lower not in ("buy", "sell", "long", "short"):
                raise ValueError('Position type must be "buy", "sell", "long", or "short"')
            return v_lower
        logger.debug("validate_position_type: position_type is None (optional field not provided)")
        return None

    def validate_stop_loss_vs_entry(self) -> None:
        """Cross-field validation: stop loss must be within bounds of entry price."""
        if self.stop_loss_price is None or self.entry_price is None:
            return

        if self.position_type and self.position_type in ("buy", "long"):
            if self.stop_loss_price >= self.entry_price:
                raise ValueError(
                    f"For long positions, stop_loss_price ({self.stop_loss_price}) "
                    f"must be below entry_price ({self.entry_price})"
                )
            risk_amount = self.entry_price - self.stop_loss_price
            if risk_amount < 0.01:
                raise ValueError("Stop loss is too close to entry price (min risk: $0.01)")
        elif self.position_type and self.position_type in ("sell", "short"):
            if self.stop_loss_price <= self.entry_price:
                raise ValueError(
                    f"For short positions, stop_loss_price ({self.stop_loss_price}) "
                    f"must be above entry_price ({self.entry_price})"
                )
            risk_amount = self.stop_loss_price - self.entry_price
            if risk_amount < 0.01:
                raise ValueError("Stop loss is too close to entry price (min risk: $0.01)")

    def validate_targets_vs_entry(self) -> None:
        """Cross-field validation: targets must be above entry price (for longs)."""
        if self.entry_price is None:
            return

        targets = [self.target_1_price, self.target_2_price, self.target_3_price]
        for i, target in enumerate(targets, 1):
            if target is None:
                continue

            if self.position_type and self.position_type in ("buy", "long"):
                if target <= self.entry_price:
                    raise ValueError(f"Target {i} ({target}) must be above entry_price ({self.entry_price})")
            elif self.position_type and self.position_type in ("sell", "short"):
                if target >= self.entry_price:
                    raise ValueError(f"Target {i} ({target}) must be below entry_price ({self.entry_price})")

    def validate_targets_ordered(self) -> None:
        """Cross-field validation: targets should be in ascending order (for longs)."""
        targets = [self.target_1_price, self.target_2_price, self.target_3_price]
        valid_targets = [t for t in targets if t is not None]

        if len(valid_targets) < 2:
            return

        if self.position_type and self.position_type in ("buy", "long"):
            for i in range(len(valid_targets) - 1):
                if valid_targets[i] >= valid_targets[i + 1]:
                    raise ValueError("Targets must be in ascending order (T1 < T2 < T3) for long positions")
