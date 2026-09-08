"""Regression test: every field_mapping target column must also be listed in that config's
schema_cols frozenset, or every fetch of that concept raises sec_base.py's "not in target
schema" RuntimeError for EVERY symbol.

FOUND 2026-09-07 (goal session: "scores don't make sense, reloads fail every time" audit):
migration 1270 added net_income_attributable_to_common (annual/quarterly income_statement)
and _INCOME_FIELD_MAPPING was updated to map two SEC concepts to it, but the sibling
schema_cols frozensets in get_income_statement_config() were never updated to include it -
unlike goodwill_impairment_loss (migration 1271), added correctly in both places the same
day. Live-confirmed: annual/quarterly_income_statement extraction raised this RuntimeError
for essentially every symbol in the universe (BTU, BULL, BUSE, BV, ... CYRX, ...), even after
the migration 1270/1271 DB columns were applied - self._schema_cols is a hardcoded Python
frozenset, not introspected from the live DB, so the code fix is what was missing, not the
DB schema. test_financial_statements_field_mapping_completeness.py already guards
field_mapping-vs-fetched-concepts; this guards the field_mapping-vs-schema_cols half of the
same "code needs updating in two places" bug class that test doesn't cover.
"""

from loaders.helpers.financial_statements_balance_config import get_balance_sheet_config
from loaders.helpers.financial_statements_cashflow_config import get_cash_flow_config
from loaders.helpers.financial_statements_income_config import get_income_statement_config


def _assert_field_mapping_targets_in_schema_cols(cfg: dict) -> None:
    schema_cols = cfg["schema_cols"]
    field_mapping = cfg["field_mapping"]
    missing = sorted({target for target in field_mapping.values() if target not in schema_cols})
    assert not missing, (
        f"[{cfg['table_name']}] field_mapping targets missing from schema_cols "
        f"(every fetch of these will raise 'not in target schema' for every symbol): {missing}"
    )


class TestSchemaColsCoversFieldMappingTargets:
    def test_income_statement_annual(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_income_statement_config("annual"))

    def test_income_statement_quarterly(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_income_statement_config("quarterly"))

    def test_balance_sheet_annual(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_balance_sheet_config("annual"))

    def test_balance_sheet_quarterly(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_balance_sheet_config("quarterly"))

    def test_cash_flow_annual(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_cash_flow_config("annual"))

    def test_cash_flow_quarterly(self) -> None:
        _assert_field_mapping_targets_in_schema_cols(get_cash_flow_config("quarterly"))
