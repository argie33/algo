"""Regression: the market-close polling loop's attempt cap must scale with max_wait_sec.

Bug: max_attempts was a fixed 60 (60 checks x 3s wait = 180s), independent of
max_wait_sec. algo_config seeds yfinance_market_close_timeout_eod_sec=1800 and
_morning_sec=600 (migration 111) specifically to tolerate yfinance's documented
5-15 min EOD lag - but the fixed 180s attempt cap always fired first, raising
RuntimeError("Max attempts (60) reached") minutes before the configured budget
was exhausted, on every ordinary "still lagging, no errors yet" run.
"""

from loaders.load_prices import PriceLoader


class TestMarketCloseMaxAttemptsScalesWithTimeout:
    def test_eod_timeout_gets_enough_attempts_to_use_full_budget(self):
        wait_between_checks = 3
        max_wait_sec = 1800  # seeded yfinance_market_close_timeout_eod_sec

        max_attempts = PriceLoader._compute_market_close_max_attempts(max_wait_sec, wait_between_checks)

        # Pre-fix this was hardcoded to 60, capping real wait time at ~180s - a tiny
        # fraction of the configured 1800s. The cap must not bind before the time budget.
        assert max_attempts * wait_between_checks >= max_wait_sec

    def test_morning_timeout_gets_enough_attempts_to_use_full_budget(self):
        wait_between_checks = 3
        max_wait_sec = 600  # seeded yfinance_market_close_timeout_morning_sec

        max_attempts = PriceLoader._compute_market_close_max_attempts(max_wait_sec, wait_between_checks)

        assert max_attempts * wait_between_checks >= max_wait_sec

    def test_short_override_timeout_keeps_a_sane_floor(self):
        # A short override (e.g. a test or manual call) shouldn't get an attempt cap
        # so small it can't even ride out a couple of slow checks.
        max_attempts = PriceLoader._compute_market_close_max_attempts(30, 3)

        assert max_attempts >= 60

    def test_prefix_fixed_cap_would_have_failed_this_regression(self):
        """Documents the exact pre-fix behavior this test guards against."""
        pre_fix_fixed_max_attempts = 60
        wait_between_checks = 3
        eod_max_wait_sec = 1800

        # Pre-fix: 60 * 3 = 180s, nowhere near the configured 1800s budget.
        assert pre_fix_fixed_max_attempts * wait_between_checks < eod_max_wait_sec

        # Post-fix: the real cap comfortably covers the configured budget.
        fixed_max_attempts = PriceLoader._compute_market_close_max_attempts(eod_max_wait_sec, wait_between_checks)
        assert fixed_max_attempts * wait_between_checks >= eod_max_wait_sec
