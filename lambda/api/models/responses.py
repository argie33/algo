"""Pydantic models for API responses - single source of truth for response types."""
from typing import Optional, Any, Dict, List, Generic, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field

T = TypeVar('T')


class DataFreshness(BaseModel):
    """Metadata about data freshness in a response."""
    status: str = Field(..., description="Status of data freshness: OK, WARNING, STALE, CRITICAL")
    table_name: Optional[str] = Field(None, description="Table being checked")
    age_hours: Optional[float] = Field(None, description="Age of data in hours")
    age_days: Optional[float] = Field(None, description="Age of data in days")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")
    warning_threshold_days: Optional[int] = Field(None, description="Days before warning")


class BaseResponse(BaseModel):
    """Base response wrapper for all API responses."""
    statusCode: int = Field(..., description="HTTP status code")
    data_freshness: Optional[DataFreshness] = Field(None, description="Data freshness metadata")


class SuccessResponse(BaseResponse):
    """Success response for single object."""
    statusCode: int = Field(default=200, description="HTTP status code")
    data: Dict[str, Any] = Field(..., description="Response data")


class ListResponseData(BaseModel):
    """Container for list response data."""
    items: List[Dict[str, Any]] = Field(..., description="List of items")
    total: Optional[int] = Field(None, description="Total count of items")
    limit: Optional[int] = Field(None, description="Limit used in query")
    offset: Optional[int] = Field(None, description="Offset used in query")


class ListResponse(BaseResponse):
    """Success response for paginated lists."""
    statusCode: int = Field(default=200, description="HTTP status code")
    data: ListResponseData = Field(..., description="List data with pagination metadata")


class ErrorResponse(BaseResponse):
    """Error response."""
    statusCode: int = Field(..., description="HTTP error code")
    errorType: str = Field(..., description="Error type for client-side handling")
    message: str = Field(..., description="Human-readable error message")
    error: str = Field(..., alias="_error", description="Error type identifier")
    diagnostic: Optional[Dict[str, Any]] = Field(None, alias="_diagnostic", description="Diagnostic info for developers")


class HealthStatus(BaseModel):
    """Health check response."""
    status: str = Field(..., description="health, degraded, or unhealthy")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(..., description="Check timestamp")
    api_route_imports: Optional[Dict[str, Any]] = Field(None)
    freshness: Optional[Dict[str, Any]] = Field(None)
    last_load_time: Optional[datetime] = Field(None)


class HealthResponse(BaseResponse):
    """Health check response wrapper."""
    statusCode: int = Field(default=200)
    data: HealthStatus = Field(...)


class StockProfile(BaseModel):
    """Stock profile response."""
    symbol: str
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    employees: Optional[int] = None
    exchange: Optional[str] = None


class StockProfileResponse(SuccessResponse):
    """Stock profile response."""
    data: StockProfile


class KeyMetrics(BaseModel):
    """Key financial metrics for a stock."""
    symbol: str
    date: Optional[datetime] = None
    pe_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    peg_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    fcf_yield: Optional[float] = None
    debt_to_equity: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    profit_margin: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    held_percent_insiders: Optional[float] = None
    held_percent_institutions: Optional[float] = None


class KeyMetricsResponse(ListResponse):
    """Key metrics list response."""
    pass


class Signal(BaseModel):
    """Trading signal."""
    id: Optional[int] = None
    symbol: str
    signal: str = Field(..., description="BUY or SELL")
    date: datetime
    timeframe: Optional[str] = None
    signal_type: Optional[str] = None
    strength: Optional[float] = None
    entry_quality_score: Optional[float] = None
    signal_quality_score: Optional[float] = None
    volume_surge_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    rsi: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_21: Optional[float] = None
    atr: Optional[float] = None
    adx: Optional[float] = None
    mansfield_rs: Optional[float] = None
    rs_rating: Optional[float] = None
    breakout_quality: Optional[float] = None
    risk_pct: Optional[float] = None
    current_gain_pct: Optional[float] = None
    days_in_position: Optional[int] = None
    position_size_recommendation: Optional[float] = None
    stage_number: Optional[int] = None
    reason: Optional[str] = None
    substage: Optional[str] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    base_type: Optional[str] = None
    base_length_days: Optional[int] = None
    market_stage: Optional[str] = None
    buylevel: Optional[float] = None
    stoplevel: Optional[float] = None
    signal_triggered_date: Optional[datetime] = None
    entry_price: Optional[float] = None
    buy_zone_start: Optional[float] = None
    buy_zone_end: Optional[float] = None
    pivot_price: Optional[float] = None
    initial_stop: Optional[float] = None
    trailing_stop: Optional[float] = None
    sell_level: Optional[float] = None
    profit_target_8pct: Optional[float] = None
    profit_target_20pct: Optional[float] = None
    profit_target_25pct: Optional[float] = None
    exit_trigger_1_price: Optional[float] = None
    exit_trigger_2_price: Optional[float] = None
    avg_volume_50d: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_fallback: Optional[bool] = Field(None, alias="_is_fallback")


class SignalsResponse(ListResponse):
    """Trading signals list response."""
    pass


class IncomeStatement(BaseModel):
    """Annual or quarterly income statement."""
    symbol: str
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None


class IncomeStatementResponse(ListResponse):
    """Income statement list response."""
    pass


class BalanceSheet(BaseModel):
    """Annual or quarterly balance sheet."""
    symbol: str
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    stockholders_equity: Optional[float] = None


class BalanceSheetResponse(ListResponse):
    """Balance sheet list response."""
    pass


class PriceData(BaseModel):
    """Daily price data."""
    symbol: str
    date: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    adjusted_close: Optional[float] = None


class PriceDataResponse(ListResponse):
    """Price data list response."""
    pass


class Sector(BaseModel):
    """Sector information."""
    sector: str
    count: Optional[int] = None
    average_pe: Optional[float] = None
    average_score: Optional[float] = None


class SectorResponse(ListResponse):
    """Sector list response."""
    pass


class Industry(BaseModel):
    """Industry information."""
    industry: str
    sector: Optional[str] = None
    count: Optional[int] = None
    average_score: Optional[float] = None


class IndustryResponse(ListResponse):
    """Industry list response."""
    pass


class StockScore(BaseModel):
    """Stock quality score."""
    symbol: str
    score: Optional[float] = None
    percentile: Optional[float] = None
    components: Optional[Dict[str, Any]] = None


class StockScoresResponse(ListResponse):
    """Stock scores list response."""
    pass


class Trade(BaseModel):
    """Trading record."""
    id: Optional[int] = None
    symbol: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    quantity: Optional[int] = None
    status: Optional[str] = None


class TradesResponse(ListResponse):
    """Trades list response."""
    pass


class EarningsData(BaseModel):
    """Earnings report data."""
    symbol: str
    date: datetime
    eps: Optional[float] = None
    revenue: Optional[float] = None
    guidance: Optional[str] = None


class EarningsResponse(ListResponse):
    """Earnings list response."""
    pass


class EconomicIndicator(BaseModel):
    """Economic indicator data."""
    indicator: str
    date: datetime
    value: Optional[float] = None
    previous_value: Optional[float] = None
    forecast: Optional[float] = None


class EconomicResponse(ListResponse):
    """Economic indicators list response."""
    pass


class SearchResult(BaseModel):
    """Search result."""
    symbol: str
    name: Optional[str] = None
    type: Optional[str] = None
    exchange: Optional[str] = None


class SearchResponse(ListResponse):
    """Search results response."""
    pass


class ContactSubmission(BaseModel):
    """Contact form submission."""
    id: Optional[str] = None
    email: str
    name: Optional[str] = None
    subject: str
    message: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None


class ContactResponse(SuccessResponse):
    """Contact form response."""
    data: ContactSubmission


class Settings(BaseModel):
    """User settings."""
    theme: Optional[str] = None
    notifications: Optional[bool] = None
    language: Optional[str] = None
    timezone: Optional[str] = None


class SettingsResponse(SuccessResponse):
    """Settings response."""
    data: Settings


class DataCoverageStatus(BaseModel):
    """Data coverage and freshness status."""
    table_name: str
    row_count: int
    age_days: float
    status: str
    last_updated: Optional[datetime] = None


class DataCoverageResponse(ListResponse):
    """Data coverage status response."""
    pass
