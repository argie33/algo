"""Regression test: ConsolidatedFinancialStatementsLoader.output_tables (loaders/
load_financial_statements.py) listed 9 tables including ttm_income_statement/ttm_cash_flow/
ttm_balance_sheet, even though get_all_statement_configs() dropped every ("*", "ttm") combo
2026-07-13 (SecEdgarStatementLoader never accepted period='ttm'). Since runner.py marks every
name in output_tables COMPLETED/FAILED after each run (SESSION 113 FIX), this made all three
phantom tables report COMPLETED/100% on every real run - live-confirmed in data_loader_status
(execution_started 2026-08-18 00:04, all three COMPLETED/100.00%).

ttm_income_statement/ttm_cash_flow are real tables frozen since 2026-05-22 (already worked
around via exclusions in pipeline_health.py's KNOWN_DEPRECATED_TABLES and
loader_registry.py's LOADER_FILE_TO_TABLES, both of which say the loader's own config was the
actual thing that needed fixing). ttm_balance_sheet was never created by any migration at all
- balance sheet is a point-in-time snapshot, not a trailing-twelve-month aggregate, so it was
never a coherent concept - and querying it crashes with UndefinedTable (live-reproduced via
dashboard/freshness_enhancements.py's per-table duplicate-row quality check, which iterates
every table data_loader_status knows about).
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def test_output_tables_excludes_dead_ttm_combos() -> None:
    output_tables = ConsolidatedFinancialStatementsLoader.output_tables

    for dead in ("ttm_income_statement", "ttm_cash_flow", "ttm_balance_sheet"):
        assert dead not in output_tables, (
            f"{dead} must not be in output_tables - get_all_statement_configs() never emits "
            f"a 'ttm' period combo (dropped 2026-07-13), so this loader never writes to it, "
            f"and runner.py falsely marks it COMPLETED on every run regardless"
        )

    assert set(output_tables) == {
        "annual_income_statement",
        "quarterly_income_statement",
        "annual_balance_sheet",
        "quarterly_balance_sheet",
        "annual_cash_flow",
        "quarterly_cash_flow",
    }, f"output_tables should be exactly the 6 real annual/quarterly combos, got {output_tables}"
