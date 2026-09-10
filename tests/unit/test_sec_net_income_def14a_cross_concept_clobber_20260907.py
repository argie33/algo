"""Regression test for a cross-concept variant of the DEF 14A scale-error bug (see
test_sec_statements_primary_form_outranks_def14a_scale_error.py for the same-concept case
that fix already covers).

Live-confirmed via PG&E Corp (PCG) FY2025: PG&E's real 10-K tags "ProfitLoss" (not
"NetIncomeLoss" at all - live-confirmed via real SEC companyconcept JSON, PG&E has zero
NetIncomeLoss entries from any 10-K), correctly extracted as $2,703,000,000 (matches
pretax_income - income_tax_expense exactly). But PG&E's DEF 14A Pay vs Performance table
ALSO tags "NetIncomeLoss" - a DIFFERENT concept - mistagged in thousands as raw "2593"
instead of $2,593,000,000. Because _aggregate_concepts's documented "last resort" fallback
(no competing primary-form NetIncomeLoss entry exists) accepts the DEF 14A value for the
"net_income_loss" aggregation column, and sec_base.py's transform() previously used a
blind "last-listed-concept-wins" rule to resolve the two DIFFERENT concepts
("profit_loss" and "net_income_loss") both mapping to db column "net_income", the
DEF-14A-sourced value silently overwrote the correct 10-K figure - a ~1,042,265x
understatement with no data_unavailable/reason flag, caught only by
algo/monitoring/data_patrol/checks/tie_out.py's pretax_to_net_income identity check.

Fixed: transform() now tracks which sec_field's rank (propagated from
_aggregate_concepts_apply_entry_value via the newly-preserved `_rank_{col}` keys - see
sec_statements_aggregate.py's result-building comment) most recently wrote "net_income",
and refuses to let a rank-0 (non-primary-form) concept overwrite a value a rank>0 concept
already wrote for that same db column.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestNetIncomeCrossConceptDef14aClobber:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "net_income", "data_unavailable", "reason"})
        loader._field_mapping = {
            "profit_loss": "net_income",
            "net_income_loss": "net_income",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_rank0_def14a_net_income_loss_does_not_clobber_rank2_profit_loss(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PCG",
            "fiscal_year": 2025,
            # ProfitLoss: real 10-K figure, rank 2 (primary annual-report form).
            "profit_loss": 2_703_000_000.0,
            "_rank_profit_loss": 2,
            # NetIncomeLoss: PG&E's only entry for this concept is a DEF 14A Pay vs
            # Performance re-tag, rank 0 - accepted by _aggregate_concepts as the
            # documented last-resort fallback since no primary-form entry competes with
            # it WITHIN this concept, but it must not win against a DIFFERENT concept's
            # real value.
            "net_income_loss": 2593.0,
            "_rank_net_income_loss": 0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income"] == 2_703_000_000.0

    def test_rank0_net_income_loss_still_used_when_no_competing_concept_wrote_it(self) -> None:
        """Proxy-only reporter (no ProfitLoss/other net_income concept at all) - the
        rank-0 fallback must still populate net_income rather than leaving it NULL,
        matching test_sec_statements_primary_form_outranks_def14a_scale_error.py's
        test_non_primary_form_still_used_as_last_resort_fallback for the same-concept case.
        """
        loader = self._make_loader()
        row = {
            "symbol": "EE",
            "fiscal_year": 2026,
            "net_income_loss": 12_345.0,
            "_rank_net_income_loss": 0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income"] == 12_345.0

    def test_rank2_concept_processed_after_rank0_still_overwrites_correctly(self) -> None:
        """Order independence: a real 10-K concept processed AFTER the DEF 14A fallback
        (dict insertion order can vary by which concept sec_income_statement.py lists
        first) must still win - the guard only ever blocks rank 0 from clobbering an
        existing higher-rank value, never the reverse.
        """
        loader = self._make_loader()
        row = {
            "symbol": "PCG",
            "fiscal_year": 2025,
            "net_income_loss": 2593.0,
            "_rank_net_income_loss": 0,
            "profit_loss": 2_703_000_000.0,
            "_rank_profit_loss": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income"] == 2_703_000_000.0
