#!/bin/bash

# Script to detect current deployment and generate dynamic configuration
set -e

echo "🔍 Detecting current deployment configuration..."

# Extract current API Gateway ID from existing config
CURRENT_API_URL=$(grep -r "ye9syrnj8c.execute-api" frontend/.env* 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d '"' || echo "")

if [ -n "$CURRENT_API_URL" ]; then
    # Parse the URL components
    API_GATEWAY_ID=$(echo "$CURRENT_API_URL" | sed 's/https:\/\/\([^.]*\).*/\1/')
    AWS_REGION=$(echo "$CURRENT_API_URL" | sed 's/.*execute-api\.\([^.]*\).*/\1/')
    API_STAGE=$(echo "$CURRENT_API_URL" | sed 's/.*amazonaws.com\/\(.*\)/\1/')
    
    echo "✅ Current deployment detected:"
    echo "  API Gateway ID: $API_GATEWAY_ID"
    echo "  AWS Region: $AWS_REGION"
    echo "  API Stage: $API_STAGE"
    echo "  Full API URL: $CURRENT_API_URL"
else
    echo "❌ Could not detect current deployment"
    echo "Please provide your API Gateway details:"
    read -p "API Gateway ID (e.g., ye9syrnj8c): " API_GATEWAY_ID
    read -p "AWS Region (default: us-east-1): " AWS_REGION
    read -p "API Stage (default: dev): " API_STAGE
    
    AWS_REGION=${AWS_REGION:-us-east-1}
    API_STAGE=${API_STAGE:-dev}
    CURRENT_API_URL="https://${API_GATEWAY_ID}.execute-api.${AWS_REGION}.amazonaws.com/${API_STAGE}"
fi

echo ""
echo "📝 Generating dynamic configuration..."

# Create dynamic environment template
cat > .env.template << EOF
# Dynamic deployment configuration - Auto-generated
# Copy this to your specific environment files

# Core API Configuration
API_GATEWAY_ID=${API_GATEWAY_ID}
AWS_REGION=${AWS_REGION}
API_STAGE=${API_STAGE}
API_GATEWAY_URL=https://\${API_GATEWAY_ID}.execute-api.\${AWS_REGION}.amazonaws.com
VITE_API_URL=\${API_GATEWAY_URL}/\${API_STAGE}

# CORS Configuration  
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,\${API_GATEWAY_URL}

# Frontend Runtime Config
VITE_SERVERLESS=true
VITE_ENVIRONMENT=production
VITE_AWS_REGION=\${AWS_REGION}

# Development flags
VITE_ENABLE_DEBUG=true
VITE_ENABLE_MOCK_DATA=false
EOF

echo "✅ Template created: .env.template"
echo ""
echo "🔧 Next steps:"
echo "1. Review the template above"
echo "2. Run './update-config.sh' to apply dynamic configuration"
echo "3. Configure Cognito settings"