#!/bin/bash
# ============================================================
# Initialize PostgreSQL for Local Development
# Runs automatically when docker-compose starts
# ============================================================

set -e

echo "PostgreSQL initialization script starting..."

# This script runs INSIDE the PostgreSQL container
# after the data directory is initialized but BEFORE the server starts
#
# At this point:
# - The database superuser (postgres) exists
# - Default database 'postgres' exists
# - Network is NOT yet available to other services
# - Cannot run Python scripts yet (need database running)
#
# This script creates the initial database and user
# The actual schema (tables, indexes) is created by init_database.py
# which runs AFTER the database is running

# Create the stocks database and user
echo "Creating database 'stocks' and user..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create the application user (if not exists)
    DO \$\$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'stocks') THEN
            CREATE USER stocks WITH PASSWORD '$POSTGRES_PASSWORD';
        END IF;
    END \$\$;

    -- Grant privileges to the stocks user
    GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO stocks;

    -- Set default privileges for future tables
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stocks;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stocks;

    -- Enable required extensions
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

    -- Show what was created
    SELECT 'Database and user setup complete' as message;
EOSQL

echo "PostgreSQL initialization complete"
echo "Schema will be created by init_database.py when it runs"
