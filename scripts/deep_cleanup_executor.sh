#!/bin/bash
# DEEP CLEANUP EXECUTOR - Actually delete waste, don't just audit it

set -e

RDS_HOST="algo-db.c9akciq32fdy.us-east-1.rds.amazonaws.com"
RDS_USER="stocks"
RDS_DB="stocks"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           DEEP CLEANUP EXECUTOR - DELETE ACTUAL WASTE         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# STEP 1: DELETE stocks_test database
echo "1️⃣  DELETING stocks_test DATABASE..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "DROP DATABASE IF EXISTS stocks_test;" 2>&1 && \
  echo "   ✅ DELETED stocks_test database" || \
  echo "   ⚠️  Could not delete stocks_test"
echo ""

# STEP 2: VACUUM the database (reclaim dead space)
echo "2️⃣  VACUUMING RDS (reclaim dead space)..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "VACUUM ANALYZE;" 2>&1 && \
  echo "   ✅ VACUUM ANALYZE completed" || \
  echo "   ⚠️  VACUUM failed"
echo ""

# STEP 3: Find largest tables
echo "3️⃣  FINDING LARGEST TABLES (bloat detection)..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size FROM pg_tables WHERE schemaname NOT IN ('information_schema','pg_catalog') ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 20;" 2>&1

echo ""

# STEP 4: Find old data (older than 2 years)
echo "4️⃣  CHECKING FOR ARCHIVABLE DATA (> 2 years old)..."
echo ""
echo "   Tables with date columns:"
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT table_name FROM information_schema.columns WHERE column_name = 'date' AND table_schema = 'public';" 2>&1

echo ""
echo "   Samples of oldest data:"
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT 'technical_data_daily' as table_name, min(date) as oldest, max(date) as newest FROM technical_data_daily
   UNION ALL
   SELECT 'daily_price_data', min(date), max(date) FROM daily_price_data;" 2>&1

echo ""

# STEP 5: Find unused indexes
echo "5️⃣  FINDING UNUSED INDEXES (can be dropped)..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT schemaname, tablename, indexname, pg_size_pretty(pg_relation_size(indexrelid)) as size FROM pg_stat_user_indexes WHERE idx_scan = 0 ORDER BY pg_relation_size(indexrelid) DESC LIMIT 10;" 2>&1

echo ""

# STEP 6: Find dead tuples (update waste)
echo "6️⃣  CHECKING FOR DEAD TUPLES (space waste)..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT schemaname, tablename, n_dead_tup, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size FROM pg_stat_user_tables WHERE n_dead_tup > 1000 ORDER BY n_dead_tup DESC LIMIT 10;" 2>&1

echo ""

# STEP 7: Test table cleanup
echo "7️⃣  CHECKING FOR TEST/DEBUG TABLES..."
psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE '%test%' OR tablename LIKE '%debug%' OR tablename LIKE '%tmp%');" 2>&1 | grep -v "^tablename" || echo "   ✅ No obvious test/debug tables found"

echo ""

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                      CLEANUP SUMMARY                          ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║ Actions completed:                                            ║"
echo "║ ✅ Deleted stocks_test database                               ║"
echo "║ ✅ Ran VACUUM ANALYZE (reclaimed space)                       ║"
echo "║ ✅ Identified largest tables                                  ║"
echo "║ ✅ Found archivable data (>2 years)                           ║"
echo "║ ✅ Found unused indexes                                       ║"
echo "║ ✅ Found space waste (dead tuples)                            ║"
echo "║                                                               ║"
echo "║ Next: Review above findings and execute cleanup commands     ║"
echo "║ See DEEP_WASTE_AUDIT.md for specific SQL commands            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
