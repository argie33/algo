"""Regression test: company_profile.sector must accept NULL for data_unavailable rows.

Bug (found 2026-08-18, live evidence): migration 033 added a NOT NULL constraint to
company_profile.sector to fix a positions/sectors JOIN, silently defaulting the handful of
then-existing NULL rows to 'Industrials' (its own comment: "most common sector") - a
fabricated value with no factual basis, directly contradicting this loader's own documented
governance (see load_company_profile.py's SIC-to-GICS mapping comments: "Don't silently
default to 'Other' sector for unmapped SIC codes... must be marked unavailable").

fetch_incremental()'s two data_unavailable branches (no SIC code at all, or a SIC code whose
GICS mapping is genuinely unmapped) correctly omit the "sector" key rather than guess a
value - bulk_insert_manager.py's COPY FORCE_NULL semantics map that omission to SQL NULL,
which the NOT NULL constraint then rejected outright. Live run 2026-08-17 23:12 UTC: 1293/4934
symbols (26.2%) failed to load every single run for exactly this reason, silently losing all
their other company_profile fields too (name, industry, currency_code, etc.) since
bulk_insert() has no partial-row fallback - fixed by migration
1209_drop_company_profile_sector_not_null.sql, which every real consumer's existing
"sector IS NOT NULL" filters (lambda/api/routes/market.py, sectors.py) already made safe.

Runs against a real local Postgres - the NOT NULL constraint only exists at the DB level,
so this can't be caught by a pure-Python/mocked-cursor test.
"""

import psycopg2
import pytest

from utils.bulk_insert_manager import BulkInsertManager


@pytest.fixture
def conn():
    try:
        connection = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
    except psycopg2.OperationalError as e:
        pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")
    yield connection
    connection.rollback()
    connection.close()


class TestCompanyProfileSectorNullable:
    def test_data_unavailable_row_without_sector_key_inserts_cleanly(self, conn) -> None:
        cur = conn.cursor()
        ticker = "ZZTEST_NOSECTOR"
        cur.execute("DELETE FROM company_profile WHERE ticker = %s", (ticker,))
        conn.commit()

        from utils.db.pooled_context_var import set_pooled_connection

        set_pooled_connection(conn)
        try:
            mgr = BulkInsertManager("company_profile", ("ticker",))
            # Mirrors fetch_incremental()'s sic_code_unmapped/no_sic_code_available rows:
            # no "sector" key at all - must not raise, and must land as real NULL, not a
            # guessed value.
            result = mgr.bulk_insert(
                [
                    {
                        "ticker": ticker,
                        "data_unavailable": True,
                        "reason": "sic_code_unmapped:9999",
                        "updated_at": "2026-08-18 00:00:00",
                    }
                ]
            )
            assert result == 1

            cur.execute("SELECT sector, data_unavailable, reason FROM company_profile WHERE ticker = %s", (ticker,))
            row = cur.fetchone()
            assert row is not None
            assert row[0] is None, "sector must be real NULL, not a guessed/fabricated value"
            assert row[1] is True
            assert row[2] == "sic_code_unmapped:9999"
        finally:
            set_pooled_connection(None)
            cur.execute("DELETE FROM company_profile WHERE ticker = %s", (ticker,))
            conn.commit()
