#!/usr/bin/env python3
"""
Centralized Fallback Registry - Single Source of Truth for All Fallback Patterns

This module documents all fallback chains in the platform to prevent:
1. Undocumented fallback behavior that surprises users
2. Silent failures that mask real problems
3. Inconsistent fallback logic across similar operations

PRINCIPLE: All fallback chains must be:
- Explicitly documented here
- Logged with context when fallback occurs
- Testable (fallback behavior must be verifiable)
- Measured (track fallback usage in metrics)

FALLBACK STRUCTURE:
Each fallback chain specifies:
- Purpose: what data/service is being fetched
- Primary source: preferred data source
- Fallbacks: ordered list of alternatives
- When to use: conditions triggering each fallback
- Logging: what gets logged at each stage
- Metrics: what gets tracked
- Recovery: when does system return to primary source

DOCUMENTED FALLBACK CHAINS:

1. DATABASE CREDENTIALS (config/credential_manager.py)
   Primary: AWS Secrets Manager (via DB_SECRET_ARN)
   Fallbacks:
     1. Environment variables (DB_HOST, DB_PASSWORD, etc.)
     2. Secrets Manager individual secret names
     3. Default values (only for non-critical fields like DB_PORT)
   Logging: Every step logged with [CREDENTIAL] prefix
   Note: DB_HOST never has fallback for safety

2. VIX DATA (algo/algo_circuit_breaker.py)
   Primary: Live VIX from market data API
   Fallbacks:
     1. Historical VIX from database
     2. Computed VIX from SPY returns (fallback estimation)
     3. Neutral 20.0 (last resort - halts trading for safety)
   Logging: Every level logged clearly
   Recovery: Returns to live API on next cycle

3. PERFORMANCE METRICS (tools/dashboard/dashboard.py)
   Primary: API endpoint (/api/algo/performance)
   Fallbacks:
     1. Database cache of last successful API response
     2. Hardcoded defaults (if both fail)
   Logging: Logs with "stale_alerts" indicating fallback
   Recovery: Retries API on next load

4. ALPACA CREDENTIALS (config/credential_manager.py)
   Primary: AWS Secrets Manager (user-specific or shared)
   Fallbacks:
     1. Cached credentials (if Secrets Manager unavailable)
     2. Environment variables
     3. Legacy individual secret names
   Logging: Clear "graceful fallback" message
   Caching: 10-minute TTL for fallback resilience

5. DATABASE CONNECTION (utils/db_connection.py)
   Primary: Direct connection to RDS endpoint
   Fallbacks:
     1. Retry with exponential backoff (up to 5 retries)
     2. RDS Proxy endpoint (if direct fails)
   No fallback: Localhost (rejected for safety)
   Logging: Retry count and wait time logged
   Recovery: Connection pool monitoring tracks failed connections

6. PRICE DATA LOADING (loaders/)
   Primary: Fresh API fetch (latest data)
   Fallbacks:
     1. Watermark-based incremental load (data up to N days ago)
     2. Full historical load (if watermark missing)
   Logging: Watermark status and fetch scope logged
   Recovery: Advances watermark on successful load

7. MARKET DATA (algo/algo_circuit_breaker.py, signals/)
   Primary: Real-time market data API
   Fallbacks:
     1. Previous day's data if today unavailable
     2. Computed values from technical indicators
   Logging: "using fallback data" message
   Recovery: Next cycle fetches fresh data
"""

import logging
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FallbackTrigger(Enum):
    """Why did we use a fallback?"""
    PRIMARY_UNAVAILABLE = "primary source failed"
    PRIMARY_SLOW = "primary source too slow"
    PRIMARY_PARTIAL = "primary source incomplete"
    CREDENTIALS_INVALID = "primary credentials invalid"
    NETWORK_ERROR = "network error"
    TIMEOUT = "timeout"
    STALENESS = "data too old"
    MANUAL_OVERRIDE = "explicitly requested"


@dataclass
class FallbackStep:
    """Single step in a fallback chain."""
    name: str  # e.g., "environment_variables", "database_cache"
    priority: int  # 0=primary, 1=first fallback, 2=second fallback, etc.
    description: str
    conditions: str  # When this is used (e.g., "if API fails")
    logs_with: str  # Log prefix or message pattern
    hardcoded_values: Optional[Dict[str, Any]] = None  # If fallback returns hardcoded values, document them here


@dataclass
class FallbackChain:
    """Complete fallback chain for a resource."""
    resource: str  # What we're fetching (e.g., "vix_data", "alpaca_credentials")
    primary_source: str
    fallbacks: List[FallbackStep]
    metrics_tracked: List[str]  # What metrics are collected
    recovery_condition: str  # When do we return to primary source
    safety_notes: str  # Any safety considerations


# Global registry of all fallback chains
FALLBACK_CHAINS: Dict[str, FallbackChain] = {
    "vix_data": FallbackChain(
        resource="VIX Index",
        primary_source="Live market data API",
        fallbacks=[
            FallbackStep(
                name="historical_database",
                priority=1,
                description="VIX from database (same-day or previous close)",
                conditions="Primary API unavailable or returns no data",
                logs_with="[VIX] using historical data from database"
            ),
            FallbackStep(
                name="computed_from_spy",
                priority=2,
                description="Estimated VIX from SPY volatility",
                conditions="Database also missing or incomplete",
                logs_with="[VIX] computed estimate from SPY returns"
            ),
        ],
        metrics_tracked=["vix_fallback_uses", "vix_source_by_day", "vix_estimation_error"],
        recovery_condition="Next trading day or manual data refresh",
        safety_notes="When all sources fail (API, database, SPY data), VIX check halts trading. Never return neutral default (20.0) — trading cannot proceed without volatility assessment.",
    ),

    "alpaca_credentials": FallbackChain(
        resource="Alpaca API Credentials",
        primary_source="AWS Secrets Manager",
        fallbacks=[
            FallbackStep(
                name="credential_cache",
                priority=1,
                description="Cached credentials from previous fetch",
                conditions="Secrets Manager unavailable (network/permission error)",
                logs_with="[CREDENTIAL] using cached Alpaca credentials (age warning included)"
            ),
            FallbackStep(
                name="environment_variables",
                priority=2,
                description="APCA_API_KEY_ID and APCA_API_SECRET_KEY env vars",
                conditions="Cache empty or expired",
                logs_with="[CREDENTIAL] loaded from environment variables"
            ),
        ],
        metrics_tracked=["alpaca_credential_cache_hits", "alpaca_credential_misses", "alpaca_secrets_manager_errors"],
        recovery_condition="Next credential refresh cycle (TTL-based)",
        safety_notes="Cache TTL is 10 minutes - enables resilience but can return stale credentials. Monitoring should alert if cache age exceeds TTL.",
    ),

    "database_credentials": FallbackChain(
        resource="Database Credentials",
        primary_source="AWS Secrets Manager (DB_SECRET_ARN)",
        fallbacks=[
            FallbackStep(
                name="environment_variables",
                priority=1,
                description="Individual env vars: DB_HOST, DB_PASSWORD, DB_PORT, etc.",
                conditions="Secrets Manager unavailable",
                logs_with="[DB_CREDENTIAL] loaded from environment variables"
            ),
            FallbackStep(
                name="legacy_secret_names",
                priority=2,
                description="Individual secrets: db/username, db/password",
                conditions="Environment variables incomplete",
                logs_with="[DB_CREDENTIAL] loaded from individual secret names"
            ),
        ],
        metrics_tracked=["db_credential_source_used", "db_credential_fetch_latency"],
        recovery_condition="Each new DatabaseContext connection",
        safety_notes="DB_HOST never falls back to localhost for safety. System fails-fast if DB_HOST missing.",
    ),

    "performance_metrics": FallbackChain(
        resource="Performance Metrics (Dashboard)",
        primary_source="Database direct fetch (trades + portfolio snapshots)",
        fallbacks=[
            FallbackStep(
                name="incomplete_data",
                priority=1,
                description="Return None for metrics without sufficient data (no trades, no snapshots, missing values)",
                conditions="Closed trades empty or portfolio snapshots insufficient (e.g., < 2 snapshots for Sharpe)",
                logs_with="[METRICS] insufficient data — returning None for metrics without samples"
            ),
        ],
        metrics_tracked=["performance_fetch_failures", "metrics_with_null_values"],
        recovery_condition="When trades close or new portfolio snapshots available",
        safety_notes="Never return hardcoded all-zero metrics. Instead return None for individual metrics without sufficient data. Dashboard displays '--' for unavailable metrics. Users know data is missing vs. showing fake zeros.",
    ),

    "price_data": FallbackChain(
        resource="Price Data",
        primary_source="Fresh API fetch (latest available)",
        fallbacks=[
            FallbackStep(
                name="watermark_incremental",
                priority=1,
                description="Load incrementally from last successful watermark",
                conditions="Full load fails or is partial",
                logs_with="[PRICE] using watermark-based incremental load"
            ),
            FallbackStep(
                name="full_historical",
                priority=2,
                description="Full historical load from API",
                conditions="Watermark missing or corrupted",
                logs_with="[PRICE] watermark missing, loading full history"
            ),
        ],
        metrics_tracked=["price_watermark_advances", "price_full_loads_vs_incremental", "price_load_latency"],
        recovery_condition="Watermark advances on successful load",
        safety_notes="Watermark atomicity is critical - never update watermark without successful data load.",
    ),
}


def get_fallback_chain(resource: str) -> Optional[FallbackChain]:
    """Get documented fallback chain for a resource.

    Args:
        resource: Resource name (e.g., 'vix_data', 'alpaca_credentials')

    Returns:
        FallbackChain if documented, None otherwise
    """
    return FALLBACK_CHAINS.get(resource)


def log_fallback_usage(
    resource: str,
    fallback_step: str,
    trigger: FallbackTrigger,
    context: str = "",
    error: Optional[Exception] = None,
) -> None:
    """Log that a fallback was used.

    Args:
        resource: What resource (e.g., 'vix_data')
        fallback_step: Which fallback (e.g., 'database_cache')
        trigger: Why (e.g., FallbackTrigger.PRIMARY_UNAVAILABLE)
        context: Additional context (e.g., symbol, timestamp)
        error: Optional exception that triggered fallback
    """
    msg = f"[FALLBACK] {resource} → {fallback_step} (reason: {trigger.value})"
    if context:
        msg += f" [{context}]"
    if error:
        msg += f" error: {str(error)[:100]}"

    # Log level depends on fallback priority
    chain = get_fallback_chain(resource)
    if chain:
        # Find priority of this fallback
        for step in chain.fallbacks:
            if step.name == fallback_step:
                if step.priority == 1:
                    logger.warning(msg)
                elif step.priority == 2:
                    logger.error(msg)
                else:
                    logger.critical(msg)
                break
    else:
        logger.warning(msg + " (chain not documented)")


def validate_fallback_chain_documented(resource: str) -> bool:
    """Check if a fallback resource is documented.

    Args:
        resource: Resource name to check

    Returns:
        True if documented, False otherwise
    """
    is_documented = resource in FALLBACK_CHAINS
    if not is_documented:
        logger.warning(f"[FALLBACK_UNDOCUMENTED] {resource} has fallback behavior but no FallbackChain entry")
    return is_documented


def get_hardcoded_fallback_values(resource: str, fallback_step: str) -> Optional[Dict[str, Any]]:
    """Get hardcoded fallback values for a resource/fallback step combination.

    This is useful for auditing and detecting when the system is returning fake/placeholder data
    to users (e.g., all-zero performance metrics when the API is unavailable).

    Args:
        resource: Resource name (e.g., 'performance_metrics')
        fallback_step: Which fallback step (e.g., 'hardcoded_defaults')

    Returns:
        Dict of hardcoded values if this fallback uses them, None otherwise
    """
    chain = get_fallback_chain(resource)
    if not chain:
        return None
    for step in chain.fallbacks:
        if step.name == fallback_step:
            return step.hardcoded_values
    return None


def is_hardcoded_fallback_data(resource: str, data: Dict) -> bool:
    """Check if returned data matches a hardcoded fallback pattern (all zeros, etc).

    This helps identify when we're showing users fake placeholder data instead of real metrics.

    Args:
        resource: What resource this data is for
        data: The returned data

    Returns:
        True if data matches a hardcoded fallback pattern
    """
    chain = get_fallback_chain(resource)
    if not chain:
        return False

    # Check each fallback step to see if data matches its hardcoded values
    for step in chain.fallbacks:
        if not step.hardcoded_values:
            continue
        # If all keys in the data match the hardcoded values, this is likely fallback data
        matches = all(
            data.get(k) == v
            for k, v in step.hardcoded_values.items()
            if k in data
        )
        if matches:
            return True
    return False


if __name__ == "__main__":
    print("Fallback Registry - Documented Fallback Chains")
    print("\nRegistered fallback chains:")
    for resource_name, chain in FALLBACK_CHAINS.items():
        print(f"\n{resource_name}:")
        print(f"  Primary: {chain.primary_source}")
        print(f"  Fallbacks:")
        for step in chain.fallbacks:
            print(f"    {step.priority}. {step.name}: {step.description}")
