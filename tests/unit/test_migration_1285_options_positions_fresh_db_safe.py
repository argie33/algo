"""Regression test: migration 1285 (algo_options_positions) must be safe to apply to a
genuinely fresh/empty database.

Same bug class this session's CLAUDE.md documents repeatedly (options_chains/iv_history never
had a CREATE TABLE anywhere in this repo's history until migrations 1283/1284 fixed it):
migrations/run.py's apply_all_pending() runs migrations in ascending numeric order and stops
at the FIRST failure, so any bare (non-`IF NOT EXISTS`) DDL in a brand new migration would
block every migration numbered after it on a cold start. This is a genuinely new table (no
prior migration ever created or altered it), so this test simply proves every statement is
idempotent/guarded rather than proving a pre-existing gap was closed.
"""

from pathlib import Path

MIGRATION_1285 = (
    Path(__file__).resolve().parent.parent.parent / "migrations" / "versions" / "1285_create_algo_options_positions.sql"
)


def _source() -> str:
    return MIGRATION_1285.read_text(encoding="utf-8")


def test_migration_file_exists():
    assert MIGRATION_1285.exists(), f"Expected migration file at {MIGRATION_1285}"


def test_create_table_is_guarded():
    src = _source()
    assert "CREATE TABLE IF NOT EXISTS algo_options_positions" in src


def test_indexes_are_guarded():
    src = _source()
    assert "CREATE INDEX IF NOT EXISTS idx_algo_options_positions_symbol_status" in src
    assert "CREATE INDEX IF NOT EXISTS idx_algo_options_positions_status" in src


def test_no_unguarded_ddl_statements():
    """Every top-level DDL statement in this migration must be defensive (IF NOT EXISTS /
    IF EXISTS) - a fresh DB has none of these objects yet, and a re-run must also not fail."""
    src = _source()
    statements = [s.strip() for s in src.split(";") if s.strip() and not s.strip().startswith("--")]
    for stmt in statements:
        upper = stmt.upper()
        if upper.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in upper, f"Unguarded CREATE TABLE: {stmt[:80]}"
        elif upper.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
            assert "IF NOT EXISTS" in upper, f"Unguarded CREATE INDEX: {stmt[:80]}"
        elif upper.startswith("ALTER TABLE"):
            assert "IF EXISTS" in upper, f"Unguarded ALTER TABLE: {stmt[:80]}"


def test_status_check_constraint_covers_full_lifecycle():
    """Spec section 5's lifecycle: open -> assigned -> closed/rolled/expired."""
    src = _source()
    assert "CHECK (status IN ('open', 'assigned', 'closed', 'rolled', 'expired'))" in src


def test_option_type_and_strategy_leg_check_constraints_present():
    src = _source()
    assert "CHECK (option_type IN ('put', 'call'))" in src
    assert "CHECK (strategy_leg IN ('csp', 'covered_call'))" in src


def test_rolled_from_id_is_self_referential_fk():
    src = _source()
    assert "rolled_from_id BIGINT REFERENCES algo_options_positions(id)" in src
