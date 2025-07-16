#!/bin/bash

# Start Claude Code Token Monitor
# This script runs the monitor in the background

echo "🚀 Starting Claude Code Token Monitor..."

# Check if monitor is already running
if pgrep -f "claude-monitor" > /dev/null; then
    echo "⚠️  Monitor is already running. Stopping existing instance..."
    pkill -f "claude-monitor"
    sleep 2
fi

# Start the monitor in the background
nohup claude-monitor --plan max20 --reset-hour 3 --timezone $(timedatectl show --property=Timezone --value 2>/dev/null || echo "UTC") > /home/stocks/algo/claude-monitor.log 2>&1 &

echo "✅ Monitor started in background"
echo "📝 Logs are being written to: /home/stocks/algo/claude-monitor.log"
echo "🔍 To view logs: tail -f /home/stocks/algo/claude-monitor.log"
echo "🛑 To stop monitor: pkill -f claude-monitor"