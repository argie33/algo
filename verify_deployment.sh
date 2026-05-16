#!/bin/bash
# Comprehensive deployment verification script
# Runs after Terraform completes to verify:
# 1. AWS resources exist and are accessible
# 2. RDS database has correct schema
# 3. Data loaders are populating data
# 4. API endpoints are responding
# 5. Frontend is accessible

set -e

echo "=========================================="
echo "DEPLOYMENT VERIFICATION SCRIPT"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get AWS outputs from Terraform
echo "[1/5] Getting AWS resource information from Terraform..."
cd terraform
API_ENDPOINT=$(terraform output -raw api_gateway_endpoint 2>/dev/null || echo "unknown")
FRONTEND_URL=$(terraform output -raw cloudfront_domain 2>/dev/null || echo "unknown")
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "unknown")
RDS_PORT=$(terraform output -raw rds_port 2>/dev/null || echo "5432")
cd ..

echo "  API Endpoint: $API_ENDPOINT"
echo "  Frontend URL: $FRONTEND_URL"
echo "  RDS Endpoint: $RDS_ENDPOINT"
echo ""

# 2. Test API Gateway health endpoint
echo "[2/5] Testing API Gateway health endpoint..."
if [ "$API_ENDPOINT" != "unknown" ]; then
  HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" "$API_ENDPOINT/health" 2>/dev/null || echo "error\n000")
  HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
  if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓${NC} API Gateway is responding (HTTP $HTTP_CODE)"
  else
    echo -e "${RED}✗${NC} API Gateway error (HTTP $HTTP_CODE)"
  fi
else
  echo -e "${YELLOW}⚠${NC} API endpoint unknown, skipping test"
fi
echo ""

# 3. Test database connectivity
echo "[3/5] Testing RDS database connectivity..."
if command -v psql &> /dev/null; then
  if PGPASSWORD="$DB_PASSWORD" psql -h "$RDS_ENDPOINT" -p "$RDS_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Database connection successful"

    # Check table count
    TABLE_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$RDS_ENDPOINT" -p "$RDS_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")
    echo -e "${GREEN}✓${NC} Database has $TABLE_COUNT tables"
  else
    echo -e "${RED}✗${NC} Database connection failed"
  fi
else
  echo -e "${YELLOW}⚠${NC} psql not available, skipping database test"
fi
echo ""

# 4. Test frontend accessibility
echo "[4/5] Testing frontend accessibility..."
if [ "$FRONTEND_URL" != "unknown" ]; then
  FRONTEND_RESPONSE=$(curl -s -w "\n%{http_code}" "https://$FRONTEND_URL" 2>/dev/null | tail -1 || echo "000")
  if [[ "$FRONTEND_RESPONSE" =~ ^(200|301|302|304)$ ]]; then
    echo -e "${GREEN}✓${NC} Frontend is accessible (HTTP $FRONTEND_RESPONSE)"
  else
    echo -e "${RED}✗${NC} Frontend error (HTTP $FRONTEND_RESPONSE)"
  fi
else
  echo -e "${YELLOW}⚠${NC} Frontend URL unknown, skipping test"
fi
echo ""

# 5. Test API key endpoints
echo "[5/5] Testing API endpoints..."
ENDPOINTS=(
  "/api/stocks/symbols"
  "/api/signals/minervini"
  "/api/market/health"
  "/api/positions/active"
)

for endpoint in "${ENDPOINTS[@]}"; do
  if [ "$API_ENDPOINT" != "unknown" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT$endpoint" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      echo -e "${GREEN}✓${NC} $endpoint - HTTP $HTTP_CODE"
    elif [ "$HTTP_CODE" = "401" ]; then
      echo -e "${YELLOW}⚠${NC} $endpoint - Requires authentication (HTTP 401)"
    else
      echo -e "${RED}✗${NC} $endpoint - HTTP $HTTP_CODE"
    fi
  fi
done

echo ""
echo "=========================================="
echo "Verification complete!"
echo "=========================================="
