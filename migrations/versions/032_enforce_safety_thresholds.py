#!/usr/bin/env python3
"""
Migration 032: Enforce Safety Thresholds and Entry Quality Gates

This migration ensures critical safety features are enabled with proper thresholds:

1. Entry Quality Gates (Hard Guards):
   - rs_slope_gate_enabled: false (warn-only, not hard-gate — consolidating bases show flat RS)
   - volume_decay_gate_enabled: false (warn-only, not hard-gate — accumulation shows declining volume)
   - Note: These are intentionally set to warn-only (false) per migration-007 to allow legitimate
     Minervini setups through while still logging concerns for review.

2. Quality Score Thresholds (Hard Gates):
   - min_signal_quality_score: 60 (0-100 scale, signal quality gate)
   - min_swing_score: 55.0 (regime manager may raise higher)
   - min_completeness_score: 70 (data completeness %, Minervini standard)
   - These ensure we only trade high-quality signals, preventing low-quality entries.

3. Earnings Blackout (Hard Gate):
   - earnings_blackout_days_before: 7 (block entries 7 days pre-earnings)
   - earnings_blackout_days_after: 3 (block entries 3 days post-earnings)
   - Prevents whipsaws from earnings surprises; critical for gap-risk management.

4. Other Liquidity & Fundamentals:
   - min_volume_ma_50d: 300000 (minimum 50-day average volume)
   - min_avg_daily_dollar_volume: 500000 (minimum daily dollar volume)
   - min_price_history_days: 200 (avoid IPO stocks <1yr post-IPO, per Minervini)
   - max_short_interest_pct: 30.0 (avoid heavily shorted stocks)

These thresholds prevent the system from trading any stock regardless of quality,
which is the core risk: weak signals + missing earnings data = blown stops.
"""

from migrations.migration_helper import DatabaseContext


DESCRIPTION = "Enforce safety thresholds for entry quality gates and earnings blackout"

# Safety config values: all thresholds that prevent low-quality trading
_SAFETY_CONFIG = [
    # Entry Quality Gates (warn-only, not hard-gates)
    ("rs_slope_gate_enabled", "false", "bool"),
    ("volume_decay_gate_enabled", "false", "bool"),

    # Quality Score Thresholds (hard gates)
    ("min_signal_quality_score", "60", "int"),
    ("min_swing_score", "55.0", "float"),
    ("min_completeness_score", "70", "int"),

    # Earnings Blackout (hard gate)
    ("earnings_blackout_days_before", "7", "int"),
    ("earnings_blackout_days_after", "3", "int"),

    # Liquidity Thresholds
    ("min_volume_ma_50d", "300000", "int"),
    ("min_avg_daily_dollar_volume", "500000", "float"),
    ("min_daily_volume_shares", "500000", "int"),
    ("min_price_history_days", "200", "int"),

    # Fundamental Filters
    ("max_short_interest_pct", "30.0", "float"),
    ("min_market_cap_millions", "300.0", "float"),
    ("min_float_millions", "50.0", "float"),
    ("max_spread_pct", "0.5", "float"),
]


def up():
    """Enforce all safety thresholds to prevent weak-signal trading."""
    with DatabaseContext("write") as cur:
        for key, value, value_type in _SAFETY_CONFIG:
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, updated_by)
                VALUES (%s, %s, %s, 'migration-032')
                ON CONFLICT (key) DO UPDATE SET
                    value = %s,
                    updated_by = 'migration-032',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, value_type, value),
            )


def down():
    """Rollback: no changes needed (restoration is manual)."""
