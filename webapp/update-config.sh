#!/bin/bash

# Script to update all configuration files with dynamic values
set -e

# Source the detected values
API_GATEWAY_ID="ye9syrnj8c"
AWS_REGION="us-east-1"  
API_STAGE="dev"
API_GATEWAY_URL="https://${API_GATEWAY_ID}.execute-api.${AWS_REGION}.amazonaws.com"
FULL_API_URL="${API_GATEWAY_URL}/${API_STAGE}"

echo "🔧 Updating configuration files with dynamic values..."
echo "  API Gateway ID: $API_GATEWAY_ID"
echo "  AWS Region: $AWS_REGION"
echo "  API Stage: $API_STAGE"
echo "  Full API URL: $FULL_API_URL"
echo ""

# Update frontend environment files
echo "📝 Updating frontend environment files..."

# Frontend .env.development
cat > frontend/.env.development << EOF
# Development Environment - Dynamic Configuration
VITE_API_URL=${FULL_API_URL}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=dev

# AWS Configuration
VITE_AWS_REGION=${AWS_REGION}

# AWS Cognito Configuration - Leave empty to use development mode
VITE_COGNITO_USER_POOL_ID=
VITE_COGNITO_CLIENT_ID=
VITE_COGNITO_DOMAIN=
VITE_COGNITO_REDIRECT_SIGN_IN=http://localhost:3000
VITE_COGNITO_REDIRECT_SIGN_OUT=http://localhost:3000

# Development flags
VITE_ENABLE_DEBUG=true
VITE_ENABLE_MOCK_DATA=false
EOF

# Frontend .env.production
cat > frontend/.env.production << EOF
# Production Environment - Dynamic Configuration
VITE_API_URL=${FULL_API_URL}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=production

# AWS Configuration
VITE_AWS_REGION=${AWS_REGION}

# AWS Cognito Configuration - To be filled by deployment
VITE_COGNITO_USER_POOL_ID=
VITE_COGNITO_CLIENT_ID=
VITE_COGNITO_DOMAIN=
VITE_COGNITO_REDIRECT_SIGN_IN=https://CLOUDFRONT_DOMAIN_PLACEHOLDER
VITE_COGNITO_REDIRECT_SIGN_OUT=https://CLOUDFRONT_DOMAIN_PLACEHOLDER

# Production flags
VITE_ENABLE_DEBUG=false
VITE_ENABLE_MOCK_DATA=false
EOF

# Frontend .env.dev
cat > frontend/.env.dev << EOF
# Dev Environment - Dynamic Configuration
VITE_API_URL=${FULL_API_URL}
VITE_SERVERLESS=true
VITE_ENVIRONMENT=dev
VITE_AWS_REGION=${AWS_REGION}
EOF

# Update runtime config
cat > frontend/public/config.js << EOF
// Runtime configuration - dynamically generated
window.__CONFIG__ = {
  "API_URL": "${FULL_API_URL}",
  "ENVIRONMENT": "production", 
  "VERSION": "1.0.0",
  "AWS_REGION": "${AWS_REGION}",
  "API_GATEWAY_ID": "${API_GATEWAY_ID}",
  "API_STAGE": "${API_STAGE}"
};
EOF

# Update lambda environment
echo "📝 Updating lambda environment file..."
cat > lambda/.env << EOF
# Local development environment variables - Dynamic Configuration
NODE_ENV=development
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=postgres
DB_PASSWORD=password

# AWS Configuration
AWS_REGION=${AWS_REGION}
WEBAPP_AWS_REGION=${AWS_REGION}
API_GATEWAY_ID=${API_GATEWAY_ID}
API_STAGE=${API_STAGE}
API_GATEWAY_URL=${API_GATEWAY_URL}

# AWS Cognito Configuration - Leave empty for development mode
COGNITO_USER_POOL_ID=
COGNITO_CLIENT_ID=

# CORS Configuration
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,${API_GATEWAY_URL}
EOF

echo "✅ Configuration files updated!"
echo ""
echo "📋 Updated files:"
echo "  - frontend/.env.development"  
echo "  - frontend/.env.production"
echo "  - frontend/.env.dev"
echo "  - frontend/public/config.js"
echo "  - lambda/.env"
echo ""
echo "🔧 Next: Update server.js CORS and setup scripts..."
EOF