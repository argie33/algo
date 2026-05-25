#!/usr/bin/env python3
"""
Validate that algo configuration is appropriate for real-money trading.

Checks against best practices and catches dangerous combinations.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.algo_config import get_config
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class ConfigValidator:
    def __init__(self):
        self.config = get_config()
        self.errors = []
        self.warnings = []
        self.info = []

    def validate(self):
        """Run all validation checks."""
        self.check_risk_parameters()
        self.check_stop_loss_config()
        self.check_entry_filters()
        self.check_exit_rules()
        self.check_circuit_breakers()
        self.check_portfolio_limits()

    def check_risk_parameters(self):
        """Risk management fundamentals."""
        base_risk = float(self.config.get('base_risk_pct', 0.75))
        max_positions = int(self.config.get('max_positions', 12))
        max_daily_loss = float(self.config.get('max_daily_loss_pct', 2.0))

        # Base risk per trade should be 0.5-1.5%
        if base_risk < 0.25:
            self.errors.append(f"base_risk_pct too low ({base_risk}%): minimum 0.25% for meaningful trades")
        elif base_risk > 2.0:
            self.warnings.append(f"base_risk_pct high ({base_risk}%): recommend <= 1.5% for stability")
        else:
            self.info.append(f"[OK] base_risk_pct = {base_risk}% (good for real money)")

        # Max positions
        if max_positions < 1:
            self.errors.append("max_positions < 1 (no trading allowed)")
        elif max_positions > 20:
            self.warnings.append(f"max_positions high ({max_positions}): hard to monitor, recommend <= 12")
        else:
            self.info.append(f"[OK] max_positions = {max_positions} (manageable)")

        # Daily loss
        if max_daily_loss < 1.0:
            self.warnings.append(f"max_daily_loss_pct low ({max_daily_loss}%): may halt too easily")
        elif max_daily_loss > 5.0:
            self.warnings.append(f"max_daily_loss_pct high ({max_daily_loss}%): large daily losses allowed")
        else:
            self.info.append(f"[OK] max_daily_loss_pct = {max_daily_loss}% (conservative)")

    def check_stop_loss_config(self):
        """Stop loss and target configuration."""
        max_stop = float(self.config.get('max_stop_distance_pct', 12.0))
        t1_r = float(self.config.get('t1_target_r_multiple', 1.5))
        t2_r = float(self.config.get('t2_target_r_multiple', 3.0))
        t3_r = float(self.config.get('t3_target_r_multiple', 4.0))

        # Stop distance
        if max_stop < 2:
            self.warnings.append(f"max_stop_distance_pct low ({max_stop}%): may get stopped out on noise")
        elif max_stop > 15:
            self.warnings.append(f"max_stop_distance_pct high ({max_stop}%): too much risk per trade")
        else:
            self.info.append(f"[OK] max_stop_distance_pct = {max_stop}% (reasonable)")

        # Target alignment
        if t1_r >= t2_r or t2_r >= t3_r:
            self.errors.append(f"Target R-multiples not ascending: T1={t1_r}, T2={t2_r}, T3={t3_r}")
        else:
            self.info.append(f"[OK] Targets ascending: T1={t1_r}R, T2={t2_r}R, T3={t3_r}R")

        # Reward/risk ratio
        min_reward_risk_ratio = t1_r  # Risk 1 to make 1.5+
        if min_reward_risk_ratio < 1.0:
            self.errors.append(f"Minimum reward/risk ratio too low ({min_reward_risk_ratio}): lose more than you make")

    def check_entry_filters(self):
        """Entry signal quality."""
        min_trend_score = int(self.config.get('min_trend_template_score', 8))
        min_swing_score = float(self.config.get('min_swing_score', 55.0))
        min_sqs = int(self.config.get('min_signal_quality_score', 30))
        max_signal_age = int(self.config.get('max_signal_age_days', 3))

        # Trend score
        if min_trend_score > 7:
            self.warnings.append(f"min_trend_template_score high ({min_trend_score}): may reject good setups, recommend 5-6")
        elif min_trend_score < 5:
            self.warnings.append(f"min_trend_template_score low ({min_trend_score}): allowing weaker trends")
        else:
            self.info.append(f"[OK] min_trend_template_score = {min_trend_score} (canonical Minervini standard)")

        # Swing score
        if min_swing_score < 30:
            self.warnings.append(f"min_swing_score too low ({min_swing_score}): allowing many C/D grade setups")
        elif min_swing_score > 70:
            self.warnings.append(f"min_swing_score too high ({min_swing_score}): may be too restrictive, recommend <= 60")
        else:
            self.info.append(f"[OK] min_swing_score = {min_swing_score} (selective)")

        # Signal quality
        if min_sqs < 20:
            self.warnings.append(f"min_signal_quality_score very low ({min_sqs}): accepting poor quality signals")
        elif min_sqs > 70:
            self.warnings.append(f"min_signal_quality_score high ({min_sqs}): may reject all signals")

        # Signal age
        if max_signal_age > 7:
            self.warnings.append(f"max_signal_age_days high ({max_signal_age}): stale signals may be losing momentum")
        else:
            self.info.append(f"[OK] max_signal_age_days = {max_signal_age} (fresh signals only)")

    def check_exit_rules(self):
        """Exit configuration."""
        max_hold = int(self.config.get('max_hold_days', 20))
        min_hold = int(self.config.get('min_hold_days', 1))

        if min_hold < 0:
            self.errors.append("min_hold_days < 0 (invalid)")
        elif min_hold == 0:
            self.warnings.append("min_hold_days = 0: could exit same day (risky)")
        else:
            self.info.append(f"[OK] min_hold_days = {min_hold} (allows quick exits if needed)")

        if max_hold < min_hold:
            self.errors.append(f"max_hold_days ({max_hold}) < min_hold_days ({min_hold})")
        elif max_hold > 60:
            self.warnings.append(f"max_hold_days high ({max_hold}): position left open too long")
        else:
            self.info.append(f"[OK] max_hold_days = {max_hold} (20d typical for swing trading)")

    def check_circuit_breakers(self):
        """Fail-safe kill switches."""
        halt_dd = float(self.config.get('halt_drawdown_pct', 20.0))
        max_dd_15 = float(self.config.get('risk_reduction_at_minus_15', 0.25))
        max_dd_10 = float(self.config.get('risk_reduction_at_minus_10', 0.5))
        vix_halt = float(self.config.get('vix_max_threshold', 35.0))
        vix_caution = float(self.config.get('vix_caution_threshold', 25.0))

        if halt_dd > 30:
            self.warnings.append(f"halt_drawdown_pct high ({halt_dd}%): allows large losses before halting")
        elif halt_dd < 10:
            self.warnings.append(f"halt_drawdown_pct low ({halt_dd}%): may halt too easily on first losing day")
        else:
            self.info.append(f"[OK] halt_drawdown_pct = {halt_dd}% (conservative fail-closed)")

        if max_dd_15 > 0.5:
            self.warnings.append(f"risk_reduction_at_minus_15 high ({max_dd_15}): not enough reduction")
        elif max_dd_15 == 0:
            self.info.append(f"[OK] risk_reduction_at_minus_15 = {max_dd_15} (halt at -15%)")

        if vix_halt < 30:
            self.warnings.append(f"vix_max_threshold low ({vix_halt}): may halt in normal volatility")
        elif vix_halt > 50:
            self.warnings.append(f"vix_max_threshold high ({vix_halt}): allowing extreme volatility")
        else:
            self.info.append(f"[OK] vix_max_threshold = {vix_halt} (VIX > 35 = crisis)")

    def check_portfolio_limits(self):
        """Concentration and leverage limits."""
        max_pos_size = float(self.config.get('max_position_size_pct', 8.0))
        max_sector = int(self.config.get('max_positions_per_sector', 5))
        max_industry = int(self.config.get('max_positions_per_industry', 3))
        max_invested = float(self.config.get('max_total_invested_pct', 95.0))

        if max_pos_size > 15:
            self.warnings.append(f"max_position_size_pct high ({max_pos_size}%): large single position")
        else:
            self.info.append(f"[OK] max_position_size_pct = {max_pos_size}% (diversified)")

        if max_sector > 5:
            self.warnings.append(f"max_positions_per_sector high ({max_sector}): sector concentration risk")
        else:
            self.info.append(f"[OK] max_positions_per_sector = {max_sector} (sector diversification)")

        if max_invested > 90:
            self.warnings.append(f"max_total_invested_pct high ({max_invested}%): limited cash reserve")
        else:
            self.info.append(f"[OK] max_total_invested_pct = {max_invested}% (cash buffer maintained)")

    def report(self):
        """Print validation report."""
        print("\n" + "=" * 80)
        print("PRODUCTION CONFIGURATION VALIDATION")
        print("=" * 80 + "\n")

        if self.errors:
            print("[ERROR] CRITICAL ERRORS (must fix before real money):")
            for err in self.errors:
                print(f"  - {err}")
            print()

        if self.warnings:
            print("[WARNING] WARNINGS (review before deploying):")
            for warn in self.warnings:
                print(f"  - {warn}")
            print()

        if self.info:
            print("[OK] GOOD PRACTICES:")
            for good in self.info:
                print(f"  {good}")
            print()

        print("=" * 80)
        if self.errors:
            print(f"STATUS: NOT READY (fix {len(self.errors)} critical errors)")
            return False
        elif self.warnings:
            print(f"STATUS: REVIEW NEEDED ({len(self.warnings)} warnings)")
            return True
        else:
            print(f"STATUS: READY FOR PRODUCTION")
            return True


if __name__ == '__main__':
    validator = ConfigValidator()
    validator.validate()
    is_ready = validator.report()
    sys.exit(0 if is_ready else 1)
