"""Regression test for the 2026-08-20 fix: PooledConnectionManager.acquire() handed out
whatever pool.getconn() returned with zero validation that it was still a live connection.

Live-reproduced: load_sec_valuations.py acquired a pooled connection and failed with
"InterfaceError: cursor already closed" on the very first symbol's query - 13ms after
"Acquired pooled connection" logged - then identically for every remaining symbol (this
class's whole design is one connection reused for the loader's entire run), cascading to a
total loader failure (4251/5098 symbols failed, log
logs/load_sec_valuations_1787248266.log). release()'s rollback-before-return (Session 108,
see its own docstring) only guards a connection going bad *during* a run - it can't catch one
that was already dead *before* this run's acquire() ever touched it (e.g. died from a
server-side idle timeout while sitting in the pool between loader runs). The fix: probe with
a cheap SELECT 1 at checkout, and if that fails, discard the connection and get another
instead of handing back a poisoned one.
"""

from unittest.mock import MagicMock, patch

import psycopg2.pool
import pytest

from utils.db.pooled_connection_manager import PooledConnectionManager


class TestDeadConnectionLivenessCheck:
    @patch("utils.db.connection._get_connection_pool")
    def test_dead_connection_is_discarded_and_a_fresh_one_is_used(self, mock_get_pool):
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)

        dead_conn = MagicMock()
        dead_cursor = MagicMock()
        dead_cursor.execute.side_effect = Exception("cursor already closed")
        dead_conn.cursor.return_value = dead_cursor

        live_conn = MagicMock()
        live_cursor = MagicMock()
        live_conn.cursor.return_value = live_cursor

        mock_pool.getconn.side_effect = [dead_conn, live_conn]
        mock_get_pool.return_value = mock_pool

        manager = PooledConnectionManager("test_loader", timeout_sec=5)
        conn = manager.acquire()

        assert conn is live_conn
        # The dead connection must be explicitly discarded (closed), not silently dropped -
        # putconn(close=True) removes it from the pool instead of recycling a broken connection.
        mock_pool.putconn.assert_called_once_with(dead_conn, close=True)
        assert mock_pool.getconn.call_count == 2

    @patch("utils.db.connection._get_connection_pool")
    def test_all_dead_connections_raises_after_max_retries(self, mock_get_pool):
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)

        def make_dead_conn():
            conn = MagicMock()
            cursor = MagicMock()
            cursor.execute.side_effect = Exception("cursor already closed")
            conn.cursor.return_value = cursor
            return conn

        mock_pool.getconn.side_effect = [make_dead_conn() for _ in range(5)]
        mock_get_pool.return_value = mock_pool

        manager = PooledConnectionManager("test_loader", timeout_sec=5)
        with pytest.raises(RuntimeError, match="dead connections"):
            manager.acquire()

        # Every dead connection encountered must be discarded, never handed to the caller.
        assert mock_pool.putconn.call_count == mock_pool.getconn.call_count

    @patch("utils.db.connection._get_connection_pool")
    def test_live_connection_on_first_try_is_returned_without_extra_getconn_calls(self, mock_get_pool):
        mock_pool = MagicMock(spec=psycopg2.pool.SimpleConnectionPool)
        live_conn = MagicMock()
        mock_pool.getconn.return_value = live_conn
        mock_get_pool.return_value = mock_pool

        manager = PooledConnectionManager("test_loader", timeout_sec=5)
        conn = manager.acquire()

        assert conn is live_conn
        assert mock_pool.getconn.call_count == 1
        mock_pool.putconn.assert_not_called()
