"""AlgoConfig.DEFAULTS entries for market condition and macroeconomic/earnings stress gates.

Part of the AlgoConfig.DEFAULTS dict, split by domain out of
algo/infrastructure/config/main.py (2026-09-05) to keep that file focused on
runtime config logic. Pure data, no behavior changed. Reassembled in main.py as
{**CONFIG_DEFAULTS_RISK, **CONFIG_DEFAULTS_SIGNALS, **CONFIG_DEFAULTS_MARKET,
**CONFIG_DEFAULTS_DATA_QUALITY, **CONFIG_DEFAULTS_SYSTEM}.
"""

from typing import Any

CONFIG_DEFAULTS_MARKET: dict[str, tuple[Any, ...]] = {
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
    # Advanced Filters
    "block_days_before_earnings": (
        "5",
        "int",
        "Block entries N days before earnings",
        "Economic & Earnings",
    ),
}
