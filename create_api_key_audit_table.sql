-- API Key Audit Log Table
-- Tracks all API key operations for security and compliance

CREATE TABLE IF NOT EXISTS api_key_audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    session_id UUID,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_api_key_audit_user_id ON api_key_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_api_key_audit_timestamp ON api_key_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_api_key_audit_action ON api_key_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_api_key_audit_provider ON api_key_audit_log(provider);
CREATE INDEX IF NOT EXISTS idx_api_key_audit_session_id ON api_key_audit_log(session_id);

-- Add comments for documentation
COMMENT ON TABLE api_key_audit_log IS 'Audit log for all API key operations';
COMMENT ON COLUMN api_key_audit_log.user_id IS 'Cognito user ID (sub claim)';
COMMENT ON COLUMN api_key_audit_log.action IS 'Action performed (API_KEY_STORED, API_KEY_ACCESSED, API_KEY_DELETED, API_KEY_TESTED)';
COMMENT ON COLUMN api_key_audit_log.provider IS 'API provider (alpaca, polygon, finnhub, etc.)';
COMMENT ON COLUMN api_key_audit_log.session_id IS 'Unique session identifier';
COMMENT ON COLUMN api_key_audit_log.ip_address IS 'Client IP address';
COMMENT ON COLUMN api_key_audit_log.user_agent IS 'Client user agent string';
COMMENT ON COLUMN api_key_audit_log.success IS 'Whether the operation succeeded';
COMMENT ON COLUMN api_key_audit_log.error_message IS 'Error message if operation failed';
COMMENT ON COLUMN api_key_audit_log.additional_data IS 'Additional context data as JSON';

-- Create a view for recent audit events
CREATE OR REPLACE VIEW recent_api_key_audit AS
SELECT 
    id,
    user_id,
    action,
    provider,
    session_id,
    timestamp,
    ip_address,
    success,
    error_message
FROM api_key_audit_log
WHERE timestamp >= NOW() - INTERVAL '30 days'
ORDER BY timestamp DESC;

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT ON api_key_audit_log TO your_app_user;
-- GRANT SELECT ON recent_api_key_audit TO your_app_user;