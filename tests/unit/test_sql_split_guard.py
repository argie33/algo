"""Regression tests for utils/db/sql_split_guard.py.

Guards sector/industry performance queries (lambda/api/routes/sectors.py,
lambda/api/routes/industries.py) against a stock split silently corrupting a
per-stock return computed directly from two price_daily.close values - see
module docstring on sql_split_guard.py for the full story.
"""

import psycopg2
import pytest

from utils.db.sql_split_guard import split_guard_sql


class TestSplitGuardSqlGeneration:
    def test_substitutes_given_column_expressions(self):
        sql = split_guard_sql("p1.close", "pnow.close")
        assert "p1.close" in sql
        assert "pnow.close" in sql

    def test_no_stray_percent_sign(self):
        """CRITICAL: this SQL is spliced into an f-string that psycopg2 later executes as a
        parameterized query (cur.execute(query, (limit, offset))). psycopg2 scans the WHOLE
        query text - including comments and generated fragments - for %s-style placeholders;
        one unescaped literal percent sign anywhere throws IndexError: tuple index out of
        range at execute() time, unrelated to any actual placeholder. This exact bug was
        introduced and caught live during this fix."""
        sql = split_guard_sql("p1.close", "pnow.close")
        assert "%" not in sql

    def test_uses_not_wrapping_the_whole_condition(self):
        # Must exclude (return False) only when BOTH the gap floor AND ratio match are true -
        # a bare "NOT EXISTS(...)" without the gap floor would treat 25%+ ordinary volatility
        # as a candidate split (see test_matches_* below).
        sql = split_guard_sql("a", "b")
        assert sql.startswith("NOT (")


class TestSplitGuardSqlAgainstLiveEngine:
    """Executes the generated SQL directly against Postgres (SELECT-only, no table
    dependency) to verify it's syntactically valid and semantically correct - a pure string
    assertion can't catch a SQL syntax error or a sign/direction mistake in the expression.
    """

    @pytest.fixture(scope="class")
    def cur(self):
        try:
            conn = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
        except psycopg2.OperationalError:
            pytest.skip("No local Postgres instance available")
        cur = conn.cursor()
        yield cur
        cur.close()
        conn.close()

    def _eval(self, cur, close_a: float, close_b: float) -> bool:
        sql = split_guard_sql(str(close_a), str(close_b))
        cur.execute(f"SELECT {sql}")
        row = cur.fetchone()
        return bool(row[0])

    def test_clean_2_for_1_split_is_excluded(self, cur):
        # $200 -> $100 close-to-close: matches split ratio 2, gap well above the 30% floor.
        assert self._eval(cur, 200.0, 100.0) is False

    def test_clean_1_for_10_reverse_split_is_excluded(self, cur):
        assert self._eval(cur, 1.0, 10.0) is False

    def test_ordinary_10_pct_move_not_excluded(self, cur):
        assert self._eval(cur, 100.0, 110.0) is True

    def test_ordinary_25_pct_penny_stock_move_not_excluded(self, cur):
        """Regression: a bare ratio-match (no gap floor) would treat this as a fake 5-for-4
        split and wrongly exclude a real, if volatile, penny-stock return - the exact
        opposite failure mode this guard exists to prevent. A clean 1.25 ratio (25% gap) is
        below the 30% floor tick_validator.py itself requires before ever considering a
        ratio as a candidate split, so this must NOT be excluded."""
        assert self._eval(cur, 4.00, 3.20) is True  # ratio exactly 1.25

    def test_large_move_matching_1_5_ratio_is_excluded(self, cur):
        assert self._eval(cur, 150.0, 100.0) is False

    def test_extreme_move_not_matching_any_clean_ratio_not_excluded(self, cur):
        # A genuine 40% crash (e.g. delisting/bad news) shouldn't match any clean ratio.
        assert self._eval(cur, 100.0, 60.0) is True
