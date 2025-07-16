#!/bin/bash

# Script to start development database in Docker

echo "Starting PostgreSQL database for development..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    exit 1
fi

# Stop any existing postgres container
docker stop postgres-dev 2>/dev/null
docker rm postgres-dev 2>/dev/null

# Start PostgreSQL container
docker run -d \
    --name postgres-dev \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=password \
    -e POSTGRES_DB=stocks \
    -p 5432:5432 \
    postgres:14-alpine

echo "Waiting for PostgreSQL to start..."
sleep 5

# Check if database is ready
for i in {1..30}; do
    if docker exec postgres-dev pg_isready -U postgres >/dev/null 2>&1; then
        echo "✅ PostgreSQL is ready!"
        break
    fi
    echo "Waiting for PostgreSQL to be ready... ($i/30)"
    sleep 1
done

# Create tables using the SQL scripts
echo ""
echo "Creating database tables..."

# Run the SQL scripts
for sql_file in create_health_status_table.sql create_api_keys_table.sql; do
    if [ -f "$sql_file" ]; then
        echo "Running $sql_file..."
        docker exec -i postgres-dev psql -U postgres -d stocks < "$sql_file"
    fi
done

# Create user tables
echo "Creating user tables..."
docker exec -i postgres-dev psql -U postgres -d stocks <<EOF
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

-- Insert a test user for development
INSERT INTO users (id, email, first_name, last_name) 
VALUES ('dev-user-123', 'dev@example.com', 'Dev', 'User')
ON CONFLICT (id) DO NOTHING;

SELECT 'User tables created successfully' as status;
EOF

echo ""
echo "✅ Development database is ready!"
echo ""
echo "Database connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: stocks"
echo "  Username: postgres"
echo "  Password: password"
echo ""
echo "To stop the database: docker stop postgres-dev"
echo "To remove the database: docker rm postgres-dev"