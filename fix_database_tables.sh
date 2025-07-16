#!/bin/bash

# Script to create missing database tables

echo "Creating missing database tables..."

# Database connection parameters
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-algo}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-devpassword}"

# Export password for psql
export PGPASSWORD="$DB_PASSWORD"

# Function to run SQL file
run_sql_file() {
    local sql_file=$1
    echo "Running $sql_file..."
    
    if [ -f "$sql_file" ]; then
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$sql_file" 2>&1 | head -20
        if [ $? -eq 0 ]; then
            echo "✓ Successfully executed $sql_file"
        else
            echo "✗ Failed to execute $sql_file"
        fi
    else
        echo "✗ SQL file not found: $sql_file"
    fi
    echo "---"
}

# Create health_status table first (required for monitoring)
run_sql_file "create_health_status_table.sql"

# Create user_api_keys table (required for API key management)
run_sql_file "create_api_keys_table.sql"

# Create user-related tables
echo "Creating user-related tables..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF
-- Create users table if not exists
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(20),
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    currency VARCHAR(10) DEFAULT 'USD',
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    two_factor_secret VARCHAR(255),
    recovery_codes TEXT,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create user notification preferences table
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id),
    email_notifications BOOLEAN DEFAULT TRUE,
    push_notifications BOOLEAN DEFAULT TRUE,
    price_alerts BOOLEAN DEFAULT TRUE,
    portfolio_updates BOOLEAN DEFAULT TRUE,
    market_news BOOLEAN DEFAULT FALSE,
    weekly_reports BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create user theme preferences table
CREATE TABLE IF NOT EXISTS user_theme_preferences (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(id),
    dark_mode BOOLEAN DEFAULT FALSE,
    primary_color VARCHAR(20) DEFAULT '#1976d2',
    chart_style VARCHAR(50) DEFAULT 'candlestick',
    layout VARCHAR(50) DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);

SELECT 'User tables created successfully' as status;
EOF

echo "Database tables creation completed!"

# Verify tables were created
echo ""
echo "Verifying created tables..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('health_status', 'user_api_keys', 'users', 'user_notification_preferences', 'user_theme_preferences')
ORDER BY table_name;"

unset PGPASSWORD