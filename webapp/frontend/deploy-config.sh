#!/bin/bash

# Deployment Configuration Script
# This script updates the runtime configuration with proper values during deployment
# Usage: ./deploy-config.sh <environment> <api-gateway-url> <cognito-user-pool-id> <cognito-client-id>

set -e

# Configuration parameters
ENVIRONMENT=${1:-production}
STACK_NAME=${2:-"stocks-webapp-${1:-production}"}
API_GATEWAY_URL=${3:-""}
COGNITO_USER_POOL_ID=${4:-""}
COGNITO_CLIENT_ID=${5:-""}
AUTO_FETCH_FROM_CF=${6:-"true"}

# Auto-fetch from CloudFormation if enabled and values not provided
if [ "$AUTO_FETCH_FROM_CF" = "true" ]; then
    echo "🔍 Auto-fetching configuration from CloudFormation stack: $STACK_NAME"
    
    # Check if stack exists
    if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" >/dev/null 2>&1; then
        echo "❌ Error: CloudFormation stack '$STACK_NAME' not found"
        echo "Available stacks:"
        aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'StackSummaries[].StackName' --output table
        exit 1
    fi
    
    # Fetch real values from CloudFormation outputs
    if [ -z "$API_GATEWAY_URL" ]; then
        API_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
            --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" --output text)
        echo "📡 Fetched API Gateway URL: $API_GATEWAY_URL"
    fi
    
    if [ -z "$COGNITO_USER_POOL_ID" ]; then
        COGNITO_USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)
        echo "🔐 Fetched Cognito User Pool ID: ${COGNITO_USER_POOL_ID:0:15}..."
    fi
    
    if [ -z "$COGNITO_CLIENT_ID" ]; then
        COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
            --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text)
        echo "🔑 Fetched Cognito Client ID: ${COGNITO_CLIENT_ID:0:8}..."
    fi
fi

# Validate required parameters after auto-fetch
if [ -z "$API_GATEWAY_URL" ]; then
    echo "❌ Error: API Gateway URL is required"
    echo "Usage: $0 <environment> [stack-name] [api-gateway-url] [cognito-user-pool-id] [cognito-client-id] [auto-fetch]"
    echo "Example: $0 dev stocks-webapp-dev"  
    echo "Example: $0 prod stocks-webapp-prod https://abc123.execute-api.us-east-1.amazonaws.com/prod us-east-1_ABC123 xyz789"
    exit 1
fi

if [ -z "$COGNITO_USER_POOL_ID" ]; then
    echo "❌ Error: Cognito User Pool ID is required"
    echo "Set AUTO_FETCH_FROM_CF=false if providing manually"
    exit 1
fi

if [ -z "$COGNITO_CLIENT_ID" ]; then
    echo "❌ Error: Cognito Client ID is required"
    echo "Set AUTO_FETCH_FROM_CF=false if providing manually"
    exit 1
fi

echo "🚀 Configuring deployment for environment: $ENVIRONMENT"
echo "🏗️ CloudFormation Stack: $STACK_NAME"
echo "📡 API Gateway URL: $API_GATEWAY_URL"
echo "🔐 Cognito User Pool ID: ${COGNITO_USER_POOL_ID:0:15}..."
echo "🔑 Cognito Client ID: ${COGNITO_CLIENT_ID:0:8}..."
echo "⚙️ Auto-fetch from CF: $AUTO_FETCH_FROM_CF"

# Path to config file
CONFIG_FILE="public/config.js"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Error: Config file not found at $CONFIG_FILE"
    exit 1
fi

# Backup original config
cp "$CONFIG_FILE" "$CONFIG_FILE.backup"
echo "📝 Created backup: $CONFIG_FILE.backup"

# Create updated config
cat > "$CONFIG_FILE" << EOF
/**
 * Production Runtime Configuration
 * Generated automatically during deployment - DO NOT EDIT MANUALLY
 * Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
 */

window.__CONFIG__ = {
  // Build Information
  BUILD_TIME: "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  VERSION: "${VERSION:-1.0.0}",
  ENVIRONMENT: "$ENVIRONMENT",
  
  // API Configuration
  API: {
    BASE_URL: "$API_GATEWAY_URL",
    VERSION: "v1",
    TIMEOUT: 30000,
    RETRY_ATTEMPTS: 3,
    RETRY_DELAY: 1000
  },
  
  // AWS Configuration
  AWS: {
    REGION: "${AWS_REGION:-us-east-1}"
  },
  
  // Cognito Configuration
  COGNITO: {
    USER_POOL_ID: "$COGNITO_USER_POOL_ID",
    CLIENT_ID: "$COGNITO_CLIENT_ID",
    REGION: "${AWS_REGION:-us-east-1}",
    DOMAIN: "${COGNITO_DOMAIN:-}",
    REDIRECT_SIGN_IN: "${COGNITO_REDIRECT_SIGN_IN:-\${window.location.origin}}",
    REDIRECT_SIGN_OUT: "${COGNITO_REDIRECT_SIGN_OUT:-\${window.location.origin}}"
  },
  
  // Feature Flags
  FEATURES: {
    AUTHENTICATION: true,
    COGNITO_AUTH: true,
    OAUTH_AUTH: ${FEATURE_OAUTH_AUTH:-false},
    BIOMETRIC_AUTH: ${FEATURE_BIOMETRIC_AUTH:-false},
    
    TRADING: true,
    PAPER_TRADING: true,
    REAL_TRADING: ${FEATURE_REAL_TRADING:-false},
    CRYPTO_TRADING: ${FEATURE_CRYPTO_TRADING:-false},
    OPTIONS_TRADING: ${FEATURE_OPTIONS_TRADING:-false},
    
    AI_FEATURES: true,
    AI_SIGNALS: true,
    AI_PORTFOLIO_OPTIMIZATION: ${FEATURE_AI_PORTFOLIO:-true},
    AI_RISK_ANALYSIS: ${FEATURE_AI_RISK:-true},
    
    DATA_FEATURES: true,
    REALTIME_DATA: ${FEATURE_REALTIME_DATA:-true},
    HISTORICAL_DATA: true,
    NEWS_DATA: true,
    SOCIAL_SENTIMENT: ${FEATURE_SOCIAL_SENTIMENT:-false},
    
    UI_FEATURES: true,
    DARK_MODE: true,
    CUSTOM_THEMES: ${FEATURE_CUSTOM_THEMES:-false},
    MOBILE_SUPPORT: true,
    ACCESSIBILITY: true,
    
    DEVELOPMENT_FEATURES: false,
    DEBUG_MODE: ${DEBUG_MODE:-false},
    MOCK_DATA: false,
    DEV_TOOLS: false
  },
  
  // External API Configuration
  EXTERNAL_APIS: {
    ALPACA: {
      BASE_URL: "${ALPACA_BASE_URL:-https://paper-api.alpaca.markets}",
      DATA_URL: "${ALPACA_DATA_URL:-https://data.alpaca.markets}",
      WS_URL: "${ALPACA_WS_URL:-wss://stream.data.alpaca.markets}",
      IS_PAPER: ${ALPACA_IS_PAPER:-true}
    },
    POLYGON: {
      BASE_URL: "${POLYGON_BASE_URL:-https://api.polygon.io}",
      WS_URL: "${POLYGON_WS_URL:-wss://socket.polygon.io}"
    },
    FMP: {
      BASE_URL: "${FMP_BASE_URL:-https://financialmodelingprep.com/api}"
    },
    FINNHUB: {
      BASE_URL: "${FINNHUB_BASE_URL:-https://finnhub.io/api/v1}",
      WS_URL: "${FINNHUB_WS_URL:-wss://ws.finnhub.io}"
    }
  },
  
  // Performance Configuration
  PERFORMANCE: {
    CACHE: {
      ENABLED: ${CACHE_ENABLED:-true},
      TTL: {
        MARKET_DATA: ${CACHE_MARKET_DATA_TTL:-60000},
        PORTFOLIO: ${CACHE_PORTFOLIO_TTL:-300000},
        NEWS: ${CACHE_NEWS_TTL:-900000},
        STATIC: ${CACHE_STATIC_TTL:-3600000}
      }
    },
    RATE_LIMIT: {
      ENABLED: ${RATE_LIMIT_ENABLED:-true},
      REQUESTS_PER_MINUTE: ${RATE_LIMIT_PER_MINUTE:-100},
      REQUESTS_PER_HOUR: ${RATE_LIMIT_PER_HOUR:-1000},
      REQUESTS_PER_DAY: ${RATE_LIMIT_PER_DAY:-10000}
    },
    WEBSOCKET: {
      ENABLED: ${WEBSOCKET_ENABLED:-true},
      RECONNECT_INTERVAL: ${WS_RECONNECT_INTERVAL:-5000},
      MAX_RECONNECT_ATTEMPTS: ${WS_MAX_RECONNECT:-10},
      HEARTBEAT_INTERVAL: ${WS_HEARTBEAT_INTERVAL:-30000}
    }
  },
  
  // Security Configuration
  SECURITY: {
    ENCRYPTION_ENABLED: ${ENCRYPTION_ENABLED:-true},
    SESSION_TIMEOUT: ${SESSION_TIMEOUT:-3600000},
    TOKEN_REFRESH_BEFORE: ${TOKEN_REFRESH_BEFORE:-300000},
    MAX_CONCURRENT_SESSIONS: ${MAX_CONCURRENT_SESSIONS:-3},
    CSP_ENABLED: ${CSP_ENABLED:-true},
    CSP_REPORT_ONLY: ${CSP_REPORT_ONLY:-false}
  },
  
  // Monitoring Configuration
  MONITORING: {
    LOGGING_ENABLED: ${LOGGING_ENABLED:-true},
    LOG_LEVEL: "${LOG_LEVEL:-info}",
    LOG_CONSOLE: ${LOG_CONSOLE:-true},
    LOG_REMOTE: ${LOG_REMOTE:-false},
    ERROR_TRACKING_ENABLED: ${ERROR_TRACKING_ENABLED:-false},
    ANALYTICS_ENABLED: ${ANALYTICS_ENABLED:-false}
  }
};

// Environment-specific overrides
if (window.__CONFIG__.ENVIRONMENT === 'development') {
  window.__CONFIG__.FEATURES.DEBUG_MODE = true;
  window.__CONFIG__.FEATURES.MOCK_DATA = true;
  window.__CONFIG__.FEATURES.DEV_TOOLS = true;
  window.__CONFIG__.MONITORING.LOG_LEVEL = 'debug';
  window.__CONFIG__.SECURITY.CSP_REPORT_ONLY = true;
}

// Validation
window.__CONFIG__.validate = function() {
  const errors = [];
  const warnings = [];
  
  if (this.FEATURES.AUTHENTICATION && this.FEATURES.COGNITO_AUTH) {
    if (!this.COGNITO.USER_POOL_ID) {
      errors.push('COGNITO.USER_POOL_ID is required');
    }
    if (!this.COGNITO.CLIENT_ID) {
      errors.push('COGNITO.CLIENT_ID is required');
    }
  }
  
  if (!this.API.BASE_URL) {
    errors.push('API.BASE_URL is required');
  }
  
  return { errors, warnings, isValid: errors.length === 0 };
};

// Auto-validate
setTimeout(() => {
  const validation = window.__CONFIG__.validate();
  if (validation.errors.length > 0) {
    console.error('❌ Configuration Errors:', validation.errors);
  }
  if (validation.warnings.length > 0) {
    console.warn('⚠️ Configuration Warnings:', validation.warnings);
  }
  if (validation.isValid) {
    console.log('✅ Configuration validated successfully');
  }
}, 100);
EOF

echo "✅ Configuration updated successfully!"
echo "🔍 Validating configuration..."

# Basic validation
if grep -q "$COGNITO_USER_POOL_ID" "$CONFIG_FILE"; then
    echo "✅ Cognito User Pool ID configured"
else
    echo "❌ Failed to configure Cognito User Pool ID"
    exit 1
fi

if grep -q "$COGNITO_CLIENT_ID" "$CONFIG_FILE"; then
    echo "✅ Cognito Client ID configured"
else
    echo "❌ Failed to configure Cognito Client ID"
    exit 1
fi

if grep -q "$API_GATEWAY_URL" "$CONFIG_FILE"; then
    echo "✅ API Gateway URL configured"
else
    echo "❌ Failed to configure API Gateway URL"
    exit 1
fi

echo "🎉 Deployment configuration completed successfully!"
echo ""
echo "📋 Summary:"
echo "  Environment: $ENVIRONMENT"
echo "  API URL: $API_GATEWAY_URL"
echo "  Cognito Pool: ${COGNITO_USER_POOL_ID:0:15}..."
echo "  Cognito Client: ${COGNITO_CLIENT_ID:0:8}..."
echo ""
echo "⚠️  Remember to:"
echo "  1. Set environment variables for external API keys"
echo "  2. Configure proper CORS settings on API Gateway"
echo "  3. Test authentication flow after deployment"
echo "  4. Monitor logs for any configuration issues"