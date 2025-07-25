#!/bin/bash

# Fix Validation Script
# Tests the CloudFront fix and validates all functionality

set -e

echo "🔍 Validating CloudFront API Fix"
echo "================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m' 
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Step 1: Test API Health
echo -e "${BLUE}Step 1: Testing API health endpoint...${NC}"

API_RESPONSE=$(curl -s -H "Accept: application/json" https://d1zb7knau41vl9.cloudfront.net/api/health)
CONTENT_TYPE=$(curl -s -I https://d1zb7knau41vl9.cloudfront.net/api/health | grep -i content-type | cut -d' ' -f2- | tr -d '\r')

if echo "$CONTENT_TYPE" | grep -q "application/json"; then
    echo -e "${GREEN}✅ API health returns JSON${NC}"
    
    # Try to parse JSON
    if echo "$API_RESPONSE" | jq . > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Valid JSON response${NC}"
        SUCCESS_STATUS=$(echo "$API_RESPONSE" | jq -r '.success // false')
        if [ "$SUCCESS_STATUS" = "true" ]; then
            echo -e "${GREEN}✅ API reports success status${NC}"
        else
            echo -e "${YELLOW}⚠️  API returns JSON but success=false${NC}"
        fi
    else
        echo -e "${RED}❌ Response is not valid JSON${NC}"
        echo "Response: $API_RESPONSE"
    fi
else
    echo -e "${RED}❌ API health still returns HTML${NC}"
    echo "Content-Type: $CONTENT_TYPE"
    echo -e "${YELLOW}CloudFront changes may still be propagating...${NC}"
fi

# Step 2: Run comprehensive API test
echo -e "${BLUE}Step 2: Running comprehensive API test...${NC}"

if [ -f "test-api-routing.js" ]; then
    node test-api-routing.js | tail -n 20
else
    echo -e "${YELLOW}⚠️  test-api-routing.js not found${NC}"
fi

# Step 3: Test frontend build
echo -e "${BLUE}Step 3: Testing frontend build...${NC}"

if [ -d "frontend" ]; then
    cd frontend
    
    # Check if dependencies are installed
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing frontend dependencies...${NC}"
        npm install
    fi
    
    # Run build test
    echo -e "${BLUE}Running frontend build test...${NC}"
    if npm run build > build.log 2>&1; then
        echo -e "${GREEN}✅ Frontend builds successfully${NC}"
    else
        echo -e "${RED}❌ Frontend build failed${NC}"
        tail -n 10 build.log
    fi
    
    cd ..
else
    echo -e "${YELLOW}⚠️  Frontend directory not found${NC}"
fi

# Step 4: Generate summary report
echo ""
echo -e "${BLUE}📊 VALIDATION SUMMARY${NC}"
echo "======================"

# Test each critical endpoint
ENDPOINTS=(
    "/api/health"
    "/api/stocks" 
    "/api/portfolio/holdings"
    "/api/market/overview"
)

WORKING=0
TOTAL=${#ENDPOINTS[@]}

for endpoint in "${ENDPOINTS[@]}"; do
    RESPONSE=$(curl -s -H "Accept: application/json" "https://d1zb7knau41vl9.cloudfront.net$endpoint")
    if echo "$RESPONSE" | jq . > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $endpoint"
        ((WORKING++))
    else
        echo -e "${RED}❌${NC} $endpoint"
    fi
done

echo ""
echo -e "Working endpoints: ${GREEN}$WORKING${NC}/${TOTAL}"

if [ $WORKING -eq $TOTAL ]; then
    echo -e "${GREEN}🎉 ALL SYSTEMS OPERATIONAL!${NC}"
    echo -e "${GREEN}Frontend pages should now display live data${NC}"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Open your web application"
    echo "2. Check Dashboard for live data"
    echo "3. Verify Portfolio loads holdings"
    echo "4. Confirm all widgets display content"
elif [ $WORKING -gt 0 ]; then
    echo -e "${YELLOW}⚠️  PARTIAL SUCCESS${NC}"
    echo "Some endpoints working, CloudFront may still be propagating"
    echo "Wait 5-10 more minutes and re-run this script"
else
    echo -e "${RED}❌ NO ENDPOINTS WORKING${NC}"
    echo "CloudFront configuration may need to be checked"
    echo "Review MANUAL_CLOUDFRONT_FIX.md for troubleshooting"
fi

echo ""
echo -e "${BLUE}To re-run validation: ./validate-fix.sh${NC}"