"""Regression test for the 2026-09-07 fix: shares_outstanding_basic/diluted were never
sanity-checked against the SAME row's shares_outstanding_dei - both come from the same
filing (dei is the cover-page share count, basic/diluted the weighted-average count for the
fiscal period the same filing covers), so a many-multiple disagreement between them is a
confidently-wrong filer/filing-agent XBRL tagging error, not real data.

Live-confirmed via SOAR FY2025: shares_outstanding_basic=shares_outstanding_diluted=4,386,829
against the SAME row's shares_outstanding_dei=38,895,663 (~8.87x) and the independent
company_info_sec.shares_outstanding=53,633,248 (~12.2x - under
_reject_implausible_shares_outstanding's 20x threshold and so not caught there). The
understated share count inflated diluted_eps to $1.18 (real EPS on a correct share count
would be ~$0.13), crushing pe_ratio to 0.20 and making SOAR the single most "undervalued"
name in the whole universe (value_score=100.0) on a confidently-wrong denominator.
"""

from typing import Any

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


class TestSharesOutstandingDeiSameRowMismatchRejected:
    def test_soar_shaped_row_basic_and_diluted_both_rejected(self) -> None:
        """SOAR FY2025-shaped row: basic and diluted both ~8.87x below the same row's dei
        must both be nulled out."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "SOAR",
            "fiscal_year": 2025,
            "shares_outstanding_basic": 4_386_829,
            "shares_outstanding_diluted": 4_386_829,
            "shares_outstanding_dei": 38_895_663,
        }
        loader._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch([row])
        assert row["shares_outstanding_basic"] is None
        assert row["shares_outstanding_diluted"] is None

    def test_moderate_same_filing_variance_is_not_rejected(self) -> None:
        """A real, moderate cover-page-vs-weighted-average difference (buybacks/issuances
        during the year) must survive untouched - only many-multiple gaps are tagging
        errors."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "CHRS",
            "fiscal_year": 2025,
            "shares_outstanding_basic": 117_143_457,
            "shares_outstanding_diluted": 117_143_457,
            "shares_outstanding_dei": 149_889_902,  # ratio ~1.28x
        }
        loader._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch([row])
        assert row["shares_outstanding_basic"] == 117_143_457
        assert row["shares_outstanding_diluted"] == 117_143_457

    def test_dei_smaller_than_basic_diluted_also_rejected(self) -> None:
        """Symmetric case: dei implausibly SMALL relative to basic/diluted must also fire -
        the mismatch is bidirectional evidence something's wrong, not just one direction."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "ZZZ",
            "fiscal_year": 2025,
            "shares_outstanding_basic": 50_000_000,
            "shares_outstanding_diluted": 50_000_000,
            "shares_outstanding_dei": 4_000_000,  # ratio 12.5x
        }
        loader._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch([row])
        assert row["shares_outstanding_basic"] is None
        assert row["shares_outstanding_diluted"] is None

    def test_missing_dei_does_not_crash_or_reject(self) -> None:
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "NODEI",
            "fiscal_year": 2025,
            "shares_outstanding_basic": 1_000_000,
            "shares_outstanding_diluted": 1_000_000,
            "shares_outstanding_dei": None,
        }
        loader._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch([row])
        assert row["shares_outstanding_basic"] == 1_000_000
        assert row["shares_outstanding_diluted"] == 1_000_000

    def test_rejection_recorded_for_post_run_force_null(self) -> None:
        """Same _explicit_null_rejections mechanism _reject_implausible_shares_outstanding/
        _reject_diluted_shares_below_basic use, so post_run() force-nulls the stale DB value
        on a re-fetch, not just this run's in-memory row."""
        loader = _make_loader()
        row: dict[str, Any] = {
            "symbol": "SOAR",
            "fiscal_year": 2025,
            "shares_outstanding_basic": 4_386_829,
            "shares_outstanding_diluted": 4_386_829,
            "shares_outstanding_dei": 38_895_663,
        }
        loader._reject_shares_outstanding_basic_diluted_dei_same_row_mismatch([row])
        assert any(
            field == "shares_outstanding_diluted" and pk.get("symbol") == "SOAR" and pk.get("fiscal_year") == 2025
            for pk, field in loader._explicit_null_rejections
        )
        assert any(
            field == "shares_outstanding_basic" and pk.get("symbol") == "SOAR" and pk.get("fiscal_year") == 2025
            for pk, field in loader._explicit_null_rejections
        )
