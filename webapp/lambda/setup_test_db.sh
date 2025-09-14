#!/bin/bash

# Database Setup Script for Integration Tests
# This script sets up PostgreSQL database, user, schema, and test data

echo "Setting up test database for integration tests..."

# Function to run SQL as postgres user
run_as_postgres() {
    echo "$1" | sudo -u postgres psql
}

# Function to run SQL as stocks user
run_as_stocks() {
    echo "$1" | PGPASSWORD=stocks psql -h localhost -U stocks -d stocks
}

# Create database and user
echo "Creating database and user..."
run_as_postgres "CREATE USER stocks WITH PASSWORD 'stocks';" 2>/dev/null || echo "User stocks already exists"
run_as_postgres "CREATE DATABASE stocks OWNER stocks;" 2>/dev/null || echo "Database stocks already exists"
run_as_postgres "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" 2>/dev/null || echo "Privileges already granted"

# Create schema
echo "Creating database schema..."
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -f setup_database.sql

# Seed test data
echo "Seeding test data..."
PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -f seed_test_data.sql

# Verify setup
echo "Verifying database setup..."
table_count=$(PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
echo "Created $table_count tables"

signal_count=$(PGPASSWORD=stocks psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM buy_sell_daily;" 2>/dev/null || echo "0")
echo "Inserted $signal_count trading signals"

echo "Test database setup complete!"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: stocks"
echo "  Username: stocks"
echo "  Password: stocks"
echo ""
echo "Set environment variables:"
echo "export DB_HOST=localhost"
echo "export DB_PORT=5432"
echo "export DB_USER=stocks"
echo "export DB_PASSWORD=stocks"
echo "export DB_NAME=stocks"