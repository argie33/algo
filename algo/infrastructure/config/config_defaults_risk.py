"""AlgoConfig.DEFAULTS entries for risk sizing, drawdown/circuit-breaker defense, exposure and liquidity.

Part of the AlgoConfig.DEFAULTS dict, split by domain out of
algo/infrastructure/config/main.py (2026-09-05) to keep that file focused on
runtime config logic. Pure data, no behavior changed. Reassembled in main.py as
{**CONFIG_DEFAULTS_RISK, **CONFIG_DEFAULTS_SIGNALS, **CONFIG_DEFAULTS_MARKET,
**CONFIG_DEFAULTS_DATA_QUALITY, **CONFIG_DEFAULTS_SYSTEM}.
"""

from typing import Any

CONFIG_DEFAULTS_RISK: dict[str, tuple[Any, ...]] = {
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
    "max_total_invested_pct": (
        "95.0",
        "float",
        "Max % of portfolio in open positions",
        "Risk Management",
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
    # REAL-MONEY-READINESS FINDING (2026-09-06 audit): min_days_before_reentry_same_symbol
    # above is a pure flip-flop-prevention reset period (5 days) with no tax awareness at
    # all - a stop-out at a LOSS followed by a re-entry into the same symbol 6-29 days later
    # (which the 5-day reset already permits) systematically triggers the IRS wash-sale rule
    # (30-day window before/after a loss sale), disallowing that loss for tax purposes in a
    # taxable account. Wash sale only applies to LOSSES, not gains, so this is a SEPARATE,
    # longer cooldown applied only on top of the existing reset period when the prior
    # stop-out/time-exit closed at a loss (see trade_validator.py's check_reentry_rules) -
    # a profitable stop-out (e.g. a trailing stop) still only waits the shorter 5-day reset.
    # 31 = the IRS's 30-calendar-day window + 1 day buffer.
    "wash_sale_cooldown_days": (
        "31",
        "int",
        "Days to wait before re-entering a symbol after a LOSS exit (IRS wash-sale rule: 30-day window + 1 day buffer). Only applies to loss exits, not profitable ones.",
        "Position Monitoring",
    ),
    "reentry_cooldown_minutes": (
        "30",
        "int",
        "Minutes to wait after close before re-entering same symbol (flip-flop prevention)",
        "Position Monitoring",
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
    "min_adv_shares": ("50000", "int", "Minimum average daily volume (shares)", "Liquidity Requirements"),
    "min_adv_dollars": ("500000", "float", "Minimum average daily dollar volume", "Liquidity Requirements"),
    "min_order_size_dollars": ("100.0", "float", "Minimum order size in dollars", "Liquidity Requirements"),
    "phase1_min_coverage_pct": ("75", "int", "Phase 1: Minimum data coverage %", "Liquidity Requirements"),
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
    # Portfolio Variance Threshold
    "portfolio_variance_threshold": (
        "0.15",
        "float",
        "Portfolio variance threshold to trigger CB circuit breaker",
        "Risk Metrics",
    ),
    "max_risk_per_trade_pct": ("18.0", "float", "Maximum risk per trade %", "Risk Management"),
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
    # Pyramiding Configuration - REAL-MONEY-READINESS FINDING (2026-09-05): pyramid_enabled
    # was previously seeded/defaulted "true" but is dead config - grepped the entire trading
    # codebase (not just this file) for pyramid_enabled/pyramid_add_1_gain_pct/
    # pyramid_add_2_gain_pct/pyramid_split_pct: zero references anywhere outside
    # config_defaults/config_schema/migrations. There is no code path that reads these
    # values to actually split an entry into multiple tranches - pretrade_checks.py
    # hard-blocks any new entry order for a symbol that already has an open position, so
    # multi-entry pyramiding cannot fire through the current entry path even in principle.
    # An operator seeing pyramid_enabled=true in config would reasonably (and wrongly)
    # believe multi-tranche position stacking is active and governed by these thresholds.
    # Defaulted to "false" and labeled "NOT IMPLEMENTED" so the config stops asserting a
    # capability that doesn't exist - fix if pyramiding is ever actually wired up, or
    # remove these four keys entirely. NOTE: migrations 005/018 seed the LIVE algo_config
    # DB with pyramid_enabled="true" - this code-default change does not retroactively fix
    # already-seeded rows; that needs a separate one-time data migration/UPDATE.
    "pyramid_enabled": (
        "false",
        "bool",
        "NOT IMPLEMENTED - enable multi-entry pyramiding (no code path currently reads this)",
        "Position Management",
    ),
    "pyramid_add_1_gain_pct": (
        "2.0",
        "float",
        "NOT IMPLEMENTED - gain threshold for first add (pyramiding)",
        "Position Management",
    ),
    "pyramid_add_2_gain_pct": (
        "4.0",
        "float",
        "NOT IMPLEMENTED - gain threshold for second add (pyramiding)",
        "Position Management",
    ),
    "pyramid_split_pct": (
        "50.0",
        "float",
        "NOT IMPLEMENTED - split position % per add (pyramiding)",
        "Position Management",
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
}
