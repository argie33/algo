-- Migration 001: Add schema version tracking table
-- Description: Enables versioning of database schema changes with rollback capability
-- Created: 2026-05-31

CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT NOW(),
    rolled_back_at TIMESTAMP NULL
);

-- Index for efficient version lookups
CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);
CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at ON schema_version(applied_at);
