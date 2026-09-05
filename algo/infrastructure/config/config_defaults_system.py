"""AlgoConfig.DEFAULTS entries for system/execution-mode/SQL/network/dashboard/feature-flag settings.

Part of the AlgoConfig.DEFAULTS dict, split by domain out of
algo/infrastructure/config/main.py (2026-09-05) to keep that file focused on
runtime config logic. Pure data, no behavior changed. Reassembled in main.py as
{**CONFIG_DEFAULTS_RISK, **CONFIG_DEFAULTS_SIGNALS, **CONFIG_DEFAULTS_MARKET,
**CONFIG_DEFAULTS_DATA_QUALITY, **CONFIG_DEFAULTS_SYSTEM}.
"""

from typing import Any

CONFIG_DEFAULTS_SYSTEM: dict[str, tuple[Any, ...]] = {
    # Dashboard Configuration (E8, E9 - Operator-tunable thresholds)
    "dashboard_min_quality_threshold": (
        "40.0",
        "float",
        "Minimum signal quality score to display (0-100; E8)",
        "Dashboard Configuration",
    ),
    "dashboard_metrics_max_age_minutes": (
        "120",
        "int",
        "Maximum age of metrics in minutes before warning (E9)",
        "Dashboard Configuration",
    ),
    # Execution Mode
    "execution_mode": ("paper", "string", "paper|dry|review|auto", "Execution Mode"),
    "alpaca_paper_trading": ("true", "bool", "Use Alpaca paper account", "Execution Mode"),
    "credentials_are_production": (
        "false",
        "bool",
        "Using real production credentials (requires explicit enable for live trading)",
        "Execution Mode",
    ),
    "initial_capital_paper_trading": (
        "100000.0",
        "float",
        "Initial capital for paper trading mode (portfolio value base)",
        "Execution Mode",
    ),
    "max_trades_per_day": ("5", "int", "Max new trades per day", "Execution Mode"),
    "default_portfolio_value": (
        "100000.0",
        "float",
        "Bootstrap portfolio value when Alpaca unreachable and no snapshot (Alpaca paper starts at $100k)",
        "Execution Mode",
    ),
    # Feature Flags
    "enable_algo": ("true", "bool", "Enable algo trading", "Feature Flags"),
    "enable_backtesting": ("false", "bool", "Enable backtest mode", "Feature Flags"),
    "verbose_logging": ("true", "bool", "Detailed logging", "Feature Flags"),
    # Network Configuration
    "api_request_timeout_seconds": (
        "5",
        "int",
        "HTTP request timeout (seconds) for Alpaca/FRED/market data APIs",
        "Network Configuration",
    ),
    "db_connection_timeout_seconds": (
        "15",
        "int",
        "Database connection timeout (seconds)  - RDS Proxy adds latency",
        "Network Configuration",
    ),
    # Failsafe Configuration
    "failsafe_ecs_timeout_sec": (
        "180",
        "int",
        "Max seconds to wait for ECS task to reach RUNNING state (Fargate provisioning under load: 45-150s)",
        "Failsafe Configuration",
    ),
    "failsafe_grace_period_minutes": (
        "240",
        "int",
        "Grace period before second failsafe (min). Morning 2-9:30AM: "
        "expected load ~285min, allows 2:00+240m=6:00 expiry. Must be <390.",
        "Failsafe Configuration",
    ),
    # Loader Rate Limiting Configuration
    "loader_rate_limit_circuit_break_threshold_morning": (
        "480",
        "int",
        "Circuit break threshold (seconds) during morning prep (8 min)",
        "Loader Rate Limiting",
    ),
    "loader_rate_limit_circuit_break_threshold_eod": (
        "180",
        "int",
        "Circuit break threshold (seconds) during EOD (3 min)",
        "Loader Rate Limiting",
    ),
    "loader_rate_limit_requests_per_min": (
        "120",
        "int",
        "Rate limit: maximum requests per minute",
        "Loader Rate Limiting",
    ),
    "loader_timeout_seconds": (
        "300",
        "int",
        "Loader operation timeout in seconds",
        "Loader Rate Limiting",
    ),
    "loader_emergency_mode_threshold_multiplier": (
        "0.5",
        "float",
        "Emergency mode triggered at N% of task timeout",
        "Loader Rate Limiting",
    ),
    # Dashboard Fetcher Failure Configuration
    "dashboard_fetcher_failure_threshold": (
        "0.5",
        "float",
        "Dashboard: if >N% of fetchers fail, enter degraded mode",
        "Dashboard Configuration",
    ),
    # SQL Query INTERVAL Configuration (replaces 80+ hardcoded INTERVAL values in SQL queries)
    "sql_interval_1d_days": ("1", "int", "1-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_7d_days": ("7", "int", "7-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_14d_days": (
        "14",
        "int",
        "14-day lookback interval for SQL queries",
        "SQL Query Configuration",
    ),
    "sql_interval_24h_days": (
        "1.0",
        "float",
        "24-hour lookback interval for SQL queries (in days)",
        "SQL Query Configuration",
    ),
    "sql_interval_30d_days": ("30", "int", "30-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_50d_days": ("50", "int", "50-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_60d_days": ("60", "int", "60-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_90d_days": ("90", "int", "90-day lookback interval for SQL queries", "SQL Query Configuration"),
    "sql_interval_365d_days": (
        "365",
        "int",
        "365-day (1-year) lookback interval for SQL queries",
        "SQL Query Configuration",
    ),
    "sql_interval_52w_days": (
        "364",
        "int",
        "52-week (~364-day) lookback interval for SQL queries",
        "SQL Query Configuration",
    ),
    # Retry Configuration (replaces 3 hardcoded retry counts)
    # API & Data Configuration
    "alpaca_api_key": ("", "string", "Alpaca API key (from environment)", "System"),
    "alpaca_api_secret": ("", "string", "Alpaca API secret (from environment)", "System"),
    "alpaca_base_url": (
        "https://paper-api.alpaca.markets",
        "string",
        "Alpaca trading API base URL",
        "System",
    ),
    "grade_override_enabled": (
        "false",
        "bool",
        "Enable signal grade override for testing",
        "System",
    ),
    "grade_override_max_duration_minutes": (
        "60",
        "int",
        "Max duration for signal grade override (minutes)",
        "System",
    ),
    "lookback_price_1m": ("30", "int", "Lookback window for 1-month price (days)", "System"),
    "lookback_price_1y": ("252", "int", "Lookback window for 1-year price (days)", "System"),
    "lookback_price_3m": ("60", "int", "Lookback window for 3-month price (days)", "System"),
    "lookback_price_6m": ("120", "int", "Lookback window for 6-month price (days)", "System"),
    "lookback_ranking_long": ("84", "int", "Ranking long window (days)", "System"),
    "lookback_ranking_medium": ("28", "int", "Ranking medium window (days)", "System"),
    "lookback_ranking_short": ("7", "int", "Ranking short window (days)", "System"),
    "yfinance_market_close_timeout_eod_sec": (
        "30",
        "int",
        "yfinance market close timeout (EOD, seconds)",
        "System",
    ),
    "yfinance_market_close_timeout_morning_sec": (
        "30",
        "int",
        "yfinance market close timeout (morning, seconds)",
        "System",
    ),
    # Orchestrator Halt Configuration
    "orchestrator_halt_enabled": (
        "true",
        "bool",
        "Enable orchestrator halt on data issues",
        "System",
    ),
    # API Configuration
    "alpaca_api_base_url": (
        "https://paper-api.alpaca.markets",
        "string",
        "Alpaca API base URL",
        "External APIs",
    ),
    # API Retry Configuration
    "retry_count_fred_api": (
        "3",
        "int",
        "Retry count for FRED API calls",
        "External APIs",
    ),
    "retry_count_aaii_sentiment": (
        "3",
        "int",
        "Retry count for AAII sentiment API calls",
        "External APIs",
    ),
    "retry_count_db_migration": (
        "3",
        "int",
        "Retry count for database migrations",
        "Database",
    ),
}
