"""Regression test for adding us-gaap:SecuredDebt/NotesPayableCurrent
(utils/external/sec_balance_sheet.py), found via the 2026-09-09 xbrl_concept_coverage_scan.py
comment-leak fix (see test_xbrl_concept_coverage_comment_leak_20260909.py) - both concepts
were quoted in comments explaining DE's/AFL's debt-tagging behavior but never actually
fetched. 400 (SecuredDebt) and 834 (NotesPayableCurrent) real filers tag them
(scan-confirmed post-fix).

SecuredDebt supersedes the prior "deliberately not mapped, no summing mechanism" decision
(2026-09-03, DE debt gap investigation): made fallback-only instead - DebtCurrent (a real,
more specific concept DE also tags) is listed/processed first and already claims
short_term_debt for DE, so SecuredDebt's own fallback-only check correctly skips DE and
never silently drops its DebtCurrent value; a filer that tags ONLY SecuredDebt (no
CommercialPaper/ShortTermBorrowings/DebtCurrent/etc.) now gets a real value instead of NULL.

NotesPayableCurrent is the current-portion split of the already-fetched bare "NotesPayable"
concept (which targets long_term_debt) - same generic-name caution as DebtCurrent, fallback-
only so a more specific concept always wins.
"""

import inspect

from loaders.helpers.financial_statements_balance_config import (
    _BALANCE_FIELD_MAPPING,
    _DEBT_FALLBACK_ONLY_FIELDS,
)
from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_balance_sheet_config
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestSecuredDebtNotesPayableCurrentAdded:
    def test_concepts_map_to_short_term_debt_and_are_fallback_only(self) -> None:
        for concept in ("SecuredDebt", "NotesPayableCurrent"):
            target_key = _to_snake(concept)
            assert _BALANCE_FIELD_MAPPING[target_key] == "short_term_debt"
            assert target_key in _DEBT_FALLBACK_ONLY_FIELDS

    def test_concepts_are_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_balance_sheet)
        assert "SecuredDebt" in source
        assert "NotesPayableCurrent" in source

    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_balance_sheet_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._fallback_only_fields = config.get("fallback_only_fields", frozenset())
        return loader

    def test_secured_debt_only_filer_fills_short_term_debt(self) -> None:
        """A filer tagging only SecuredDebt (no DebtCurrent/CommercialPaper/etc. at all)
        previously got NULL short_term_debt despite real data being present."""
        loader = self._make_loader()
        row = {"symbol": "TEST", "fiscal_year": 2025, "secured_debt": 6_596_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 6_596_000.0

    def test_secured_debt_never_overwrites_debt_current(self) -> None:
        """DE-style collision: DebtCurrent (a real, more specific concept) must keep its
        value; SecuredDebt (fallback-only) must not silently drop it."""
        loader = self._make_loader()
        row = {
            "symbol": "DE",
            "fiscal_year": 2025,
            "debt_current": 13_796_000.0,
            "secured_debt": 6_596_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 13_796_000.0

    def test_notes_payable_current_fills_short_term_debt_when_nothing_else_did(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "TEST", "fiscal_year": 2025, "notes_payable_current": 1_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 1_000_000.0

    def test_notes_payable_current_never_overwrites_commercial_paper(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "commercial_paper": 7_980_000.0,
            "notes_payable_current": 1_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 7_980_000.0
