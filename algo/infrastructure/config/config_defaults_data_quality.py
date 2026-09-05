"""AlgoConfig.DEFAULTS entries for data patrol, staleness and data-quality thresholds.

Part of the AlgoConfig.DEFAULTS dict, split by domain out of
algo/infrastructure/config/main.py (2026-09-05) to keep that file focused on
runtime config logic. Pure data, no behavior changed. Reassembled in main.py as
{**CONFIG_DEFAULTS_RISK, **CONFIG_DEFAULTS_SIGNALS, **CONFIG_DEFAULTS_MARKET,
**CONFIG_DEFAULTS_DATA_QUALITY, **CONFIG_DEFAULTS_SYSTEM}.
"""

from typing import Any

CONFIG_DEFAULTS_DATA_QUALITY: dict[str, tuple[Any, ...]] = {
    "max_data_staleness_days": ("3", "int", "Max data age in days", "Data Quality"),
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
    # Data Loader Coverage Thresholds (Phase 1 data freshness checks)
    "technical_daily_coverage_threshold_pct": (
        "95",
        "int",
        "Min % daily technical coverage",
        "Data Quality",
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
