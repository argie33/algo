#!/usr/bin/env python3
"""
Verification tests for Session 281 critical fixes.

Tests verify:
1. FileLockManager uses atomic file creation (no race condition)
2. Dev mode security bypass fixed (no import-time auto-enable)
3. LOCAL_MODE fail-open removed from orchestrator
4. Position creation validates stop price is NOT NULL
5. Buy/sell signal generation fails-closed on price filter errors
"""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestFileLockManagerAtomicity:
    """Verify FileLockManager uses atomic file creation (Session 281 Fix #2)."""

    def test_acquire_uses_os_open_with_o_excl(self) -> None:
        """Verify acquire() uses os.open() with O_CREAT | O_EXCL flag."""
        import inspect

        from utils.db.local_file_lock import FileLockManager

        manager = FileLockManager()
        source = inspect.getsource(manager.acquire)

        # Verify atomic creation pattern is present
        assert "os.O_CREAT | os.O_EXCL" in source, \
            "FileLockManager.acquire() must use os.open() with O_CREAT | O_EXCL for atomicity"
        assert "os.fdopen" in source, \
            "FileLockManager.acquire() must use os.fdopen() to write to atomic-created fd"
        assert "FileExistsError" in source, \
            "FileLockManager.acquire() must catch FileExistsError from O_EXCL race"

    def test_lock_file_creation_is_atomic(self) -> None:
        """Verify two concurrent attempts to acquire same lock only one succeeds."""
        import threading

        from utils.db.local_file_lock import FileLockManager

        with tempfile.TemporaryDirectory() as tmpdir:
            # Override lock directory for testing
            manager = FileLockManager()
            manager.lock_dir = Path(tmpdir)

            results = {"process_1": False, "process_2": False}
            barrier = threading.Barrier(2)

            def try_acquire(process_name: str) -> None:
                """Try to acquire lock with synchronization barrier."""
                barrier.wait()  # Both threads start at same time
                results[process_name] = manager.acquire(lock_key="test-lock", timeout_seconds=1)

            t1 = threading.Thread(target=try_acquire, args=("process_1",))
            t2 = threading.Thread(target=try_acquire, args=("process_2",))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # Exactly ONE should succeed (atomic lock creation)
            acquired_count = sum(1 for v in results.values() if v)
            assert acquired_count == 1, \
                f"Atomic lock should be acquired by exactly 1 process. Got: {results}"


class TestDevModeSecurityBypass:
    """Verify dev mode auto-enable only happens when dev_server directly executed (Session 281 Fix #3)."""

    def test_dev_server_only_enables_in_main(self) -> None:
        """Verify ALLOW_DEV_TOKENS_TEST auto-enable only in if __name__ == "__main__" block."""
        # Read the dev_server.py source
        dev_server_path = Path(__file__).parent.parent / "lambda" / "api" / "dev_server.py"
        with open(dev_server_path) as f:
            source = f.read()

        # Verify the auto-enable happens inside if __name__ == "__main__" block
        assert 'if __name__ == "__main__":' in source, \
            "dev_server.py must guard dev token auto-enable with if __name__ == '__main__'"
        assert 'os.environ["ALLOW_DEV_TOKENS_TEST"] = "true"' in source, \
            "dev_server.py must set ALLOW_DEV_TOKENS_TEST env var"

        # Verify security check when imported
        assert 'raise RuntimeError' in source, \
            "dev_server.py must raise RuntimeError if imported with ALLOW_DEV_TOKENS_TEST enabled"
        assert "CRITICAL SECURITY" in source, \
            "dev_server.py must warn about security bypass risk"

    def test_dev_server_fails_if_imported_with_dev_tokens_enabled(self) -> None:
        """Verify importing dev_server with ALLOW_DEV_TOKENS_TEST=true fails.

        The guard in dev_server.py runs at module-import time (top-level code, not inside a
        function), so it can only be triggered by a fresh import - re-importing an
        already-cached module in this process would be a no-op. Spawn a subprocess that
        imports the module with the flag set beforehand, and assert it fails with the
        expected security error (not just any RuntimeError).
        """
        import subprocess
        import sys

        # "lambda" is a Python keyword and can't appear in a plain `import` statement -
        # importlib.import_module() takes the dotted path as a string instead.
        env = {**os.environ, "ALLOW_DEV_TOKENS_TEST": "true"}
        result = subprocess.run(
            [sys.executable, "-c", "import importlib; importlib.import_module('lambda.api.dev_server')"],
            cwd=str(Path(__file__).parent.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0, (
            "Importing dev_server.py with ALLOW_DEV_TOKENS_TEST=true must fail "
            f"(security bypass guard did not trigger). stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "CRITICAL SECURITY" in result.stderr, (
            f"Expected 'CRITICAL SECURITY' RuntimeError, got stderr={result.stderr!r}"
        )


class TestPositionCreationValidation:
    """Verify position creation validates stop price (Session 281 Fix #4)."""

    def test_position_creation_requires_stop_price(self) -> None:
        """Verify position creation raises error if stop_loss_price is NULL."""
        # Check that validation is present in entry handler
        # This is a documentation test - actual validation happens at DB insert
        source_files = [
            Path(__file__).parent.parent / "algo" / "trading" / "executor_entry_handler.py",
        ]

        for source_file in source_files:
            with open(source_file) as f:
                source = f.read()
                if "NULL or invalid stop_loss" in source:
                    # Validation found
                    assert "stop_loss_price" in source, \
                        "Must validate stop_loss_price in position creation"
                    return

        pytest.fail("Position creation must validate stop_loss_price is NOT NULL")

    def test_database_should_enforce_not_null_on_stop_price(self) -> None:
        """Verify algo_positions.current_stop_price is enforced NOT NULL at the DB level.

        This was a skipped reminder ("TODO Session 282: add migration") for ~40 sessions -
        the migration was actually applied at some point since, but the test kept skipping
        instead of ever confirming it, so a regression (e.g. a migration rollback) would
        have gone unnoticed. Converted to a real assertion.

        Deliberately connects via raw psycopg2 instead of DatabaseContext/get_db_connection:
        tests/conftest.py's pytest_configure() globally patches psycopg2.pool.SimpleConnectionPool
        and utils.db.connection.get_db_connection for the whole suite (CI has no live Postgres
        service, so every other test goes through that hermetic mock) - going through either
        would silently hand back canned fixture rows instead of real schema, always "passing"
        regardless of actual DB state. Skips (doesn't fail) when no live DB is reachable, since
        CI legitimately has none; this is a local-dev schema guard, not a CI gate.
        """
        import psycopg2

        try:
            conn = psycopg2.connect("dbname=stocks user=stocks host=localhost", connect_timeout=3)
        except psycopg2.OperationalError as e:
            pytest.skip(f"No live local Postgres reachable (expected in CI): {e}")

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'algo_positions' AND column_name = 'current_stop_price'
                """
            )
            row = cur.fetchone()
        finally:
            conn.close()

        assert row is not None, "algo_positions.current_stop_price column not found"
        is_nullable = row[0]
        assert is_nullable == "NO", (
            f"algo_positions.current_stop_price must be NOT NULL at the DB level for data "
            f"integrity (currently nullable={is_nullable}); application-level validation in "
            f"executor_entry_handler.py alone is not sufficient defense-in-depth"
        )


class TestBuySellSignalForeignKeyValidation:
    """Verify buy_sell signal generation fails-closed on price filter errors (Session 281 Fix #12)."""

    def test_price_filter_failure_raises_error(self) -> None:
        """Verify buy_sell_daily loader fails-closed if price filtering fails."""
        import inspect

        from loaders.load_buy_sell_daily import SignalsDailyLoader

        source = inspect.getsource(SignalsDailyLoader.run)

        # Verify fail-closed behavior
        assert "raise RuntimeError" in source or "raise Exception" in source, \
            "buy_sell_daily loader must raise error (fail-closed) if price filter fails"
        assert "may cause foreign key errors" not in source, \
            "buy_sell_daily must NOT proceed 'anyway' on filter failures"
        assert "Cannot generate" in source or "critical for data integrity" in source, \
            "buy_sell_daily must explain why price validation is critical"


class TestPartialFillHandling:
    """Audit test: verify partial fill handling (Session 281 Issue #5)."""

    def test_partial_fill_status_tracked(self) -> None:
        """Document that 'partially_filled' status is tracked in reconciliation."""
        import inspect

        from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter

        # Check that partially_filled is referenced
        source = inspect.getsource(AlpacaBrokerAdapter)
        assert "partially_filled" in source, \
            "AlpacaBrokerAdapter must track 'partially_filled' status from broker"

    def test_reconciliation_must_handle_partial_fills(self) -> None:
        """Document: need to verify reconciliation handles partial fills correctly."""
        pytest.skip(
            "AUDIT TODO (Session 282): Verify reconciliation correctly handles partially_filled trades. "
            "Test scenario: entry trade with 100 shares but only 60 filled. "
            "1. Verify position_qty = 60 (not 100) "
            "2. Verify risk calculations use 60 shares "
            "3. Verify exit logic closes 60 shares, not 100"
        )


class TestOrchhestratorLockingFailsClosed:
    """Verify orchestrator fails-closed when DynamoDB locks unavailable (Session 281 Fix #1 + Session 282)."""

    def test_orchestrator_lock_no_failopen_in_local_mode(self) -> None:
        """Verify orchestrator._handle_concurrency_lock() does NOT fail-open in LOCAL_MODE."""
        import inspect

        from algo.orchestration.orchestrator import Orchestrator

        source = inspect.getsource(Orchestrator._handle_concurrency_lock)

        # Verify no fail-open pattern
        assert "return None  # Fail open" not in source, \
            "Orchestrator must NOT fail-open when DynamoDB unavailable"
        assert "fail-open and allow execution" not in source, \
            "Orchestrator must NOT allow concurrent execution without locks"
        assert "Distributed lock system unavailable" in source, \
            "Orchestrator must report lock unavailability clearly"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
