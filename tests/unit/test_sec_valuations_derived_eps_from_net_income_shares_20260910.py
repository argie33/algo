"""Regression test (2026-09-10, goal: "under 500" push, eps_never_tagged_in_filings bucket).

Live-confirmed BULL/CCXI/GSRFR/HONA/PGACR: real net_income every fiscal year but zero rows,
ever, with a tagged earnings_per_share concept - pe_ratio/peg_ratio fell through to
"eps_never_tagged_in_filings" ("Missing SEC/XBRL data") even though a real EPS is trivially
derivable from net_income and the loader's own already-resolved company_info_sec.shares_
outstanding. IncomeStatementContextMixin._fetch_income_statement_context derives
ttm_eps_basic = net_income / shares_outstanding as a last resort, only after both existing
tagged-EPS fallback tiers (same-row, prior-row) have failed, and only for domestic filers.

UPDATED 2026-09-13 (goal: "question our own assumptions" audit): a same-day attempt to also
cover foreign private issuers here (cross-checking cis_shares_outstanding against yfinance)
was reverted after a live BP loader run showed cis_shares_outstanding
(company_info_sec.shares_outstanding) is NULL for BP - a domestic-forms-only field, empty
for exactly the FPIs that need a fallback in the first place. The FPI case is now handled
separately in SecValuationsLoader._derive_fpi_eps_from_resolved_shares, AFTER shares_out is
fully resolved (see test_sec_valuations_fpi_eps_derivation_from_resolved_shares_20260913.py) -
this file covers only the original domestic-only tier, unchanged.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FetchAllOnceCursor:
    """Mimics `_fetch_income_statement_context`'s own `cur.fetchall()` call for the income-
    statement query, plus graceful no-op fetchone/fetchall for the downstream
    `_get_total_cash_and_debt` call this method also makes (not under test here)."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self._first_fetchall = True

    def execute(self, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple]:
        if self._first_fetchall:
            self._first_fetchall = False
            return self._rows
        return []

    def fetchone(self) -> tuple | None:
        return None


class TestDerivedEpsFromNetIncomeAndShares:
    def test_derives_eps_when_never_tagged_but_net_income_and_shares_real(self) -> None:
        # fiscal_year, revenue, net_income, eps(None), op_income, pretax, dep, amort,
        # shares_outstanding_basic(None), income_tax, is_fpi(False), sic_code, interest_expense,
        # cis.shares_outstanding
        income_rows = [
            (
                2025,
                50_000_000.0,
                3_171_373.0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                None,
                None,
                41_900_000.0,
            ),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        result = loader._fetch_income_statement_context(cur, "CCXI")

        ttm_eps_basic = result[6]
        assert ttm_eps_basic == 3_171_373.0 / 41_900_000.0

    def test_foreign_private_issuer_not_derived_here(self) -> None:
        """This tier stays domestic-only - FPIs are handled downstream in fetch_incremental
        (_derive_fpi_eps_from_resolved_shares), not here, since cis_shares_outstanding is
        frequently NULL for exactly this population (see module docstring)."""
        income_rows = [
            (2025, 50_000_000.0, 3_171_373.0, None, None, None, None, None, None, None, True, None, None, 41_900_000.0),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        result = loader._fetch_income_statement_context(cur, "FPITEST")

        assert result[6] is None

    def test_no_shares_outstanding_not_derived(self) -> None:
        income_rows = [
            (2025, 50_000_000.0, 3_171_373.0, None, None, None, None, None, None, None, False, None, None, None),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        result = loader._fetch_income_statement_context(cur, "NOSHARES")

        assert result[6] is None

    def test_real_tagged_eps_wins_over_derivation(self) -> None:
        income_rows = [
            (
                2025,
                50_000_000.0,
                3_171_373.0,
                0.15,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                None,
                None,
                41_900_000.0,
            ),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        result = loader._fetch_income_statement_context(cur, "HASREALEPS")

        assert result[6] == 0.15
