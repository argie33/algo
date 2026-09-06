"""Regression test: a raw '%' character in fetch_incremental()'s primary anchor query SQL text
(even inside a SQL comment) breaks psycopg2's %s-style parameter substitution.

Found 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, sec_valuations
shares_outstanding_scale_mismatch fix): a docstring-style comment added inline in the SQL
("...-712%/-645% sustainable_growth_rate...") introduced two literal '%' characters. psycopg2
scans the entire query string for '%'-prefixed sequences when doing %s substitution, not just
the intended placeholders - the extra literal '%' characters corrupted the substitution and
broke fetch_incremental() for EVERY symbol (100% failure, `IndexError: tuple index out of
range`) until caught by live-running the loader, not by the existing mocked-cursor unit tests
(which don't exercise real psycopg2 parameter substitution and can't catch this class of bug).

This test guards against a regression by asserting the raw '%' count in the query text exactly
equals the '%s' placeholder count - any other literal '%' (in a comment, a LIKE pattern, etc.)
would fail this and must be rewritten (spell out the percentage in words, or escaping isn't an
option here since '%%' inside a comment would still be visible as literal text to a reader, not
just to psycopg2 - avoiding the character in comments entirely is the safe rule for this file).
"""

import re

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _extract_primary_anchor_sql() -> str:
    import inspect

    source = inspect.getsource(ValueQualityGrowthMetricsLoader.fetch_incremental)
    match = re.search(
        r'"""\s*SELECT CASE WHEN abs\.data_unavailable.*?"""',
        source,
        re.S,
    )
    assert match, "could not locate the primary anchor query in fetch_incremental's source"
    return match.group(0)


def test_primary_anchor_query_percent_count_matches_placeholder_count():
    sql = _extract_primary_anchor_sql()

    total_percent = sql.count("%")
    placeholder_percent = sql.count("%s")

    assert total_percent == placeholder_percent, (
        f"found {total_percent} '%' characters but only {placeholder_percent} are '%s' "
        "placeholders - a stray literal '%' (e.g. in a comment) will corrupt psycopg2's "
        "parameter substitution for this entire query and break fetch_incremental() for "
        "every symbol"
    )
