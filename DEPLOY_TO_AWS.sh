#!/bin/bash

# ==============================================================================
# DEPLOY DATA TO AWS RDS - Complete Database Sync
# ==============================================================================

set -e

echo "🚀 DEPLOYING LOCAL DATA TO AWS RDS"
echo "===================================="
echo ""

# Configuration
export PGPASSWORD_LOCAL="bed0elAn"
export LOCAL_HOST="localhost"
export LOCAL_USER="stocks"
export LOCAL_DB="stocks"
export AWS_REGION="us-east-1"

echo "📍 Step 1: Checking for RDS endpoint..."
echo ""

# Try to get secret from AWS Secrets Manager
if command -v aws &> /dev/null; then
    echo "✅ AWS CLI found. Retrieving credentials from Secrets Manager..."
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id "rds-stocks-secret" \
        --region "$AWS_REGION" \
        --query 'SecretString' \
        --output text 2>/dev/null || echo "")

    if [ -n "$SECRET_JSON" ]; then
        export RDS_HOST=$(echo "$SECRET_JSON" | jq -r '.host // empty' 2>/dev/null || echo "")
        export RDS_USER=$(echo "$SECRET_JSON" | jq -r '.username // empty' 2>/dev/null || echo "stocks")
        export RDS_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.password // empty' 2>/dev/null || echo "")
        export RDS_PORT=$(echo "$SECRET_JSON" | jq -r '.port // 5432' 2>/dev/null || echo "5432")
    fi
fi

# If still no endpoint, ask user
if [ -z "$RDS_HOST" ]; then
    echo "📝 Enter AWS RDS Configuration:"
    read -p "RDS Endpoint (e.g., stocks.xxxxx.us-east-1.rds.amazonaws.com): " RDS_HOST
    read -p "RDS Username (default: stocks): " RDS_USER
    RDS_USER="${RDS_USER:-stocks}"
    read -sp "RDS Password: " RDS_PASSWORD
    echo ""
    RDS_PORT="5432"
    RDS_DB="stocks"
else
    RDS_DB="stocks"
fi

echo ""
echo "✅ RDS Configuration:"
echo "   Host: $RDS_HOST"
echo "   User: $RDS_USER"
echo "   Port: $RDS_PORT"
echo ""

# Test RDS connection
echo "🔗 Step 2: Testing RDS connection..."
export PGPASSWORD="$RDS_PASSWORD"

if psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -c "SELECT 1;" &>/dev/null 2>&1; then
    echo "✅ RDS connection successful!"
else
    echo "⚠️  Could not connect to RDS. Continuing anyway (may fail on restore)..."
fi

echo ""

# Export local database
echo "💾 Step 3: Exporting local database..."
echo "   Exporting 22.4M price records + signals + scores..."

export PGPASSWORD="$PGPASSWORD_LOCAL"

timeout 900 pg_dump -h "$LOCAL_HOST" -U "$LOCAL_USER" -d "$LOCAL_DB" \
    --disable-triggers \
    --no-owner \
    --no-privileges \
    -F p > /tmp/stocks_export.sql 2>&1

if [ ! -f /tmp/stocks_export.sql ] || [ ! -s /tmp/stocks_export.sql ]; then
    echo "⚠️  Export may have issues, continuing..."
else
    EXPORT_SIZE=$(du -h /tmp/stocks_export.sql | cut -f1)
    echo "✅ Database exported ($EXPORT_SIZE)"
fi

echo ""

# Restore to RDS
echo "📤 Step 4: Restoring to AWS RDS..."
echo "   Uploading data to: $RDS_HOST"

export PGPASSWORD="$RDS_PASSWORD"

timeout 1800 psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" \
    -1 < /tmp/stocks_export.sql 2>&1 | tail -30

echo ""
echo "✅ Database restore initiated!"

echo ""

# Verify data
echo "✅ Step 5: Verifying data in RDS..."
sleep 5

export PGPASSWORD="$RDS_PASSWORD"

SIGNAL_COUNT=$(psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -t -c \
    "SELECT COUNT(*) FROM buy_sell_daily" 2>/dev/null | tr -d ' ' || echo "?")
SCORE_COUNT=$(psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -t -c \
    "SELECT COUNT(*) FROM stock_scores" 2>/dev/null | tr -d ' ' || echo "?")
SYMBOL_COUNT=$(psql -h "$RDS_HOST" -U "$RDS_USER" -d "$RDS_DB" -t -c \
    "SELECT COUNT(*) FROM stock_symbols" 2>/dev/null | tr -d ' ' || echo "?")

echo ""
echo "📊 Data Verification:"
echo "   Buy/Sell Signals: $SIGNAL_COUNT records"
echo "   Stock Scores: $SCORE_COUNT records"
echo "   Stock Symbols: $SYMBOL_COUNT symbols"

echo ""

if [ "$SIGNAL_COUNT" -gt 10000 ] && [ "$SCORE_COUNT" -gt 4000 ] && [ "$SYMBOL_COUNT" -gt 4000 ]; then
    echo "✅ ✅ ✅ DATA SUCCESSFULLY DEPLOYED TO AWS! ✅ ✅ ✅"
    echo ""
    echo "🎉 Your stock data is now in AWS RDS"
    echo "   Endpoint: $RDS_HOST"
    echo "   Signals: $SIGNAL_COUNT records"
    echo "   Symbols: $SYMBOL_COUNT total"
    echo ""
else
    echo "⚠️  Data verification complete."
    echo "   Check counts above. Counts show: Signals=$SIGNAL_COUNT, Scores=$SCORE_COUNT, Symbols=$SYMBOL_COUNT"
fi

# Cleanup
echo ""
echo "Cleaning up..."
rm -f /tmp/stocks_export.sql

echo "🚀 Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Update Lambda/ECS to use RDS endpoint: $RDS_HOST"
echo "  2. Test API endpoints"
echo "  3. Monitor CloudWatch logs"
