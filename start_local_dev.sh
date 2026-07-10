#!/usr/bin/env bash
# Start local development environment (dev_server + dashboard TUI)
#
# Usage:
#   ./start_local_dev.sh                # Start dashboard in local mode with watch
#   ./start_local_dev.sh --no-watch     # Single refresh, don't watch
#   ./start_local_dev.sh --dashboard-only # Start dashboard only (dev_server already running)
#
# Requirements: Python 3.11+, PostgreSQL running on localhost:5432

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${API_PORT:-3001}"
NO_WATCH=false
DASHBOARD_ONLY=false
DEV_SERVER_PID=

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-watch)
            NO_WATCH=true
            shift
            ;;
        --dashboard-only)
            DASHBOARD_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--no-watch] [--dashboard-only]"
            exit 1
            ;;
    esac
done

cleanup() {
    if [[ -n "$DEV_SERVER_PID" ]]; then
        echo ""
        echo "Cleaning up..."
        kill $DEV_SERVER_PID 2>/dev/null || true
        wait $DEV_SERVER_PID 2>/dev/null || true
        echo "✓ Stopped dev_server"
    fi
}

trap cleanup EXIT

echo "=== LOCAL DEVELOPMENT ENVIRONMENT ==="
echo "Starting local dev_server + dashboard..."
echo ""

# Start dev_server in background if not --dashboard-only
if [[ "$DASHBOARD_ONLY" != "true" ]]; then
    echo "[1/2] Starting dev_server on http://localhost:$API_PORT"
    cd "$SCRIPT_DIR"
    python api-pkg/dev_server.py &
    DEV_SERVER_PID=$!
    echo "  Process ID: $DEV_SERVER_PID"

    # Wait for dev_server to be ready
    echo "  Waiting for dev_server to be ready..."
    attempts=0
    while [[ $attempts -lt 30 ]]; do
        if curl -s -H "Authorization: Bearer dev-admin" \
                 "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
            echo "  ✓ dev_server ready (took $((attempts*500))ms)"
            break
        fi
        sleep 0.5
        ((attempts++))
    done

    if [[ $attempts -ge 30 ]]; then
        echo "ERROR: dev_server did not start in time (30s)" >&2
        exit 1
    fi
    echo ""
fi

# Start dashboard with --local flag
echo "[2/2] Starting dashboard (LOCAL MODE)"
echo "  Dashboard API: http://localhost:$API_PORT"

if [[ "$NO_WATCH" == "true" ]]; then
    echo "  Mode: Single refresh"
    python -m dashboard --local
else
    echo "  Mode: Watch mode (refresh every 30s)"
    echo "  Press 'q' to quit"
    python -m dashboard --local -w 30
fi

