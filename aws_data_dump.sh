#!/bin/bash
##############################################################################
# AWS Data Dump and Sync Utility
# Exports local PostgreSQL data to format ready for AWS RDS
##############################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
LOCAL_DB="stocks"
LOCAL_USER="postgres"
LOCAL_HOST="localhost"
LOCAL_PORT="5432"
BACKUP_DIR="/tmp/aws_dumps"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DUMP_FILE="$BACKUP_DIR/stocks_dump_$TIMESTAMP.sql"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}      AWS DATA DUMP & SYNC UTILITY${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Check local database connectivity
echo -e "${YELLOW}[1/5] Checking local database connectivity...${NC}"
psql -U "$LOCAL_USER" -h "$LOCAL_HOST" -d "$LOCAL_DB" -c "SELECT 1" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Local database connected${NC}"
else
    echo -e "${RED}❌ Failed to connect to local database${NC}"
    exit 1
fi
echo ""

# Step 2: Get current data counts
echo -e "${YELLOW}[2/5] Getting current data counts...${NC}"
psql -U "$LOCAL_USER" -h "$LOCAL_HOST" -d "$LOCAL_DB" -t -c "
SELECT
    'positioning_metrics: ' || COUNT(*) || ' rows'
FROM positioning_metrics
UNION ALL
SELECT
    'momentum_metrics: ' || COUNT(*) || ' rows'
FROM momentum_metrics
UNION ALL
SELECT
    'stock_scores: ' || COUNT(*) || ' rows'
FROM stock_scores
" 2>/dev/null || true
echo ""

# Step 3: Create SQL dump
echo -e "${YELLOW}[3/5] Creating SQL dump...${NC}"
echo "   Output: $DUMP_FILE"

# Dump only the data we need (positioning_metrics, momentum_metrics, stock_scores)
pg_dump \
    -U "$LOCAL_USER" \
    -h "$LOCAL_HOST" \
    -d "$LOCAL_DB" \
    --data-only \
    -t positioning_metrics \
    -t momentum_metrics \
    -t stock_scores \
    > "$DUMP_FILE" 2>/dev/null

if [ -f "$DUMP_FILE" ]; then
    DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    echo -e "${GREEN}✅ SQL dump created (${DUMP_SIZE})${NC}"
else
    echo -e "${RED}❌ Failed to create SQL dump${NC}"
    exit 1
fi
echo ""

# Step 4: Create compressed backup
echo -e "${YELLOW}[4/5] Creating compressed backup...${NC}"
COMPRESSED_FILE="${DUMP_FILE}.gz"
gzip -c "$DUMP_FILE" > "$COMPRESSED_FILE"

if [ -f "$COMPRESSED_FILE" ]; then
    COMPRESSED_SIZE=$(du -h "$COMPRESSED_FILE" | cut -f1)
    echo -e "${GREEN}✅ Backup compressed (${COMPRESSED_SIZE})${NC}"
else
    echo -e "${RED}❌ Failed to compress backup${NC}"
    exit 1
fi
echo ""

# Step 5: Display next steps
echo -e "${YELLOW}[5/5] Displaying deployment options...${NC}"
echo ""
echo -e "${GREEN}Data dumps created successfully!${NC}"
echo ""
echo -e "${BLUE}NEXT STEPS FOR AWS DEPLOYMENT:${NC}"
echo ""
echo "Option 1: Direct AWS Sync (recommended)"
echo "  export AWS_RDS_ENDPOINT=\"your-instance.rds.amazonaws.com\""
echo "  export AWS_RDS_USER=\"postgres\""
echo "  export AWS_RDS_PASSWORD=\"your-password\""
echo "  python3 sync_data_to_aws.py --full"
echo ""
echo "Option 2: Using AWS Secrets Manager"
echo "  export AWS_SECRET_ARN=\"arn:aws:secretsmanager:region:account:secret:name\""
echo "  python3 sync_data_to_aws.py --full"
echo ""
echo "Option 3: Manual SQL import"
echo "  gunzip -c $COMPRESSED_FILE | psql -U postgres -h your-aws-endpoint -d stocks"
echo ""
echo -e "${BLUE}Available Dumps:${NC}"
ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}' || echo "  (No compressed dumps found)"
echo ""
echo -e "${GREEN}Local Dump Path: ${DUMP_FILE}${NC}"
echo -e "${GREEN}Compressed Backup: ${COMPRESSED_FILE}${NC}"
echo ""
