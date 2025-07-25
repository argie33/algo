#!/bin/bash
# Fix Priority 1 Issues - Database, Health, and API URL Configuration
# This script helps fix the 3 most critical issues preventing site functionality

set -e

echo "🔧 Financial Dashboard - Priority 1 Fixes"
echo "=========================================="
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to prompt for input with default
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    
    echo -n "$prompt [$default]: "
    read input
    if [ -z "$input" ]; then
        eval "$var_name='$default'"
    else
        eval "$var_name='$input'"
    fi
}

echo "📋 Step 1: Check Current Environment"
echo "-----------------------------------"

# Check if we're in the right directory
if [ ! -f "lambda/utils/database.js" ]; then
    echo "❌ Error: Please run this script from the webapp root directory"
    echo "   Expected to find: lambda/utils/database.js"
    exit 1
fi

echo "✅ Directory structure looks correct"

# Check Node.js
if command_exists node; then
    NODE_VERSION=$(node --version)
    echo "✅ Node.js version: $NODE_VERSION"
else
    echo "❌ Node.js not found. Please install Node.js first."
    exit 1
fi

# Check AWS CLI
if command_exists aws; then
    AWS_VERSION=$(aws --version 2>&1 | cut -d' ' -f1)
    echo "✅ AWS CLI: $AWS_VERSION"
else
    echo "⚠️ AWS CLI not found. Some features may not work."
fi

echo ""

echo "🗄️ Step 2: Database Configuration"
echo "---------------------------------"

echo "Current database environment variables:"
echo "  DB_HOST: ${DB_HOST:-'not set'}"
echo "  DB_USER: ${DB_USER:-'not set'}"
echo "  DB_PASSWORD: ${DB_PASSWORD:+'[SET]'}"
echo "  DB_NAME: ${DB_NAME:-'not set'}"
echo "  DB_SECRET_ARN: ${DB_SECRET_ARN:-'not set'}"
echo ""

echo "Choose database configuration method:"
echo "1. Direct environment variables (simpler, less secure)"
echo "2. AWS Secrets Manager ARN (recommended for production)"
echo "3. Skip database configuration"

echo -n "Enter choice [1-3]: "
read db_choice

case $db_choice in
    1)
        echo ""
        echo "🔧 Configuring direct database environment variables..."
        
        prompt_with_default "Database host" "localhost" DB_HOST
        prompt_with_default "Database port" "5432" DB_PORT
        prompt_with_default "Database name" "financial_dashboard" DB_NAME
        prompt_with_default "Database user" "postgres" DB_USER
        
        echo -n "Database password: "
        read -s DB_PASSWORD
        echo ""
        
        # Export variables for current session
        export DB_HOST="$DB_HOST"
        export DB_PORT="$DB_PORT"
        export DB_NAME="$DB_NAME"
        export DB_USER="$DB_USER"
        export DB_PASSWORD="$DB_PASSWORD"
        
        echo "✅ Database environment variables set for current session"
        echo ""
        echo "⚠️  IMPORTANT: To make these permanent, add to your deployment:"
        echo "   export DB_HOST=\"$DB_HOST\""
        echo "   export DB_PORT=\"$DB_PORT\""
        echo "   export DB_NAME=\"$DB_NAME\""
        echo "   export DB_USER=\"$DB_USER\""
        echo "   export DB_PASSWORD=\"$DB_PASSWORD\""
        echo ""
        ;;
    2)
        echo ""
        echo "🔑 Configuring AWS Secrets Manager..."
        
        prompt_with_default "Secrets Manager ARN" "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:rds-db-credentials/cluster-XXXXX" DB_SECRET_ARN
        
        export DB_SECRET_ARN="$DB_SECRET_ARN"
        
        echo "✅ Secrets Manager ARN set: $DB_SECRET_ARN"
        echo ""
        echo "⚠️  IMPORTANT: Ensure Lambda has IAM permission:"
        echo "   secretsmanager:GetSecretValue for $DB_SECRET_ARN"
        echo ""
        ;;
    3)
        echo "⏭️ Skipping database configuration"
        echo ""
        ;;
    *)
        echo "❌ Invalid choice. Skipping database configuration."
        echo ""
        ;;
esac

echo "🩺 Step 3: Test Database Connection"
echo "----------------------------------"

if [ "$db_choice" != "3" ]; then
    echo "Testing database connection with current configuration..."
    
    if cd lambda && node scripts/test-database-connection.js; then
        echo "✅ Database connection test passed!"
    else
        echo "❌ Database connection test failed. Check configuration above."
        echo "   You can run the test again with:"
        echo "   cd lambda && node scripts/test-database-connection.js"
    fi
    cd ..
else
    echo "⏭️ Skipping database connection test"
fi

echo ""

echo "🌐 Step 4: Frontend API URL Configuration"
echo "----------------------------------------"

echo "Current frontend configuration:"
echo "  REACT_APP_API_URL: ${REACT_APP_API_URL:-'not set'}"
echo ""

echo "Choose API URL configuration method:"
echo "1. Set REACT_APP_API_URL environment variable"
echo "2. Update frontend config files directly"
echo "3. Skip API URL configuration"

echo -n "Enter choice [1-3]: "
read api_choice

case $api_choice in
    1)
        echo ""
        prompt_with_default "API Gateway URL" "https://your-api-id.execute-api.us-east-1.amazonaws.com/dev" REACT_APP_API_URL
        
        export REACT_APP_API_URL="$REACT_APP_API_URL"
        
        echo "✅ REACT_APP_API_URL set: $REACT_APP_API_URL"
        echo ""
        echo "⚠️  IMPORTANT: Add to your deployment environment:"
        echo "   export REACT_APP_API_URL=\"$REACT_APP_API_URL\""
        echo ""
        ;;
    2)
        echo ""
        echo "🔧 Updating frontend configuration files..."
        
        prompt_with_default "API Gateway URL" "https://your-api-id.execute-api.us-east-1.amazonaws.com/dev" API_URL
        
        # Update public/config.js if it exists
        if [ -f "frontend/public/config.js" ]; then
            echo "Updating frontend/public/config.js..."
            sed -i.bak "s|https://[^']*execute-api[^']*|$API_URL|g" frontend/public/config.js
            echo "✅ Updated frontend/public/config.js"
        fi
        
        echo "✅ Frontend configuration updated"
        echo ""
        ;;
    3)
        echo "⏭️ Skipping API URL configuration"
        echo ""
        ;;
    *)
        echo "❌ Invalid choice. Skipping API URL configuration."
        echo ""
        ;;
esac

echo "🔍 Step 5: Test Health Endpoints"
echo "-------------------------------"

if [ "${REACT_APP_API_URL:-}" != "" ]; then
    API_BASE_URL="$REACT_APP_API_URL"
elif [ "${API_URL:-}" != "" ]; then
    API_BASE_URL="$API_URL"
else
    API_BASE_URL="https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev"
fi

echo "Testing health endpoints at: $API_BASE_URL"
echo ""

# Test quick health endpoint
echo -n "Testing /api/health/quick... "
if command_exists curl; then
    if curl -s -f -m 10 "$API_BASE_URL/api/health/quick" > /dev/null 2>&1; then
        echo "✅ PASS"
    else
        echo "❌ FAIL"
    fi
else
    echo "⏭️ SKIP (curl not available)"
fi

# Test database health endpoint
echo -n "Testing /api/health/database/quick... "
if command_exists curl; then
    if curl -s -f -m 10 "$API_BASE_URL/api/health/database/quick" > /dev/null 2>&1; then
        echo "✅ PASS"
    else
        echo "❌ FAIL"
    fi
else
    echo "⏭️ SKIP (curl not available)"
fi

# Test diagnostic endpoint
echo -n "Testing /api/health/diagnostic... "
if command_exists curl; then
    if curl -s -f -m 10 "$API_BASE_URL/api/health/diagnostic" > /dev/null 2>&1; then
        echo "✅ PASS"
    else
        echo "❌ FAIL"
    fi
else
    echo "⏭️ SKIP (curl not available)"
fi

echo ""

echo "📝 Step 6: Generate Configuration Summary"
echo "---------------------------------------"

# Create configuration summary file
cat > priority1-fix-summary.txt << EOF
Financial Dashboard - Priority 1 Fixes Summary
Generated: $(date)

DATABASE CONFIGURATION:
- Method: ${db_choice:-'Not configured'}
- DB_HOST: ${DB_HOST:-'not set'}
- DB_USER: ${DB_USER:-'not set'}
- DB_NAME: ${DB_NAME:-'not set'}
- DB_SECRET_ARN: ${DB_SECRET_ARN:-'not set'}

API URL CONFIGURATION:
- Method: ${api_choice:-'Not configured'}
- REACT_APP_API_URL: ${REACT_APP_API_URL:-'not set'}
- API_URL: ${API_URL:-'not set'}

ENVIRONMENT VARIABLES TO SET IN DEPLOYMENT:
$([ "$DB_HOST" != "" ] && echo "export DB_HOST=\"$DB_HOST\"")
$([ "$DB_USER" != "" ] && echo "export DB_USER=\"$DB_USER\"")
$([ "$DB_NAME" != "" ] && echo "export DB_NAME=\"$DB_NAME\"")
$([ "$DB_PASSWORD" != "" ] && echo "export DB_PASSWORD=\"[REDACTED]\"")
$([ "$DB_SECRET_ARN" != "" ] && echo "export DB_SECRET_ARN=\"$DB_SECRET_ARN\"")
$([ "$REACT_APP_API_URL" != "" ] && echo "export REACT_APP_API_URL=\"$REACT_APP_API_URL\"")

NEXT STEPS:
1. Deploy backend with database environment variables
2. Deploy frontend with API URL configuration  
3. Test health endpoints: $API_BASE_URL/api/health/diagnostic
4. Run database test: cd lambda && node scripts/test-database-connection.js
5. Check Priority 2 issues: Authentication and API Key management

FILES MODIFIED:
- lambda/utils/database.js (enhanced error reporting)
- lambda/utils/databaseConfigValidator.js (new diagnostic tool)
- lambda/routes/health-v3.js (enhanced health endpoints)
- frontend/src/services/configurationService.js (improved URL resolution)
- frontend/src/services/apiUrlResolver.js (new intelligent URL resolver)
EOF

echo "✅ Configuration summary saved to: priority1-fix-summary.txt"
echo ""

echo "🎉 Priority 1 Fixes Complete!"
echo "=============================="
echo ""
echo "Summary of changes made:"
echo "✅ Enhanced database configuration with better error reporting"
echo "✅ Added database connection validator and test script"
echo "✅ Improved health endpoints with diagnostic information"
echo "✅ Enhanced frontend API URL resolution with fallback mechanisms"
echo "✅ Created configuration summary and deployment guide"
echo ""
echo "📋 Next steps:"
echo "1. Review the configuration summary in: priority1-fix-summary.txt"
echo "2. Deploy your application with the environment variables shown above"
echo "3. Test the health endpoints to verify fixes are working"
echo "4. Proceed to Priority 2 fixes (Authentication and API Keys)"
echo ""
echo "🔍 For detailed diagnostics, run:"
echo "   $API_BASE_URL/api/health/diagnostic"
echo ""
echo "💾 All configuration values have been saved to priority1-fix-summary.txt"
echo "   Review this file before deployment!"

exit 0