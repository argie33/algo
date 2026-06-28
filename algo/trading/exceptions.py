"""Trading system exceptions for precise error handling and recovery.

Enables distinguishing between:
- Data errors (invalid prices, missing data) → fail-closed
- Transient errors (API timeouts, rate limits) → retry
- Configuration errors (missing thresholds) → raise immediately
- Database errors (connection, query) → retry or fail-closed
- Non-blocking errors (notifications) → log and continue
"""


class TradingError(Exception):
    """Base exception for all trading system errors."""


class InvalidTradeError(TradingError):
    """Trade input validation failed (price, stop, shares invalid).

    Fail-closed: reject the trade, do not retry.
    """


class DuplicatePositionError(TradingError):
    """Trade would create duplicate position (idempotency violation).

    Fail-closed: idempotent safety check, reject trade.
    """


class PretradeCheckFailedError(TradingError):
    """Pre-trade hard stop triggered (risk, exposure, etc).

    Fail-closed: independent risk layer rejection, do not retry.
    """


class DataUnavailableError(TradingError):
    """Required data missing (portfolio value, market exposure, etc).

    Fail-closed: cannot trade without data, halt execution.
    """


class ConfigurationError(TradingError):
    """Required configuration value missing or invalid.

    Fatal: indicates system misconfiguration, no retry.
    """


class OrderExecutionError(TradingError):
    """Alpaca order submission or status check failed.

    May be retryable (transient API error) or fatal (order rejected).
    """


class OrderRejectedError(OrderExecutionError):
    """Alpaca rejected the order (bad price, insufficient buying power, etc).

    Fail-closed: order rejected by broker, do not retry.
    """


class ExchangeAPIError(TradingError):
    """Exchange API error (Alpaca timeout, connection refused, etc).

    Potentially retryable: transient network/API issues.
    """


class DatabaseError(TradingError):
    """Database operation failed (connection, query, transaction).

    Potentially retryable: transient database issues.
    """


class AuditLogError(TradingError):
    """Failed to write audit log (database critical).

    Critical: audit failures indicate data integrity risk, raise immediately.
    """


class NotificationError(TradingError):
    """Failed to send notification (email, Slack, SMS).

    Non-blocking: notification failures should not halt trading.
    """


class PortfolioValueError(DataUnavailableError):
    """Cannot determine current portfolio value.

    Fail-closed: position sizing requires accurate portfolio value.
    """


class PositionSizeError(TradingError):
    """Position sizing failed (invalid calculation, missing data).

    Fail-closed: position sizing must be correct or skip the trade.
    """
