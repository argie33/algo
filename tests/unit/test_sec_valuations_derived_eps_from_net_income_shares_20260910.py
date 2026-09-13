"""Regression test (2026-09-10, goal: "under 500" push, eps_never_tagged_in_filings bucket).

Live-confirmed BULL/CCXI/GSRFR/HONA/PGACR: real net_income every fiscal year but zero rows,
ever, with a tagged earnings_per_share concept - pe_ratio/peg_ratio fell through to
"eps_never_tagged_in_filings" ("Missing SEC/XBRL data") even though a real EPS is trivially
derivable from net_income and the loader's own already-resolved company_info_sec.shares_
outstanding. IncomeStatementContextMixin._fetch_income_statement_context now derives
ttm_eps_basic = net_income / shares_outstanding as a last resort, only after both existing
tagged-EPS fallback tiers (same-row, prior-row) have failed.

UPDATED 2026-09-13 (goal: "question our own assumptions" audit): originally excluded every
foreign private issuer outright (see _fpi_ads_adjusted_eps's ADS-ratio-mismatch rationale).
Live re-verified across all 19 real eps_never_tagged_in_filings symbols that this was
overbroad - every one of them (BP/AZUL/BIPC/FMX/etc.) already has cis_shares_outstanding on
the correct per-listing basis (current_price * cis_shares_outstanding exactly reproduces
their own already-computed market_cap). FPIs are no longer blanket-excluded; instead the
derivation cross-checks cis_shares_outstanding against yfinance's own per-LISTING
sharesOutstanding (already on the correct ADS/USD basis) using the same
SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO=2 tolerance the shares-resolution cascade uses
elsewhere for the identical question - a real ADS mismatch (e.g. TSM's 5:1) still correctly
fails this check and skips derivation.
"""

from unittest.mock import patch

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

    def test_foreign_private_issuer_no_yfinance_confirmation_not_derived(self) -> None:
        """When the yfinance cross-check itself fails/returns nothing, there's no
        independent confirmation cis_shares_outstanding is on the right basis - stays
        unavailable rather than trusting an unconfirmed FPI share count."""
        income_rows = [
            (2025, 50_000_000.0, 3_171_373.0, None, None, None, None, None, None, None, True, None, None, 41_900_000.0),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        with patch.object(SecValuationsLoader, "_fetch_live_fpi_shares_outstanding_yfinance", return_value=None):
            result = loader._fetch_income_statement_context(cur, "FPITEST")

        assert result[6] is None

    def test_foreign_private_issuer_ads_mismatch_not_derived(self) -> None:
        """TSM-shaped real ADS mismatch (~5x): yfinance's per-listing share count disagrees
        with cis_shares_outstanding by far more than SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO
        - must still be rejected, not derived from the wrong (home-market) share basis."""
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
                True,
                None,
                None,
                41_900_000.0,  # cis_shares_outstanding - home-market basis
            ),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_fpi_shares_outstanding_yfinance",
            return_value=41_900_000.0 / 5,  # real ADS-basis count, ~5x smaller
        ):
            result = loader._fetch_income_statement_context(cur, "FPIMISMATCH")

        assert result[6] is None

    def test_foreign_private_issuer_confirmed_by_yfinance_is_derived(self) -> None:
        """BP-shaped real case: cis_shares_outstanding agrees with yfinance's per-listing
        sharesOutstanding (within tolerance) - confirms no ADS multiplier is hiding in the
        SEC-sourced count, so derivation may safely proceed for this FPI."""
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
                True,
                None,
                None,
                41_900_000.0,
            ),
        ]
        loader = _make_loader()
        cur = _FetchAllOnceCursor(income_rows)

        with patch.object(
            SecValuationsLoader,
            "_fetch_live_fpi_shares_outstanding_yfinance",
            return_value=41_500_000.0,  # within 2x tolerance of cis_shares_outstanding
        ):
            result = loader._fetch_income_statement_context(cur, "BPLIKE")

        assert result[6] == 3_171_373.0 / 41_900_000.0

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
