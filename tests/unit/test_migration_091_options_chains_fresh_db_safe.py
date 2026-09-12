"""Regression test: migration 091 must not hard-fail on a genuinely fresh database.

Found auditing this session's options work (goal session 2026-09-12): options_chains and
iv_history are both created for the first time by later migrations (1283/1284), which run
AFTER 091 in migrations/run.py's numeric ordering. migrations/run.py's apply_all_pending()
stops at the first failed migration, so any bare (non-`IF EXISTS`) DDL against either table
in 091 would block every migration numbered after it (127 through 9999) on a cold start -
this only went unnoticed because every already-provisioned environment had both tables
created out-of-band before 091 first ran there.
"""

from pathlib import Path

MIGRATION_091 = (
    Path(__file__).resolve().parent.parent.parent / "migrations" / "versions" / "091_fix_options_schema_for_signals.py"
)


def _source() -> str:
    return MIGRATION_091.read_text(encoding="utf-8")


def test_options_chains_add_column_alter_is_guarded():
    # The RENAME COLUMN statement is separately guarded by an `if cur.fetchone():` check
    # against information_schema.columns, which can only be truthy if the table already
    # exists - only the unconditional ADD COLUMN alter needed the IF EXISTS fix.
    src = _source()
    assert "ALTER TABLE IF EXISTS options_chains\n            ADD COLUMN IF NOT EXISTS iv" in src


def test_create_index_statements_check_table_exists_first():
    src = _source()
    assert "to_regclass('iv_history')" in src
    assert "to_regclass('options_chains')" in src
