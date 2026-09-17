"""Regression test for the 2026-09-17 fix (goal session: xbrl_yfinance_line_item_report
remediation, long_term_debt top-cluster sweep): ABCB (Ameris Bancorp, CIK 0000351569) tags
BOTH a real "SubordinatedDebt" fact AND a real, genuinely distinct "OtherBorrowings" fact
every fiscal year. Both concepts are fallback-only, first-populated-wins, with
"SubordinatedDebt" listed before "OtherBorrowings" in sec_balance_sheet.py's concept-fetch
list - so SubordinatedDebt permanently won the long_term_debt slot and OtherBorrowings (the
filer's real, usually much larger, other borrowed-funds instrument) never got a chance to
write at all.

Live-confirmed via real SEC companyfacts JSON 2026-09-17, every fiscal year on file in
xbrl_yfinance_line_item_report, EXACT match to yfinance's flagged value only when BOTH
concepts are summed:
    FY2022: $128,322,000 + $1,875,736,000 = $2,004,058,000 (yfinance-flagged, exact)
    FY2023: $130,315,000 + $509,586,000 = $639,901,000 (yfinance-flagged, exact)
    FY2024: $132,309,000 + $291,788,000 = $424,097,000 (yfinance-flagged, exact)
    FY2025: $134,302,000 + $558,039,000 = $692,341,000 (yfinance-flagged, exact)

See loaders/helpers/sec_zero_component_guards.py's
is_other_borrowings_additive_to_subordinated_debt docstring for the guard this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestOtherBorrowingsAdditiveToSubordinatedDebtFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "subordinated_debt": "long_term_debt",
            "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": "long_term_debt",
            "other_borrowings": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {
                "subordinated_debt",
                "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust",
                "other_borrowings",
            }
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["subordinated_debt"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["other_borrowings"] == "long_term_debt"
        assert "subordinated_debt" in _DEBT_FALLBACK_ONLY_FIELDS
        assert "other_borrowings" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_abcb_fy2022_subordinated_debt_and_other_borrowings_sum(self) -> None:
        """Real fetch order: SubordinatedDebt processed before OtherBorrowings (concept-fetch
        list order in sec_balance_sheet.py)."""
        loader = self._make_loader()
        row = {
            "symbol": "ABCB",
            "fiscal_year": 2022,
            "subordinated_debt": 128_322_000.0,
            "other_borrowings": 1_875_736_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 2_004_058_000.0

    def test_abcb_fy2025_subordinated_debt_and_other_borrowings_sum(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ABCB",
            "fiscal_year": 2025,
            "subordinated_debt": 134_302_000.0,
            "other_borrowings": 558_039_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 692_341_000.0

    def test_junior_subordinated_debenture_family_also_sums_with_other_borrowings(self) -> None:
        """IBOC/HBT-style trust-preferred concept - same additive family."""
        loader = self._make_loader()
        row = {
            "symbol": "TESTBANK",
            "fiscal_year": 2025,
            "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": 50_000_000.0,
            "other_borrowings": 25_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 75_000_000.0

    def test_other_borrowings_alone_still_a_plain_single_write_when_no_existing_value(self) -> None:
        """FFIN-style case: OtherBorrowings is sometimes a filer's ENTIRE real debt figure on
        its own, with no subordinated-debt-family concept present at all - must not be
        affected by this additive guard (no existing value to sum against)."""
        loader = self._make_loader()
        row = {
            "symbol": "FFIN",
            "fiscal_year": 2025,
            "other_borrowings": 21_055_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 21_055_000.0

    def test_other_borrowings_does_not_sum_against_an_unrelated_existing_source(self) -> None:
        """The guard is scoped to specifically the subordinated-debt/trust-preferred family
        having written the existing value - it must not double-count against an already-
        resolved, unrelated total (e.g. a combined-debt-total concept) that may already be
        the filer's complete debt figure."""
        loader = self._make_loader()
        loader._field_mapping["long_term_debt_and_capital_lease_obligations"] = "long_term_debt"
        loader._fallback_only_fields = loader._fallback_only_fields | {"long_term_debt_and_capital_lease_obligations"}
        row = {
            "symbol": "TESTCO",
            "fiscal_year": 2025,
            "long_term_debt_and_capital_lease_obligations": 5_000_000_000.0,
            "other_borrowings": 25_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 5_000_000_000.0
