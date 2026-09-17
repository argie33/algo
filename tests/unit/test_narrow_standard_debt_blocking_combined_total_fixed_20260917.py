"""Regression test for the 2026-09-17 fix (goal session: data-coverage-metrics accuracy sweep,
xbrl_yfinance_line_item_report long_term_debt audit): DPZ, MAR, BALL, PPC, LNTH, CRL each still
tag a real, nonzero plain "LongTermDebt" fact (the standard concept) that has become an
immaterial single note/instrument, while their real total debt moved years ago to a combined
concept like "LongTermDebtAndCapitalLeaseObligations" - the ordinary "standard concept always
wins if present, no matter how small" rule silently kept the tiny, wrong value.

Live-confirmed via real SEC companyfacts JSON 2026-09-17: DPZ FY2025 plain LongTermDebt=$14.6M
(a real but minor note) vs LongTermDebtAndCapitalLeaseObligations=$4,810,683,000 - an EXACT
match to yfinance's flagged value. MAR/BALL/PPC/LNTH: same shape, exact yfinance matches.

See loaders/helpers/sec_zero_component_guards.py's is_narrow_standard_debt_blocking_combined_total
docstring for the guard this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestNarrowStandardDebtBlockingCombinedTotalFixed:
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
            "long_term_debt_and_capital_lease_obligations": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"long_term_debt_and_capital_lease_obligations"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_combined_obligations_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["long_term_debt_and_capital_lease_obligations"] == "long_term_debt"
        assert "long_term_debt_and_capital_lease_obligations" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_dpz_style_tiny_standard_concept_overridden_by_much_larger_combined_total(self) -> None:
        """Standard concept processed FIRST (blocked by the ordinary fallback-only gate,
        overridden by is_narrow_standard_debt_blocking_combined_total)."""
        loader = self._make_loader()
        row = {
            "symbol": "DPZ",
            "fiscal_year": 2025,
            "long_term_debt": 14_600_000.0,
            "long_term_debt_and_capital_lease_obligations": 4_810_683_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 4_810_683_000.0

    def test_dpz_real_fetch_order_combined_concept_first_then_standard(self) -> None:
        """The actual live DPZ/MAR/BALL/PPC/LNTH/CRL shape: sec_balance_sheet.py's own
        concept-fetch list lists the combined-total concept BEFORE "LongTermDebt", so it's
        processed (and written) FIRST, then the plain standard concept - not fallback-gated at
        all - would otherwise unconditionally overwrite it via ordinary last-listed-wins.
        Guarded by is_immaterial_standard_debt_overwriting_combined_total.
        """
        loader = self._make_loader()
        row = {
            "symbol": "DPZ",
            "fiscal_year": 2025,
            "long_term_debt_and_capital_lease_obligations": 4_810_683_000.0,
            "long_term_debt": 14_600_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 4_810_683_000.0

    def test_combined_total_still_does_not_override_a_close_or_comparable_standard_value(self) -> None:
        """A modest gap (e.g. one extra bond issuance, well under the 5x floor) must not
        trigger the override - this guard is deliberately narrow to the DPZ-magnitude shape,
        not a general "prefer the bigger number" rule.
        """
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "long_term_debt": 1_000_000_000.0,
            "long_term_debt_and_capital_lease_obligations": 1_200_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_000_000_000.0

    def test_combined_total_does_not_override_when_existing_value_came_from_a_fallback_concept(self) -> None:
        """The override is scoped to specifically the standard "long_term_debt" concept having
        written the small value - it must not re-litigate an ordinary fallback-vs-fallback
        priority contest that already resolved correctly.
        """
        loader = self._make_loader()
        loader._field_mapping["some_other_fallback_debt_concept"] = "long_term_debt"
        loader._fallback_only_fields = frozenset(
            {"long_term_debt_and_capital_lease_obligations", "some_other_fallback_debt_concept"}
        )
        row = {
            "symbol": "TESTCO",
            "fiscal_year": 2025,
            "some_other_fallback_debt_concept": 5_000_000.0,
            "long_term_debt_and_capital_lease_obligations": 500_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 5_000_000.0

    def test_standard_concept_does_not_overwrite_combined_total_on_a_modest_gap(self) -> None:
        """Real fetch order (combined first), but the standard concept's value is only
        modestly smaller (well under the 5x floor) - a legitimate, more-precise update should
        still win normally, not be blocked."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "long_term_debt_and_capital_lease_obligations": 1_200_000_000.0,
            "long_term_debt": 1_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_000_000_000.0

    def test_combined_total_still_never_overwrites_a_large_real_standard_value(self) -> None:
        """Unchanged AAPL-style case (test_pgr_debt_combined_amount_concept_fixed_20260903.py's
        own equivalent test) - a real, large standard-concept value must still be protected.
        """
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
            "long_term_debt_and_capital_lease_obligations": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0
