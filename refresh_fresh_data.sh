#!/bin/bash

# Refresh Fresh Market Data Script
# Runs every 4 hours during market hours to keep latest data current
# Can be added to crontab or run manually

SCRIPT_DIR="/home/stocks/algo"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="/tmp/fresh_data_refresh.log"

echo "[${TIMESTAMP}] Starting fresh market data refresh..." >> "${LOG_FILE}"

cd "${SCRIPT_DIR}"

# Run the comprehensive fresh data getter (includes all pages)
python3 get_latest_comprehensive_data.py >> "${LOG_FILE}" 2>&1
RESULT=$?

if [ $RESULT -eq 0 ]; then
  echo "[${TIMESTAMP}] ✅ Fresh data refresh completed successfully" >> "${LOG_FILE}"
  echo "✅ Fresh market data updated at ${TIMESTAMP}"
else
  echo "[${TIMESTAMP}] ❌ Fresh data refresh failed with code ${RESULT}" >> "${LOG_FILE}"
  echo "❌ Failed to refresh fresh data"
fi

# Keep log file from getting too large (keep last 1000 lines)
tail -1000 "${LOG_FILE}" > "${LOG_FILE}.tmp"
mv "${LOG_FILE}.tmp" "${LOG_FILE}"

exit $RESULT
