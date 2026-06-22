#!/usr/bin/env python3
"""
Migration 001: Initialize Schema Version Tracking

This is the first migration and serves as a baseline.
It creates the schema_version table to track all future migrations.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Initialize schema version tracking table"


def up():
    """Create schema_version table."""
    sql = """
    CREATE TABLE IF NOT EXISTS schema_version (
        id SERIAL PRIMARY KEY,
        version VARCHAR(100) UNIQUE NOT NULL,
        description TEXT,
        applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        rolled_back_at TIMESTAMP WITH TIME ZONE NULL,
        applied_by VARCHAR(255),
        checksum VARCHAR(64)
    );

    CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);
    CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at ON schema_version(applied_at DESC);
    """

    with DatabaseContext("write") as cur:
        cur.execute(sql)


def down():
    """Drop schema_version table."""
    sql = """
    DROP TABLE IF EXISTS schema_version CASCADE;
    """

    with DatabaseContext("write") as cur:
        cur.execute(sql)
