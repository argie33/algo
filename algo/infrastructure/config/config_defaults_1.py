"""First half of AlgoConfig.DEFAULTS, extracted from algo/infrastructure/config/main.py
(2026-09-05, file-size ratchet: that file is a Tier-2 bloater flagged for decomposition).
Pure data, no logic changed - split across two files (see config_defaults_2.py for the
second half) to stay under the 800-line new-file cap. AlgoConfig.DEFAULTS itself is
reassembled as {**CONFIG_DEFAULTS_1, **CONFIG_DEFAULTS_2} in main.py.
"""

from typing import Any

CONFIG_DEFAULTS_1: dict[str, tuple[Any, ...]] = {
    # Risk Management
    "base_risk_pct": (
        "0.75",
        "float",
        "Base portfolio risk per trade",
        "Risk Management",
    ),
    "max_position_size_pct": (
        "6.3",
        "float",
        "Maximum single position size",
        "Risk Management",
    ),
    "max_positions": (
        "15",
        "int",
        "Maximum concurrent positions",
        "Risk Management",
    ),
    "max_concentration_pct": (
        "50.0",
        "float",
        "Max concentration in top position",
        "Risk Management",
    ),
    # Drawdown Defense
    "halt_drawdown_pct": (
        "-20.0",
        "float",
        "Portfolio drawdown % to halt trading (CB1)",
        "Drawdown Defense",
    ),
    "risk_reduction_at_minus_5": (
        "0.75",
        "float",
        "Risk % at -5% drawdown",
        "Drawdown Defense",
    ),
    "risk_reduction_at_minus_10": (
        "0.5",
        "float",
        "Risk % at -10% drawdown",
        "Drawdown Defense",
    ),
    "risk_reduction_at_minus_15": (
        "0.25",
        "float",
        "Risk % at -15% drawdown",
        "Drawdown Defense",
    ),
    "risk_reduction_at_minus_20": (
        "0.0",
        "float",
        "Risk % at -20% drawdown (halt)",
        "Drawdown Defense",
    ),
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
        "2.0",
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
    "max_total_invested_pct": (
        "95.0",
        "float",
        "Max % of portfolio in open positions",
        "Risk Management",
    ),
    # Market Conditions
    "max_distribution_days": ("4", "int", "Max market distribution days", "Market Conditions"),
    "require_stage_2_market": (
        "false",
        "bool",
        "Require market Stage 2 at Tier 2 (CB6 blocks Stage 4; weinstein check managed)",
        "Market Conditions",
    ),
    "vix_max_threshold": ("35.0", "float", "VIX level to halt trading", "Market Conditions"),
    "vix_alert_threshold": (
        "30.0",
        "float",
        "VIX level to trigger RED alert (dashboard display)",
        "Market Conditions",
    ),
    "vix_caution_threshold": ("25.0", "float", "VIX level to reduce positions", "Market Conditions"),
    "vix_caution_risk_reduction": (
        "0.75",
        "float",
        "Risk multiplier when VIX > caution threshold",
        "Market Conditions",
    ),
    # Market Exposure Engine  - Veto Thresholds (H12)
    "market_exposure_veto1_breadth_pct": (
        "30",
        "int",
        "Breadth threshold for veto 1: SPY < 30wk MA AND breadth < N%",
        "Market Exposure",
    ),
    "market_exposure_veto1_cap_pct": (
        "25.0",
        "float",
        "Exposure cap % when veto 1 triggered (SPY < 30wk MA AND weak breadth)",
        "Market Exposure",
    ),
    "market_exposure_veto2_vix_threshold": (
        "40.0",
        "float",
        "VIX threshold for veto 2: VIX > N and rising",
        "Market Exposure",
    ),
    "market_exposure_veto2_cap_pct": (
        "30.0",
        "float",
        "Exposure cap % when veto 2 triggered (VIX > 40 rising)",
        "Market Exposure",
    ),
    "market_exposure_veto3_distribution_days_threshold": (
        "9",
        "int",
        "Distribution days threshold for veto 3 (9+ days)",
        "Market Exposure",
    ),
    "market_exposure_veto3_cap_pct": (
        "35.0",
        "float",
        "Exposure cap % when veto 3 triggered (6+ distribution days)",
        "Market Exposure",
    ),
    "market_exposure_veto4_cap_pct": (
        "40.0",
        "float",
        "Exposure cap % when veto 4 triggered (no FTD while SPY below 30wk MA)",
        "Market Exposure",
    ),
    "market_exposure_veto5_credit_spread_threshold": (
        "8.5",
        "float",
        "Credit spread threshold for veto 5 (systemic stress)",
        "Market Exposure",
    ),
    "market_exposure_veto5_cap_pct": (
        "30.0",
        "float",
        "Exposure cap % when veto 5 triggered (HY spread > 8.5%)",
        "Market Exposure",
    ),
    # Economic Regime Stress Scores (H12)
    "econ_stress_curve_inverted_severe": (
        "35.0",
        "float",
        "Stress score for severe yield curve inversion (<-0.5% for 8+ weeks)",
        "Economic Stress",
    ),
    "econ_stress_curve_inverted_moderate": (
        "20.0",
        "float",
        "Stress score for moderate yield curve inversion (<0%)",
        "Economic Stress",
    ),
    "econ_stress_curve_flat": (
        "8.0",
        "float",
        "Stress score for flat yield curve (<0.2%)",
        "Economic Stress",
    ),
    "econ_stress_hy_spread_severe": (
        "35.0",
        "float",
        "Stress score for severe HY credit spread (>6.5%)",
        "Economic Stress",
    ),
    "econ_stress_hy_spread_elevated": (
        "20.0",
        "float",
        "Stress score for elevated HY credit spread (>5.0%)",
        "Economic Stress",
    ),
    "econ_stress_hy_widening": (
        "15.0",
        "float",
        "Stress score for HY spread widening (>1.5pp in 60d)",
        "Economic Stress",
    ),
    "econ_stress_claims_severe": (
        "30.0",
        "float",
        "Stress score for severe jobless claims (>30% in 26w)",
        "Economic Stress",
    ),
    "econ_stress_claims_elevated": (
        "15.0",
        "float",
        "Stress score for elevated jobless claims (>20% in 26w)",
        "Economic Stress",
    ),
    "econ_stress_financial_severe": (
        "25.0",
        "float",
        "Stress score for severe financial stress (>1.5Ïƒ)",
        "Economic Stress",
    ),
    "econ_stress_financial_elevated": (
        "12.0",
        "float",
        "Stress score for elevated financial stress (>0.8Ïƒ)",
        "Economic Stress",
    ),
    "econ_stress_moderate_threshold": (
        "40",
        "int",
        "Stress level for moderate economic regime penalty (4 pts, no cap)",
        "Economic Stress",
    ),
    "econ_stress_severe_threshold": (
        "60",
        "int",
        "Stress level for severe economic regime penalty (7 pts, cap at 40%)",
        "Economic Stress",
    ),
    "econ_stress_severe_cap_pct": (
        "40.0",
        "float",
        "Exposure cap % at severe economic stress (stress >= 60)",
        "Economic Stress",
    ),
    "put_call_bullish_threshold": (
        "0.8",
        "float",
        "Put/Call ratio bullish threshold (<= for bullish)",
        "Market Conditions",
    ),
    "put_call_fearful_threshold": (
        "1.0",
        "float",
        "Put/Call ratio fearful threshold (>= for fearful)",
        "Market Conditions",
    ),
    "upvol_good_threshold": (
        "60.0",
        "float",
        "Up volume % threshold for good market (>= for GREEN)",
        "Market Conditions",
    ),
    "upvol_caution_threshold": (
        "50.0",
        "float",
        "Up volume % threshold for caution (>= for YELLOW)",
        "Market Conditions",
    ),
    "breadth_good_threshold": (
        "50",
        "int",
        "NH-NL difference threshold for good breadth (>= for GREEN)",
        "Market Conditions",
    ),
    "breadth_caution_threshold": (
        "0",
        "int",
        "NH-NL difference threshold for caution (>= for YELLOW)",
        "Market Conditions",
    ),
    "yield_curve_good_threshold": (
        "0.5",
        "float",
        "Yield curve slope for bullish signal (>= for GREEN)",
        "Market Conditions",
    ),
    "beta_warning_threshold": (
        "1.2",
        "float",
        "Portfolio beta threshold for caution (>= for WARNING)",
        "Market Conditions",
    ),
    "beta_caution_threshold": (
        "0.8",
        "float",
        "Portfolio beta threshold for bullish (>= for YELLOW)",
        "Market Conditions",
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
    # Drawdown Re-engagement (Sprint 3)
    "re_engage_recovery_pct": (
        "8.0",
        "float",
        "% recovery from peak to resume trading",
        "Drawdown Defense",
    ),
    "re_engage_min_days": ("5", "int", "Min days after halt before re-engagement", "Drawdown Defense"),
    "require_ftd_to_re_engage": (
        "true",
        "bool",
        "Require Follow-Through Day signal",
        "Drawdown Defense",
    ),
    # Re-engagement lockouts (Sprint 3 generalization, 2026-09-04): minimum elapsed
    # trading days after a VIX/daily-loss/weekly-loss/total-risk halt before the
    # breaker may clear, mirroring drawdown's re_engage_min_days above. Shorter than
    # drawdown's 5 days (a deep-drawdown capital-preservation event warrants the
    # longest lockout) but long enough that a same-day metric recovery can't
    # immediately re-clear a halt within the same trading session. daily_loss/
    # total_risk move on an intraday timescale (a single extra session is enough to
    # prevent same-day flap); vix_spike/weekly_loss track slower, noisier multi-day
    # conditions and get one extra day of margin.
    "vix_spike_min_reengagement_days": (
        "3",
        "int",
        "Min trading days after a VIX-spike halt before re-engagement",
        "Drawdown Defense",
    ),
    "daily_loss_min_reengagement_days": (
        "2",
        "int",
        "Min trading days after a daily-loss halt before re-engagement",
        "Drawdown Defense",
    ),
    "weekly_loss_min_reengagement_days": (
        "3",
        "int",
        "Min trading days after a weekly-loss halt before re-engagement",
        "Drawdown Defense",
    ),
    "total_risk_min_reengagement_days": (
        "2",
        "int",
        "Min trading days after a total-open-risk halt before re-engagement",
        "Drawdown Defense",
    ),
    # Circuit Breaker Thresholds (CB)
    "max_daily_loss_pct": ("2.0", "float", "Max daily loss % before halt", "Risk Management"),
    "max_consecutive_losses": ("3", "int", "Max consecutive losing trades (live)", "Risk Limits"),
    "paper_mode_max_consecutive_losses": ("5", "int", "Max consecutive losing trades (paper mode)", "Risk Limits"),
    "min_win_rate_pct": ("40.0", "float", "Min win rate % to trade", "Risk Limits"),
    "min_live_sharpe_ratio": (
        "0.0",
        "float",
        "Min acceptable live Sharpe ratio (halt if lower in auto mode)",
        "Risk Limits",
    ),
    "max_total_risk_pct": ("4.0", "float", "Max total open risk %", "Risk Limits"),
    "min_risk_pct_floor": (
        "0.10",
        "float",
        "Minimum risk % floor when safety multipliers reduce position size",
        "Risk Management",
    ),
    "max_weekly_loss_pct": ("5.0", "float", "Max weekly loss % before halt", "Risk Management"),
    "max_data_staleness_days": ("3", "int", "Max data age in days", "Data Quality"),
    "daily_profit_cap_pct": ("2.0", "float", "Daily profit cap %", "Position Sizing"),
    "sector_drawdown_halt_pct": (
        "-12.0",
        "float",
        "Sector drawdown % to halt trading",
        "Drawdown Defense",
    ),
    # Position Monitoring & Re-entry
    "position_halt_flag_count": ("2", "int", "Flags to propose early exit", "Position Monitoring"),
    "max_reentries_per_name": ("2", "int", "Max times to re-enter same symbol", "Position Sizing"),
    "min_days_before_reentry_same_symbol": (
        "5",
        "int",
        "Days to wait before re-entering symbol",
        "Position Monitoring",
    ),
    "reentry_cooldown_minutes": (
        "30",
        "int",
        "Minutes to wait after close before re-entering same symbol (flip-flop prevention)",
        "Position Monitoring",
    ),
    # Economic Calendar
    "halt_entries_before_major_release_minutes": (
        "60",
        "int",
        "Halt entries N minutes before major release",
        "Economic & Earnings",
    ),
    # Earnings Blackout
    "earnings_blackout_days_before": (
        "7",
        "int",
        "Days before earnings to block entries",
        "Economic & Earnings",
    ),
    "earnings_blackout_days_after": (
        "3",
        "int",
        "Days after earnings to block entries",
        "Economic & Earnings",
    ),
    "min_price_history_days": (
        "200",
        "int",
        "Min trading days of price history (IPO age gate - Minervini avoids stocks <1yr post-IPO)",
        "Liquidity Requirements",
    ),
    "min_daily_volume_shares": ("500000", "int", "Minimum daily volume shares", "Liquidity Requirements"),
    "max_spread_pct": ("0.5", "float", "Maximum bid-ask spread %", "Liquidity Requirements"),
    "min_market_cap_millions": ("300.0", "float", "Minimum market cap $M", "Liquidity Requirements"),
    "min_float_millions": ("50.0", "float", "Minimum float shares $M", "Liquidity Requirements"),
    "max_short_interest_pct": ("30.0", "float", "Maximum short interest %", "Liquidity Requirements"),
    # Advanced Filters
    "block_days_before_earnings": (
        "5",
        "int",
        "Block entries N days before earnings",
        "Economic & Earnings",
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
    "min_adv_shares": ("50000", "int", "Minimum average daily volume (shares)", "Liquidity Requirements"),
    "min_adv_dollars": ("500000", "float", "Minimum average daily dollar volume", "Liquidity Requirements"),
    "min_order_size_dollars": ("100.0", "float", "Minimum order size in dollars", "Liquidity Requirements"),
    "phase1_min_coverage_pct": ("75", "int", "Phase 1: Minimum data coverage %", "Liquidity Requirements"),
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
}
