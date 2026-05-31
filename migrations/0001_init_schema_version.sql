-- Initialize schema versioning table for tracking database migrations
-- Migration: 0001
-- Description: Add schema_version table for migration tracking
-- Date: 2026-05-30

CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT NOW(),
    rolled_back_at TIMESTAMP NULL,
    checksum VARCHAR(64)
);

-- Create index on version for faster lookups
CREATE INDEX IF NOT EXISTS idx_schema_version_version ON schema_version(version);

-- Create index on applied_at for sorting
CREATE INDEX IF NOT EXISTS idx_schema_version_applied_at ON schema_version(applied_at DESC);
