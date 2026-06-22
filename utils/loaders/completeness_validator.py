#!/usr/bin/env python3
"""
Loader Data Completeness Validator

Ensures loaders have loaded all critical data before marking execution complete.
Provides diagnostic information for failures to aid debugging and SLA compliance.

Usage:
    from utils.loaders.completeness_validator import LoaderCompletenessValidator

    validator = LoaderCompletenessValidator(table_name="price_daily", symbol_count=5000)
    result = validator.validate(actual_symbols_loaded=4950)  # 99% completion

    if not result.is_complete:
        logger.error(f"Data incomplete: {result.failure_reason}")
"""

import logging
from dataclasses import dataclass

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Minimum symbol coverage required for loader to be considered "complete"
# DEFAULT: 95% coverage. Can be overridden per-loader via LOADER_COMPLETENESS_MIN_PCT env var
MIN_COMPLETION_PCT = 95.0


@dataclass
class CompletenessResult:
    """Result of a completeness validation check."""

    is_complete: bool
    completion_pct: float
    symbols_loaded: int
    symbols_expected: int
    failure_reason: str | None = None
    recommendations: list[str] | None = None

    def __post_init__(self):
        if self.recommendations is None:
            self.recommendations = []


class LoaderCompletenessValidator:
    """Validates that a loader has loaded sufficient data to proceed."""

    def __init__(
        self,
        table_name: str,
        symbol_count: int,
        min_completion_pct: float = MIN_COMPLETION_PCT,
    ):
        """Initialize validator.

        Args:
            table_name: Name of the loader table being validated
            symbol_count: Expected number of symbols to load
            min_completion_pct: Minimum % completion required (default 95%)
        """
        self.table_name = table_name
        self.symbol_count = max(1, symbol_count)  # Prevent division by zero
        self.min_completion_pct = min_completion_pct

    def validate(
        self,
        actual_symbols_loaded: int,
        execution_duration_sec: float | None = None,
    ) -> CompletenessResult:
        """Validate that loader has loaded sufficient data.

        Args:
            actual_symbols_loaded: Number of symbols successfully loaded
            execution_duration_sec: Time taken to load data (for SLA reporting)

        Returns:
            CompletenessResult with completion % and failure reason if incomplete
        """
        completion_pct = (actual_symbols_loaded / self.symbol_count * 100) if self.symbol_count > 0 else 100.0

        is_complete = completion_pct >= self.min_completion_pct

        failure_reason = None
        recommendations = []

        if not is_complete:
            symbols_missing = self.symbol_count - actual_symbols_loaded
            failure_reason = (
                f"Data incomplete: loaded {actual_symbols_loaded}/{self.symbol_count} symbols "
                f"({completion_pct:.1f}%), need {self.min_completion_pct}%. "
                f"Missing {symbols_missing} symbols."
            )

            # Suggest remediation based on missing count
            if symbols_missing <= 50:
                recommendations.append(
                    "Small gap (<1%): Check for transient API errors or network timeouts. May succeed on retry."
                )
            elif symbols_missing <= 250:  # < 5%
                recommendations.append(
                    "Moderate gap (1-5%): Check for rate limiting or data source issues. "
                    "Retry with reduced parallelism."
                )
            else:  # >= 5%
                recommendations.append(
                    "Large gap (>5%): Major data source failure. Check API status, database connectivity. "
                    "Manual investigation required."
                )

            # Add SLA context if duration provided
            if execution_duration_sec:
                recommendations.append(
                    f"Execution took {execution_duration_sec / 60:.1f} min. "
                    "Approaching timeout may indicate performance degradation."
                )

        result = CompletenessResult(
            is_complete=is_complete,
            completion_pct=completion_pct,
            symbols_loaded=actual_symbols_loaded,
            symbols_expected=self.symbol_count,
            failure_reason=failure_reason,
            recommendations=recommendations,
        )

        # Log the result
        if is_complete:
            logger.info(
                f"[{self.table_name}] ✓ Data completeness validation PASSED: "
                f"{actual_symbols_loaded}/{self.symbol_count} symbols ({completion_pct:.1f}%)"
            )
        else:
            logger.error(f"[{self.table_name}] ✗ Data completeness validation FAILED: {failure_reason}")
            for rec in recommendations:
                logger.warning(f"  → {rec}")

        return result

    def validate_upstream_completeness(self, upstream_table: str) -> CompletenessResult:
        """Validate that upstream loader has sufficient data.

        Used by downstream loaders to check if they can proceed.

        Args:
            upstream_table: Name of the upstream loader table to check

        Returns:
            CompletenessResult from upstream loader's most recent run
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT symbols_loaded, symbol_count, completion_pct, status
                    FROM data_loader_status
                    WHERE table_name = %s
                    ORDER BY last_updated DESC
                    LIMIT 1
                    """,
                    (upstream_table,),
                )

                result = cur.fetchone()
                if not result:
                    # No status record found
                    logger.error(
                        f"[{self.table_name}→{upstream_table}] Upstream loader has no status record. "
                        "Cannot verify completeness."
                    )
                    return CompletenessResult(
                        is_complete=False,
                        completion_pct=0,
                        symbols_loaded=0,
                        symbols_expected=0,
                        failure_reason=f"No status record for upstream loader {upstream_table}",
                        recommendations=[
                            "Ensure upstream loader ran and recorded status",
                            "Check if upstream loader crashed before updating status",
                        ],
                    )

                symbols_loaded, symbol_count, completion_pct, status = result

                # NULL completion_pct means global loader (not symbol-based)
                if completion_pct is None:
                    completion_pct = 100.0

                is_complete = completion_pct >= self.min_completion_pct and status in (
                    "COMPLETED",
                    "INCOMPLETE",
                )

                if not is_complete:
                    logger.error(
                        f"[{self.table_name}→{upstream_table}] Upstream incomplete: "
                        f"{symbols_loaded}/{symbol_count} symbols ({completion_pct:.1f}%), status={status}"
                    )

                return CompletenessResult(
                    is_complete=is_complete,
                    completion_pct=completion_pct or 0,
                    symbols_loaded=symbols_loaded or 0,
                    symbols_expected=symbol_count or 0,
                    failure_reason=(
                        f"Upstream {upstream_table} only {completion_pct:.1f}% complete " if not is_complete else None
                    ),
                )

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[{self.table_name}→{upstream_table}] Failed to check upstream completeness: {e}")
            return CompletenessResult(
                is_complete=False,
                completion_pct=0,
                symbols_loaded=0,
                symbols_expected=0,
                failure_reason=str(e),
            )
