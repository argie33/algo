"""Second half of AlgoConfig.DEFAULTS, extracted from algo/infrastructure/config/main.py
(2026-09-05, file-size ratchet: that file is a Tier-2 bloater flagged for decomposition).
Pure data, no logic changed - split across two files (see config_defaults_1.py for the
first half) to stay under the 800-line new-file cap. AlgoConfig.DEFAULTS itself is
reassembled as {**CONFIG_DEFAULTS_1, **CONFIG_DEFAULTS_2} in main.py.
"""

from typing import Any

CONFIG_DEFAULTS_2: dict[str, tuple[Any, ...]] = {
    "phase7_min_composite_score": (
        "60",
        "int",
        "Phase 7: Minimum composite score 0-100 for signal filtering",
        "Signal Generation",
    ),
    "advanced_filters_grade_threshold_aplus": (
        "90",
        "int",
        "Advanced filters: A+ grade threshold (score >= this value)",
        "Advanced Filters",
    ),
    "advanced_filters_grade_threshold_a": (
        "80",
        "int",
        "Advanced filters: A grade threshold (score >= this value)",
        "Advanced Filters",
    ),
    "advanced_filters_grade_threshold_b": (
        "70",
        "int",
        "Advanced filters: B grade threshold (score >= this value)",
        "Advanced Filters",
    ),
    "advanced_filters_grade_threshold_c": (
        "60",
        "int",
        "Advanced filters: C grade threshold (score >= this value)",
        "Advanced Filters",
    ),
    "advanced_filters_grade_threshold_d": (
        "50",
        "int",
        "Advanced filters: D grade threshold (score >= this value)",
        "Advanced Filters",
    ),
    # Risk Metrics Calculation (M3 - Risk Thresholds)
    "var_percentile": (
        "5",
        "int",
        "Percentile for VaR calculation (5 = 95% confidence, measures 5th percentile loss)",
        "Risk Metrics",
    ),
    "cvar_percentile": (
        "5",
        "int",
        "Percentile for CVaR calculation (5 = worst 5% of days)",
        "Risk Metrics",
    ),
    "stressed_var_percentile": (
        "10",
        "int",
        "Percentile for stressed VaR (10 = worst 10% of days)",
        "Risk Metrics",
    ),
    "dashboard_grade_threshold_a": (
        "80",
        "int",
        "Dashboard signals: A grade threshold (score >= this value)",
        "Risk Metrics",
    ),
    "dashboard_grade_threshold_b": (
        "60",
        "int",
        "Dashboard signals: B grade threshold (score >= this value)",
        "Risk Metrics",
    ),
    "dashboard_grade_threshold_c": (
        "40",
        "int",
        "Dashboard signals: C grade threshold (score >= this value)",
        "Risk Metrics",
    ),
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
    # Data Staleness Thresholds
    "data_staleness_fresh_days": (
        "3",
        "int",
        "Data age (days) considered fresh",
        "Data Staleness",
    ),
    "data_staleness_stale_days_monday": (
        "10",
        "int",
        "Data age (days) on Monday to be considered stale",
        "Data Staleness",
    ),
    "data_staleness_stale_days_other": (
        "3",
        "int",
        "Data age (days) on non-Monday to be considered stale",
        "Data Staleness",
    ),
    # Signal Strength Thresholds
    "signal_weak_threshold": (
        "40.0",
        "float",
        "Signal score below this = weak signal",
        "Signal Strength",
    ),
    "signal_medium_threshold": (
        "60.0",
        "float",
        "Signal score 40-60 (by default) = medium strength",
        "Signal Strength",
    ),
    "signal_strong_threshold": (
        "80.0",
        "float",
        "Signal score 60-80 = strong, >=80 = very strong",
        "Signal Strength",
    ),
    # Dashboard Fetcher Failure Configuration
    "dashboard_fetcher_failure_threshold": (
        "0.5",
        "float",
        "Dashboard: if >N% of fetchers fail, enter degraded mode",
        "Dashboard Configuration",
    ),
    # Portfolio Variance Threshold
    "portfolio_variance_threshold": (
        "0.15",
        "float",
        "Portfolio variance threshold to trigger CB circuit breaker",
        "Risk Metrics",
    ),
    # Data Patrol Staleness Thresholds (days; see data_patrol_config.py for usage)
    "patrol_staleness_price": ("7", "int", "Days before price_daily considered stale", "Data Patrol Configuration"),
    "patrol_staleness_technical_data": (
        "7",
        "int",
        "Days before technical_data_daily considered stale",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_fundamentals": (
        "60",
        "int",
        "Days before fundamentals (quarterly data) considered stale",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_growth_metrics": (
        "30",
        "int",
        "Days before growth_metrics considered stale",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_stock_scores": (
        "7",
        "int",
        "Days before stock_scores considered stale",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_aaii_sentiment": (
        "7",
        "int",
        "Days before aaii_sentiment considered stale",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_earnings_history": (
        "120",
        "int",
        "Days before earnings_history considered stale",
        "Data Patrol Configuration",
    ),
    # Data Patrol Volume Thresholds
    "patrol_high_volume_threshold": (
        "100000000",
        "int",
        "Volume sanity check: daily volume above this = suspicious",
        "Data Patrol",
    ),
    "patrol_low_volume_threshold": (
        "1000",
        "int",
        "Volume sanity check: daily volume below this = suspicious",
        "Data Patrol",
    ),
    "patrol_new_low_volume_alert": (
        "5",
        "int",
        "Alert when N stocks hit 52w volume lows",
        "Data Patrol",
    ),
    # Data Patrol Quality Thresholds
    "patrol_max_null_pct_threshold": (
        "5.0",
        "float",
        "Max allowed null % in a data table",
        "Data Patrol Configuration",
    ),
    "patrol_max_daily_move_pct": (
        "0.5",
        "float",
        "Flag OHLC rows with daily move > N * 100%",
        "Data Patrol Configuration",
    ),
    "patrol_max_daily_move_count": (
        "10",
        "int",
        "Max allowed extreme daily moves per run",
        "Data Patrol Configuration",
    ),
    # Data Patrol Coverage Thresholds
    "patrol_price_daily_14d_min": (
        "40000",
        "int",
        "Min rows in price_daily over last 14 days",
        "Data Patrol Configuration",
    ),
    "patrol_buy_sell_daily_14d_min": (
        "800",
        "int",
        "Min rows in buy_sell_daily over last 14 days",
        "Data Patrol Configuration",
    ),
    "patrol_signal_quality_scores_14d_min": (
        "300",
        "int",
        "Min rows in signal_quality_scores over last 14 days (sparse by design: live daily "
        "counts range ~510-2510 symbols/day; 300 is a catastrophic-failure floor, not a "
        "target)",
        "Data Patrol Configuration",
    ),
    "patrol_coverage_ratio_min": (
        "0.8",
        "float",
        "Min coverage ratio (0-1) for data completeness check",
        "Data Patrol Configuration",
    ),
    "patrol_min_coverage_ratio": (
        "80.0",
        "float",
        "Min coverage ratio % (0-100) for universe coverage",
        "Data Patrol Configuration",
    ),
    "patrol_min_universe_pct": (
        "80.0",
        "float",
        "Min % of active universe that must have data",
        "Data Patrol Configuration",
    ),
    # Advanced Filters Feature Flag
    "enable_advanced_filters": ("false", "bool", "Enable advanced signal filters", "Advanced Filters"),
    # Data Patrol Staleness Thresholds (per-table granularity)
    "patrol_staleness_price_daily": ("2", "int", "Max staleness days for price_daily", "Data Patrol Configuration"),
    "patrol_staleness_technical_daily": (
        "2",
        "int",
        "Max staleness days for technical_daily",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_buy_sell_daily": (
        "3",
        "int",
        "Max staleness days for buy_sell_daily",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_trend_data": ("3", "int", "Max staleness days for trend_data", "Data Patrol Configuration"),
    "patrol_staleness_signal_quality_scores": (
        "3",
        "int",
        "Max staleness days for signal_quality_scores",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_market_health": (
        "1",
        "int",
        "Max staleness days for market_health",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_sector_ranking": (
        "3",
        "int",
        "Max staleness days for sector_ranking",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_industry_ranking": (
        "3",
        "int",
        "Max staleness days for industry_ranking",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_insider_transactions": (
        "7",
        "int",
        "Max staleness days for insider_transactions",
        "Data Patrol Configuration",
    ),
    "patrol_staleness_analyst_upgrades": (
        "7",
        "int",
        "Max staleness days for analyst_upgrades",
        "Data Patrol Configuration",
    ),
    # Data Patrol Coverage Error/Warning Thresholds (% of active universe a critical
    # table must cover; below error_pct -> ERROR, below warn_pct -> WARN). Defaults match
    # the live DB-configured values (96/98) so a missing config row fails toward the real
    # operating threshold instead of silently disabling the check (a stale "5.0" fallback
    # here previously meant coverage had to collapse below 5% before anything fired).
    "patrol_coverage_error_threshold_pct": (
        "96",
        "float",
        "Min symbol coverage % for critical tables before ERROR",
        "Data Patrol Configuration",
    ),
    "patrol_coverage_warning_threshold_pct": (
        "98",
        "float",
        "Min symbol coverage % for critical tables before WARN",
        "Data Patrol Configuration",
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
    "max_risk_per_trade_pct": ("18.0", "float", "Maximum risk per trade %", "Risk Management"),
    "patrol_corporate_action_drop_ratio": (
        "-0.3",
        "float",
        "Corporate action price drop ratio threshold",
        "Data Quality",
    ),
    "patrol_corporate_action_lookback_days": (
        "30",
        "int",
        "Corporate action lookback window (days)",
        "Data Quality",
    ),
    "patrol_identical_ohlc_threshold": ("100", "int", "Identical OHLC threshold (cents)", "Data Quality"),
    # BUG FOUND 2026-08-11: this key's only real consumer (data_patrol_config.py's
    # get_loader_contracts()) uses it as a `min_rows` threshold for market_exposure_daily,
    # a table with exactly 1 row/day by design. The "10.0"/float/"% " description here
    # described an unrelated percent-exposure concept that was never actually wired to
    # this key anywhere in the codebase (grepped clean) - meanwhile the live DB had it
    # set to 80, so the loader_contract demanded 80+ rows from a table that structurally
    # never has more than ~2 (its 1-day lookback window), an unconditional permanent
    # ERROR every day. Corrected to match the key's one real usage.
    "patrol_market_exposure_daily_min": (
        "1",
        "int",
        "Min rows in market_exposure_daily within the loader contract's 1-day lookback (table is 1 row/day by design)",
        "Data Quality",
    ),
    "patrol_new_zero_symbols_error": ("100", "int", "New zero symbols error threshold", "Data Quality"),
    "patrol_new_zero_symbols_warn": ("50", "int", "New zero symbols warning threshold", "Data Quality"),
    "patrol_price_xval_mismatch_pct": (
        "5.0",
        "float",
        "Price cross-validation mismatch threshold %",
        "Data Quality",
    ),
    "patrol_technical_daily_14d_min": (
        "90",
        "int",
        "Technical data 14-day minimum coverage %",
        "Data Quality",
    ),
    "patrol_trend_14d_min": ("90", "int", "Trend data 14-day minimum coverage %", "Data Quality"),
    "patrol_xval_top_n_symbols": ("100", "int", "Cross-validation top N symbols count", "Data Quality"),
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
    # Data Loader Coverage Thresholds (Phase 1 data freshness checks)
    "technical_daily_coverage_threshold_pct": (
        "95",
        "int",
        "Min % daily technical coverage",
        "Data Quality",
    ),
    # Orchestrator Halt Configuration
    "orchestrator_halt_enabled": (
        "true",
        "bool",
        "Enable orchestrator halt on data issues",
        "System",
    ),
    # Exposure Constraints
    "halt_new_entries": (
        "false",
        "bool",
        "Legacy: halt new entry orders",
        "Risk Management",
    ),
    "max_new_positions_today": (
        "15",
        "int",
        "Legacy: max new positions per day",
        "Risk Management",
    ),
    # Pyramiding Configuration
    "pyramid_enabled": (
        "true",
        "bool",
        "Enable multi-entry pyramiding",
        "Position Management",
    ),
    "pyramid_add_1_gain_pct": (
        "2.0",
        "float",
        "Gain threshold for first add (pyramiding)",
        "Position Management",
    ),
    "pyramid_add_2_gain_pct": (
        "4.0",
        "float",
        "Gain threshold for second add (pyramiding)",
        "Position Management",
    ),
    "pyramid_split_pct": (
        "50.0",
        "float",
        "Split position % per add (pyramiding)",
        "Position Management",
    ),
    # Signal Data Quality
    "signal_max_data_age_days": (
        "3",
        "int",
        "Maximum age of signal data for trading",
        "Data Quality",
    ),
    # Loader & Order Staleness Detection
    "stale_loader_threshold_minutes": (
        "60",
        "int",
        "Alert if loader stale for this many minutes",
        "Data Quality",
    ),
    "stale_order_alert_minutes": (
        "30",
        "int",
        "Alert if order pending for this many minutes",
        "Risk Management",
    ),
    "stale_order_auto_cancel_minutes": (
        "120",
        "int",
        "Auto-cancel if order pending for this many minutes",
        "Risk Management",
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
    # Market Open Entry Exclusion
    "market_open_exclusion_enabled": (
        "false",
        "bool",
        "Block Phase 8 entries for N minutes after market open (high false-breakout rate)",
        "Risk Management",
    ),
    "market_open_exclusion_minutes": (
        "30",
        "int",
        "Minutes after 9:30 AM ET market open to block entries (0=disabled, 30=default)",
        "Risk Management",
    ),
    # Exit Strategy Configuration
    "exit_on_minervini_break": (
        "false",
        "bool",
        "Exit on Minervini trend template break (disabled - 0% win rate from testing)",
        "Exit Strategy",
    ),
    # Loader Failure Rate Thresholds
    "loader_max_fail_rate_price": (
        "0.05",
        "float",
        "Max acceptable failure rate for price loaders (5%)",
        "Data Quality",
    ),
    "loader_max_fail_rate_buy_sell": (
        "0.1",
        "float",
        "Max acceptable failure rate for buy/sell loaders (10%)",
        "Data Quality",
    ),
}
