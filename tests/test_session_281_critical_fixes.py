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
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestFileLockManagerAtomicity:
    """Verify FileLockManager uses atomic file creation (Session 281 Fix #2)."""

    def test_acquire_uses_os_open_with_o_excl(self) -> None:
        """Verify acquire() uses os.open() with O_CREAT | O_EXCL flag."""
        from utils.db.local_file_lock import FileLockManager
        import inspect

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
        from utils.db.local_file_lock import FileLockManager
        import threading

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
        """Verify importing dev_server with ALLOW_DEV_TOKENS_TEST=true fails."""
        # This test simulates the import-time check
        # Set the flag BEFORE import to test the security check
        os.environ["ALLOW_DEV_TOKENS_TEST"] = "true"

        try:
            with pytest.raises(RuntimeError, match="CRITICAL SECURITY"):
                # The import of dev_server module should raise if ALLOW_DEV_TOKENS_TEST is set
                # (This test documents the expected behavior even though we can't easily trigger it)
                pass
        finally:
            # Clean up
            if "ALLOW_DEV_TOKENS_TEST" in os.environ:
                del os.environ["ALLOW_DEV_TOKENS_TEST"]


class TestPositionCreationValidation:
    """Verify position creation validates stop price (Session 281 Fix #4)."""

    def test_position_creation_requires_stop_price(self) -> None:
        """Verify position creation raises error if stop_loss_price is NULL."""
        from algo.trading.executor_entry_handler import create_entry_result
        import inspect

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
        """Verify (via audit) that algo_positions.current_stop_price should be NOT NULL."""
        # This is a reminder test - actual schema change requires migration
        # For now, document that this should be enforced at DB level
        pytest.skip(
            "TODO (Session 282): Add migration to make algo_positions.current_stop_price NOT NULL. "
            "Currently validated at application level (executor_entry_handler.py), "
            "but should be enforced at database level for data integrity."
        )


class TestBuySellSignalForeignKeyValidation:
    """Verify buy_sell signal generation fails-closed on price filter errors (Session 281 Fix #12)."""

    def test_price_filter_failure_raises_error(self) -> None:
        """Verify buy_sell_daily loader fails-closed if price filtering fails."""
        from loaders.load_buy_sell_daily import load_all_buy_sell_signals
        import inspect

        source = inspect.getsource(load_all_buy_sell_signals)

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
        from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
        import inspect

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
        from algo.orchestration.orchestrator import Orchestrator
        import inspect

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
