#!/bin/bash

# Setup test data for local development
# Make sure PostgreSQL is running and environment variables are set

echo "🚀 Setting up test data for local development..."

# Check if required environment variables are set
if [ -z "$DB_HOST" ] || [ -z "$DB_NAME" ] || [ -z "$DB_USER" ]; then
    echo "⚠️  Setting default database connection variables..."
    export DB_HOST="localhost"
    export DB_NAME="stocks"  
    export DB_USER="postgres"
    export DB_PASSWORD="password"
fi

echo "📊 Database: $DB_HOST:5432/$DB_NAME"
echo "👤 User: $DB_USER"

# Run the SQL script
echo "🔧 Populating test data..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f "$(dirname "$0")/populate-test-data.sql"

if [ $? -eq 0 ]; then
    echo "✅ Test data populated successfully!"
    echo ""
    echo "🧪 You can now test these endpoints:"
    echo "  - curl http://localhost:3001/api/signals/momentum/AAPL"
    echo "  - curl http://localhost:3001/api/dashboard/summary"  
    echo "  - curl http://localhost:3001/api/market/aaii"
    echo "  - curl http://localhost:3001/api/economic/data"
    echo "  - curl http://localhost:3001/api/positioning/stocks"
else
    echo "❌ Failed to populate test data"
    exit 1
fi