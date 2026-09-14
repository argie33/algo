"""Regression test: StalenessChecker must cover every one of the 19 loader-registry tables
found to have ZERO DataPatrol coverage of any kind (goal session 2026-09-13, "patrols and
checks" comprehensiveness audit).

Found by diffing every `loaders/loader_registry.py` `LOADER_TABLES` entry against the set of
tables referenced by any DataPatrol checker (staleness/coverage/quality/tie-out/everything) -
a systematic audit, not a bug-report-driven one. All 19 tables are real, actively-loaded,
live-confirmed fresh as of 2026-09-13 before adding: algo_metrics_daily, capital_routing_daily,
company_info_sec, company_profile, earnings_calendar, economic_calendar, economic_data,
etf_price_daily, etf_price_monthly, etf_price_weekly, etf_symbols,
institutional_holdings_13f, market_exposure_daily, price_monthly, sec_segment_info,
sec_segment_metrics, sector_performance, sector_rotation_signal, short_interest_finra.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig

_NEW_TABLES = [
    "algo_metrics_daily",
    "capital_routing_daily",
    "company_info_sec",
    "company_profile",
    "earnings_calendar",
    "economic_calendar",
    "economic_data",
    "etf_price_daily",
    "etf_price_monthly",
    "etf_price_weekly",
    "etf_symbols",
    "institutional_holdings_13f",
    "market_exposure_daily",
    "price_monthly",
    "sec_segment_info",
    "sec_segment_metrics",
    "sector_performance",
    "sector_rotation_signal",
    "short_interest_finra",
]


def _cursor_with_latest_date(latest_date_str: str) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        sql = cursor._last_sql
        if "MAX(" in sql:
            return (1, latest_date_str)
        return (0,)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessLoaderRegistryCoverageGap:
    def test_all_19_tables_have_exactly_one_staleness_result_when_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        for table in _NEW_TABLES:
            rows = [r for r in results if r.target_table == table and "age_days" in r.details]
            assert len(rows) == 1, f"{table}: expected exactly 1 staleness result, got {len(rows)}"
            assert rows[0].severity == "info", f"{table}: expected info severity when fresh"
