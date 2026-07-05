#!/usr/bin/env python3
"""
Centralized constants for magic numbers across the algo system.

This module consolidates all hardcoded thresholds, multipliers, and limits
to make changes easier and provide a single source of truth. Thresholds that
require runtime tuning are stored in algo_config database table and fetched
via AlgoConfig.get() — these constants represent compile-time defaults only.

Organization:
- Rate Limiting & API Thresholds
- Portfolio & Risk Management
- Data Quality & Monitoring
- Price & Volume Sanity
- Data Loader Contracts
- Regime & Market Conditions
"""

# ── Rate Limiting & API Thresholds ──────────────────────────────────────────

# Calls per minute for external APIs
YFINANCE_RATE_LIMIT_CPM = 400  # Optimized: 150 was too slow (80+ min for 10k stocks). >1000 triggers yfinance rate limit. 400 = ~30 min for full universe.
ALPACA_DATA_RATE_LIMIT_CPM = 180  # Alpaca data API 200 req/min with 10% headroom
ALPHA_VANTAGE_RATE_LIMIT_CPM = 4  # Free tier: 5 req/min with 20% headroom
DEFAULT_RATE_LIMIT_CPM = 30  # Conservative fallback
SEC_EDGAR_RATE_LIMIT_CPM = 2  # SEC allows 10 req/sec; 2 = extra conservative for parallel tasks

# Retry backoff configuration
RETRY_BASE_DELAY_SEC = 1.0
RETRY_MAX_DELAY_SEC = 60.0
RETRY_BACKOFF_MULTIPLIER = 2.0
RETRY_JITTER_MIN_FACTOR = 0.75  # Min multiplier for jitter (±25%)
RETRY_JITTER_MAX_FACTOR = 1.25  # Max multiplier for jitter

# Connection pooling
DB_MAX_CONNECTIONS = 100  # db.t4g.small safety threshold
DB_POOL_ALERT_THRESHOLD_PCT = 80  # Alert when pool usage > 80%
DB_POOL_TIMEOUT_SEC = 300

# ── Portfolio & Risk Management ─────────────────────────────────────────────

# Regime-based position sizing multipliers (applied to max_position_size_pct)
REGIME_POSITION_SIZE_CONFIRMED_UPTREND = 1.0
REGIME_POSITION_SIZE_UPTREND_UNDER_PRESSURE = 0.75
REGIME_POSITION_SIZE_CAUTION = 0.5
REGIME_POSITION_SIZE_CORRECTION = 0.0

# Regime-based hold time multipliers (applied to max_hold_days = 20)
REGIME_HOLD_DAYS_CONFIRMED_UPTREND = 1.5  # 30 days
REGIME_HOLD_DAYS_UPTREND_UNDER_PRESSURE = 1.0  # 20 days
REGIME_HOLD_DAYS_CAUTION = 0.75  # 15 days
REGIME_HOLD_DAYS_CORRECTION = 0.5  # 10 days

# Regime-based target multipliers
REGIME_TARGET_CONFIRMED_UPTREND = 1.0
REGIME_TARGET_UPTREND_UNDER_PRESSURE = 1.0
REGIME_TARGET_CAUTION = 0.8
REGIME_TARGET_CORRECTION = 0.6

# Regime-based parameter adaptation speed (alpha for weight update)
REGIME_WEIGHT_UPDATE_ALPHA_CONFIRMED_UPTREND = 0.10
REGIME_WEIGHT_UPDATE_ALPHA_UPTREND_UNDER_PRESSURE = 0.05
REGIME_WEIGHT_UPDATE_ALPHA_CAUTION = 0.05
REGIME_WEIGHT_UPDATE_ALPHA_CORRECTION = 0.0  # Freeze weights in correction

# ── Data Quality & Monitoring ───────────────────────────────────────────────

# Data Patrol check performance thresholds
PATROL_SLOW_CHECK_THRESHOLD_SEC = 5.0  # Alert if any check takes > 5 seconds
PATROL_OVERALL_SLOW_THRESHOLD_SEC = 120.0  # Alert if patrol takes > 120 seconds

# Data staleness windows (days) — defaults, configurable via algo_config
STALENESS_WINDOW_PRICE_DAILY = 7
STALENESS_WINDOW_TECHNICAL_DATA = 7
STALENESS_WINDOW_BUY_SELL_DAILY = 7
STALENESS_WINDOW_SIGNAL_QUALITY = 7
STALENESS_WINDOW_STOCK_SCORES = 14
STALENESS_WINDOW_EARNINGS_HISTORY = 120

# NULL value anomaly detection
NULL_ANOMALY_MAX_PCT = 5  # Alert if >5% NULLs on latest date

# Zero/identical OHLC detection (parameterized in algo_config)
ZERO_SYMBOLS_ERROR_THRESHOLD = 30  # Alert ERROR if >30 NEW zero-volume symbols
ZERO_SYMBOLS_WARN_THRESHOLD = 5  # Alert WARN if >5 NEW zero-volume symbols
IDENTICAL_OHLC_THRESHOLD = 30  # Alert WARN if >30 symbols with identical OHLC

# Price sanity checks
EXTREME_PRICE_MOVE_RATIO = 0.5  # Flag moves > 50% in one day
EXTREME_MOVE_COUNT_THRESHOLD = 10  # Flag if >10 extreme moves in window
EXTREME_MOVE_COUNT_LOOKBACK_DAYS = 5
PRICE_XVAL_MISMATCH_PCT = 5  # >5% difference from Yahoo/Alpaca = suspicious

# Volume sanity
VOLUME_LOW_THRESHOLD = 1_000_000  # Flag if volume < this (penny stock threshold)
VOLUME_HIGH_THRESHOLD = 100_000_000  # Flag if volume > this (extreme threshold)
NEW_LOW_VOLUME_ALERT_COUNT = 50  # Alert if >50 NEW low-volume symbols
VOLUME_NEW_LOW_PCT = 50  # Flag if volume < 50% of 20d avg

# Corporate actions detection
CORPORATE_ACTION_DROP_RATIO = -0.3  # Flag if >30% drop in 1 day (likely split/halt/delisting)
CORPORATE_ACTION_LOOKBACK_DAYS = 30

# ── Data Loader Contracts ───────────────────────────────────────────────────

# Minimum acceptable data volumes
LOADER_PRICE_DAILY_14D_MIN = 40_000  # ~5000 symbols x 14 days x 60% coverage
LOADER_TECHNICAL_DAILY_14D_MIN = 40_000
LOADER_BUY_SELL_DAILY_14D_MIN = 800  # 50+ per day minimum
LOADER_TREND_TEMPLATE_14D_MIN = 16_000  # 4900+ symbols x 14 days x 20% coverage
LOADER_SIGNAL_QUALITY_14D_MIN = 16_000
LOADER_MARKET_HEALTH_14D_MIN = 10  # ~14 daily rows expected
LOADER_MARKET_EXPOSURE_14D_MIN = 4  # Most days

# Buy/sell signal quality
BUY_SELL_CLEAN_PCT_THRESHOLD = 80  # <80% clean BUY/SELL signals = alert

# Coverage ratios (symbol alignment)
COVERAGE_RATIO_MIN_STRICT = 0.95  # 95% coverage for high-quality tables
COVERAGE_RATIO_MIN_NORMAL = 0.90  # 90% coverage for standard tables
COVERAGE_RATIO_MIN_LOOSE = 0.80  # 80% coverage minimum
COVERAGE_RATIO_MIN_UNIVERSE_PCT = 75  # 75% of universe must have data

# ETF-specific
ETF_PRICE_FRESHNESS_MAX_DAYS = 3
ETF_PRICE_MIN_COUNT = 30
ETF_SIGNAL_MIN_DAILY = 5
ETF_SIGNAL_MIN_WEEKLY = 1

# Fundamental data
FUNDAMENTAL_DATA_QUARTERLY_MAX_DAYS = 45
FUNDAMENTAL_DATA_ANNUAL_MAX_DAYS = 120
KEY_METRICS_MAX_DAYS = 14
KEY_METRICS_MIN_COVERAGE_PCT = 80

# Earnings data
EARNINGS_ESTIMATE_MAX_DAYS = 7
EARNINGS_REVISIONS_MAX_DAYS = 14
EARNINGS_COVERAGE_MIN_PCT = 80

# Sentiment data
SENTIMENT_MAX_DAYS = 7

# Price data cross-validation (Alpaca/Yahoo)
XVAL_TOP_N_SYMBOLS = 10

# ── Data Pagination & Batch Processing ──────────────────────────────────────

# Price loader batching
LOAD_PRICES_BATCH_SIZE_EOD = 100  # End-of-day loading batch size
LOAD_PRICES_BATCH_SIZE_INTRADAY = 50  # Intraday loading batch size
LOAD_PRICES_SMART_SIZE_EOD = 100
LOAD_PRICES_SMART_SIZE_INTRADAY = 50
LOAD_PRICES_CIRCUIT_BREAK_WAIT_THRESHOLD_PCT = 0.8  # 8 minutes of 10 minute window
LOAD_PRICES_BATCH_REDUCED_THRESHOLD_SEC = 600  # 10 minutes in seconds
LOAD_PRICES_FINAL_RETRY_TIME_PCT = 0.8  # 80% of 7-hour limit

# Single batch max wait before considering slowdown
LOAD_PRICES_MAX_SINGLE_BATCH_WAIT_SEC = 600  # 10 minutes

# ── Sentinel Values ─────────────────────────────────────────────────────────

# Price bounds validation
MAX_REASONABLE_STOCK_PRICE = 100_000
MIN_REASONABLE_STOCK_PRICE = 0.001

# Time-based calculations
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

# Percentage calculations (for readability)
PERCENT_MULTIPLIER = 100
