-- Migration: Create user_api_keys table for encrypted API key storage
-- This table stores encrypted broker API keys for user portfolio integration

CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,  -- AWS Cognito user ID (sub)
    provider VARCHAR(50) NOT NULL,  -- broker name: 'alpaca', 'td_ameritrade', etc.
    
    -- Encrypted API key fields (using AES-256-GCM)
    encrypted_api_key TEXT NOT NULL,
    key_iv VARCHAR(32) NOT NULL,     -- 16-byte IV as hex
    key_auth_tag VARCHAR(32) NOT NULL, -- 16-byte auth tag as hex
    
    -- Encrypted API secret fields (optional, for brokers that need it)
    encrypted_api_secret TEXT,
    secret_iv VARCHAR(32),           -- 16-byte IV as hex  
    secret_auth_tag VARCHAR(32),     -- 16-byte auth tag as hex
    
    -- User-specific salt for encryption
    user_salt VARCHAR(32) NOT NULL,  -- 16-byte salt as hex
    
    -- Metadata
    description TEXT,
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    UNIQUE(user_id, provider, is_active) -- Only one active key per user per provider
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(user_id, provider, is_active);

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_user_api_keys_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_user_api_keys_updated_at
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_user_api_keys_updated_at();

-- Comments for documentation
COMMENT ON TABLE user_api_keys IS 'Stores encrypted broker API keys for user portfolio integration';
COMMENT ON COLUMN user_api_keys.user_id IS 'AWS Cognito user ID (sub field from JWT token)';
COMMENT ON COLUMN user_api_keys.provider IS 'Broker identifier: alpaca, td_ameritrade, etc.';
COMMENT ON COLUMN user_api_keys.encrypted_api_key IS 'AES-256-GCM encrypted API key';
COMMENT ON COLUMN user_api_keys.user_salt IS 'User-specific salt for key derivation';