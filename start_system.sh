#!/bin/bash
# Start the algo system in local or AWS mode
# Usage: ./start_system.sh local   # Development (localhost)
#        ./start_system.sh aws     # Production (AWS endpoints)

set -e

MODE=${1:-local}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$MODE" = "local" ]; then
    echo "Starting Algo System in LOCAL MODE"
    echo "===================================="
    echo ""
    echo "Terminal 1 (API Server):"
    echo "  cd \"$REPO_ROOT\""
    echo "  python api-pkg/dev_server.py"
    echo ""
    echo "Terminal 2 (Dashboard):"
    echo "  cd \"$REPO_ROOT\""
    echo "  python -m dashboard --local"
    echo ""
    echo "Starting API server..."
    cd "$REPO_ROOT/api-pkg"
    python dev_server.py

elif [ "$MODE" = "aws" ]; then
    echo "Starting Algo System in AWS MODE"
    echo "=================================="
    echo ""
    echo "Requires AWS credentials and Cognito configuration."
    echo "Environment variables needed:"
    echo "  - DASHBOARD_API_URL: AWS Lambda API endpoint"
    echo "  - COGNITO_USER_POOL_ID: Cognito User Pool ID"
    echo "  - COGNITO_CLIENT_ID: Cognito Client ID"
    echo ""
    echo "Starting dashboard..."
    cd "$REPO_ROOT"
    python -m dashboard

else
    echo "Usage: $0 [local|aws]"
    echo "  local - Development mode (recommended)"
    echo "  aws   - Production mode (requires AWS credentials)"
    exit 1
fi
