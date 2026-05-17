"""
Input validation schema using Pydantic for all API endpoints.
Ensures bad data never enters the system.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Tuple
from datetime import datetime, timedelta
import re


class SymbolRequest(BaseModel):
    """Validate stock symbol format."""
    symbol: str = Field(..., min_length=1, max_length=20)

    @validator('symbol')
    def validate_symbol_format(cls, v):
        """Symbol must be uppercase alphanumeric with optional dots/hyphens."""
        if not re.match(r'^[A-Z0-9.\-]{1,20}$', v):
            raise ValueError(f'Invalid symbol format: {v}. Expected uppercase alphanumeric with optional . or -')
        return v.upper()


class PaginationParams(BaseModel):
    """Validate pagination parameters."""
    limit: int = Field(default=25, ge=1, le=10000)
    offset: int = Field(default=0, ge=0, le=1000000)

    @validator('offset')
    def validate_offset_not_too_large(cls, v, values):
        """Offset must be reasonable."""
        if v > 1000000:
            raise ValueError(f'Offset {v} exceeds maximum (1000000)')
        return v


class DateRangeParams(BaseModel):
    """Validate date range parameters."""
    start_date: Optional[str] = Field(None)
    end_date: Optional[str] = Field(None)
    days_back: Optional[int] = Field(None, ge=1, le=730)  # Max 2 years

    @validator('start_date', 'end_date', pre=True, always=True)
    def validate_date_format(cls, v):
        """Date must be YYYY-MM-DD format."""
        if v is None:
            return v
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f'Invalid date format: {v}. Expected YYYY-MM-DD')
        return v

    @validator('end_date')
    def end_after_start(cls, v, values):
        """End date must be after start date."""
        if v is None or 'start_date' not in values or values['start_date'] is None:
            return v
        start = datetime.strptime(values['start_date'], '%Y-%m-%d')
        end = datetime.strptime(v, '%Y-%m-%d')
        if end < start:
            raise ValueError(f'End date {v} must be after start date {values["start_date"]}')
        return v


class PriceData(BaseModel):
    """Validate OHLCV price data."""
    symbol: str
    date: str
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: int = Field(..., ge=0)

    @validator('date')
    def validate_date(cls, v):
        """Date must be valid YYYY-MM-DD."""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f'Invalid date: {v}. Expected YYYY-MM-DD')
        return v

    @validator('high')
    def validate_high(cls, v, values):
        """High must be >= all other prices."""
        if 'low' in values and v < values['low']:
            raise ValueError(f'High {v} must be >= low {values["low"]}')
        return v

    @validator('low')
    def validate_low(cls, v, values):
        """Low must be <= all other prices."""
        if 'high' in values and v > values['high']:
            raise ValueError(f'Low {v} must be <= high {values["high"]}')
        if 'open' in values and v > values['open']:
            raise ValueError(f'Low {v} must be <= open {values["open"]}')
        if 'close' in values and v > values['close']:
            raise ValueError(f'Low {v} must be <= close {values["close"]}')
        return v

    @validator('close', 'open')
    def validate_price_in_range(cls, v, values):
        """Close and open must be between low and high."""
        if 'low' in values and 'high' in values:
            if not (values['low'] <= v <= values['high']):
                raise ValueError(f'Price {v} must be between low {values["low"]} and high {values["high"]}')
        return v


class TradeRequest(BaseModel):
    """Validate trade execution request."""
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: int = Field(..., gt=0, le=100000)
    entry_price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    target_1: Optional[float] = Field(None, gt=0)
    target_2: Optional[float] = Field(None, gt=0)
    target_3: Optional[float] = Field(None, gt=0)

    @validator('symbol')
    def validate_symbol(cls, v):
        """Symbol must be valid format."""
        if not re.match(r'^[A-Z0-9.\-]{1,20}$', v):
            raise ValueError(f'Invalid symbol: {v}')
        return v

    @validator('stop_loss')
    def validate_stop_loss(cls, v, values):
        """Stop loss must be below entry price."""
        if 'entry_price' in values:
            entry = values['entry_price']
            if v >= entry:
                raise ValueError(f'Stop loss {v} must be below entry price {entry}')
            # Stop must be at least 1% below entry
            if v >= entry * 0.99:
                raise ValueError(f'Stop loss too tight: {v} within 1% of entry {entry}')
        return v

    @validator('target_1', 'target_2', 'target_3')
    def validate_targets(cls, v, values):
        """Targets must be above entry price and in ascending order."""
        if v is None:
            return v
        if 'entry_price' in values and v <= values['entry_price']:
            raise ValueError(f'Target {v} must be above entry price {values["entry_price"]}')
        return v

    @validator('target_2')
    def target_2_above_target_1(cls, v, values):
        """Target 2 must be above Target 1."""
        if v is None or 'target_1' not in values or values['target_1'] is None:
            return v
        if v <= values['target_1']:
            raise ValueError(f'Target 2 {v} must be above Target 1 {values["target_1"]}')
        return v

    @validator('target_3')
    def target_3_above_target_2(cls, v, values):
        """Target 3 must be above Target 2."""
        if v is None or 'target_2' not in values or values['target_2'] is None:
            return v
        if v <= values['target_2']:
            raise ValueError(f'Target 3 {v} must be above Target 2 {values["target_2"]}')
        return v


class ScoreData(BaseModel):
    """Validate stock score data."""
    symbol: str
    momentum_score: Optional[float] = Field(None, ge=0, le=100)
    growth_score: Optional[float] = Field(None, ge=0, le=100)
    stability_score: Optional[float] = Field(None, ge=0, le=100)
    value_score: Optional[float] = Field(None, ge=0, le=100)
    quality_score: Optional[float] = Field(None, ge=0, le=100)
    positioning_score: Optional[float] = Field(None, ge=0, le=100)
    composite_score: Optional[float] = Field(None, ge=0, le=100)

    @validator('symbol')
    def validate_symbol(cls, v):
        """Symbol must be valid format."""
        if not re.match(r'^[A-Z0-9.\-]{1,20}$', v):
            raise ValueError(f'Invalid symbol: {v}')
        return v


class ContactRequest(BaseModel):
    """Validate contact form submission."""
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., regex=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    subject: str = Field(..., min_length=5, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)

    @validator('email')
    def validate_email(cls, v):
        """Email must be valid format."""
        if '@' not in v or '.' not in v.split('@')[1]:
            raise ValueError(f'Invalid email: {v}')
        return v.lower()


def validate_request(data: dict, model_class) -> Tuple[bool, Optional[str], Optional[object]]:
    """
    Validate request data against Pydantic model.

    Returns: (is_valid, error_message, validated_data)
    """
    try:
        validated = model_class(**data)
        return True, None, validated
    except ValueError as e:
        return False, str(e), None
    except Exception as e:
        return False, f'Validation error: {str(e)}', None
