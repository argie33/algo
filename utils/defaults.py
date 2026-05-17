#!/usr/bin/env python3
"""
System-wide default configuration values.

Centralized place for all hardcoded defaults used throughout the system.
Modules should import from here instead of defining their own os.getenv() with defaults.
"""

# Database Configuration Defaults
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "stocks"
DB_NAME = "stocks"

# Logging Defaults
LOG_LEVEL = "INFO"

# Alpaca Trading Defaults
ALPACA_PAPER_TRADING = True

# Feature Flag Defaults
ENABLE_CIRCUIT_BREAKER = True
ENABLE_POSITION_SIZING = True
ENABLE_EARNINGS_BLACKOUT = True

DEFAULT_POSITION_SIZE_PCT = 2.0

# MAX_POSITION_SIZE_PCT: 8% ceiling prevents concentration risk in single stock
# Rationale: Institutional best practice (10-15% for institutions), 8% for retail conservatism
MAX_POSITION_SIZE_PCT = 8.0

# BASE_RISK_PCT: 0.75% maximum daily drawdown threshold before circuit breaker triggers
# Rationale: Prevents large single-day losses; aligned with institutional risk limits
BASE_RISK_PCT = 0.75

# MAX_EXPOSURE_PCT: 30% total portfolio allocation limit to avoid overleveraging
# Rationale: Keeps 70% in cash for opportunities and shock absorption
MAX_EXPOSURE_PCT = 30.0

MIN_SIGNAL_STRENGTH = 0.6

# MIN_TREND_CONFIDENCE: 0.55 = 55% confidence that trend direction is established
# Rationale: Slightly lower than signal strength; trends harder to confirm than single indicator
MIN_TREND_CONFIDENCE = 0.55

# MIN_PATTERN_MATCH: 0.7 = 70% similarity to historical chart patterns
# Rationale: High threshold to reduce false positives from pattern-matching algorithms
MIN_PATTERN_MATCH = 0.7

TIER_NORMAL_MULTIPLIER = 1.0
TIER_CAUTION_MULTIPLIER = 0.75
TIER_PRESSURE_MULTIPLIER = 0.5
TIER_HALT_MULTIPLIER = 0.0

# Data Loading Defaults
LOADER_PARALLELISM = 8
LOADER_TIMEOUT_SECONDS = 300

# Event Bridge Scheduling Defaults
EVENTBRIDGE_RULE_SCHEDULE = "cron(0 17 * * ? *)"  # 5:30 PM ET
EVENTBRIDGE_TIMEZONE = "America/New_York"
