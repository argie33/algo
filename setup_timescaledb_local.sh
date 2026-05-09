#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# TimescaleDB Local Setup Script
#
# Run this to:
#   1. Start PostgreSQL with TimescaleDB
#   2. Initialize database schema
#   3. Apply TimescaleDB migration
#   4. Run performance benchmarks
#
# Usage: bash setup_timescaledb_local.sh
# ════════════════════════════════════════════════════════════════════════════

set -e

echo "════════════════════════════════════════════════════════════════"
echo "TimescaleDB Local Setup"
echo "════════════════════════════════════════════════════════════════"

# Step 1: Stop existing containers
echo ""
echo "Step 1: Stopping existing containers..."
docker-compose -f docker-compose.local.yml down 2>/dev/null || true

# Step 2: Start PostgreSQL with TimescaleDB
echo ""
echo "Step 2: Starting PostgreSQL 15 with TimescaleDB..."
docker-compose -f docker-compose.local.yml up -d postgres

# Step 3: Wait for database to be ready
echo ""
echo "Step 3: Waiting for database to start (30 seconds)..."
sleep 30

# Step 4: Verify connection
echo ""
echo "Step 4: Verifying database connection..."
docker exec stocks_postgres_local psql -U stocks -d stocks -c "SELECT version();" || {
    echo "✗ Failed to connect. Check container logs:"
    echo "  docker-compose -f docker-compose.local.yml logs postgres"
    exit 1
}

echo "✓ Database is online"

# Step 5: Initialize schema (if tables don't exist)
echo ""
echo "Step 5: Ensuring schema is initialized..."
docker exec stocks_postgres_local psql -U stocks -d stocks -c "
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = 'public';
" > /tmp/table_count.txt

TABLE_COUNT=$(cat /tmp/table_count.txt | tail -1 | tr -d ' ')
if [ "$TABLE_COUNT" -eq 0 ]; then
    echo "  No tables found. Running init_database.py..."
    python init_database.py
else
    echo "  ✓ Schema already exists ($TABLE_COUNT tables)"
fi

# Step 6: Apply TimescaleDB migration
echo ""
echo "Step 6: Applying TimescaleDB migration..."
python migrate_timescaledb.py

# Step 7: Run benchmarks
echo ""
echo "Step 7: Running performance benchmarks..."
python test_timescaledb_performance.py

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✓ Setup complete!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Database is running at: localhost:5432"
echo "  User: stocks"
echo "  Password: (from .env.local)"
echo "  Database: stocks"
echo ""
echo "Next steps:"
echo "  1. Verify queries are fast: python test_timescaledb_performance.py"
echo "  2. Check hypertable stats: psql -h localhost -U stocks -d stocks -c \"SELECT * FROM timescaledb_information.hypertables;\""
echo "  3. Deploy to AWS RDS: terraform apply -target=aws_db_parameter_group.main"
echo ""
