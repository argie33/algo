"""Regression test for the 2026-08-25 fix (goal session, financial-review audit):
algo/risk/var.py's beta_exposure() already documents "Beta exposure > 2.0 (2x market risk) ->
WARNING" as this system's own institutional convention, but it only ever fired as a Phase 9
(end-of-cycle) REPORT - nothing previously stopped Phase 8 from opening the entry that pushes
the book over that exact threshold in the first place.

PreTradeChecks._check_portfolio_beta() (algo/trading/pretrade_checks.py) now blocks a new
entry that would push the position-value-weighted portfolio beta above max_portfolio_beta
(default 2.0, reusing var.py's own convention). It fails OPEN (never blocks) only when the
CANDIDATE's own beta is unavailable, since stability_metrics.beta coverage is still filling
in for some symbols (this codebase's own documented data-maturity gap).

UPDATED 2026-09-06 (real-money-readiness audit): an EXISTING open position missing a beta
reading used to fail this entire check open (skip it, allow the entry) rather than just
weighting that one position conservatively - a single stale/not-yet-computed beta row
anywhere in the book disabled this cap for every new entry. Now matches
intraday_risk_monitor.py's identical fix: a missing-beta existing position is weighted at
a conservative beta=1.0 (market-average) instead of disabling the check entirely.
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

    def test_zero_portfolio_value_with_open_positions_fails_closed(self):
        # UPDATED 2026-09-06 (adversarial review): a non-positive portfolio_value used to
        # silently PASS the candidate (return True, None) instead of blocking - the one
        # inconsistency with every other non-positive-equity consumer in this codebase
        # (var.py, intraday_risk_monitor.py, _check_top5_concentration). Fixed to fail
        # closed. Requires an existing open position so the check doesn't short-circuit
        # via the earlier "no open positions" fast path before ever reaching this guard.
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(
            candidate_beta_row=(1.5,),
            open_positions_rows=[("HELD", 10, 100.0)],
            open_betas_rows=[("HELD", 1.0)],
        )
        try:
            checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("0"), cur)
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass

    def test_missing_beta_for_open_position_weighted_conservatively_still_passes_when_low(self):
        """A missing-beta position is weighted at an assumed beta=1.0, not dropped/skipped -
        this small position's contribution keeps the total well under the cap either way."""
        checks = PreTradeChecks(config=_config())
        cur = _FakeCursor(
            candidate_beta_row=(1.5,),
            open_positions_rows=[("HELD", 10, 100.0)],
            open_betas_rows=[],  # HELD's beta missing entirely
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("1000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None

    def test_missing_beta_for_open_position_no_longer_disables_the_check(self):
        """Regression for the 2026-09-06 fix: a missing-beta existing position used to skip
        this ENTIRE check (return True unconditionally) rather than being weighted at a
        conservative beta=1.0 - so a large existing position with a genuinely high candidate
        beta would silently sail through. With beta=1.0 assumed for HELD instead: weighted
        beta after = (60000*1.0 + 30000*3.0)/100000 = 1.5, which BREACHES a 1.4 cap - blocked,
        proving the check is actually still being enforced rather than skipped."""
        checks = PreTradeChecks(config=_config(max_portfolio_beta=1.4))
        cur = _FakeCursor(
            candidate_beta_row=(3.0,),
            open_positions_rows=[("HELD", 600, 100.0)],  # $60,000, beta missing
            open_betas_rows=[],
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("30000"), Decimal("100000"), cur)
        assert ok is False
        assert reason is not None
        assert "1.4" in reason

    def test_high_beta_entry_pushing_portfolio_over_cap_blocked(self):
        checks = PreTradeChecks(config=_config(max_portfolio_beta=2.0))
        # BUG FIX 2026-09-06: normalizes by portfolio_value (TOTAL account equity, cash
        # included) - matching var.py's beta_exposure(), which this check's own docstring
        # claims to reuse the "2.0 convention" from - NOT by existing_value+position_value
        # (invested capital only), which the old (buggy) version of this test locked in.
        # Existing book: $50,000 (100 sh @ $500) at beta 3.0. Candidate: $30,000 at beta 3.0.
        # Weighted avg after = (50000*3.0 + 30000*3.0) / 100000 (portfolio_value) = 2.4 > 2.0.
        cur = _FakeCursor(
            candidate_beta_row=(3.0,),
            open_positions_rows=[("HELD", 100, 500.0)],
            open_betas_rows=[("HELD", 3.0)],
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("30000"), Decimal("100000"), cur)
        assert ok is False
        assert reason is not None
        assert "2.0" in reason
        assert "2.4" in reason

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

    def test_uninvested_cash_is_not_ignored_in_the_denominator(self):
        """Regression for the 2026-09-06 fix: this check used to normalize by
        existing_value+position_value (invested capital only), silently ignoring the
        portfolio_value parameter - so a book sitting mostly in cash would compute a
        portfolio_beta_after far higher than var.py's beta_exposure() would ever report for
        the same account, needlessly blocking entries that could never breach the real 2.0
        total-account threshold. Half the account in cash, invested book at beta 3.0 - the
        true (portfolio_value-normalized) weighted beta is under the cap even though the
        invested-only weighted beta would have breached it.
        """
        checks = PreTradeChecks(config=_config(max_portfolio_beta=2.0))
        # Existing: $40,000 at beta 3.0. Candidate: $10,000 at beta 3.0. Total account
        # equity: $100,000 (i.e. $50,000 of that is uninvested cash).
        # Invested-only (the old, buggy denominator): (40000*3+10000*3)/50000 = 3.0 - WOULD
        # have wrongly blocked. Portfolio-value-normalized (correct): (120000+30000)/100000
        # = 1.5 - correctly passes.
        cur = _FakeCursor(
            candidate_beta_row=(3.0,),
            open_positions_rows=[("HELD", 400, 100.0)],
            open_betas_rows=[("HELD", 3.0)],
        )
        ok, reason = checks._check_portfolio_beta("NEWSYM", Decimal("10000"), Decimal("100000"), cur)
        assert ok is True
        assert reason is None
