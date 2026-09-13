"""Regression test for the 2026-09-13 fix: shares_outstanding_basic/diluted were never
sanity-checked against a DIFFERENT fiscal year's shares_outstanding_dei from the same symbol,
only the SAME row's (see
test_financial_statements_shares_outstanding_dei_same_row_mismatch_20260907.py's own sibling
guard). Foreign 20-F filers that don't re-tag dei:EntityCommonStockSharesOutstanding every year
have this structural blind spot: the two fields never land on the same row, so the same-row
guard never fires despite both facts existing in the same batch.

Live-confirmed via CCU (Compania Cervecerias Unidas), verified in our OWN live DB (not just
the raw SEC facts): dei tagged only for FY2022 (369,502,872 - stable across its real filing
history 2017-2025), shares_outstanding_basic only populated FY2015-2018 (369,502,872,000 -
exactly 1000x, a filer-side XBRL decimals-tag error). This works because CCU's real share
count is genuinely stable year to year, so even a distant-year dei anchor still lands on an
exact 1000x multiple.

NOTE: PAGS (PagSeguro) was initially suspected to share this exact bug shape (its own FY2023
20-F mistagged WeightedAverageShares with 3 extra zeros, self-corrected by the filer a year
later in its own next 20-F's comparative column) but does NOT trigger THIS specific check -
PAGS's real share count grew ~23% between its only dei anchor (FY2017, 262,288,607) and the
corrupted FY2023 value, so the true ratio (~1227x) isn't a clean-enough 1000x match. PAGS's
fix needs a different mechanism (comparing against the specific later-filed correct comparative
fact directly in the XBRL extraction engine, not a downstream dei cross-check) - see
ifrs_shares_outstanding_1000x_filer_typo_class_20260913 in memory for the full writeup. Several
other initially-suspected filers (China Natural Resources, Suzano, XTL Biopharma, Telefonica
Brasil, Sangoma) turned out to be FALSE ALARMS on closer inspection - their raw
`ifrs-full:NumberOfSharesOutstanding` concept is corrupted in SEC's own data, but this codebase
deliberately never extracts shares_outstanding_basic from that concept (see
sec_income_statement.py's own "TRIED AND REJECTED" comment), so their real DB values were
already correct all along.
"""

from typing import Any

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


class TestSharesOutstandingScaleOutlierVsOwnDeiHistory:
    def test_ccu_shaped_batch_1000x_outlier_rejected(self) -> None:
        """CCU-shaped batch: dei only on FY2022's row, shares_outstanding_basic only on
        FY2015-2018's rows (exactly 1000x dei) - the cross-year check must still catch it."""
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "CCU", "fiscal_year": 2015, "shares_outstanding_basic": 369_502_872_000},
            {"symbol": "CCU", "fiscal_year": 2016, "shares_outstanding_basic": 369_502_872_000},
            {"symbol": "CCU", "fiscal_year": 2017, "shares_outstanding_basic": 369_502_872_000},
            {"symbol": "CCU", "fiscal_year": 2018, "shares_outstanding_basic": 369_502_872_000},
            {"symbol": "CCU", "fiscal_year": 2022, "shares_outstanding_dei": 369_502_872},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        for row in rows[:4]:
            assert row["shares_outstanding_basic"] is None
        # the reference row itself is untouched (no basic/diluted value to reject there)
        assert rows[4]["shares_outstanding_dei"] == 369_502_872

    def test_clean_1000x_multiple_across_distant_years_rejected(self) -> None:
        """A synthetic case with a genuinely exact 1000x ratio across distant fiscal years
        must still be caught, regardless of how many years apart the dei anchor is."""
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "SYN", "fiscal_year": 2015, "shares_outstanding_dei": 50_000_000},
            {"symbol": "SYN", "fiscal_year": 2024, "shares_outstanding_basic": 50_000_000_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert rows[1]["shares_outstanding_basic"] is None

    def test_pags_real_shape_not_rejected_by_this_mechanism(self) -> None:
        """PAGS's real case (live-confirmed): its only dei anchor (FY2017, 262,288,607) is 6
        years removed from the corrupted FY2023 value (321,806,480,000), and PAGS's real share
        count genuinely grew ~23% in that span - the resulting ratio (~1227x) is NOT a clean
        1000x match, so this check correctly does NOT fire (a real, if imperfect, precision
        tradeoff - see this file's module docstring for why PAGS needs a different fix)."""
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "PAGS", "fiscal_year": 2017, "shares_outstanding_dei": 262_288_607},
            {"symbol": "PAGS", "fiscal_year": 2023, "shares_outstanding_basic": 321_806_480_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert rows[1]["shares_outstanding_basic"] == 321_806_480_000

    def test_real_organic_growth_across_years_not_rejected(self) -> None:
        """A real company's share count growing moderately over years (buybacks/issuances,
        not a clean power-of-10) must survive untouched."""
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "GROW", "fiscal_year": 2020, "shares_outstanding_dei": 100_000_000},
            {"symbol": "GROW", "fiscal_year": 2023, "shares_outstanding_basic": 128_000_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert rows[1]["shares_outstanding_basic"] == 128_000_000

    def test_no_dei_anywhere_in_batch_for_symbol_does_not_crash_or_reject(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "NODEI", "fiscal_year": 2025, "shares_outstanding_basic": 1_000_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert rows[0]["shares_outstanding_basic"] == 1_000_000

    def test_different_symbols_in_same_batch_do_not_cross_contaminate(self) -> None:
        """Another symbol's dei value in the same batch must never be used as a reference for
        an unrelated symbol."""
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "OTHER", "fiscal_year": 2022, "shares_outstanding_dei": 369_502_872},
            {"symbol": "CCU", "fiscal_year": 2015, "shares_outstanding_basic": 369_502_872_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert rows[1]["shares_outstanding_basic"] == 369_502_872_000

    def test_rejection_recorded_for_post_run_force_null(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "CCU", "fiscal_year": 2022, "shares_outstanding_dei": 369_502_872},
            {"symbol": "CCU", "fiscal_year": 2015, "shares_outstanding_basic": 369_502_872_000},
        ]
        loader._reject_shares_outstanding_scale_outlier_vs_own_dei_history(rows)
        assert any(
            field == "shares_outstanding_basic" and pk.get("symbol") == "CCU" and pk.get("fiscal_year") == 2015
            for pk, field in loader._explicit_null_rejections
        )
