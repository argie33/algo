-- Add API idempotency cache table to prevent duplicate requests
-- Prevents duplicate POST requests by caching request signatures and responses
-- Entries are automatically cleaned up after 24 hours

CREATE TABLE IF NOT EXISTS api_idempotency_cache (
    id SERIAL PRIMARY KEY,
    request_signature VARCHAR(64) UNIQUE NOT NULL,
    response_data JSONB NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CHECK (LENGTH(request_signature) = 64)
);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_cache_signature
    ON api_idempotency_cache(request_signature);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_cache_created_at
    ON api_idempotency_cache(created_at DESC);

-- Auto-cleanup job: delete entries older than 24 hours
-- This could be called periodically via a maintenance script or Lambda function
CREATE OR REPLACE FUNCTION cleanup_api_idempotency_cache()
RETURNS void AS $$
BEGIN
    DELETE FROM api_idempotency_cache
    WHERE created_at < NOW() - INTERVAL '24 hours';
END;
$$ LANGUAGE plpgsql;
