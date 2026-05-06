#!/bin/bash
# Deploy automated monitoring to cron
# Usage: bash deploy_cron.sh
# This sets up daily orchestrator + optional continuous monitoring

set -e

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/var/log/algo"

echo "========================================="
echo "Algo Monitoring Deployment"
echo "========================================="
echo

# Check prerequisites
echo "[1/4] Checking prerequisites..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

if ! python3 -c "import psycopg2" 2>/dev/null; then
    echo "ERROR: psycopg2 not installed"
    exit 1
fi

# Create log directory
echo "[2/4] Setting up logging..."
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/orchestrator.log"
touch "$LOG_DIR/monitor.log"
touch "$LOG_DIR/trends.log"
chmod 755 "$LOG_DIR"

# Check .env.local
echo "[3/4] Checking configuration..."
if [ ! -f "$REPO_PATH/.env.local" ]; then
    echo "ERROR: .env.local not found"
    echo "  1. Copy .env.template to .env.local"
    echo "  2. Fill in your credentials"
    echo "  3. Run this script again"
    exit 1
fi

# Show current cron (if any)
echo "[4/4] Current cron jobs:"
crontab -l 2>/dev/null | grep algo || echo "  (none yet)"

echo
echo "========================================="
echo "Cron Job Setup"
echo "========================================="
echo

# Create crontab entries
CRON_ENTRIES=$(cat <<'EOF'
# Algo Monitoring — Daily orchestrator (8 AM, Mon-Fri)
0 8 * * 1-5 cd REPO_PATH && python3 algo_orchestrator.py >> LOG_DIR/orchestrator.log 2>&1

# Algo Monitoring — Continuous critical checks (every 15 min, 9:30-16:00 ET, Mon-Fri)
*/15 9-16 * * 1-5 cd REPO_PATH && python3 algo_continuous_monitor.py --once >> LOG_DIR/monitor.log 2>&1

# Algo Monitoring — Weekly trends (Friday 5 PM)
0 17 * * 5 cd REPO_PATH && python3 algo_quality_trends.py --days 7 >> LOG_DIR/trends.log 2>&1
EOF
)

# Replace placeholders
CRON_ENTRIES="${CRON_ENTRIES//REPO_PATH/$REPO_PATH}"
CRON_ENTRIES="${CRON_ENTRIES//LOG_DIR/$LOG_DIR}"

echo "Ready to install these cron jobs:"
echo
echo "$CRON_ENTRIES"
echo
echo "========================================="
echo

read -p "Install cron jobs? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Add to crontab
    (crontab -l 2>/dev/null || true; echo "$CRON_ENTRIES") | crontab -
    echo "✓ Cron jobs installed"

    echo
    echo "Daily schedule:"
    echo "  8:00 AM   — Run full patrol + orchestrator"
    echo "  9:30-4:00 — Continuous monitoring (every 15 min)"
    echo "  5:00 PM   — Weekly trends analysis"
    echo
    echo "Logs:"
    echo "  $LOG_DIR/orchestrator.log  — Daily runs"
    echo "  $LOG_DIR/monitor.log       — Continuous checks"
    echo "  $LOG_DIR/trends.log        — Weekly analysis"
    echo
    crontab -l | grep algo
else
    echo "Skipped. You can:"
    echo "  1. Run manually: python3 algo_orchestrator.py"
    echo "  2. Install cron later"
    echo "  3. Use systemd/supervisor/etc"
fi

echo
echo "========================================="
echo "Setup Complete!"
echo "========================================="
