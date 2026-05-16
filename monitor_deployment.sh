#!/bin/bash
# Monitor AWS deployment status and test endpoints

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         AWS DEPLOYMENT MONITORING & TESTING                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

API_ENDPOINT="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
FRONTEND_URL="https://d5j1h4wzrkvw7.cloudfront.net"

# ═══════════════════════════════════════════════════════════════════
# CHECK GITHUB ACTIONS DEPLOYMENT
# ═══════════════════════════════════════════════════════════════════

echo "1. GitHub Actions Deployment Status"
echo "   View at: https://github.com/argie33/algo/actions"
echo

if command -v gh &> /dev/null; then
    echo "   Latest workflow run:"
    gh run list --repo argie33/algo --limit 1 --json status,conclusion,name 2>/dev/null || echo "   (requires 'gh auth login')"
else
    echo "   (GitHub CLI not installed)"
fi

echo

# ═══════════════════════════════════════════════════════════════════
# TEST API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

echo "2. API Endpoint Testing"
echo

# Test health endpoint
echo "   Testing: GET /api/health"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/api/health")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ HTTP $HTTP_CODE - API is healthy"
else
    echo "   ✗ HTTP $HTTP_CODE - API health check failed"
fi

# Test stocks endpoint
echo "   Testing: GET /api/stocks"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/api/stocks?limit=1")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ HTTP $HTTP_CODE - Stocks endpoint working"
else
    echo "   ✗ HTTP $HTTP_CODE - Stocks endpoint failed"
fi

# Test algo status
echo "   Testing: GET /api/algo/status"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/api/algo/status")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ HTTP $HTTP_CODE - Algo status endpoint working"
else
    echo "   ✗ HTTP $HTTP_CODE - Algo status endpoint failed"
fi

# Test market exposure
echo "   Testing: GET /api/algo/markets"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/api/algo/markets")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ HTTP $HTTP_CODE - Market exposure endpoint working"
else
    echo "   ✗ HTTP $HTTP_CODE - Market exposure endpoint failed"
fi

echo

# ═══════════════════════════════════════════════════════════════════
# CHECK FRONTEND
# ═══════════════════════════════════════════════════════════════════

echo "3. Frontend Status"
echo "   URL: $FRONTEND_URL"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL")
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ HTTP $HTTP_CODE - Frontend is accessible"
else
    echo "   ✗ HTTP $HTTP_CODE - Frontend not accessible"
fi

echo

# ═══════════════════════════════════════════════════════════════════
# CHECK AWS RESOURCES (if credentials available)
# ═══════════════════════════════════════════════════════════════════

echo "4. AWS Resources"
echo

if command -v aws &> /dev/null; then
    # Check Lambda functions
    if aws lambda list-functions --region us-east-1 &>/dev/null; then
        LAMBDA_COUNT=$(aws lambda list-functions --region us-east-1 --query 'Functions[?contains(FunctionName, `algo`)].FunctionName' --output text | wc -w)
        echo "   ✓ Lambda functions: $LAMBDA_COUNT algo-related functions deployed"
    fi

    # Check RDS database
    if aws rds describe-db-instances --region us-east-1 &>/dev/null; then
        DB_STATUS=$(aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1 --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "not found")
        echo "   Database status: $DB_STATUS"
    fi

    # Check API Gateway
    if aws apigateway get-rest-apis --region us-east-1 &>/dev/null; then
        API_COUNT=$(aws apigateway get-rest-apis --region us-east-1 --query 'items[?contains(name, `algo`)].name' --output text | wc -w)
        echo "   ✓ API Gateway: $API_COUNT API gateway(s) deployed"
    fi
else
    echo "   (AWS CLI not installed - optional)"
fi

echo

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    SUMMARY                                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

echo "Next Steps:"
echo "1. Wait for GitHub Actions to complete (if not already done)"
echo "2. Once API returns 200 OK, system is deployed"
echo "3. Load frontend at: $FRONTEND_URL"
echo "4. Run local verification: python3 verify_system_ready.py"
echo "5. Monitor logs: aws logs tail /aws/lambda/algo-orchestrator --follow"
echo

echo "Documentation:"
echo "- Deployment Guide: AWS_DEPLOYMENT_RUNBOOK.md"
echo "- Status: STATUS.md"
echo "- Architecture: ALGO_ARCHITECTURE.md"
echo
