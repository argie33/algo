"""Regression test for the 2026-09-13 fix (steady-wiggling-unicorn.md plan): the primary
income-statement path (`_fetch_income_statement_context`) used to treat the latest ANNUAL
filing's EPS/revenue/net_income as "TTM" even when up to ~12 months stale, while 4 fresher real
quarters already sat in `quarterly_income_statement` unused. Live-confirmed on MU (Micron):
stored pe_ratio 127.48 off a stale FY2025 annual EPS of $7.59, vs. real-world P/E ~22 (TTM EPS
~$44) once FY2026 Q2/Q3's much higher diluted EPS ($12.07/$24.67) are included.

`_compute_ttm_income_from_quarters` (loaders/helpers/sec_valuations_checks.py) now supplies a
genuine rolling TTM (revenue+net_income+EPS, period_end-guarded) that the primary path prefers
over the annual row whenever it validates - and a year-ago TTM (offset=4) for a consistent PEG
`prior_year_eps`. It opens its own `DatabaseContext` (same convention as its sibling
`_compute_ttm_eps_from_quarters`, see test_sec_valuations_pe_ratio_ttm_from_quarters_rescue_
20260905.py) rather than reusing `_fetch_income_statement_context`'s own `cur` - deliberately,
so this new query doesn't insert itself into the sequential/index-based mock-cursor call
sequence dozens of OTHER `_fetch_income_statement_context`/`fetch_incremental` unit tests
already hardcode.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


def _annual_row(fiscal_year, revenue, net_income, eps):
    # (fiscal_year, revenue, net_income, earnings_per_share, operating_income, pretax_income,
    #  depreciation_expense, amortization_expense, shares_outstanding_basic, income_tax_expense,
    #  is_foreign_private_issuer, sic_code, interest_expense, shares_outstanding)
    return (
        fiscal_year,
        revenue,
        net_income,
        eps,
        None,
        None,
        None,
        None,
        1_000_000_000.0,
        None,
        False,
        "3674",
        None,
        None,
    )


def _quarter(period_end, revenue, net_income, eps):
    return (period_end, revenue, net_income, eps)


class _AnnualCursor:
    """Mirrors _fetch_income_statement_context's own real call sequence for a symbol with real
    annual data and no other special-case branches hit - the fake cursor PASSED IN to
    `_fetch_income_statement_context`. The new quarterly-TTM lookup uses its own separate
    `DatabaseContext` (patched below), so this fixture never needs to know about it.
    """

    def __init__(self, annual_rows):
        self._annual_rows = annual_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM annual_income_statement" in self._last_query:
            return self._annual_rows
        return []

    def fetchone(self):
        return None


class _QuarterlyFakeCtx:
    """A patchable `DatabaseContext("read")` stand-in returning a fixed quarterly row set for
    ANY query issued through it - `_compute_ttm_income_from_quarters` is the only thing that
    opens a DatabaseContext inside `_fetch_income_statement_context`'s call graph, so no query
    dispatch is needed here, just an offset-aware fetchall (current window vs. year-ago window,
    distinguished by the `OFFSET %s` param the real query always passes).
    """

    def __init__(self, current_quarters, prior_quarters=None):
        self._current_quarters = current_quarters
        self._prior_quarters = prior_quarters or []
        self._last_params: tuple = ()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self._last_params = params or ()

    def fetchall(self):
        offset = self._last_params[1] if len(self._last_params) > 1 else 0
        return self._prior_quarters if offset == 4 else self._current_quarters


def _patched_quarterly_ctx(current_quarters, prior_quarters=None):
    ctx = _QuarterlyFakeCtx(current_quarters, prior_quarters)
    return patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=ctx)


class TestTtmPreferredOverStaleAnnual:
    def test_fresh_valid_quarterly_ttm_overrides_stale_annual_eps(self):
        """The core new behavior: a stale annual EPS ($7.59, MU's real FY2025 figure) must be
        replaced by a genuine rolling TTM built from 4 fresher real quarters, once that window
        validates (present/distinct/~91-days-apart/recent)."""
        loader = _make_loader()
        today = date.today()
        current_quarters = [
            _quarter(today - timedelta(days=5), 28_243_000_000.0, 5_000_000_000.0, 24.67),
            _quarter(today - timedelta(days=96), 13_785_000_000.0, 2_000_000_000.0, 12.07),
            _quarter(today - timedelta(days=187), 9_301_000_000.0, 300_000_000.0, 1.68),
            _quarter(today - timedelta(days=278), 8_053_000_000.0, 250_000_000.0, 1.41),
        ]
        cur = _AnnualCursor(annual_rows=[_annual_row(2025, 37_378_000_000.0, 8_539_000_000.0, 7.59)])

        with _patched_quarterly_ctx(current_quarters):
            result = loader._fetch_income_statement_context(cur, "MU")

        assert not isinstance(result, list)
        (_, _, _, _, ttm_revenue, ttm_net_income, ttm_eps_basic, *_rest) = result
        assert ttm_eps_basic == 24.67 + 12.07 + 1.68 + 1.41
        assert ttm_revenue == 28_243_000_000.0 + 13_785_000_000.0 + 9_301_000_000.0 + 8_053_000_000.0
        assert ttm_net_income == 5_000_000_000.0 + 2_000_000_000.0 + 300_000_000.0 + 250_000_000.0

    def test_prior_year_eps_uses_year_ago_ttm_not_stale_annual_prior_year(self):
        """peg_ratio's growth leg must compare TTM-over-TTM, not the new quarterly-TTM current
        figure against an annual-sourced prior_year_eps from a different measurement window."""
        loader = _make_loader()
        today = date.today()
        current_quarters = [_quarter(today - timedelta(days=d), 1_000.0, 100.0, 2.0) for d in (5, 96, 187, 278)]
        prior_quarters = [_quarter(today - timedelta(days=d), 1_000.0, 100.0, 1.0) for d in (369, 460, 551, 642)]
        cur = _AnnualCursor(
            annual_rows=[
                _annual_row(2025, 4_000.0, 400.0, 8.0),
                _annual_row(2024, 3_500.0, 350.0, 7.0),
            ]
        )

        with _patched_quarterly_ctx(current_quarters, prior_quarters):
            result = loader._fetch_income_statement_context(cur, "TESTQTTM")

        assert not isinstance(result, list)
        prior_year_eps = result[7]
        assert prior_year_eps == 4.0  # sum of the 4 prior-window quarters' EPS (1.0 * 4)

    def test_prior_year_ttm_unavailable_leaves_prior_year_eps_none_not_mismatched(self):
        """When the year-ago window doesn't validate (e.g. only 2 quarters that far back),
        prior_year_eps must be None - never silently fall back to the stale annual prior-year
        figure, which would compare two different measurement windows in one growth calc."""
        loader = _make_loader()
        today = date.today()
        current_quarters = [_quarter(today - timedelta(days=d), 1_000.0, 100.0, 2.0) for d in (5, 96, 187, 278)]
        cur = _AnnualCursor(
            annual_rows=[
                _annual_row(2025, 4_000.0, 400.0, 8.0),
                _annual_row(2024, 3_500.0, 350.0, 7.0),
            ]
        )

        with _patched_quarterly_ctx(current_quarters, prior_quarters=[]):
            result = loader._fetch_income_statement_context(cur, "TESTNOPTOOL")

        assert not isinstance(result, list)
        assert result[7] is None

    def test_stale_quarters_do_not_override_annual(self):
        """A quarterly window whose most recent quarter is >400 days old must not override the
        annual figure - staleness recency guard must still apply to the current-period window."""
        loader = _make_loader()
        today = date.today()
        stale_quarters = [_quarter(today - timedelta(days=d), 1_000.0, 100.0, 2.0) for d in (450, 541, 632, 723)]
        cur = _AnnualCursor(annual_rows=[_annual_row(2025, 4_000.0, 400.0, 8.0)])

        with _patched_quarterly_ctx(stale_quarters):
            result = loader._fetch_income_statement_context(cur, "TESTSTALEQ")

        assert not isinstance(result, list)
        ttm_eps_basic = result[6]
        assert ttm_eps_basic == 8.0  # unchanged, from the annual row

    def test_gap_in_quarters_does_not_override_annual(self):
        """Quarters not spaced ~91 days apart (a missing quarter never loaded) must not
        validate - the annual figure stays in place rather than summing a bogus window."""
        loader = _make_loader()
        today = date.today()
        gapped_quarters = [
            _quarter(today - timedelta(days=5), 1_000.0, 100.0, 2.0),
            _quarter(today - timedelta(days=96), 1_000.0, 100.0, 2.0),
            # missing a quarter here - jumps straight to ~1 year back
            _quarter(today - timedelta(days=365), 1_000.0, 100.0, 2.0),
            _quarter(today - timedelta(days=456), 1_000.0, 100.0, 2.0),
        ]
        cur = _AnnualCursor(annual_rows=[_annual_row(2025, 4_000.0, 400.0, 8.0)])

        with _patched_quarterly_ctx(gapped_quarters):
            result = loader._fetch_income_statement_context(cur, "TESTGAPQ")

        assert not isinstance(result, list)
        ttm_eps_basic = result[6]
        assert ttm_eps_basic == 8.0  # unchanged, from the annual row
