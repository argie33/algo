"""Pydantic models for API request bodies - single source of truth for request validation."""
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


class TradePreviewRequest(BaseModel):
    """Request model for POST /api/algo/preview - Calculate position preview before trade entry."""
    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)", min_length=1, max_length=10)
    entry_price: float = Field(..., description="Proposed entry price for position", gt=0)
    stop_loss_price: Optional[float] = Field(None, description="Stop loss price level")

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format - alphanumeric with optional dash/caret."""
        if not re.match(r'^[A-Z0-9\-\^]{1,10}$', v.upper()):
            raise ValueError('Symbol must be 1-10 alphanumeric characters, dashes, or carets')
        return v.upper()

    @field_validator('stop_loss_price')
    @classmethod
    def validate_stop_loss(cls, v: Optional[float], info) -> Optional[float]:
        """Validate that stop loss is below entry price if provided."""
        if v is not None and 'entry_price' in info.data:
            entry_price = info.data['entry_price']
            if v >= entry_price:
                raise ValueError('Stop loss price must be below entry price')
        return v


class PreTradeImpactRequest(BaseModel):
    """Request model for POST /api/algo/pre-trade-impact - Analyze impact of potential trade."""
    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)", min_length=1, max_length=10)
    entry_price: Optional[float] = Field(None, description="Proposed entry price (optional)")
    position_dollars: Optional[float] = Field(None, description="Position size in dollars (optional)")
    position_pct: Optional[float] = Field(None, description="Position size as percentage of portfolio (optional)")

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format - alphanumeric with optional dash/caret."""
        if not re.match(r'^[A-Z0-9\-\^]{1,10}$', v.upper()):
            raise ValueError('Symbol must be 1-10 alphanumeric characters, dashes, or carets')
        return v.upper()

    @field_validator('entry_price')
    @classmethod
    def validate_entry_price(cls, v: Optional[float]) -> Optional[float]:
        """Validate entry price is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError('Entry price must be greater than 0')
        return v

    @field_validator('position_dollars')
    @classmethod
    def validate_position_dollars(cls, v: Optional[float]) -> Optional[float]:
        """Validate position size in dollars is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError('Position dollars must be greater than 0')
        return v

    @field_validator('position_pct')
    @classmethod
    def validate_position_pct(cls, v: Optional[float]) -> Optional[float]:
        """Validate position percentage is between 0 and 100 if provided."""
        if v is not None:
            if v <= 0 or v > 100:
                raise ValueError('Position percentage must be between 0 and 100')
        return v


class ContactSubmissionRequest(BaseModel):
    """Request model for POST /api/contact - Submit contact form."""
    name: str = Field(..., description="Contact name", min_length=1, max_length=100)
    email: str = Field(..., description="Contact email address", min_length=5, max_length=200)
    subject: Optional[str] = Field(None, description="Message subject", max_length=200)
    message: str = Field(..., description="Message body", min_length=1, max_length=5000)
    phone: Optional[str] = Field(None, description="Phone number (optional)", max_length=20)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format using RFC 5322 simplified pattern."""
        # Same pattern used in contact.py for consistency
        email_pattern = re.compile(
            r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~\-]+@[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        )
        if not email_pattern.match(v):
            raise ValueError('Invalid email format')
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format if provided."""
        if v is not None and v.strip():
            # Pattern: +1-800-555-0123, (800) 555-0123, etc.
            if not re.match(r'^\+?[\d\s\-\(\)]{10,15}$', v):
                raise ValueError('Phone number format invalid')
            return v
        return None

    @field_validator('name', 'message', 'subject')
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Strip leading/trailing whitespace from string fields."""
        if v is not None:
            v = v.strip()
        return v

    @field_validator('message', 'name', 'subject')
    @classmethod
    def check_dangerous_content(cls, v: Optional[str], info) -> Optional[str]:
        """Check for dangerous patterns that could indicate XSS/SQL injection attempts."""
        if v is None:
            return v

        field_name = info.field_name
        dangerous_patterns = [
            r'<script', r'<iframe', r'<embed', r'<object', r'<img[\s/]',
            r'<svg\s+[^>]*on', r'javascript:', r'vbscript:', r'data:text/html',
            r'on\w+[\s/]*=', r'&#x[0-9a-fA-F]+;', r'&#\d{2,};',
            r'formaction\s*=', r'onfocus\s*=', r'onblur\s*=',
            r'union\s+select', r'drop\s+table', r'update\s+\w+\s+set',
            r'delete\s+from', r'insert\s+into', r';\s*rm\s', r';\s*cat\s',
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError(f'{field_name} contains invalid content')

        return v


class VerifyUserEmailRequest(BaseModel):
    """Request model for POST /api/admin/verify-user-email - Verify user email in Cognito."""
    username: str = Field(..., description="Cognito username to verify", min_length=1, max_length=256)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format - alphanumeric, dash, underscore, email format allowed."""
        # Allow email format or standard username format
        if not re.match(r'^[a-zA-Z0-9._\-@+]+$', v):
            raise ValueError('Username must contain only alphanumeric characters, dots, underscores, dashes, @ or +')
        return v


class ManualTradeRequest(BaseModel):
    """Request model for POST /api/trades/manual - Manually log a trade entry."""
    symbol: str = Field(..., description="Stock ticker symbol (1-10 chars)", min_length=1, max_length=10)
    trade_type: str = Field(default='buy', description="Trade type: buy or sell")
    quantity: int = Field(..., description="Trade quantity (must be positive)", gt=0)
    price: float = Field(..., description="Trade price per share (must be positive)", gt=0)
    execution_date: Optional[str] = Field(None, description="Trade execution date (YYYY-MM-DD format, defaults to today)")
    stop_loss_price: Optional[float] = Field(None, description="Stop loss price (optional)")

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format - alphanumeric with optional dash/caret."""
        if not re.match(r'^[A-Z0-9\-\^]{1,10}$', v.upper()):
            raise ValueError('Symbol must be 1-10 alphanumeric characters, dashes, or carets')
        return v.upper()

    @field_validator('trade_type')
    @classmethod
    def validate_trade_type(cls, v: str) -> str:
        """Validate trade type is buy or sell."""
        v_lower = v.lower()
        if v_lower not in ('buy', 'sell'):
            raise ValueError('Trade type must be "buy" or "sell"')
        return v_lower

    @field_validator('execution_date')
    @classmethod
    def validate_execution_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate execution date format if provided."""
        if v is not None:
            try:
                # Validate it's a valid date format (YYYY-MM-DD)
                from datetime import datetime
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Execution date must be in YYYY-MM-DD format')
        return v

    @field_validator('stop_loss_price')
    @classmethod
    def validate_stop_loss(cls, v: Optional[float], info) -> Optional[float]:
        """Validate stop loss if provided (optional but must be > 0)."""
        if v is not None and v <= 0:
            raise ValueError('Stop loss price must be greater than 0')
        return v
