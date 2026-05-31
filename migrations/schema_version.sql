-- Schema version tracking table
-- Tracks all schema migrations applied to the database
-- Supports rollback capability for future enhancements

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
