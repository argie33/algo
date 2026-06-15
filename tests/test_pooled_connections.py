#!/usr/bin/env python3
"""Test suite for connection pool optimization (Issue #7 fix).

Tests the PooledConnectionManager, PoolSemaphore, and DatabaseContext integration
to ensure connection reuse reduces pool churn from 5-10 creates/closes per loader
to 1 create/1 release per loader.
"""

import unittest
import threading
import time
from unittest.mock import patch, MagicMock
import psycopg2.pool

# Import the components we're testing
from utils.db.pooled_connection_manager import PoolSemaphore, PooledConnectionManager
from utils.db.pooled_context_var import (
    set_pooled_connection,
    get_pooled_connection,
    has_pooled_connection,
)

class TestPoolSemaphore(unittest.TestCase):
    """Test PoolSemaphore for backpressure control."""

    def test_semaphore_acquire_release(self):
        """Test basic acquire/release."""
        sem = PoolSemaphore(max_concurrent=2, timeout_sec=1)

        # Should succeed
        self.assertTrue(sem.acquire("loader1"))
        self.assertTrue(sem.acquire("loader2"))

        # Should timeout - all slots taken
        self.assertFalse(sem.acquire("loader3", timeout=0.1))

        # Release and try again
        sem.release("loader1")
        self.assertTrue(sem.acquire("loader3"))

        # Cleanup
        sem.release("loader2")
        sem.release("loader3")

    def test_semaphore_status(self):
        """Test status reporting."""
        sem = PoolSemaphore(max_concurrent=3, timeout_sec=1)

        status = sem.status()
        self.assertEqual(status["active_count"], 0)
        self.assertEqual(status["max_concurrent"], 3)
        self.assertEqual(status["available_slots"], 3)

        sem.acquire("loader1")
        status = sem.status()
        self.assertEqual(status["active_count"], 1)
        self.assertEqual(status["available_slots"], 2)

        sem.release("loader1")

    def test_semaphore_concurrent_access(self):
        """Test concurrent acquire/release from multiple threads."""
        sem = PoolSemaphore(max_concurrent=5, timeout_sec=5)
        results = []

        def try_acquire(name):
            success = sem.acquire(name)
            results.append(success)
            if success:
                time.sleep(0.1)
                sem.release(name)

        threads = [
            threading.Thread(target=try_acquire, args=(f"loader{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should eventually succeed
        self.assertEqual(len(results), 10)
        self.assertEqual(sum(results), 10)

class TestPooledConnectionManager(unittest.TestCase):
    """Test PooledConnectionManager lifecycle."""

    @patch("utils.db.connection._get_connection_pool")
    def test_manager_acquire_release(self, mock_get_pool):
        """Test acquire and release flow."""
        # Setup mock pool
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)
        mock_conn = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        # Test acquire
        manager = PooledConnectionManager("test_loader", timeout_sec=5)
        conn = manager.acquire()

        self.assertIsNotNone(conn)
        self.assertEqual(conn, mock_conn)
        self.assertTrue(manager.is_acquired())

        # Test release
        manager.release()
        mock_pool.putconn.assert_called_once_with(mock_conn)
        self.assertFalse(manager.is_acquired())

    @patch("utils.db.connection._get_connection_pool")
    def test_manager_double_acquire_error(self, mock_get_pool):
        """Test that double acquire raises error."""
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)
        mock_pool.getconn.return_value = MagicMock()
        mock_get_pool.return_value = mock_pool

        manager = PooledConnectionManager("test_loader")
        manager.acquire()

        # Second acquire should raise
        with self.assertRaises(RuntimeError):
            manager.acquire()

        manager.release()

    @patch("utils.db.connection._get_connection_pool")
    def test_manager_idempotent_release(self, mock_get_pool):
        """Test that release is idempotent."""
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)
        mock_pool.getconn.return_value = MagicMock()
        mock_get_pool.return_value = mock_pool

        manager = PooledConnectionManager("test_loader")
        manager.acquire()
        manager.release()

        # Second release should not crash
        manager.release()

class TestPooledContextVar(unittest.TestCase):
    """Test context variable storage of pooled connections."""

    def test_set_get_pooled_connection(self):
        """Test setting and getting pooled connection."""
        mock_conn = MagicMock()

        # Initially None
        self.assertIsNone(get_pooled_connection())
        self.assertFalse(has_pooled_connection())

        # Set and retrieve
        set_pooled_connection(mock_conn)
        self.assertEqual(get_pooled_connection(), mock_conn)
        self.assertTrue(has_pooled_connection())

        # Clear
        set_pooled_connection(None)
        self.assertIsNone(get_pooled_connection())
        self.assertFalse(has_pooled_connection())

    def test_context_isolation(self):
        """Test that context is thread-isolated."""
        results = {}

        def set_and_check(thread_id, expected):
            mock_conn = MagicMock() if expected else None
            set_pooled_connection(mock_conn)
            time.sleep(0.1)  # Let other thread run
            retrieved = get_pooled_connection()
            results[thread_id] = retrieved == mock_conn

        t1 = threading.Thread(target=set_and_check, args=(1, True))
        t2 = threading.Thread(target=set_and_check, args=(2, False))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Each thread should see its own context
        self.assertTrue(results[1])
        self.assertTrue(results[2])

class TestDatabaseContextIntegration(unittest.TestCase):
    """Test DatabaseContext reuse of pooled connections."""

    @patch("utils.db.context.get_db_connection")
    @patch("utils.db.context.get_pooled_connection")
    def test_context_reuses_pooled_connection(self, mock_get_pooled, mock_get_fresh):
        """Test that DatabaseContext reuses pooled connection if available."""
        from utils.db import DatabaseContext

        # Setup: pooled connection exists
        mock_pooled = MagicMock()
        mock_pooled.cursor.return_value = MagicMock()
        mock_get_pooled.return_value = mock_pooled

        # Create context
        with DatabaseContext("read") as cur:
            pass

        # Should have used pooled connection, not created new one
        mock_get_pooled.assert_called()
        mock_get_fresh.assert_not_called()

    @patch("utils.db.context.get_db_connection")
    @patch("utils.db.context.get_pooled_connection")
    def test_context_acquires_new_if_no_pooled(self, mock_get_pooled, mock_get_fresh):
        """Test that DatabaseContext acquires new connection if none pooled."""
        from utils.db import DatabaseContext

        # Setup: no pooled connection
        mock_get_pooled.return_value = None
        mock_fresh = MagicMock()
        mock_fresh.cursor.return_value = MagicMock()
        mock_fresh.commit.return_value = None
        mock_fresh.close.return_value = None
        mock_get_fresh.return_value = mock_fresh

        # Create context
        with DatabaseContext("read") as cur:
            pass

        # Should have acquired fresh connection and closed it
        mock_get_fresh.assert_called()
        mock_fresh.close.assert_called_once()

class TestConnectionChurnReduction(unittest.TestCase):
    """Integration test verifying connection churn reduction."""

    @patch("utils.db.connection._get_connection_pool")
    @patch("utils.db.context.get_pooled_connection")
    def test_loader_pattern_single_connection(self, mock_get_pooled_ctx, mock_get_pool):
        """Test that a loader using the new pattern creates only 1 connection."""
        # Setup
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.return_value = None
        mock_conn.rollback.return_value = None
        mock_pool.getconn.return_value = mock_conn
        mock_get_pool.return_value = mock_pool
        mock_get_pooled_ctx.return_value = mock_conn

        # Simulate loader pattern: acquire once, use multiple times
        from utils.db.pooled_connection_manager import PooledConnectionManager
        from utils.db import DatabaseContext

        manager = PooledConnectionManager("test_loader")
        set_pooled_connection(manager.acquire())

        try:
            # Multiple operations with same connection
            with DatabaseContext("read") as cur:
                pass
            with DatabaseContext("read") as cur:
                pass
            with DatabaseContext("write") as cur:
                pass
        finally:
            set_pooled_connection(None)
            manager.release()

        # Verify: only 1 getconn call (not 3)
        self.assertEqual(mock_pool.getconn.call_count, 1)
        # Verify: only 1 putconn call
        self.assertEqual(mock_pool.putconn.call_count, 1)

if __name__ == "__main__":
    unittest.main()
