"""Regression test for the 2026-08-25 fix (goal session, financial-review audit):
algo/risk/var.py's beta_exposure() already documents "Beta exposure > 2.0 (2x market risk) ->
WARNING" as this system's own institutional convention, but it only ever fired as a Phase 9
(end-of-cycle) REPORT - nothing previously stopped Phase 8 from opening the entry that pushes
the book over that exact threshold in the first place.

PreTradeChecks._check_portfolio_beta() (algo/trading/pretrade_checks.py) now blocks a new
entry that would push the position-value-weighted portfolio beta above max_portfolio_beta
(default 2.0, reusing var.py's own convention). It fails OPEN (never blocks) when the
candidate's beta or any open position's beta is unavailable, since stability_metrics.beta
coverage is still filling in for some symbols (this codebase's own documented data-maturity
gap).
"""

from decimal import Decimal

from algo.trading.pretrade_checks import PreTradeChecks


def _config(**overrides):
    base = {"max_portfolio_beta": 2.0}
    base.update(overrides)
    return base


class _FakeCursor:
    """Sequences canned responses to matched queries: candidate beta -> open positions ->
    open-positions' betas, in that fixed call order (matching _check_portfolio_beta itself)."""

    def __init__(self, candidate_beta_row, open_positions_rows, open_betas_rows):
        self._responses = [candidate_beta_row, open_positions_rows, open_betas_rows]
        self._call_index = 0
        self._last_call = None
        self.open_positions_query_params = None

    def execute(self, query, params=None):
        if "SELECT beta FROM stability_metrics WHERE symbol = %s" in query:
            self._last_call = 0
        elif "FROM algo_positions" in query:
            self._last_call = 1
            self.open_positions_query_params = params
        elif "SELECT symbol, beta FROM stability_metrics" in query:
            self._last_call = 2
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchone(self):
        return self._responses[0]

    def fetchall(self):
        return self._responses[self._last_call]


class TestPortfolioBetaCheck:
    def test_candidate_beta_unavailable_fails_open(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(candidate_beta_row=None, open_positions_rows=[], open_betas_rows=[])
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_no_open_positions_passes(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(candidate_beta_row=(1.5,), open_positions_rows=[], open_betas_rows=[])
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_missing_beta_for_open_position_fails_open(self):
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(
            candidate_beta_row=(1.5,),
            open_positions_rows=[("HELD", 10, 100.0)],
            open_betas_rows=[],  # HELD's beta missing entirely
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_high_beta_entry_pushing_portfolio_over_cap_blocked(self):
        checks = PreTradeChecks(config=_config(max_portfolio_beta=2.0))
        # Existing book: $10,000 at beta 1.0. Candidate: $10,000 at beta 4.0.
        # Weighted avg after = (10000*1.0 + 10000*4.0) / 20000 = 2.5 > 2.0 cap.
        cur = _FakeCursor(
            candidate_beta_row=(4.0,),
            open_positions_rows=[("HELD", 100, 100.0)],
            open_betas_rows=[("HELD", 1.0)],
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is False
        assert reason is not None
        assert "2.0" in reason
        assert "2.5" in reason

    def test_low_beta_entry_stays_under_cap_passes(self):
        checks = PreTradeChecks(config=_config(max_portfolio_beta=2.0))
        # Existing book: $10,000 at beta 1.0. Candidate: $10,000 at beta 1.2.
        # Weighted avg after = (10000*1.0 + 10000*1.2) / 20000 = 1.1 < 2.0 cap.
        cur = _FakeCursor(
            candidate_beta_row=(1.2,),
            open_positions_rows=[("HELD", 100, 100.0)],
            open_betas_rows=[("HELD", 1.0)],
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_open_positions_query_excludes_candidate_symbol(self):
        """Defense-in-depth: run_all()'s earlier duplicate-position check already guarantees
        the candidate has no open position by the time this method runs, but the open-
        positions query must still explicitly exclude it (matching
        _check_correlation_concentration/_check_top5_concentration's identical guard) - a
        candidate double-counted as both "existing position" and "candidate" would silently
        corrupt the weighted-average beta calculation if this method were ever reached from a
        different call path than run_all()'s own ordering guarantees."""
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(
            candidate_beta_row=(1.5,),
            open_positions_rows=[("HELD", 100, 100.0)],
            open_betas_rows=[("HELD", 1.0)],
        )
        checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert cur.open_positions_query_params is not None
        assert "NEWSYM" in cur.open_positions_query_params

    def test_missing_config_key_raises(self):
        checks = PreTradeChecks(config={})
        cur = _FakeCursor(
            candidate_beta_row=(1.5,),
            open_positions_rows=[("HELD", 100, 100.0)],
            open_betas_rows=[("HELD", 1.0)],
        )
        try:
            checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
            raise AssertionError("expected KeyError for missing max_portfolio_beta config")
        except KeyError:
            pass
