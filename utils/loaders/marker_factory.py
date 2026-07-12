"""Factory for data unavailability markers - eliminates 50+ duplicated try/except patterns."""

from typing import Any


class DataUnavailableMarker:
    """Factory for creating consistent data_unavailable markers across all loaders.

    Replaces 50+ duplicate patterns of:
        {"data_unavailable": True, "reason": "..."}

    Ensures all loaders use the same marker structure and reasoning.
    """

    # Standard reason codes
    REASON_TRANSIENT_ERROR = "transient_error_max_retries"
    REASON_API_ERROR = "api_error_non_recoverable"
    REASON_NO_DATA = "no_data_available_for_symbol"
    REASON_SCHEMA_MISMATCH = "schema_mismatch_detected"
    REASON_NO_FILINGS = "no_sec_filings_or_special_entity"
    REASON_INSUFFICIENT_HISTORY = "insufficient_historical_data"
    REASON_SYMBOL_NOT_FOUND = "symbol_not_found_in_data_source"
    REASON_DATA_STALE = "upstream_data_stale_or_missing"

    @staticmethod
    def transient_error(
        symbol: str,
        operation: str = "fetch",
        details: str = "",
    ) -> dict[str, Any]:
        """Create marker for transient errors (network, timeout, rate limit).

        Args:
            symbol: Stock symbol
            operation: What operation failed (default "fetch")
            details: Additional error details

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_TRANSIENT_ERROR,
            "operation": operation,
            "details": details,
        }

    @staticmethod
    def api_error(
        symbol: str,
        api_name: str,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Create marker for non-recoverable API errors (auth, schema, etc).

        Args:
            symbol: Stock symbol
            api_name: Name of API that failed (e.g., "SEC EDGAR", "yfinance")
            error_message: Error message from API

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_API_ERROR,
            "api": api_name,
            "error": error_message[:200],  # Truncate long messages
        }

    @staticmethod
    def no_data(
        symbol: str,
        reason: str = "no_data_available",
        source: str = "",
    ) -> dict[str, Any]:
        """Create marker when symbol has no data in source (not an error, just missing).

        Args:
            symbol: Stock symbol
            reason: Why no data (e.g., "micro-cap", "OTC", "new IPO")
            source: Data source name

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_NO_DATA,
            "explanation": reason,
            "source": source,
        }

    @staticmethod
    def schema_mismatch(
        symbol: str,
        expected_columns: int,
        actual_columns: int,
        table: str = "",
    ) -> dict[str, Any]:
        """Create marker for schema mismatches (database evolution issues).

        Args:
            symbol: Stock symbol
            expected_columns: Expected number of columns
            actual_columns: Actual number of columns
            table: Table name where mismatch occurred

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_SCHEMA_MISMATCH,
            "table": table,
            "expected_columns": expected_columns,
            "actual_columns": actual_columns,
        }

    @staticmethod
    def no_sec_filings(
        symbol: str,
        entity_type: str = "REIT/investment_trust/non-US",
    ) -> dict[str, Any]:
        """Create marker for SEC data unavailability (REITs, foreign companies, etc).

        Args:
            symbol: Stock symbol
            entity_type: Type of entity without SEC filings

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_NO_FILINGS,
            "entity_type": entity_type,
        }

    @staticmethod
    def insufficient_history(
        symbol: str,
        min_required_years: int = 1,
        available_years: int = 0,
    ) -> dict[str, Any]:
        """Create marker for insufficient historical data (young companies, new IPOs).

        Args:
            symbol: Stock symbol
            min_required_years: Minimum years needed for calculation
            available_years: Actual years available

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_INSUFFICIENT_HISTORY,
            "min_required_years": min_required_years,
            "available_years": available_years,
        }

    @staticmethod
    def upstream_dependency_missing(
        symbol: str,
        upstream_table: str,
        dependency_type: str = "data",
    ) -> dict[str, Any]:
        """Create marker when upstream data dependency is missing (freshness, completeness).

        Args:
            symbol: Stock symbol
            upstream_table: Name of upstream table/loader
            dependency_type: Type of dependency (data, freshness, etc)

        Returns:
            Dict with data_unavailable=True marker
        """
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": DataUnavailableMarker.REASON_DATA_STALE,
            "upstream_table": upstream_table,
            "dependency_type": dependency_type,
        }

    @staticmethod
    def batch_unavailable(
        symbols: list[str],
        reason: str = "batch_operation_failed",
        details: str = "",
    ) -> list[dict[str, Any]]:
        """Create markers for entire batch when operation fails.

        Args:
            symbols: List of stock symbols
            reason: Reason for batch failure
            details: Additional details

        Returns:
            List of data_unavailable markers (one per symbol)
        """
        return [
            {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": reason,
                "batch_operation": True,
                "details": details,
            }
            for symbol in symbols
        ]
