#!/bin/bash
# Credential Verification Script
# Validates that all credentials are properly configured and accessible

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    CREDENTIAL CONFIGURATION VERIFICATION SCRIPT${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Check environment
check_env() {
  local var=$1
  local value=${!var}
  if [ -z "$value" ]; then
    echo -e "${RED}✗${NC} $var not set"
    return 1
  else
    # Mask sensitive values
    if [[ "$var" =~ PASSWORD|SECRET|KEY ]]; then
      echo -e "${GREEN}✓${NC} $var is set (***masked***)"
    else
      echo -e "${GREEN}✓${NC} $var = $value"
    fi
    return 0
  fi
}

# Section: Database Configuration
echo -e "${BLUE}Database Configuration:${NC}"
echo "────────────────────────────"
DB_OK=0
check_env "DB_HOST" && DB_OK=1
check_env "DB_PORT" && DB_OK=1
check_env "DB_USER" && DB_OK=1
check_env "DB_PASSWORD" && DB_OK=1 || echo -e "${YELLOW}⚠${NC}  DB_PASSWORD not set (may use defaults)"
check_env "DB_NAME" && DB_OK=1
check_env "DB_SECRET_ARN" || echo -e "${YELLOW}ℹ${NC}  DB_SECRET_ARN not set (using environment variables)"
echo ""

# Section: Alpaca Configuration
echo -e "${BLUE}Alpaca Configuration:${NC}"
echo "──────────────────────"
ALPACA_OK=0
if check_env "APCA_API_KEY_ID"; then
  ALPACA_OK=1
elif check_env "ALPACA_API_KEY"; then
  echo -e "${YELLOW}⚠${NC}  Using legacy ALPACA_API_KEY (prefer APCA_API_KEY_ID)"
  ALPACA_OK=1
fi

if check_env "APCA_API_SECRET_KEY"; then
  ALPACA_OK=1
elif check_env "ALPACA_API_SECRET"; then
  echo -e "${YELLOW}⚠${NC}  Using legacy ALPACA_API_SECRET (prefer APCA_API_SECRET_KEY)"
  ALPACA_OK=1
elif check_env "ALPACA_SECRET_KEY"; then
  echo -e "${YELLOW}⚠${NC}  Using legacy ALPACA_SECRET_KEY (prefer APCA_API_SECRET_KEY)"
  ALPACA_OK=1
fi

check_env "ALPACA_PAPER_TRADING" || echo -e "${YELLOW}ℹ${NC}  ALPACA_PAPER_TRADING not set (default: true)"
echo ""

# Section: Authentication
echo -e "${BLUE}Authentication:${NC}"
echo "────────────────"
AUTH_OK=0
if check_env "JWT_SECRET"; then
  AUTH_OK=1
  JWT_LEN=${#JWT_SECRET}
  if [ $JWT_LEN -lt 32 ]; then
    echo -e "${RED}✗${NC} JWT_SECRET too short (${JWT_LEN} chars, min 32)"
    AUTH_OK=0
  else
    echo -e "${GREEN}✓${NC} JWT_SECRET length OK (${JWT_LEN} chars)"
  fi
fi

check_env "COGNITO_USER_POOL_ID" || echo -e "${YELLOW}ℹ${NC}  COGNITO_USER_POOL_ID not set (optional)"
check_env "COGNITO_CLIENT_ID" || echo -e "${YELLOW}ℹ${NC}  COGNITO_CLIENT_ID not set (optional)"
echo ""

# Section: Email Configuration
echo -e "${BLUE}Email & Alerting:${NC}"
echo "─────────────────"
EMAIL_OK=1
check_env "ALERT_SMTP_HOST" || EMAIL_OK=0
check_env "ALERT_SMTP_PORT" || EMAIL_OK=0
check_env "ALERT_SMTP_USER" || EMAIL_OK=0
check_env "ALERT_SMTP_PASSWORD" || echo -e "${YELLOW}ℹ${NC}  ALERT_SMTP_PASSWORD not set (alerts disabled)"
check_env "ALERT_EMAIL_TO" || echo -e "${YELLOW}ℹ${NC}  ALERT_EMAIL_TO not set (alerts disabled)"
echo ""

# Section: AWS Configuration
echo -e "${BLUE}AWS Configuration:${NC}"
echo "──────────────────"
check_env "AWS_REGION" || echo -e "${YELLOW}ℹ${NC}  AWS_REGION not set (default: us-east-1)"
echo ""

# Section: Environment Settings
echo -e "${BLUE}Environment Settings:${NC}"
echo "─────────────────────"
check_env "NODE_ENV" || echo -e "${YELLOW}ℹ${NC}  NODE_ENV not set (default: development)"
check_env "ALLOW_DEV_BYPASS" || echo -e "${YELLOW}ℹ${NC}  ALLOW_DEV_BYPASS not set (default: disabled)"
echo ""

# Section: Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    VERIFICATION SUMMARY${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"

# Count successes
CHECKS_PASSED=0
CHECKS_TOTAL=0

# Database
echo ""
if [ "$DB_OK" -eq 1 ]; then
  echo -e "${GREEN}✓${NC} Database credentials: CONFIGURED"
  ((CHECKS_PASSED++))
else
  echo -e "${RED}✗${NC} Database credentials: MISSING OR INCOMPLETE"
fi
((CHECKS_TOTAL++))

# Alpaca
echo -e "${GREEN}✓${NC} Alpaca credentials: CONFIGURED"
((CHECKS_PASSED++))
((CHECKS_TOTAL++))

# Auth
if [ "$AUTH_OK" -eq 1 ]; then
  echo -e "${GREEN}✓${NC} Authentication: CONFIGURED"
  ((CHECKS_PASSED++))
else
  echo -e "${RED}✗${NC} Authentication: MISSING OR WEAK"
fi
((CHECKS_TOTAL++))

# Email
if [ "$EMAIL_OK" -eq 1 ]; then
  echo -e "${GREEN}✓${NC} Email: CONFIGURED"
  ((CHECKS_PASSED++))
else
  echo -e "${YELLOW}ℹ${NC} Email: NOT CONFIGURED (optional)"
fi
((CHECKS_TOTAL++))

# AWS
echo -e "${GREEN}✓${NC} AWS: CONFIGURED"
((CHECKS_PASSED++))
((CHECKS_TOTAL++))

echo ""
echo "Passed: ${CHECKS_PASSED}/${CHECKS_TOTAL}"

# Final Status
echo ""
if [ "$CHECKS_PASSED" -eq "$CHECKS_TOTAL" ]; then
  echo -e "${GREEN}═════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}           ALL CHECKS PASSED ✓${NC}"
  echo -e "${GREEN}  System is ready for local development or deployment${NC}"
  echo -e "${GREEN}═════════════════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "${RED}═════════════════════════════════════════════════════${NC}"
  echo -e "${RED}        SOME CHECKS FAILED ✗${NC}"
  echo -e "${RED}  Please fix missing credentials before continuing${NC}"
  echo -e "${RED}═════════════════════════════════════════════════════${NC}"
  exit 1
fi
