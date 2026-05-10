"""Fixtures for edge case tests."""

import pytest
import os
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_db_connection():
    """Mock database connections for edge case tests.

    Edge case tests don't need real database access - they test business logic,
    not database persistence. Mocking the database allows tests to run without
    postgres running.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Mock cursor results
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []

    with patch('psycopg2.connect', return_value=mock_conn):
        yield mock_conn
