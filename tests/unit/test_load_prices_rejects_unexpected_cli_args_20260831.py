#!/usr/bin/env python3
"""Regression test: load_prices.py's main() must reject unexpected CLI arguments instead of
silently falling through to a full, unscoped production run.

BUG FOUND (goal session, real-money-readiness "check the logs" audit): load_prices.py has no
argparse - it's deliberately env-var-only ("no CLI args, cleaner for containerized execution").
But with no argument parser, ANY CLI argument (a typo, or the natural instinct to try
`--help`/`--symbols X` the way load_financial_statements.py/load_stock_scores.py support) was
silently ignored - the script just fell straight through to a full, unscoped ~5000-symbol
production run instead of erroring. Live-reproduced: `python -m loaders.load_prices --help`
acquired the real stock_prices_daily loader lock and started loading all symbols before it was
caught and stopped.

Fixed with an explicit `if len(sys.argv) > 1: ... return 1` guard at the top of main(), before
any of the heavy setup (DB connections, socket timeouts, lock acquisition) runs - preserves the
intentional env-var-only design (no new argparse) while failing loud instead of silently
running unscoped.
"""

import sys
from unittest.mock import patch

from loaders.load_prices import main


class TestLoadPricesRejectsUnexpectedCliArgs:
    def test_help_flag_returns_error_without_starting_a_run(self):
        with patch.object(sys, "argv", ["load_prices.py", "--help"]):
            result = main()
        assert result == 1, "an unexpected CLI arg must return exit code 1, not proceed"

    def test_symbols_flag_returns_error_not_silently_ignored(self):
        # --symbols is NOT supported here (unlike other loaders) - LOADER_SYMBOLS env var is
        # the only scoping mechanism. Passing --symbols must error, not silently run unscoped.
        with patch.object(sys, "argv", ["load_prices.py", "--symbols", "AAPL,MSFT"]):
            result = main()
        assert result == 1

    def test_no_args_still_proceeds_past_the_guard(self):
        # Sanity check the guard doesn't false-positive on the normal, zero-arg invocation -
        # only asserts execution gets past the argv check itself (mocks the next real step so
        # this stays a narrow unit test, not an integration test of the whole loader).
        with (
            patch.object(sys, "argv", ["load_prices.py"]),
            patch("loaders.load_prices.time.time", side_effect=RuntimeError("reached past the argv guard")),
        ):
            try:
                main()
                raise AssertionError("expected the mocked time.time() to raise")
            except RuntimeError as e:
                assert "reached past the argv guard" in str(e), (
                    "zero CLI args must proceed past the guard into the real main() body"
                )
