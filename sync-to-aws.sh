#!/bin/bash

###############################################################################
# SYNC LOCAL DATA TO AWS RDS
#
# This script dumps the local PostgreSQL database and restores it to AWS RDS
# Usage: ./sync-to-aws.sh <rds-endpoint> <rds-username>
###############################################################################

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <rds-endpoint> <rds-username>"
    echo ""
    echo "Example:"
    echo "  $0 stocks-db.c9akciq32.us-east-1.rds.amazonaws.com stocks"
    exit 1
fi

RDS_ENDPOINT="$1"
RDS_USER="$2"
RDS_PASSWORD="${RDS_PASSWORD:-bed0elAn}"  # Get from env or use default
LOCAL_USER="stocks"
LOCAL_PASSWORD="bed0elAn"
DB_NAME="stocks"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        SYNCING LOCAL DATA TO AWS RDS                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Source: localhost:5432/$DB_NAME ($LOCAL_USER)"
echo "🌐 Destination: $RDS_ENDPOINT:5432/$DB_NAME ($RDS_USER)"
echo ""

# Dump local database
echo "⏳ Dumping local database..."
PGPASSWORD="$LOCAL_PASSWORD" pg_dump \
    -h localhost \
    -U "$LOCAL_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-privileges \
    --format=custom \
    --compress=9 \
    -f /tmp/stocks_backup.dump

SIZE=$(du -h /tmp/stocks_backup.dump | cut -f1)
echo "✅ Dumped local database ($SIZE)"
echo ""

# Restore to AWS RDS
echo "⏳ Restoring to AWS RDS..."
PGPASSWORD="$RDS_PASSWORD" pg_restore \
    -h "$RDS_ENDPOINT" \
    -U "$RDS_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    /tmp/stocks_backup.dump

echo "✅ Restored data to AWS RDS"
echo ""

# Verify sync
echo "🔍 Verifying data on AWS RDS..."
REMOTE_COUNT=$(PGPASSWORD="$RDS_PASSWORD" psql \
    -h "$RDS_ENDPOINT" \
    -U "$RDS_USER" \
    -d "$DB_NAME" \
    -t -c "SELECT COUNT(*) FROM stock_symbols")

echo "✅ AWS RDS now has $REMOTE_COUNT stock symbols"
echo ""

# Cleanup
rm /tmp/stocks_backup.dump
echo "✅ SYNC COMPLETE - AWS RDS data is now up-to-date"
echo ""
echo "📊 Final verification:"
PGPASSWORD="$RDS_PASSWORD" psql \
    -h "$RDS_ENDPOINT" \
    -U "$RDS_USER" \
    -d "$DB_NAME" \
    -c "SELECT 'Stock Symbols' as resource, COUNT(*) as count FROM stock_symbols
        UNION ALL SELECT 'Stock Scores', COUNT(*) FROM stock_scores
        UNION ALL SELECT 'Daily Prices', COUNT(*) FROM price_daily
        UNION ALL SELECT 'Buy/Sell Signals', COUNT(*) FROM buy_sell_daily
        ORDER BY count DESC;"
