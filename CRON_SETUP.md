# Automated Execution - Cron Job Setup

Run your algo automatically 2x daily during market hours.

---

## Quick Setup (Linux/macOS)

```bash
# 1. Make orchestrator script executable
chmod +x scripts/run_local_orchestrator.py

# 2. Create Python wrapper script (handles virtualenv)
cat > /usr/local/bin/algo-orchestrator << 'SCRIPT'
#!/bin/bash
cd /path/to/algo
source venv/bin/activate  # or your Python venv
python scripts/run_local_orchestrator.py "$@"
SCRIPT

chmod +x /usr/local/bin/algo-orchestrator

# 3. Add to crontab
crontab -e

# Add these lines:
# Morning run: 9:30 AM ET (market open)
30 9 * * MON-FRI /usr/local/bin/algo-orchestrator --morning

# Evening run: 4:05 PM ET (after market close)
5 16 * * MON-FRI /usr/local/bin/algo-orchestrator --evening
```

Verify:
```bash
crontab -l
# Should show your two new lines
```

---

## Detailed Setup

### Step 1: Prepare Your Machine

```bash
# Ensure your machine is on 24/7 (or at scheduled times)
# macOS: System Preferences → Energy Saver → Never sleep
# Linux: Check your cron daemon is running
sudo systemctl status cron  # Ubuntu/Debian
sudo systemctl status crond  # RHEL/CentOS

# Or use a cheap VPS ($5-10/mo) to run cron jobs
```

### Step 2: Create Wrapper Script

The wrapper handles:
- Changing to project directory
- Loading Python virtualenv
- Running orchestrator
- Logging output

```bash
# Create the wrapper
sudo tee /usr/local/bin/algo-orchestrator > /dev/null << 'WRAPPER'
#!/bin/bash
set -e

# Configuration
PROJECT_DIR="/home/you/code/algo"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
SCRIPT="$PROJECT_DIR/scripts/run_local_orchestrator.py"

# Create log directory
mkdir -p "$LOG_DIR"

# Log start
echo "[$(date)] Starting orchestrator with args: $@" >> "$LOG_DIR/orchestrator.log"

# Activate virtualenv and run
cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"
python "$SCRIPT" "$@" >> "$LOG_DIR/orchestrator.log" 2>&1

# Log completion
echo "[$(date)] Orchestrator completed" >> "$LOG_DIR/orchestrator.log"
WRAPPER

# Make executable
sudo chmod +x /usr/local/bin/algo-orchestrator
```

Replace `/home/you/code/algo` with your actual project path.

### Step 3: Set Up Cron Jobs

```bash
crontab -e
```

Add these lines (adjust times for your timezone):

```cron
# Environment setup (optional, helps with mail notifications)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
MAILTO=your-email@example.com

# Morning run: 9:30 AM ET (adjust to your timezone)
# In UTC, ET 9:30 AM = UTC 1:30 PM (EDT) or UTC 2:30 PM (EST)
30 13 * * MON-FRI /usr/local/bin/algo-orchestrator --morning

# Evening run: 4:05 PM ET (adjust to your timezone)  
# In UTC, ET 4:05 PM = UTC 8:05 PM (EDT) or UTC 9:05 PM (EST)
5 20 * * MON-FRI /usr/local/bin/algo-orchestrator --evening
```

**Note:** Cron times are in system timezone. Run `date` to check:
```bash
date
# Tue Jul 17 10:30:45 EDT 2026
```

Convert your desired times to cron format:
- 9:30 AM = `30 9`
- 4:05 PM = `5 16`

### Step 4: Verify

```bash
# Check crontab was installed
crontab -l

# Watch cron logs (on macOS)
log stream --predicate 'eventMessage contains "algo"' --level debug

# Watch cron logs (on Linux)
sudo tail -f /var/log/syslog | grep CRON
```

Test manually:
```bash
# Run morning pipeline now to verify it works
/usr/local/bin/algo-orchestrator --morning

# Should complete without errors
```

---

## Monitoring & Logging

### Check Logs

```bash
# View all orchestrator output
tail -f logs/orchestrator.log

# Check last run
tail -20 logs/orchestrator.log

# Check for errors
grep ERROR logs/orchestrator.log
grep FAILED logs/orchestrator.log
```

### Email Notifications (Optional)

Cron can email you on failure:

```bash
# Edit crontab
crontab -e

# Add at top:
MAILTO=your-email@example.com

# Now cron emails on error (non-zero exit code)
```

### Slack/Webhook Notifications (Advanced)

Add to `scripts/run_local_orchestrator.py` or wrapper:

```python
import subprocess
import requests

try:
    result = subprocess.run([...], check=True)
    # Success
    requests.post("YOUR_SLACK_WEBHOOK", json={
        "text": "✅ Algo pipeline completed successfully"
    })
except subprocess.CalledProcessError as e:
    # Failure
    requests.post("YOUR_SLACK_WEBHOOK", json={
        "text": f"❌ Algo pipeline FAILED: {e}"
    })
```

---

## Windows Setup (Task Scheduler)

If you're on Windows:

```powershell
# 1. Open Task Scheduler
taskschd.msc

# 2. Create Basic Task
# Name: Algo Morning Run
# Trigger: Daily, 9:30 AM, Repeat: MON-FRI
# Action: Start a program
#   Program: C:\Python312\python.exe
#   Arguments: C:\path\to\algo\scripts\run_local_orchestrator.py --morning
#   Start in: C:\path\to\algo

# 3. Repeat for Evening Run (4:05 PM)
```

---

## Troubleshooting

### Cron Job Not Running

```bash
# 1. Check cron is running
sudo systemctl status cron

# 2. Check crontab syntax
crontab -l | head
# Should show no errors

# 3. Test with simple job
echo "0 * * * * touch /tmp/cron-test" | crontab -
# Wait one minute, check if /tmp/cron-test exists

# 4. Check cron logs
grep CRON /var/log/syslog  # Linux
log show --predicate 'process == "cron"'  # macOS
```

### "No such file or directory"

Cron runs with minimal environment. Use absolute paths:

```bash
# ❌ BAD (relative path)
30 9 * * MON-FRI cd /path/to/algo && python scripts/run.py

# ✅ GOOD (absolute path + wrapper)
30 9 * * MON-FRI /usr/local/bin/algo-orchestrator --morning
```

### "ModuleNotFoundError"

Cron doesn't load your virtualenv by default:

```bash
# ✅ Correct (activate venv in wrapper)
source /path/to/algo/venv/bin/activate
python scripts/run.py

# Or use absolute path to venv python
/path/to/algo/venv/bin/python scripts/run.py
```

### Database Connection Failed

Cron runs with a different environment. Make sure:

```bash
# 1. Database is running
docker ps | grep postgres

# 2. Database starts on boot
docker-compose up -d  # (in your repo, runs postgres with restart: unless-stopped)

# 3. Connection credentials work
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# 4. Firewall allows localhost connections
# (Usually not an issue on same machine)
```

---

## Maintenance

### Monthly: Review Logs

```bash
# Check for errors
grep -i error logs/orchestrator.log | tail -20

# Check success rate
grep SUCCESS logs/orchestrator.log | wc -l  # Should be ~40/month
```

### Quarterly: Update Cron Times

If market hours change or daylight savings:

```bash
crontab -e
# Update the times as needed
```

### Annually: Review Schedule

```bash
crontab -l
# Verify it still makes sense for your needs
```

---

## Next Steps

1. ✅ Local setup working
2. ✅ Cron jobs configured
3. ➡️ **Deploy to AWS** (see DEPLOYMENT_GUIDE.md)
4. ➡️ **Set up monitoring** (see RUNBOOK.md)
