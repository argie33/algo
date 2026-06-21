#!/usr/bin/env python3
"""
Data Freshness Validation - Prevent silent stale data usage.

Enforces freshness thresholds for critical market data to prevent
silent outages from flowing downstream to position sizing and risk calculations.

Usage:
    validator = FreshnessValidator(max_age_hours={
        'vix': 0.25,      # VIX must be < 15 min old
        'spy_price': 0.25, # SPY must be < 15 min old (market close)
        'portfolio_value': 24,  # Portfolio can be up to 1 day old
    })

    # Check if data is current before using it
    try:
        validator.check('vix', last_update_time=vix_update_datetime)
    except StaleDataError as e:
        logger.critical(f"VIX data too stale: {e}. Cannot size positions.")
        raise
"""

import logging
from datetime import datetime, timedelta, timezone


logger = logging.getLogger(__name__)


class StaleDataError(Exception):
    """Raised when data exceeds freshness threshold."""

    def __init__(
        self,
        data_name: str,
        age: timedelta,
        max_age: timedelta,
        last_update: datetime | None = None,
    ):
        self.data_name = data_name
        self.age = age
        self.max_age = max_age
        self.last_update = last_update

        hours = age.total_seconds() / 3600
        max_hours = max_age.total_seconds() / 3600
        message = f"Data '{data_name}' is too stale: {hours:.1f} hours old (max allowed: {max_hours:.1f} hours)"
        if last_update:
            message += f". Last update: {last_update.isoformat()}"

        super().__init__(message)


class FreshnessValidator:
    """
    Validate that critical market data is fresh enough to use.

    Prevents position sizing from using:
    - 9-day-old VIX (happens when yfinance is down)
    - 2-day-old portfolio snapshots (happens when reconciliation fails)
    - Non-trading-day prices (happens when API lag is extreme)

    Rationale: It's better to fail a phase than to silently use stale data
    for position sizing, where staleness directly impacts risk exposure.
    """

    # Default freshness thresholds for critical market data
    DEFAULT_THRESHOLDS: dict[str, float] = {
        # Market-critical data (position sizing): < 1 hour old
        "vix": 1.0,  # 1 hour (markets update intraday)
        "spy_close": 1.0,  # 1 hour (last trading day's close)
        "portfolio_value": 24.0,  # 1 day (portfolio snapshots)
        # Signal-critical data (generation): < 1 hour old
        "technical_indicators": 1.0,
        "market_breadth": 1.0,
        # Enrichment data (optional): < 2 hours old
        "put_call_ratio": 2.0,
        "yield_curve": 2.0,
        "sector_rotation": 4.0,
    }

    def __init__(self, max_age_hours: dict[str, float] | None = None):
        """
        Initialize validator with freshness thresholds.

        Args:
            max_age_hours: Dict mapping data names to max age in hours.
                          Defaults to DEFAULT_THRESHOLDS if not provided.
        """
        self.max_age_hours = max_age_hours or self.DEFAULT_THRESHOLDS

    def check(
        self,
        data_name: str,
        last_update: datetime | None,
        reference_time: datetime | None = None,
        allow_missing: bool = False,
    ) -> bool:
        """
        Check if data is fresh enough to use.

        Args:
            data_name: Name of data being validated (e.g., 'vix', 'spy_close')
            last_update: When the data was last updated
            reference_time: Time to compare against (defaults to now UTC)
            allow_missing: If True, missing data (None) returns False instead of raising

        Returns:
            True if data is current, False if missing (when allow_missing=True)

        Raises:
            StaleDataError: If data is older than threshold
            ValueError: If data_name is unknown
        """
        if last_update is None:
            if allow_missing:
                logger.debug(f"Data '{data_name}' is missing (None)")
                return False
            raise ValueError(f"Data '{data_name}' is missing (last_update=None)")

        if data_name not in self.max_age_hours:
            raise ValueError(f"Unknown data type '{data_name}'. Known types: {list(self.max_age_hours.keys())}")

        # Ensure datetime objects are timezone-aware
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)

        reference_time = reference_time or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)

        # Calculate age
        age = reference_time - last_update
        max_age = timedelta(hours=self.max_age_hours[data_name])

        # TRADING DAY AWARENESS: For price_data on non-trading days, allow older data
        # If it's a weekend/holiday and data is from last trading day, that's fresh enough
        if "price" in data_name.lower():
            try:
                from algo.infrastructure import MarketCalendar

                ref_date = reference_time.date()
                update_date = last_update.date()

                # If reference_time is NOT a trading day (e.g., Saturday)
                # but data is from the most recent trading day, allow it
                if not MarketCalendar.is_trading_day(ref_date):
                    # Find the last trading day before reference_time
                    check_date = ref_date
                    for _ in range(10):  # Check up to 10 days back for last trading day
                        check_date = check_date - timedelta(days=1)
                        if MarketCalendar.is_trading_day(check_date):
                            # Found last trading day
                            if update_date == check_date:
                                # Data is from last trading day - it's fresh!
                                age_hours = age.total_seconds() / 3600
                                logger.debug(
                                    f"[FRESHNESS_OK] {data_name}: {age_hours:.2f}h old "
                                    f"(from last trading day {update_date}, threshold: {self.max_age_hours[data_name]}h)"
                                )
                                return True
                            break
            except Exception as e:
                logger.debug(f"Could not check trading day for {data_name}: {e}. Using strict freshness check.")

        if age > max_age:
            raise StaleDataError(
                data_name=data_name,
                age=age,
                max_age=max_age,
                last_update=last_update,
            )

        age_hours = age.total_seconds() / 3600
        logger.debug(f"[FRESHNESS_OK] {data_name}: {age_hours:.2f}h old (threshold: {self.max_age_hours[data_name]}h)")
        return True

    def check_all(
        self,
        data_dict: dict[str, datetime | None],
        required_only: bool = False,
    ) -> dict[str, bool]:
        """
        Check freshness of multiple data sources.

        Args:
            data_dict: Dict mapping data names to last_update times
            required_only: If True, only check CRITICAL and REQUIRED data

        Returns:
            Dict mapping data name to (True if fresh, False if missing, raises if stale)
        """
        critical_data = {"vix", "spy_close", "portfolio_value", "technical_indicators"}
        required_data = {"market_breadth"}
        optional_data = {"put_call_ratio", "yield_curve", "sector_rotation"}

        results = {}
        for data_name, last_update in data_dict.items():
            # Skip optional data if only checking critical/required
            if required_only and data_name in optional_data:
                continue

            try:
                results[data_name] = self.check(
                    data_name,
                    last_update,
                    allow_missing=data_name in optional_data,
                )
            except StaleDataError as e:
                # CRITICAL/REQUIRED data: re-raise with high visibility
                if data_name in critical_data or data_name in required_data:
                    logger.critical(f"STALE CRITICAL DATA: {e}")
                    raise
                # OPTIONAL data: log warning but continue
                logger.warning(f"STALE OPTIONAL DATA: {e}")
                results[data_name] = False

        return results

    @classmethod
    def for_critical_market_data(cls) -> "FreshnessValidator":
        """Create validator for critical position-sizing data."""
        return cls(
            max_age_hours={
                "vix": 1.0,
                "spy_close": 1.0,
                "portfolio_value": 24.0,
            }
        )

    @classmethod
    def for_signal_generation(cls) -> "FreshnessValidator":
        """Create validator for signal generation data."""
        return cls(
            max_age_hours={
                "technical_indicators": 1.0,
                "market_breadth": 1.0,
            }
        )
