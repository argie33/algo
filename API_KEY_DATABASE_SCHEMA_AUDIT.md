# API Key Database Schema Audit Report

## Executive Summary

This report provides a comprehensive audit of the database schema for the API key integration system. The analysis reveals the expected schema structure, identifies potential issues, and provides recommendations for ensuring proper database foundation.

## Database Schema Analysis

### 1. Expected `user_api_keys` Table Structure

Based on the codebase analysis, the `user_api_keys` table should have the following structure:

```sql
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_iv VARCHAR(32) NOT NULL,
    key_auth_tag VARCHAR(32) NOT NULL,
    encrypted_api_secret TEXT,
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    user_salt VARCHAR(32) NOT NULL,
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(user_id, provider)
);
```

### 2. Key Findings from Code Analysis

#### Authentication System
- **User ID Type**: The system uses Cognito authentication which provides UUID strings
- **Critical Fix**: The `fix_user_id_type.sql` script shows that the original schema had `user_id` as INTEGER, but Cognito provides VARCHAR(255) strings
- **Current Implementation**: Code expects `user_id` to be VARCHAR(255) to match Cognito sub claims

#### Encryption Implementation
- **Algorithm**: Uses AES-256-GCM encryption
- **Key Derivation**: Uses `crypto.scryptSync()` with user-specific salt
- **Storage Fields**:
  - `encrypted_api_key`: Main API key (encrypted)
  - `key_iv`: Initialization vector for API key encryption
  - `key_auth_tag`: Authentication tag for API key
  - `encrypted_api_secret`: Optional API secret (encrypted)
  - `secret_iv`: Initialization vector for secret encryption
  - `secret_auth_tag`: Authentication tag for secret encryption
  - `user_salt`: User-specific salt for key derivation

#### Provider Support
- **Multi-Provider**: System supports multiple API providers (e.g., 'alpaca', 'robinhood')
- **Unique Constraint**: One active key per user per provider
- **Sandbox Support**: Boolean flag for sandbox/production environments

### 3. Required Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_provider ON user_api_keys(user_id, provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_created_at ON user_api_keys(created_at);
```

### 4. User Isolation Verification

The system implements proper user isolation through:
- **Query Filtering**: All database queries include `WHERE user_id = $1` 
- **Authentication**: Uses `req.user.sub` from Cognito JWT tokens
- **Validation**: `validateUserAuthentication()` function ensures user ID is present
- **No Cross-User Access**: No queries allow users to access other users' API keys

### 5. Missing Users Table

The system references a `users` table that may not exist. Based on the Cognito integration, this table might not be needed since authentication is handled by Cognito. However, if present, it should have:

```sql
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,  -- Cognito sub
    email VARCHAR(255) UNIQUE,
    username VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6. Database Connection Analysis

The system supports two connection methods:
- **AWS Secrets Manager**: For production (requires `DB_SECRET_ARN`)
- **Environment Variables**: For local development

Current configuration shows:
- Local: `localhost:5432` with `postgres/postgres` credentials
- Production: AWS RDS with SSL enabled via Secrets Manager

## Security Assessment

### ✅ Strengths

1. **Strong Encryption**: Uses AES-256-GCM with proper key derivation
2. **User-Specific Salts**: Each user has a unique salt for key derivation
3. **Authentication Tags**: Prevents tampering with encrypted data
4. **Environment Variables**: Encryption secret stored in environment
5. **User Isolation**: Proper query filtering by user ID
6. **Audit Trail**: `last_used` timestamp for access tracking

### ⚠️ Potential Issues

1. **Column Size Limitations**: 
   - `key_iv` (32 chars): Adequate for base64 16-byte IV
   - `key_auth_tag` (32 chars): Adequate for base64 16-byte tag
   - `user_salt` (32 chars): May be too small for optimal security (recommend 64)

2. **Missing Foreign Key**: No foreign key constraint to users table
3. **No Trigger**: Missing `updated_at` trigger for automatic timestamp updates

## Recommendations

### 1. Schema Corrections

```sql
-- Increase salt column size for better security
ALTER TABLE user_api_keys ALTER COLUMN user_salt TYPE VARCHAR(64);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_user_api_keys_updated_at
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### 2. Performance Optimizations

```sql
-- Add composite index for common queries
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_active 
    ON user_api_keys(user_id, is_active, provider);

-- Add index for last_used queries
CREATE INDEX IF NOT EXISTS idx_user_api_keys_last_used 
    ON user_api_keys(last_used) WHERE is_active = true;
```

### 3. Validation Constraints

```sql
-- Ensure provider names are standardized
ALTER TABLE user_api_keys 
    ADD CONSTRAINT chk_provider_valid 
    CHECK (provider IN ('alpaca', 'robinhood', 'td_ameritrade', 'interactive_brokers'));

-- Ensure encrypted fields are not empty
ALTER TABLE user_api_keys 
    ADD CONSTRAINT chk_encrypted_key_not_empty 
    CHECK (LENGTH(encrypted_api_key) > 0);
```

## Complete Table Creation Script

```sql
-- Create user_api_keys table with all recommendations
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_iv VARCHAR(32) NOT NULL,
    key_auth_tag VARCHAR(32) NOT NULL,
    encrypted_api_secret TEXT,
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    user_salt VARCHAR(64) NOT NULL,  -- Increased from 32
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    
    -- Constraints
    UNIQUE(user_id, provider),
    CHECK (provider IN ('alpaca', 'robinhood', 'td_ameritrade', 'interactive_brokers')),
    CHECK (LENGTH(encrypted_api_key) > 0),
    CHECK (LENGTH(user_salt) >= 32)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_active ON user_api_keys(user_id, is_active, provider);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_created_at ON user_api_keys(created_at);
CREATE INDEX IF NOT EXISTS idx_user_api_keys_last_used ON user_api_keys(last_used) WHERE is_active = true;

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_user_api_keys_updated_at
    BEFORE UPDATE ON user_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

## Testing Recommendations

1. **User Isolation Testing**: Create multiple test users and verify they cannot access each other's API keys
2. **Encryption Testing**: Verify encryption/decryption works correctly with various key lengths
3. **Performance Testing**: Test query performance with large numbers of users and API keys
4. **Security Testing**: Verify that authentication failures prevent access to API keys

## Connection Requirements

To test the database schema, you'll need:
- PostgreSQL running on localhost:5432 (for local testing)
- OR AWS RDS connection with `DB_SECRET_ARN` environment variable
- Node.js dependencies: `pg`, `dotenv`

## Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Table Structure | ✅ Defined | Matches code expectations |
| Encryption Schema | ✅ Secure | AES-256-GCM implementation |
| User Isolation | ✅ Implemented | Proper query filtering |
| Indexes | ⚠️ Partial | Basic indexes present, performance indexes recommended |
| Constraints | ⚠️ Minimal | Unique constraint present, validation constraints recommended |
| Triggers | ❌ Missing | updated_at trigger needed |
| Foreign Keys | ❌ Missing | No FK to users table (may be intentional with Cognito) |
| Column Sizes | ⚠️ Adequate | user_salt could be larger for better security |

The database schema foundation is solid but would benefit from the recommended enhancements for production use.