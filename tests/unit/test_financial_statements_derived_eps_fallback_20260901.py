"""Regression test for the 2026-09-01 fix (/goal session: data-loading gap investigation).

Live DB audit found 7,397 annual_income_statement rows with real revenue but NULL
earnings_per_share - the filer never tagged EarningsPerShareBasic/EarningsPerShareDiluted (or
an IFRS alias) at all, even though net_income and share count were tagged and are already
stored on the same row. This silently starved growth_metrics (eps_growth_1y/3y/5y) and
downstream quality/value scoring of real, derivable signal: 1,741 symbols have
revenue_growth_5y but not eps_growth_5y purely because of this gap.

Fix: `_fill_derived_eps()`, called in transform() after `_reject_implausible_shares_outstanding`
(so the shares it may divide by have already survived both scale guards) and before
`_reject_implausible_eps` (so a bad derived value still gets rejected the same way a directly
reported one would). Tiers, all only firing when earnings_per_share is still None:
1. Fall back to diluted_eps if present (a real, already-fetched XBRL value under a different
   concept - EarningsPerShareDiluted - zero derivation risk).
2. Otherwise derive earnings_per_share = net_income / shares_outstanding_diluted-or-basic (same
   row, same filing, same currency - unlike load_sec_valuations.py's shares=net_income/eps
   derivation, which mixed values from inconsistently-converted sources, no cross-source
   mismatch is possible here) - but ONLY when the divisor share count is corroborated by either
   a company_info_sec reference or this same symbol's own other fiscal years in this batch
   (both within 20x). A share count with NEITHER corroborating source is not divided by at all
   (live-confirmed on VALE FY2008 and ATHS FY2025 - both would otherwise derive a
   plausible-looking-but-wrong EPS from a scale-corrupted or uncorroborated share count).
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period=period)


def _mock_read_context(fetchall: list[tuple[Any, ...]] | None = None) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall or []
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def _transform(
    loader: ConsolidatedFinancialStatementsLoader,
    rows: list[dict[str, Any]],
    company_info_sec_rows: list[tuple[str, float]] | None = None,
) -> list[dict[str, Any]]:
    with (
        patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
        patch(
            "loaders.load_financial_statements.DatabaseContext",
            return_value=_mock_read_context(fetchall=company_info_sec_rows),
        ),
    ):
        return loader.transform(rows)


def _row(**overrides: Any) -> dict[str, Any]:
    base = {
        "symbol": "ACME",
        "fiscal_year": 2025,
        "revenue": Decimal("500000000"),
        "net_income": Decimal("40000000"),
        "earnings_per_share": None,
        "diluted_eps": None,
        "shares_outstanding_basic": None,
        "shares_outstanding_diluted": None,
        "data_unavailable": False,
        "reason": None,
    }
    base.update(overrides)
    return base


class TestDerivedEpsFallback:
    def test_falls_back_to_diluted_eps_when_basic_missing(self) -> None:
        loader = _make_loader()
        rows = [_row(diluted_eps=Decimal("2.35"), shares_outstanding_diluted=Decimal("17021276"))]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("2.35")

    def test_derives_when_corroborated_by_company_info_sec_reference(self) -> None:
        loader = _make_loader()
        rows = [_row(shares_outstanding_diluted=Decimal("20000000"))]
        result = _transform(loader, rows, company_info_sec_rows=[("ACME", 19_500_000.0)])
        assert result[0]["earnings_per_share"] == Decimal("2")

    def test_falls_back_to_basic_shares_when_diluted_shares_unavailable(self) -> None:
        loader = _make_loader()
        rows = [_row(shares_outstanding_basic=Decimal("20000000"))]
        result = _transform(loader, rows, company_info_sec_rows=[("ACME", 19_500_000.0)])
        assert result[0]["earnings_per_share"] == Decimal("2")

    def test_never_overwrites_a_real_reported_eps(self) -> None:
        loader = _make_loader()
        rows = [
            _row(
                earnings_per_share=Decimal("1.98"),
                diluted_eps=Decimal("1.95"),
                shares_outstanding_diluted=Decimal("20000000"),
            )
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("1.98")

    def test_stays_none_when_neither_eps_nor_shares_nor_net_income_available(self) -> None:
        loader = _make_loader()
        rows = [_row(net_income=None)]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] is None

    def test_stays_none_when_shares_present_but_zero(self) -> None:
        loader = _make_loader()
        rows = [_row(shares_outstanding_basic=Decimal("0"), shares_outstanding_diluted=Decimal("0"))]
        result = _transform(loader, rows, company_info_sec_rows=[("ACME", 19_500_000.0)])
        assert result[0]["earnings_per_share"] is None

    def test_derived_value_still_subject_to_implausible_eps_rejection(self) -> None:
        """A derived EPS that lands in confidently-wrong territory (here: net_income so large
        relative to a small-but-corroborated share count that the quotient blows past the
        $1,000,000/share absolute ceiling) must still be rejected - the derivation runs before
        _reject_implausible_eps precisely so this guard still applies to a derived value the
        same way it would to a directly-reported one."""
        loader = _make_loader()
        rows = [_row(net_income=Decimal("200000000000"), shares_outstanding_basic=Decimal("100000"))]
        result = _transform(loader, rows, company_info_sec_rows=[("ACME", 100_000.0)])
        # 200,000,000,000 / 100,000 = 2,000,000/share - past max_plausible_abs_eps (1,000,000).
        assert result[0]["earnings_per_share"] is None

    def test_rejects_scale_mismatch_against_company_info_sec_reference(self) -> None:
        """VALE-shaped case: shares_outstanding_basic looks internally plausible (clears the
        absolute floor) but disagrees with the independent company_info_sec reference by far
        more than 20x - an unconverted 'reported in thousands' XBRL scale error, not a real
        share count. Must not derive an EPS from it."""
        loader = _make_loader()
        rows = [_row(shares_outstanding_basic=Decimal("5062148"))]
        result = _transform(loader, rows, company_info_sec_rows=[("ACME", 5_212_406_000.0)])
        assert result[0]["earnings_per_share"] is None

    def test_rejects_scale_mismatch_against_sibling_fiscal_year_when_no_reference_exists(self) -> None:
        """Same VALE-shaped scale error, but for a symbol with no company_info_sec row at all -
        falls back to cross-checking against this same symbol's own other fiscal year in this
        batch instead."""
        loader = _make_loader()
        rows = [
            _row(symbol="VALE", fiscal_year=2008, shares_outstanding_basic=Decimal("5062148")),
            _row(
                symbol="VALE",
                fiscal_year=2009,
                earnings_per_share=Decimal("1.03"),
                shares_outstanding_basic=Decimal("5212406000"),
            ),
        ]
        result = _transform(loader, rows, company_info_sec_rows=None)
        assert result[0]["earnings_per_share"] is None

    def test_derives_using_sibling_fiscal_year_when_no_reference_exists(self) -> None:
        """Same no-company_info_sec-row situation, but the share count genuinely agrees with
        this symbol's other fiscal year (real multi-year drift within 20x) - must still derive."""
        loader = _make_loader()
        rows = [
            _row(symbol="BETA", fiscal_year=2025, shares_outstanding_diluted=Decimal("20000000")),
            _row(
                symbol="BETA",
                fiscal_year=2024,
                earnings_per_share=Decimal("1.5"),
                shares_outstanding_diluted=Decimal("19000000"),
            ),
        ]
        result = _transform(loader, rows, company_info_sec_rows=None)
        assert result[0]["earnings_per_share"] == Decimal("2")

    def test_does_not_derive_with_zero_corroborating_sources(self) -> None:
        """ATHS-shaped case: no company_info_sec row AND this is the only fiscal year this
        symbol has ever had a share count for - nothing to cross-check the share count against
        at all. Must not derive an uncorroborated EPS rather than trust a single, unverifiable
        number (same 'missing scores are better than fabricated heuristics' governance this
        file already applies elsewhere)."""
        loader = _make_loader()
        rows = [_row(symbol="ATHS", shares_outstanding_basic=Decimal("203805"))]
        result = _transform(loader, rows, company_info_sec_rows=None)
        assert result[0]["earnings_per_share"] is None
