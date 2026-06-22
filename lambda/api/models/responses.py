"""Pydantic models for API responses - single source of truth for response types."""

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class DataFreshness(BaseModel):
    """Metadata about data freshness in a response."""

    status: str = Field(..., description="Status of data freshness: OK, WARNING, STALE, CRITICAL")
    table_name: str | None = Field(None, description="Table being checked")
    age_hours: float | None = Field(None, description="Age of data in hours")
    age_days: float | None = Field(None, description="Age of data in days")
    last_updated: datetime | None = Field(None, description="Last update timestamp")
    warning_threshold_days: int | None = Field(None, description="Days before warning")


class BaseResponse(BaseModel):
    """Base response wrapper for all API responses."""

    model_config = ConfigDict(populate_by_name=True)

    status_code: int = Field(..., alias="statusCode", description="HTTP status code")
    data_freshness: DataFreshness | None = Field(None, description="Data freshness metadata")


class SuccessResponse(BaseResponse):
    """Success response for single object (generic for type safety)."""

    status_code: int = Field(default=200, alias="statusCode", description="HTTP status code")
    data: dict[str, Any] | Any = Field(..., description="Response data")


class ListResponseData(BaseModel):
    """Container for list response data."""

    items: list[dict[str, Any]] = Field(..., description="List of items")
    total: int | None = Field(None, description="Total count of items")
    limit: int | None = Field(None, description="Limit used in query")
    offset: int | None = Field(None, description="Offset used in query")


class ListResponse(BaseResponse):
    """Success response for paginated lists."""

    status_code: int = Field(default=200, alias="statusCode", description="HTTP status code")
    data: ListResponseData = Field(..., description="List data with pagination metadata")


class ErrorResponse(BaseResponse):
    """Error response."""

    status_code: int = Field(..., alias="statusCode", description="HTTP error code")
    error_type: str = Field(..., alias="errorType", description="Error type for client-side handling")
    message: str = Field(..., description="Human-readable error message")
    error: str = Field(..., alias="_error", description="Error type identifier")
    diagnostic: dict[str, Any] | None = Field(None, alias="_diagnostic", description="Diagnostic info for developers")


class HealthStatus(BaseModel):
    """Health check response."""

    status: str = Field(..., description="health, degraded, or unhealthy")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Check timestamp")
    api_route_imports: dict[str, Any] | None = Field(None)
    freshness: dict[str, Any] | None = Field(None)
    last_load_time: datetime | None = Field(None)


class HealthResponse(BaseResponse):
    """Health check response wrapper."""

    status_code: int = Field(default=200, alias="statusCode")
    data: HealthStatus = Field(...)


class StockProfile(BaseModel):
    """Stock profile response."""

    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    employees: int | None = None
    exchange: str | None = None


class StockProfileResponse(SuccessResponse):
    """Stock profile response."""

    data: StockProfile


class KeyMetrics(BaseModel):
    """Key financial metrics for a stock."""

    symbol: str
    date: datetime | None = None
    pe_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    peg_ratio: float | None = None
    dividend_yield: float | None = None
    fcf_yield: float | None = None
    debt_to_equity: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    profit_margin: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    market_cap: float | None = None
    held_percent_insiders: float | None = None
    held_percent_institutions: float | None = None


class KeyMetricsResponse(ListResponse):
    """Key metrics list response."""


class Signal(BaseModel):
    """Trading signal."""

    id: int | None = None
    symbol: str
    signal: str = Field(..., description="BUY or SELL")
    date: datetime
    timeframe: str | None = None
    signal_type: str | None = None
    strength: float | None = None
    entry_quality_score: float | None = None
    signal_quality_score: float | None = None
    volume_surge_pct: float | None = None
    risk_reward_ratio: float | None = None
    rsi: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_21: float | None = None
    atr: float | None = None
    adx: float | None = None
    mansfield_rs: float | None = None
    rs_rating: float | None = None
    breakout_quality: float | None = None
    risk_pct: float | None = None
    current_gain_pct: float | None = None
    days_in_position: int | None = None
    position_size_recommendation: float | None = None
    stage_number: int | None = None
    reason: str | None = None
    substage: str | None = None
    close: float | None = None
    volume: float | None = None
    base_type: str | None = None
    base_length_days: int | None = None
    market_stage: str | None = None
    buylevel: float | None = None
    stoplevel: float | None = None
    signal_triggered_date: datetime | None = None
    entry_price: float | None = None
    buy_zone_start: float | None = None
    buy_zone_end: float | None = None
    pivot_price: float | None = None
    initial_stop: float | None = None
    trailing_stop: float | None = None
    sell_level: float | None = None
    profit_target_8pct: float | None = None
    profit_target_20pct: float | None = None
    profit_target_25pct: float | None = None
    exit_trigger_1_price: float | None = None
    exit_trigger_2_price: float | None = None
    avg_volume_50d: float | None = None
    sector: str | None = None
    industry: str | None = None
    is_fallback: bool | None = Field(None, alias="_is_fallback")


class SignalsResponse(ListResponse):
    """Trading signals list response."""


class IncomeStatement(BaseModel):
    """Annual or quarterly income statement."""

    symbol: str
    fiscal_year: int
    fiscal_quarter: int | None = None
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None


class IncomeStatementResponse(ListResponse):
    """Income statement list response."""


class BalanceSheet(BaseModel):
    """Annual or quarterly balance sheet."""

    symbol: str
    fiscal_year: int
    fiscal_quarter: int | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None


class BalanceSheetResponse(ListResponse):
    """Balance sheet list response."""


class PriceData(BaseModel):
    """Daily price data."""

    symbol: str
    date: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    adjusted_close: float | None = None


class PriceDataResponse(ListResponse):
    """Price data list response."""


class Sector(BaseModel):
    """Sector information."""

    sector: str
    count: int | None = None
    average_pe: float | None = None
    average_score: float | None = None


class SectorResponse(ListResponse):
    """Sector list response."""


class Industry(BaseModel):
    """Industry information."""

    industry: str
    sector: str | None = None
    count: int | None = None
    average_score: float | None = None


class IndustryResponse(ListResponse):
    """Industry list response."""


class StockScore(BaseModel):
    """Stock quality score."""

    symbol: str
    score: float | None = None
    percentile: float | None = None
    components: dict[str, Any] | None = None


class StockScoresResponse(ListResponse):
    """Stock scores list response."""


class Trade(BaseModel):
    """Trading record."""

    id: int | None = None
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: datetime | None = None
    exit_price: float | None = None
    quantity: int | None = None
    status: str | None = None


class TradesResponse(ListResponse):
    """Trades list response."""


class EarningsData(BaseModel):
    """Earnings report data."""

    symbol: str
    date: datetime
    eps: float | None = None
    revenue: float | None = None
    guidance: str | None = None


class EarningsResponse(ListResponse):
    """Earnings list response."""


class EconomicIndicator(BaseModel):
    """Economic indicator data."""

    indicator: str
    date: datetime
    value: float | None = None
    previous_value: float | None = None
    forecast: float | None = None


class EconomicResponse(ListResponse):
    """Economic indicators list response."""


class SearchResult(BaseModel):
    """Search result."""

    symbol: str
    name: str | None = None
    type: str | None = None
    exchange: str | None = None


class SearchResponse(ListResponse):
    """Search results response."""


class ContactSubmission(BaseModel):
    """Contact form submission."""

    id: str | None = None
    email: str
    name: str | None = None
    subject: str
    message: str
    status: str | None = None
    created_at: datetime | None = None


class ContactResponse(SuccessResponse):
    """Contact form response."""

    data: ContactSubmission


class Settings(BaseModel):
    """User settings."""

    theme: str | None = None
    notifications: bool | None = None
    language: str | None = None
    timezone: str | None = None


class SettingsResponse(SuccessResponse):
    """Settings response."""

    data: Settings


class DataCoverageStatus(BaseModel):
    """Data coverage and freshness status."""

    table_name: str
    row_count: int
    age_days: float
    status: str
    last_updated: datetime | None = None


class DataCoverageResponse(ListResponse):
    """Data coverage status response."""
