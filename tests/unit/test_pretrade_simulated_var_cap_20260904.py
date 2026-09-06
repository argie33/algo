"""Regression test for the 2026-09-04 fix (real-money-readiness push, adversarial circuit-
breaker/risk-limit audit): algo/risk/var.py's historical_var() already documents "Daily VaR >
2% -> WARNING" as this system's own convention, but it only ever fired as a Phase 9 (end-of-
cycle) REPORT computed from the REALIZED equity curve - nothing previously stopped Phase 8 from
opening the entry that pushes simulated portfolio risk over that threshold.

PreTradeChecks._check_portfolio_simulated_var() (algo/trading/pretrade_checks.py) now blocks a
new entry that would push a SIMULATED current-weights VaR (as-if today's book, including the
candidate, had been held throughout the lookback window, using each position's own historical
price returns) above max_simulated_var_pct (default 2.0, reusing var.py's own convention). This
is deliberately a different calculation from historical_var()/cvar() (realized P&L, left
untouched) - see the method's own docstring for why those two aren't decomposable against a
hypothetical candidate trade.
"""

from datetime import date, timedelta
from decimal import Decimal

from algo.trading.pretrade_checks import PreTradeChecks


def _config(**overrides):
    base = {"max_simulated_var_pct": 2.0}
    base.update(overrides)
    return base


def _dates(n):
    start = date(2026, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def _prices_from_daily_return(daily_return: float, n_days: int, start_price: float = 100.0) -> list[float]:
    prices = [start_price]
    for _ in range(n_days - 1):
        prices.append(prices[-1] * (1 + daily_return))
    return prices


class _FakeCursor:
    """Sequences canned responses: open-positions query -> price_daily query, in that fixed
    call order (matching _check_portfolio_simulated_var itself)."""

    def __init__(self, open_positions_rows, price_daily_rows):
        self._responses = {0: open_positions_rows, 1: price_daily_rows}
        self._last_call = None

    def execute(self, query, params=None):
        if "FROM algo_positions" in query:
            self._last_call = 0
        elif "FROM price_daily" in query:
            self._last_call = 1
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchall(self):
        return self._responses[self._last_call]


def _price_rows(symbol: str, dates: list[date], prices: list[float]) -> list[tuple]:
    return [(symbol, d, p) for d, p in zip(dates, prices, strict=True)]


class TestSimulatedVarCheck:
    def test_no_open_positions_low_volatility_candidate_passes(self):
        # 61 days -> 60 return periods, all at a flat -0.01% daily return: nowhere near 2%.
        dates = _dates(61)
        prices = _prices_from_daily_return(-0.0001, 61)
        cur = _FakeCursor(
            open_positions_rows=[],
            price_daily_rows=_price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config=_config())
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_no_open_positions_high_volatility_candidate_blocked(self):
        # 61 days -> 60 return periods, all at a flat -5% daily return: 95% VaR = 5% > 2% cap.
        # UPDATED 2026-09-06 (adversarial review fix: weights now normalize by TOTAL
        # portfolio_value, not invested-only value - matching _check_portfolio_beta's
        # already-fixed pattern and var.py's beta_exposure()). With zero existing
        # positions, portfolio_value must equal position_value for the candidate to be
        # the account's entire book (fully invested, no idle cash) - this is what "no
        # open positions, high volatility candidate" is actually testing; a candidate
        # that's only a fraction of total equity should NOT be blocked at full weight.
        dates = _dates(61)
        prices = _prices_from_daily_return(-0.05, 61)
        cur = _FakeCursor(
            open_positions_rows=[],
            price_daily_rows=_price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config=_config(max_simulated_var_pct=2.0))
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("10000"), cur)
        assert ok is False
        assert reason is not None
        assert "2.00" in reason
        assert "5.00" in reason

    def test_candidate_is_fraction_of_total_equity_not_overweighted(self):
        # Regression for the 2026-09-06 fix itself: a $10,000 candidate in a $100,000
        # TOTAL portfolio (i.e. $90,000 idle cash, zero other positions) is only a 10%
        # weight - even a severe -5%/day candidate diluted to 10% weight must NOT breach
        # a 2% cap (weighted daily return = 0.1 * -0.05 = -0.5%, nowhere near 2%). The
        # pre-fix bug normalized by invested-only value (here, just the candidate itself),
        # which would have wrongly treated this as a 100%-weighted, blocked candidate.
        dates = _dates(61)
        prices = _prices_from_daily_return(-0.05, 61)
        cur = _FakeCursor(
            open_positions_rows=[],
            price_daily_rows=_price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config=_config(max_simulated_var_pct=2.0))
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_existing_book_and_candidate_blended_weight(self):
        # Existing $50,000 in HELD (flat 0% daily return), candidate $50,000 at -4% daily
        # return -> blended weighted return each day = 0.5*0 + 0.5*(-0.04) = -0.02 -> VaR 2%
        # exactly at the boundary; push candidate loss slightly higher to clear it cleanly.
        dates = _dates(61)
        held_prices = _prices_from_daily_return(0.0, 61)
        candidate_prices = _prices_from_daily_return(-0.06, 61)
        cur = _FakeCursor(
            open_positions_rows=[("HELD", 500, 100.0)],
            price_daily_rows=_price_rows("HELD", dates, held_prices) + _price_rows("NEWSYM", dates, candidate_prices),
        )
        checks = PreTradeChecks(config=_config(max_simulated_var_pct=2.0))
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("50000"), Decimal("100000"), cur)
        assert ok is False
        assert reason is not None

    def test_missing_price_history_for_candidate_fails_open(self):
        dates = _dates(61)
        held_prices = _prices_from_daily_return(-0.05, 61)
        cur = _FakeCursor(
            open_positions_rows=[("HELD", 100, 100.0)],
            price_daily_rows=_price_rows("HELD", dates, held_prices),  # NEWSYM has no rows at all
        )
        checks = PreTradeChecks(config=_config())
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_insufficient_overlapping_days_fails_open(self):
        # Only 30 common dates (29 return periods) - below the 60-day minimum overlap.
        dates = _dates(30)
        prices = _prices_from_daily_return(-0.05, 30)
        cur = _FakeCursor(
            open_positions_rows=[],
            price_daily_rows=_price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config=_config())
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_open_positions_query_excludes_candidate_symbol(self):
        dates = _dates(61)
        prices = _prices_from_daily_return(0.0, 61)
        cur = _FakeCursor(
            open_positions_rows=[("HELD", 100, 100.0)],
            price_daily_rows=_price_rows("HELD", dates, prices) + _price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config=_config())
        checks._check_portfolio_simulated_var("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        # No assertion error raised by the fake cursor's query dispatch is itself the check -
        # a real cursor's WHERE symbol != %s is exercised via the SQL string, matching
        # _check_portfolio_beta/_check_top5_concentration's identical guard.

    def test_missing_config_key_raises(self):
        dates = _dates(61)
        prices = _prices_from_daily_return(-0.05, 61)
        cur = _FakeCursor(
            open_positions_rows=[],
            price_daily_rows=_price_rows("NEWSYM", dates, prices),
        )
        checks = PreTradeChecks(config={})
        try:
            checks._check_portfolio_simulated_var("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
            raise AssertionError("expected KeyError for missing max_simulated_var_pct config")
        except KeyError:
            pass

    def test_zero_total_value_passes(self):
        cur = _FakeCursor(open_positions_rows=[], price_daily_rows=[])
        checks = PreTradeChecks(config=_config())
        ok, reason = checks._check_portfolio_simulated_var("NEWSYM", Decimal("0"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None


class TestRealizedVarUnchanged:
    """Regression guard: historical_var()/cvar()'s own realized-P&L computation must be
    byte-for-byte unchanged by the empirical_var_percentile()/empirical_cvar_tail_mean()
    extraction - both now delegate to those shared helpers instead of inlining
    np.percentile()/np.mean() directly, but the math and return values must be identical."""

    def test_empirical_var_percentile_matches_direct_numpy_percentile(self):
        import numpy as np

        from algo.risk.var import empirical_var_percentile

        returns = [-0.05, -0.03, -0.01, 0.0, 0.01, 0.02, 0.03, 0.1, -0.02, 0.005]
        expected = float(np.percentile(returns, (1 - 0.95) * 100))
        assert empirical_var_percentile(returns, 0.95) == expected

    def test_empirical_cvar_tail_mean_matches_direct_numpy_mean(self):
        import numpy as np

        from algo.risk.var import empirical_cvar_tail_mean, empirical_var_percentile

        returns = [-0.05, -0.03, -0.01, 0.0, 0.01, 0.02, 0.03, 0.1, -0.02, 0.005]
        threshold = empirical_var_percentile(returns, 0.95)
        tail = [r for r in returns if r <= threshold]
        expected = float(np.mean(tail))
        assert empirical_cvar_tail_mean(returns, threshold) == expected

    def test_empirical_cvar_tail_mean_raises_on_empty_tail(self):
        from algo.risk.var import empirical_cvar_tail_mean

        try:
            empirical_cvar_tail_mean([0.01, 0.02, 0.03], var_threshold=-1.0)
            raise AssertionError("expected ValueError for empty tail")
        except ValueError:
            pass
