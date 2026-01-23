#!/bin/bash
# Continuous monitoring runner - executes all monitoring checks and consolidates alerts

ALERT_LOG="/tmp/monitoring_consolidated.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
  echo "[$TIMESTAMP] === CONTINUOUS MONITORING CHECK STARTED ==="

  # Run aggressive monitoring
  bash /home/stocks/algo/aggressive_monitoring.sh 2>&1

  # Run data freshness monitoring
  bash /home/stocks/algo/data_freshness_monitor.sh 2>&1

  echo "[$TIMESTAMP] === CHECK COMPLETED ==="
  echo ""

} >> "$ALERT_LOG"

# Keep only last 1000 lines to prevent log from growing too large
tail -1000 "$ALERT_LOG" > "${ALERT_LOG}.tmp" && mv "${ALERT_LOG}.tmp" "$ALERT_LOG"

# Display recent alerts
echo "=== LATEST MONITORING ALERTS ==="
tail -30 "$ALERT_LOG"
