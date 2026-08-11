"""Unit tests for ExitHandler's exit-rule classification.

algo_exit_rules_distribution's schema (exit_rule/exit_reason/pnl/r_multiple) was added by
migration but nothing ever wrote to it - the table sat permanently empty, which made
lambda/api/routes/risk_dashboard.py's comprehensive risk dashboard 503 unconditionally.
_classify_exit_rule buckets exit_engine.py's real free-text exit reasons into a stable
category so the new write path (executor_exit_handler.py's real-fill exit branch) can
populate the exit_rule column without guessing at exit_engine.py's exact wording.
"""

from algo.trading.executor_exit_handler import ExitHandler


class TestClassifyExitRule:
    def test_stop_loss(self):
        assert ExitHandler._classify_exit_rule("STOP hit: $95.00 <= $95.00") == "stop_loss"

    def test_trend_break(self):
        assert ExitHandler._classify_exit_rule("Minervini trend break: closed below key MA on volume") == "trend_break"

    def test_relative_strength_break(self):
        assert (
            ExitHandler._classify_exit_rule("RS line broke below 50-DMA  - relative strength deterioration")
            == "relative_strength_break"
        )

    def test_time_exit(self):
        assert ExitHandler._classify_exit_rule("TIME exit: 30 days >= 30 max") == "time_exit"

    def test_profit_targets_are_distinguished(self):
        assert ExitHandler._classify_exit_rule("T1 exit: $150.00 >= $150.00 (1.5R)") == "profit_target_t1"
        assert ExitHandler._classify_exit_rule("T2 exit: $160.00 >= $160.00 (3R)") == "profit_target_t2"
        assert (
            ExitHandler._classify_exit_rule("T3 target hit: $170.00 >= $170.00 (4R) - FINAL EXIT") == "profit_target_t3"
        )

    def test_trailing_stop(self):
        assert ExitHandler._classify_exit_rule("Chandelier/EMA trail tightens stop to $140.00") == "trailing_stop"

    def test_td_exhaustion_matches_both_combo_and_sequential(self):
        assert ExitHandler._classify_exit_rule("TD Combo 13-count exhaustion (FULL EXIT, R=2.10)") == "td_exhaustion"
        assert ExitHandler._classify_exit_rule("TD Sequential 9-count exhaustion (R=1.80)") == "td_exhaustion"

    def test_first_red_day(self):
        assert ExitHandler._classify_exit_rule("First Red Day: down 4.20% on heavy volume (R=1.50)") == "first_red_day"

    def test_climax_exhaustion(self):
        assert (
            ExitHandler._classify_exit_rule("Climax run exhaustion: gained 28.0% in last 10d (R=3.00)")
            == "climax_exhaustion"
        )

    def test_distribution_days(self):
        assert (
            ExitHandler._classify_exit_rule(
                "Market distribution: 6 dist days > 5  - reducing 50%, stop raised to breakeven"
            )
            == "distribution_days"
        )

    def test_min_holding_period(self):
        assert (
            ExitHandler._classify_exit_rule("Minimum holding period not met: 1 days held < 3 required")
            == "min_holding_period"
        )

    def test_unrecognized_reason_falls_back_to_other(self):
        """Manual/API-triggered exits won't match exit_engine.py's known reason strings -
        must not raise or mis-bucket, must fall back to the informative "other" category."""
        assert ExitHandler._classify_exit_rule("Manual exit via admin API") == "other"
        assert ExitHandler._classify_exit_rule("") == "other"
