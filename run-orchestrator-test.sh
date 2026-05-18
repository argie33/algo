#!/bin/bash
# Run orchestrator locally with a specific date for testing

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Default to today if no date provided
TEST_DATE="${1:-$(date +%Y-%m-%d)}"

echo "🚀 Running Orchestrator Test"
echo "==========================="
echo "Test Date: $TEST_DATE"
echo ""

# ============================================================
# Verify database connection
# ============================================================
echo "Checking database connection..."
if [ -z "$DB_PASSWORD" ]; then
    echo "❌ DB_PASSWORD not set"
    echo ""
    echo "Set environment variables:"
    echo "  export DB_HOST=<host>"
    echo "  export DB_PORT=<port>"
    echo "  export DB_USER=<user>"
    echo "  export DB_NAME=<name>"
    echo "  export DB_PASSWORD=<password>"
    exit 1
fi
echo "✅ Database credentials available"

# ============================================================
# Run orchestrator with test date
# ============================================================
echo ""
echo "Running orchestrator for $TEST_DATE..."
echo ""

cd "$PROJECT_ROOT"
python3 algo/algo_orchestrator.py \
    --run-date "$TEST_DATE" \
    --mode paper \
    --verbose

echo ""
echo "✨ Test complete!"
echo ""
echo "📋 Check the results:"
echo "   SELECT * FROM algo_audit_log"
echo "   WHERE DATE(created_at) = '$TEST_DATE'"
echo "   ORDER BY created_at DESC LIMIT 100;"
