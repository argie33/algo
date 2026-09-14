"""Regression test: _check_frozen_pillar_metrics_symbols's "missing row" count compared each
pillar table against the FULL active stock_symbols population, but growth_metrics/
momentum_metrics/value_metrics/quality_metrics/stability_metrics are populated by loaders that
deliberately exclude non-operating companies (ETFs, BDCs, closed-end funds/trusts, blank-check
SPACs) via NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE - see loaders/stock_scores/
growth_scoring.py, momentum_scoring.py, risk_scoring.py, value_metrics.py, loaders/helpers/
vqg_quality_batch.py.

Live-confirmed on the local DB (2026-09-14, goal: "fix the data issues we still have"): the 73
active symbols growth_metrics/quality_metrics/value_metrics were flagging as "missing" were
exactly this excluded population (QQQ/SPY/EFA ETFs, BlackRock/Gabelli/Royce/Franklin/Invesco
closed-end funds, BDCs like MAIN/HTGC/FSK/GAIN, shell/SPAC names like IBAC/BOT/PWRL/DXYZ) - they
will never get a row, so this was a permanent false-positive WARN, the same false-positive shape
as royalty_trust_scoring_population_exclusion_gap_20260914 but in monitoring instead of scoring.
positioning_metrics has no such exclusion (loaders/load_positioning_metrics.py scores every
active symbol including funds/ETFs), so it must NOT get the exclusion clause.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def test_exclusion_clause_applied_only_to_scoring_pillar_tables():
    checker = StalenessChecker(PatrolConfig())
    cursor = MagicMock()
    cursor.fetchone.return_value = (0, 0)

    excluded_tables = {
        "growth_metrics",
        "momentum_metrics",
        "value_metrics",
        "quality_metrics",
        "stability_metrics",
    }
    for table in excluded_tables | {"positioning_metrics"}:
        checker._check_frozen_pillar_metrics_symbols(cursor, table, exclude_non_operating=table in excluded_tables)

    calls_by_table = {}
    for call in cursor.execute.call_args_list:
        sql = call.args[0]
        for table in excluded_tables | {"positioning_metrics"}:
            if f"LEFT JOIN {table} t" in sql:
                calls_by_table[table] = sql

    for table in excluded_tables:
        assert "company_info_sec c" in calls_by_table[table], f"{table} missing non-operating exclusion join"

    assert "company_info_sec c" not in calls_by_table["positioning_metrics"]
