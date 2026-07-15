#!/usr/bin/env python3
"""Database query service - wraps psycopg2 cursor to decouple handlers from direct cursor access.

Provides a simple interface for common query patterns used across 50+ API handlers.
Reduces coupling: handlers call db.query(...) instead of cur.execute(...).
"""

from __future__ import annotations

from typing import Any, cast


class DatabaseQueryService:
    """Service wrapper around psycopg2 cursor for API handlers.

    Provides:
    - execute(): Execute a query with parameters
    - fetch_one(): Fetch single row
    - fetch_all(): Fetch all rows
    - commit(): Commit transaction
    """

    def __init__(self, cursor: Any):
        self.cursor = cursor

    def execute(self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> Any:
        """Execute a query and return cursor for further operations.

        Args:
            query: SQL query string
            params: Query parameters (tuple or dict)

        Returns:
            The cursor (for backward compatibility with existing code)
        """
        self.cursor.execute(query, params)
        return self.cursor

    def fetch_one(self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> Any | None:
        """Execute query and fetch single row.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Single row or None
        """
        self.cursor.execute(query, params)
        return self.cursor.fetchone()

    def fetch_all(self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[Any]:
        """Execute query and fetch all rows.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows
        """
        self.cursor.execute(query, params)
        return cast(list[Any], self.cursor.fetchall())

    def fetch_many(self, query: str, size: int, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[Any]:
        """Execute query and fetch multiple rows.

        Args:
            query: SQL query string
            size: Number of rows to fetch
            params: Query parameters

        Returns:
            List of rows (up to size)
        """
        self.cursor.execute(query, params)
        return cast(list[Any], self.cursor.fetchmany(size))

    def commit(self) -> None:
        """Commit current transaction."""
        if self.cursor.connection:
            self.cursor.connection.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        if self.cursor.connection:
            self.cursor.connection.rollback()

    # Passthrough for backward compatibility - allow handlers to access cursor directly if needed
    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to underlying cursor."""
        return getattr(self.cursor, name)
