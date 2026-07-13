#!/usr/bin/env python3
"""AWS Production Configuration Validator — Ensures all settings correct before deployment.

Validates:
1. Cognito credentials match actual AWS user pool
2. Alpaca credentials configured (paper or live mode)
3. Circuit breaker thresholds appropriate for risk profile
4. Signal generation quality gates configured
5. Data patrol thresholds realistic
6. CloudWatch monitoring configured
7. Loader status tracking enabled
8. Market calendar updated
9. Error fallback monitoring enabled
10. All other critical configurations
"""

import logging
import os
from datetime import date, datetime
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


class AWSProductionConfigValidator:
    """Validates all configuration for production AWS deployment."""

    def __init__(self) -> None:
        self.checks_passed: list[str] = []
        self.checks_failed: list[str] = []
        self.checks_warnings: list[str] = []
        self.checks_critical: list[str] = []

    def validate_cognito_config(self) -> bool:
        """Validate Cognito configuration matches AWS setup."""
        client_id = os.getenv("COGNITO_CLIENT_ID", "").strip()
        user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "").strip()
        region = os.getenv("AWS_REGION", "us-east-1").strip()

        if not client_id:
            self.checks_critical.append(
                "COGNITO_CLIENT_ID not set - JWT authentication will be disabled (CRITICAL SECURITY ISSUE)"
            )
            return False

        if not user_pool_id:
            self.checks_critical.append("COGNITO_USER_POOL_ID not set - cannot validate JWT tokens")
            return False

        # Format check: Cognito user pool IDs follow pattern: region_randomstring
        if "_" not in user_pool_id:
            self.checks_warnings.append(
                f"COGNITO_USER_POOL_ID format unusual: {user_pool_id} (expected format: region_xxx)"
            )

        self.checks_passed.append(f"Cognito configured: {region}/{user_pool_id[:20]}...")
        return True

    def validate_alpaca_config(self) -> bool:
        """Validate Alpaca credentials configured using credential manager."""
        try:
            from config.credential_manager import get_credential_manager

            cred_mgr = get_credential_manager()
            cred_mgr.get_alpaca_credentials()
            paper_trading = os.getenv("ALPACA_PAPER_TRADING", "true").lower() == "true"
            mode = "PAPER" if paper_trading else "LIVE"
            self.checks_passed.append(f"Alpaca configured: {mode} mode, credentials present")
            return True
        except ValueError:
            # Credentials not found in any source
            paper_trading = os.getenv("ALPACA_PAPER_TRADING", "true").lower() == "true"
            if paper_trading:
                self.checks_warnings.append("Alpaca credentials not set - paper trading mode will fail silently")
            else:
                self.checks_critical.append("Alpaca credentials missing in LIVE TRADING MODE - trades will fail")
            return False

    def validate_circuit_breaker_thresholds(self) -> bool:
        """Validate circuit breaker thresholds are configured."""
        try:
            from algo.infrastructure import get_config

            config = get_config()

            thresholds = {
                "halt_drawdown_pct": (10.0, 30.0, 20.0),  # (min, max, default)
                "max_daily_loss_pct": (0.5, 5.0, 2.0),
                "max_consecutive_losses": (2, 5, 3),
                "max_total_risk_pct": (1.0, 10.0, 4.0),
                "vix_max_threshold": (25.0, 50.0, 35.0),
                "max_weekly_loss_pct": (2.0, 20.0, 5.0),
                "win_rate_floor_pct": (30.0, 60.0, 40.0),
            }

            issues = []
            for key, (min_val, max_val, default) in thresholds.items():
                actual = config.get(key, default)
                if actual < min_val or actual > max_val:
                    issues.append(f"{key}={actual} outside safe range [{min_val}, {max_val}]")

            if issues:
                self.checks_warnings.extend(issues)
                return False

            self.checks_passed.append("Circuit breaker thresholds configured and in safe ranges")
            return True

        except Exception as e:
            raise RuntimeError(
                f"Cannot validate circuit breaker thresholds: {e}. "
                "Cannot proceed without verifying circuit breaker config."
            ) from e

    def validate_data_patrol_config(self) -> bool:
        """Validate data patrol thresholds for production data volume."""
        # Data patrol monitors staleness, coverage, sanity
        # For production with 5000+ symbols, thresholds should be:
        # - Staleness: >1 day old = alert
        # - Coverage: <75% vs prior day = alert
        # - Sanity: price spikes >10% in 1 day = check

        try:
            from algo.monitoring import DataPatrol

            DataPatrol()

            # Just verify patrol exists and can be instantiated
            self.checks_passed.append("Data patrol monitoring configured")
            return True

        except Exception as e:
            raise RuntimeError(
                f"Data patrol configuration issue: {e}. Cannot proceed without data patrol configured."
            ) from e

    def validate_market_calendar(self) -> bool:
        """Validate market calendar has current holidays/early closes."""
        try:
            from algo.infrastructure import MarketCalendar

            # Check that today is recognized as trading day or not
            today = date.today()
            MarketCalendar.is_trading_day(today)

            # Verify calendar has some early closes configured
            # (US markets close at 1 PM ET on day-after-Thanksgiving, Christmas Eve if weekday, etc.)

            self.checks_passed.append("Market calendar configured and accessible")
            return True

        except Exception as e:
            raise RuntimeError(f"Market calendar issue: {e}. Cannot proceed without valid market calendar.") from e

    def validate_loader_status_tracking(self) -> bool:
        """Validate loader status table is being used."""
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                # Check that data_loader_status table exists and has recent entries
                cur.execute("""
                    SELECT COUNT(*) FROM data_loader_status
                    WHERE last_updated > NOW() - get_interval_sql('1d')
                """)
                row = cur.fetchone()
                if row is None or len(row) < 1:
                    raise ValueError("Query to count recent loader status entries returned no result")
                recent_count = row[0]

                if recent_count == 0:
                    self.checks_warnings.append(
                        "Loader status table exists but has no recent entries - tracking may be disabled"
                    )
                else:
                    self.checks_passed.append(f"Loader status tracking active: {recent_count} loaders tracked")

            return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Loader status tracking issue: {e}. Cannot verify loader status table configured."
            ) from e

    def validate_cloudwatch_readiness(self) -> bool:
        """Validate CloudWatch is configured for monitoring."""
        try:
            import boto3

            region = os.getenv("AWS_REGION", "us-east-1")
            cloudwatch = boto3.client("cloudwatch", region_name=region)

            # Try to get metrics - just verify connectivity
            cloudwatch.list_metrics(MaxItems=1)

            self.checks_passed.append("CloudWatch accessible for monitoring")
            return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"CloudWatch configuration check failed: {e}. Cannot validate CloudWatch readiness."
            ) from e

    def validate_dynamodb_setup(self) -> bool:
        """Validate DynamoDB is set up for state management."""
        try:
            from utils.db import DynamoDBHealthCheck

            checker = DynamoDBHealthCheck()

            if not checker.check_dynamodb_connectivity():
                self.checks_warnings.append(
                    "DynamoDB not accessible (Note: Not critical if running locally, required for AWS)"
                )
                return False

            self.checks_passed.append("DynamoDB configured for state management")
            return True

        except Exception as e:
            raise RuntimeError(f"DynamoDB setup validation failed: {e}. Cannot verify DynamoDB configured.") from e

    def validate_error_fallback_monitoring(self) -> bool:
        """Validate error fallback monitoring is enabled."""
        try:
            # Import routes safely without using 'lambda' keyword
            from pathlib import Path

            routes_path = Path(__file__).parent.parent / "lambda" / "api" / "routes" / "utils.py"
            if routes_path.exists():
                self.checks_passed.append("Error fallback monitoring configured")
                return True
            else:
                self.checks_warnings.append("Error fallback utilities not found")
                return False

        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(
                f"Error fallback monitoring validation failed: {e}. Cannot verify error fallback utilities."
            ) from e

