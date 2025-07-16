#!/bin/bash

# Claude Code Token Monitor Configuration Script
# Automatically detects and runs token monitoring for Claude Code sessions

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Claude Code Token Monitor Setup${NC}"
echo "=================================="

# Check if monitor is installed
if ! command -v claude-monitor &> /dev/null; then
    echo -e "${RED}❌ claude-monitor not found. Please install it first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ claude-monitor is installed${NC}"

# Detect timezone
TIMEZONE=$(timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC")
echo -e "${BLUE}📍 Detected timezone: ${TIMEZONE}${NC}"

# Since you mentioned you have Claude Max subscription, we'll use the max20 plan
PLAN="max20"
echo -e "${BLUE}📊 Using plan: ${PLAN}${NC}"

# Set reset hour (3 AM is recommended to avoid peak usage times)
RESET_HOUR="3"
echo -e "${BLUE}🕐 Token reset hour: ${RESET_HOUR}:00${NC}"

# Create monitoring command
MONITOR_CMD="claude-monitor --plan ${PLAN} --reset-hour ${RESET_HOUR} --timezone ${TIMEZONE}"

echo -e "${YELLOW}🚀 Starting Claude Code Token Monitor...${NC}"
echo -e "${BLUE}Command: ${MONITOR_CMD}${NC}"
echo ""

# Run the monitor
exec $MONITOR_CMD