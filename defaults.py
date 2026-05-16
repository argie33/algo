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

# Risk Management Defaults
DEFAULT_POSITION_SIZE_PCT = 2.0
MAX_POSITION_SIZE_PCT = 8.0
BASE_RISK_PCT = 0.75
MAX_EXPOSURE_PCT = 30.0

# Signal Quality Defaults
MIN_SIGNAL_STRENGTH = 0.6
MIN_TREND_CONFIDENCE = 0.55
MIN_PATTERN_MATCH = 0.7

# Market Exposure Tier Defaults
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
