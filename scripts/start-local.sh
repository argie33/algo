#!/bin/bash
# ============================================================
# LOCAL DEVELOPMENT STARTUP
# ONE script to rule them all — starts everything cleanly
# ============================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "════════════════════════════════════════════════════════════"
echo "  ALGO LOCAL DEVELOPMENT STARTUP"
echo "════════════════════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────────────────────
# PHASE 1: START DOCKER CONTAINERS
# ──────────────────────────────────────────────────────────────
echo "📦 Starting Docker containers..."
docker-compose up -d

# Wait for PostgreSQL to be healthy
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U stocks -d stocks >/dev/null 2>&1; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ PostgreSQL failed to start"
        exit 1
    fi
done

# ──────────────────────────────────────────────────────────────
# PHASE 2: INITIALIZE DATABASE SCHEMA
# ──────────────────────────────────────────────────────────────
echo ""
echo "🗄️  Initializing database schema..."
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=postgres
export DB_NAME=stocks
python3 init_database.py

# ──────────────────────────────────────────────────────────────
# PHASE 3: STATUS CHECK
# ──────────────────────────────────────────────────────────────
echo ""
echo "✅ LOCAL DEVELOPMENT ENVIRONMENT READY"
echo ""
echo "  Database:  postgresql://localhost:5432/stocks"
echo "  pgAdmin:   http://localhost:5050"
echo "  Redis:     localhost:6379"
echo ""
echo "To load sample data:"
echo "  python3 run-all-loaders.py"
echo ""
echo "To stop:"
echo "  docker-compose down"
echo ""
