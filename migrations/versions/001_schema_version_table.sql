-- Migration: Initialize schema_version tracking table
-- This migration creates the table for tracking applied migrations

-- Up
CREATE TABLE IF NOT EXISTS schema_version (
    id INT PRIMARY KEY,
    version VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rolled_back_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_schema_version_applied ON schema_version(rolled_back_at);

-- Down
DROP INDEX IF EXISTS idx_schema_version_applied;
DROP TABLE IF EXISTS schema_version;
