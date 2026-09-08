"""AlgoConfig.DEFAULTS entries for entry/exit rules, signal filters and quality thresholds.

Part of the AlgoConfig.DEFAULTS dict, split by domain out of
algo/infrastructure/config/main.py (2026-09-05) to keep that file focused on
runtime config logic. Pure data, no behavior changed. Reassembled in main.py as
{**CONFIG_DEFAULTS_RISK, **CONFIG_DEFAULTS_SIGNALS, **CONFIG_DEFAULTS_MARKET,
**CONFIG_DEFAULTS_DATA_QUALITY, **CONFIG_DEFAULTS_SYSTEM}.
"""

from typing import Any

CONFIG_DEFAULTS_SIGNALS: dict[str, tuple[Any, ...]] = {
    # Filter Thresholds
    "min_completeness_score": (
        "70",
        "int",
        "Minimum data completeness % (Minervini standard)",
        "Filter Thresholds",
    ),
    "min_stock_price": ("5.0", "float", "Minimum stock price $", "Filter Thresholds"),
    "min_signal_quality_score": (
        "82",
        "int",
        "Minimum SQS 0-100 (signal quality gate) - ~72% pass rate on the corrected "
        "composite (volume_confirmation excluded), matching the original 2026-07-31 "
        "calibration's target selectivity - see config_schema.py's comment",
        "Filter Thresholds",
    ),
    "max_signal_quality_score": (
        "100",
        "int",
        "Maximum SQS 0-100 (phase 8 quality gate)",
        "Filter Thresholds",
    ),
    "max_signal_age_hours": (
        "24",
        "int",
        "Maximum signal age in hours (rejects stale EOD pipeline signals)",
        "Filter Thresholds",
    ),
    "min_volume_ma_50d": ("300000", "int", "Minimum 50-day avg volume", "Filter Thresholds"),
    "min_avg_daily_dollar_volume": (
        "500000",
        "float",
        "Minimum daily dollar volume for liquidity gate",
        "Filter Thresholds",
    ),
    "require_stock_stage_2": ("true", "bool", "Require Stage 2 trend template", "Filter Thresholds"),
    "max_stop_distance_pct": ("12.0", "float", "Max stop distance % from entry", "Filter Thresholds"),
    "max_positions_per_sector": (
        "10",
        "int",
        "Max concurrent positions in one sector",
        "Filter Thresholds",
    ),
    "max_positions_per_industry": (
        "8",
        "int",
        "Max concurrent positions in one industry",
        "Filter Thresholds",
    ),
    "max_position_correlation": (
        "0.85",
        "float",
        "Block a new entry if its return correlation with any currently open position exceeds this",
        "Filter Thresholds",
    ),
    "correlation_lookback_days": (
        "60",
        "int",
        "Trading-day window used to compute position-correlation for the diversification check",
        "Filter Thresholds",
    ),
    "correlation_min_overlap_days": (
        "30",
        "int",
        "Minimum overlapping real trading days required to trust a correlation estimate (skip check below this)",
        "Filter Thresholds",
    ),
    "max_portfolio_beta": (
        # Tightened 2.0->1.5 (2026-09-06 finance-best-practices review, see
        # config_schema.py's matching entry for full reasoning): 2.0+ is an aggressive/
        # leveraged-mandate convention, 1.2-1.5 is standard for a moderate-risk active
        # strategy - this cap is a backstop (the 4.75% position-size cap already makes a
        # genuine 2.0 hard to reach), so tightening costs little while matching intent.
        "1.5",
        "float",
        "Block a new entry if it would push the position-value-weighted portfolio beta above this",
        "Filter Thresholds",
    ),
    "max_top5_concentration_pct": (
        "30.0",
        "float",
        "Block a new entry if it would push the top-5-holdings share of portfolio value above this",
        "Filter Thresholds",
    ),
    "max_simulated_var_pct": (
        "2.0",
        "float",
        "Block a new entry if it would push the simulated current-weights portfolio VaR (95%/252d, "
        "held-at-today's-weights over historical per-symbol price returns) above this pct of equity",
        "Filter Thresholds",
    ),
    "max_cvar_pct": (
        "3.0",
        "float",
        "Alert (informational only, algo/risk/var.py's daily report - not a pretrade entry gate) "
        "when realized 95%/252d CVaR (Expected Shortfall - the average loss on days worse than "
        "VaR) exceeds this pct of equity. Default is 1.5x max_simulated_var_pct's 2.0%, matching "
        "the standard fat-tailed-equity-returns ES/VaR multiplier (~1.25x under normality; higher "
        "for real equity tails) - not independently backtested against this portfolio's own "
        "return distribution, so treat as a reasonable starting point to tune once real CVaR "
        "history accumulates, not a validated number. Added 2026-09-07 (real-money-readiness "
        "audit) - CVaR was computed and persisted everywhere but never alerted on anywhere.",
        "Filter Thresholds",
    ),
    # Entry Rules (Minervini)
    "require_sma50_above_sma200": ("true", "bool", "Price and MA alignment", "Entry Rules"),
    "min_percent_from_52w_low": (
        "0.0",
        "float",
        "Min % from 52w low (Minervini standard)",
        "Entry Rules",
    ),
    "max_percent_from_52w_high": ("25.0", "float", "Max % from 52w high", "Entry Rules"),
    "min_trend_template_score": (
        "6",
        "int",
        "Min Minervini score 0-8 (score 6 allows consolidating bases through; migration-006 lowered from 7)",
        "Entry Rules",
    ),
    # Entry Quality Gates (Sprint 2)
    "max_signal_age_days": ("3", "int", "Reject BUY signals older than N days", "Entry Quality Gates"),
    "min_close_quality_pct": (
        "40.0",
        "float",
        "Close threshold: stock close at/above this % of day range. 40=upper 60%. "
        "Filters weak closes indicating distribution.",
        "Entry Quality Gates",
    ),
    "min_breakout_volume_ratio": (
        "1.25",
        "float",
        "Volume must be N x 50-day average",
        "Entry Quality Gates",
    ),
    "require_weekly_stage_2": ("false", "bool", "Require weekly chart Stage 2", "Entry Quality Gates"),
    "min_rs_line_slope_days": ("10", "int", "Days for RS line slope check", "Signal Quality Thresholds"),
    "max_rs_pct_from_60d_high": (
        "15.0",
        "float",
        "Max % RS-line below 60d high (Minervini strict = 5%)",
        "Entry Quality Gates",
    ),
    "rs_slope_gate_enabled": (
        "false",
        "bool",
        "Hard-gate T3 on RS line trending up (false=warn-only; consolidating bases show flat RS by design)",
        "Entry Quality Gates",
    ),
    "volume_decay_gate_enabled": (
        "false",
        "bool",
        "Hard-gate T3 on volume decay into breakout (false=warn-only; accumulation naturally shows drying volume)",
        "Entry Quality Gates",
    ),
    # Exit Rules
    "require_target_pullback": (
        "false",
        "bool",
        "Require 2%+ pullback before partial profit exits at T1/T2 (false = exit immediately at target)",
        "Exit Rules",
    ),
    # DISABLED 2026-09-07 (see exit_position_context.py's check_target_t1 docstring): scale-out
    # underperformed a pure trail on a 471,972-trade validation backtest. Schema default stays
    # True; live value False via migration.
    "use_scale_out_targets": (
        "true",
        "bool",
        "Enable T1/T2/T3 partial-exit scale-out (disabled live - see check_target_t1 docstring)",
        "Exit Rules",
    ),
    "t1_target_r_multiple": ("1.5", "float", "Tier 1 profit target R-mult", "Exit Rules"),
    "t2_target_r_multiple": ("3.0", "float", "Tier 2 profit target R-mult", "Signal Quality Thresholds"),
    "t3_target_r_multiple": ("4.0", "float", "Tier 3 profit target R-mult", "Signal Quality Thresholds"),
    # Imported Position Defaults (when ATR calculation fails)
    "imported_position_default_stop_loss_pct": (
        "5.0",
        "float",
        "Default stop loss % for imported positions",
        "Exit Rules",
    ),
    # REAL-MONEY-READINESS (2026-09-07 audit): an orphaned broker position (found at Alpaca,
    # no matching algo_trades/algo_positions row - e.g. a manual trade placed directly at the
    # broker) previously got a critical alert but literally zero stop-loss protection, because
    # algo_untracked_positions is deliberately kept out of algo_positions (migration 1118: "to
    # avoid circuit breaker conflicts" - it may be a deliberate manual/external holding the
    # operator does not want the algo's signal-driven exit logic touching). The fix attaches a
    # standalone (non-bracket) broker-side protective stop directly to the position - real
    # downside protection without enrolling it in algo-managed targets/Minervini-break/etc
    # exits. Reuses imported_position_default_stop_loss_pct as the stop distance below current
    # price. Defaults true (protect capital by default) but is an explicit off-switch for an
    # operator who has a specific, deliberately-unprotected manual holding at the same broker
    # account this system trades from.
    "untracked_position_auto_protective_stop_enabled": (
        "true",
        "bool",
        "Auto-submit a standalone protective stop-loss for orphaned broker positions "
        "(detected at Alpaca, not in algo_positions). Does NOT enroll the position in "
        "algo-managed exits - only attaches downside protection. Set false to disable.",
        "Exit Rules",
    ),
    "imported_position_default_target_1_pct": (
        "5.0",
        "float",
        "Default target 1 % for imported positions",
        "Exit Rules",
    ),
    "imported_position_default_target_2_pct": (
        "10.0",
        "float",
        "Default target 2 % for imported positions",
        "Exit Rules",
    ),
    "imported_position_default_target_3_pct": (
        "15.0",
        "float",
        "Default target 3 % for imported positions",
        "Exit Rules",
    ),
    "min_hold_days": ("1", "int", "Minimum days to hold", "Exit Rules"),
    "max_hold_days": ("20", "int", "Max days to hold position", "Exit Strategy"),
    "exit_on_distribution_day": ("true", "bool", "Exit on market distribution", "Exit Strategy"),
    # REMOVED 2026-08-05: exit_on_minervini_break - disabled after testing showed 0% win rate (0/4 trades)
    # Analysis: Thresholds (1% below SMA-50, 15% volume spike) too aggressive, exited good positions on false breakdowns
    # Reference: commit c4f2d6b51, investigation shows -7.55% avg loss when enabled
    "exit_on_rs_line_break_50dma": (
        "true",
        "bool",
        "Exit when RS line breaks 50-DMA",
        "Exit Rules",
    ),
    "exit_on_td_sequential": (
        "true",
        "bool",
        "Exit on TD Sequential 9/13 exhaustion",
        "Exit Rules",
    ),
    "use_chandelier_trail": ("true", "bool", "Use chandelier ATR trailing stop", "Exit Rules"),
    "switch_to_21ema_after_days": (
        "10",
        "int",
        "Days before switching chandelier to 21-EMA",
        "Exit Rules",
    ),
    "eight_week_rule_threshold_pct": (
        "20.0",
        "float",
        "ONeill 8-week hold threshold %",
        "Exit Rules",
    ),
    "eight_week_rule_window_days": ("21", "int", "Days to check for 20%+ gain", "Exit Rules"),
    "chandelier_atr_mult": ("3.0", "float", "ATR multiplier for chandelier stop", "Exit Strategy"),
    "move_be_at_r": ("1.0", "float", "R-multiple to trigger breakeven stop raise", "Exit Strategy"),
    "exit_limit_slippage_buffer_bps": (
        "50.0",
        "float",
        "Marketable-limit buffer (bps below exit_price) for non-urgent exits",
        "Exit Strategy",
    ),
    "max_extension_above_50ma_pct": (
        "15.0",
        "float",
        "Max extension above 50-DMA %",
        "Advanced Filters",
    ),
    "strong_sector_top_n": ("5", "int", "Top N sectors count as strong", "Advanced Filters"),
    "require_strong_sector": (
        "false",
        "bool",
        "Require market sector to be strong before entering",
        "Advanced Filters",
    ),
    "phase1_min_symbol_count": (
        "5000",
        "int",
        "Phase 1: Minimum symbol count for healthy coverage",
        "Advanced Filters",
    ),
    "phase1_recent_cutoff_days": (
        "2",
        "int",
        "Phase 1: lookback window (days) for 'recent' symbol coverage count",
        "Advanced Filters",
    ),
    "phase1_prior_cutoff_days": (
        "2",
        "int",
        "Phase 1: additional lookback window (days) for the prior-period coverage baseline",
        "Advanced Filters",
    ),
    "phase1_halt_table_max_tolerance_days": (
        "1",
        "int",
        "Phase 1: max days a halt-critical table may lag before halting",
        "Advanced Filters",
    ),
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
    # Advanced Filters Feature Flag
    "enable_advanced_filters": ("false", "bool", "Enable advanced signal filters", "Advanced Filters"),
    # Exit Strategy Configuration
    "exit_on_minervini_break": (
        "false",
        "bool",
        "Exit on Minervini trend template break (disabled - 0% win rate from testing)",
        "Exit Strategy",
    ),
}
