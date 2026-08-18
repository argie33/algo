"""Tests for freshness panel enhancements (data quality, coverage, failure patterns)."""

import inspect
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from dashboard import freshness_enhancements
from dashboard.freshness_enhancements import (
    enrich_health_item_with_api_diagnostics,
    enrich_health_item_with_coverage,
    enrich_health_item_with_data_quality,
    enrich_health_item_with_failure_pattern,
)


class TestDataQualityEnrichment:
    """Test data quality metrics (NULLs, duplicates, constraint violations)."""

    def test_enrich_with_quality_metrics(self) -> None:
        """Enrich health item with data quality checks."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
            "row_count": 1000000,
        }

        # Should gracefully handle when DB not available (cur=None creates own connection)
        enriched = enrich_health_item_with_data_quality(health_item)
        assert "quality_status" in enriched
        assert enriched["quality_status"] in ("ok", "warning", "error", "unknown")

    def test_enrich_skips_empty_tables(self) -> None:
        """Skip quality checks for empty tables."""
        health_item = {
            "tbl": "price_daily",
            "st": "empty",
            "row_count": 0,
        }

        enriched = enrich_health_item_with_data_quality(health_item)
        assert enriched["quality_status"] == "unknown"  # No data to check

    def test_enrich_skips_deprecated_tables(self) -> None:
        """Skip quality checks for DEPRECATED-status tables.

        FIX 2026-08-18: DEPRECATED tables (e.g. ttm_balance_sheet - never created by any
        migration, its loader stopped declaring it in output_tables) were still querying
        `SELECT ... FROM "<table>"` and crashing with UndefinedTable on every dashboard
        health-panel load, live-confirmed as 51 occurrences of the same crash across
        logs/*.log. Caught by the broad except in enrich_health_item_with_data_quality (so it
        never propagated), but only after a lower-level DB wrapper already logged it at ERROR
        - pure noise on every single load. "DEPRECATED" status must skip the query entirely,
        same as "empty"/"error", not just be caught after the fact.
        """
        health_item = {
            "tbl": "ttm_balance_sheet",
            "st": "DEPRECATED",
            # Nonzero on purpose: proves the DEPRECATED branch itself skips the query,
            # not the pre-existing row_count==0 branch.
            "row_count": 5,
        }

        enriched = enrich_health_item_with_data_quality(health_item)
        assert enriched["quality_status"] == "unknown"  # No data to check - never queried the table

    def test_handles_missing_table_name(self) -> None:
        """Gracefully handle health items without table name."""
        health_item = {"st": "ok"}

        enriched = enrich_health_item_with_data_quality(health_item)
        assert enriched == health_item  # Unchanged


class TestCoverageEnrichment:
    """Test coverage completeness metrics (symbol gaps)."""

    def test_enrich_with_coverage_metrics(self) -> None:
        """Enrich health item with coverage checks."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
            "row_count": 1000000,
        }

        enriched = enrich_health_item_with_coverage(health_item)

        # May have coverage if DB available
        if "symbol_coverage_pct" in enriched:
            assert 0 <= enriched["symbol_coverage_pct"] <= 100
            assert enriched["coverage_status"] in ("complete", "partial", "sparse", "unknown")

    def test_skips_non_symbol_tables(self) -> None:
        """Skip coverage checks for tables without symbols."""
        health_item = {
            "tbl": "schema_version",  # Not in symbol_tables set
            "st": "ok",
            "row_count": 100,
        }

        enriched = enrich_health_item_with_coverage(health_item)
        assert "symbol_coverage_pct" not in enriched  # Not applicable


class TestFailurePatternEnrichment:
    """Test failure pattern analysis (rate, windows, MTTR)."""

    def test_enrich_with_failure_patterns(self) -> None:
        """Enrich health item with failure analysis."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
        }

        enriched = enrich_health_item_with_failure_pattern(health_item)

        # Fields added even if data unavailable
        assert "failure_rate_30d" in enriched
        assert "failure_pattern" in enriched
        assert "mttr_hours" in enriched
        assert "last_5_runs" in enriched
        assert "recovery_trend" in enriched

        # Values should be reasonable
        if enriched["failure_rate_30d"] is not None:
            assert 0 <= enriched["failure_rate_30d"] <= 100
        if enriched["mttr_hours"] is not None:
            assert enriched["mttr_hours"] >= 0
        if enriched["recovery_trend"] is not None:
            assert enriched["recovery_trend"] in ("improving", "stable", "degrading")


class TestAPIDiagnosticsEnrichment:
    """Test API diagnostics (rate limits, auth, service status)."""

    def test_rate_limit_detection(self) -> None:
        """Detect rate limit errors."""
        health_item = {
            "tbl": "price_daily",
            "loader_error": "HTTP 429: rate limit hit, quota 100/100 used",
        }

        enriched = enrich_health_item_with_api_diagnostics(health_item)
        assert enriched["api_status"] == "rate_limited"
        assert "exponential backoff" in enriched["retry_strategy"]

    def test_auth_failure_detection(self) -> None:
        """Detect authentication failures."""
        health_item = {
            "tbl": "price_daily",
            "loader_error": "HTTP 401: unauthorized - credentials expired",
        }

        enriched = enrich_health_item_with_api_diagnostics(health_item)
        assert enriched["api_status"] == "auth_failed"
        assert "rotation" in enriched["retry_strategy"]

    def test_service_down_detection(self) -> None:
        """Detect service unavailable errors."""
        health_item = {
            "tbl": "price_daily",
            "loader_error": "HTTP 503: service unavailable",
        }

        enriched = enrich_health_item_with_api_diagnostics(health_item)
        assert enriched["api_status"] == "service_down"

    def test_ok_status_for_normal_errors(self) -> None:
        """Default to ok for non-API errors."""
        health_item = {
            "tbl": "price_daily",
            "loader_error": "Connection timeout",
        }

        enriched = enrich_health_item_with_api_diagnostics(health_item)
        assert enriched["api_status"] == "ok"


class TestEnrichmentChaining:
    """Test that enrichments stack correctly."""

    def test_chain_all_enrichments(self) -> None:
        """Apply all enrichments to a single item."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
            "row_count": 1000000,
        }

        # Chain all enrichments
        enriched = enrich_health_item_with_data_quality(health_item)
        enriched = enrich_health_item_with_coverage(enriched)
        enriched = enrich_health_item_with_failure_pattern(enriched)
        enriched = enrich_health_item_with_api_diagnostics(enriched)

        # All enrichments should be present (though values may be None if DB unavailable)
        assert "quality_status" in enriched
        assert "failure_rate_30d" in enriched
        assert "api_status" in enriched

    def test_enrichments_dont_lose_original_fields(self) -> None:
        """Enrichments add fields but preserve originals."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
            "row_count": 1000000,
            "age_hours": 2.5,
        }

        enriched = enrich_health_item_with_data_quality(health_item)

        assert enriched["tbl"] == "price_daily"
        assert enriched["st"] == "ok"
        assert enriched["row_count"] == 1000000
        assert enriched["age_hours"] == 2.5


class TestErrorHandling:
    """Test graceful handling of errors."""

    def test_handles_invalid_input_type(self) -> None:
        """Gracefully handle non-dict input."""
        invalid_input = "not a dict"

        result = enrich_health_item_with_data_quality(invalid_input)
        assert result == invalid_input  # Unchanged

    def test_handles_none_input(self) -> None:
        """Gracefully handle None input."""
        result = enrich_health_item_with_data_quality(None)
        assert result is None

    def test_enrichment_failures_dont_crash_panel(self) -> None:
        """If enrichment fails, system gracefully degrades."""
        health_item = {
            "tbl": "price_daily",
            "st": "ok",
        }

        # All enrichments should complete even if parts fail
        try:
            enriched = enrich_health_item_with_data_quality(health_item)
            enriched = enrich_health_item_with_coverage(enriched)
            enriched = enrich_health_item_with_failure_pattern(enriched)
            enriched = enrich_health_item_with_api_diagnostics(enriched)

            # Should reach here without exception
            assert True
        except Exception as e:
            pytest.fail(f"Enrichment chain raised exception: {e}")


class TestQualityAndCoverageSQLBugs:
    """Regression tests for two bugs confirmed live against the real dev DB 2026-07-27:

    1. `_run_data_quality_checks`'s duplicate-row check used `COUNT(DISTINCT *::text)`,
       which is not valid Postgres syntax (`*` cannot be cast directly) - it raised
       psycopg2.errors.SyntaxError on every single call, silently swallowed by a debug-level
       except, so "duplicate rows detected" was dead functionality from the day it shipped.
    2. `_calculate_coverage` queried a table `universe_stocks` with a column `is_active` -
       neither exists in this schema (confirmed via information_schema.columns); the real
       table is `stock_symbols` with column `active`. Every coverage check silently failed.

    Both are now fixed to use bounded subqueries against real schema. These tests use a
    MagicMock cursor (not a real DB connection, matching this test file's existing
    convention) to pin the actual SQL text emitted, since the bugs were syntax/schema
    errors that only a real Postgres connection would surface - a happy-path mock alone
    can't catch them, so we assert on the query strings directly.
    """

    def test_duplicate_check_does_not_use_invalid_star_cast_syntax(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        freshness_enhancements._run_data_quality_checks("price_daily", cur)

        executed_sql = [call.args[0] for call in cur.execute.call_args_list]
        assert not any("DISTINCT *::text" in sql for sql in executed_sql), (
            "Found the invalid `COUNT(DISTINCT *::text)` pattern again - `*` cannot be cast "
            "directly in Postgres; this raises SyntaxError on every call in production."
        )

    def test_null_and_duplicate_checks_bound_the_scan_via_subquery_limit(self) -> None:
        """A bare `LIMIT N` on an unwrapped aggregate query only limits the 1-row result, not
        rows scanned - confirmed live as an unbounded 8.7M-row full scan on price_daily. The
        fix wraps the scan itself in a LIMIT'd subquery, which this pins."""
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        freshness_enhancements._run_data_quality_checks("price_daily", cur)

        executed_sql = [call.args[0] for call in cur.execute.call_args_list]
        assert any("FROM (SELECT" in sql and "LIMIT" in sql for sql in executed_sql), (
            "Expected at least one query to bound its scan via a LIMIT'd subquery, not a "
            "bare LIMIT tacked onto an aggregate query."
        )

    def test_coverage_uses_real_stock_symbols_table_not_universe_stocks(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [(100,), (95,)]
        cur.fetchall.return_value = []
        freshness_enhancements._calculate_coverage("price_daily", cur)

        executed_sql = [call.args[0] for call in cur.execute.call_args_list]
        assert not any("universe_stocks" in sql for sql in executed_sql), (
            "Found a reference to `universe_stocks` again - this table does not exist in the "
            "schema (confirmed live: psycopg2.errors.UndefinedTable). The real table is "
            "`stock_symbols`."
        )
        assert not any("is_active" in sql for sql in executed_sql), (
            "Found `is_active` again - stock_symbols's boolean column is named `active`, "
            "confirmed live via information_schema.columns."
        )
        assert any("stock_symbols" in sql and "active = true" in sql for sql in executed_sql), (
            "Expected the coverage query to use the real stock_symbols.active column."
        )

    def test_source_does_not_order_by_market_cap(self) -> None:
        """stock_symbols has no market_cap column at all (confirmed via
        information_schema.columns) - ordering by it would raise UndefinedColumn even after
        fixing the table/column name bugs above."""
        source = inspect.getsource(freshness_enhancements)
        assert "ORDER BY market_cap" not in source

    def test_tables_without_created_at_are_mapped_to_real_columns(self) -> None:
        """critical_columns_map.get(table_name, ["created_at"]) silently defaults to a
        `created_at` NULL check for any table not explicitly listed. Confirmed live
        2026-08-10 (psycopg2.errors.UndefinedColumn, 36 occurrences in one dev-server
        session) that algo_performance_metrics, circuit_breaker_status, and
        sec_cash_flow_metrics all fall through to that default despite none of them having
        a created_at column - the check silently no-op'd every single call, exactly the bug
        class this file's own map comments already describe fixing for 10 other tables."""
        for table_name, real_column in [
            ("algo_performance_metrics", "metric_date"),
            ("circuit_breaker_status", "check_date"),
            ("sec_cash_flow_metrics", "symbol"),
        ]:
            cur = MagicMock()
            cur.fetchone.return_value = (0, 0)
            freshness_enhancements._run_data_quality_checks(table_name, cur)

            executed_sql = [call.args[0] for call in cur.execute.call_args_list]
            assert not any('"created_at"' in sql for sql in executed_sql), (
                f"{table_name} has no created_at column but was checked against it anyway "
                f"(silently swallowed by the except - confirmed live via psycopg2.errors.UndefinedColumn)."
            )
            assert any(f'"{real_column}"' in sql for sql in executed_sql), (
                f"Expected {table_name} to be checked against its real column {real_column}."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
