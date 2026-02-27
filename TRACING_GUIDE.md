# System Tracing & Monitoring Guide

## Overview

Comprehensive tracing is now in place to monitor system health and catch issues before they cause crashes.

## Files Created

### 1. **SYSTEM_MONITOR.sh** - System Health Monitoring
Tracks:
- System crashes/reboots
- Memory usage trends
- Service health
- Kernel errors
- Disk space

**Usage:**
```bash
# One-time system check
bash SYSTEM_MONITOR.sh

# Continuous monitoring (updates every 60 seconds)
bash SYSTEM_MONITOR.sh --continuous
```

**Log Locations:**
- `logs/system_monitoring/crash_detection.log` - Unclean shutdowns
- `logs/system_monitoring/memory_history.log` - Memory trends
- `logs/system_monitoring/system_health.log` - Health checks
- `logs/system_monitoring/alerts.log` - All alerts
- `logs/system_monitoring/loader_activity.log` - Active loaders

### 2. **LOADER_TRACER.sh** - Data Loader Execution Tracking
Tracks:
- Loader start/stop times
- Resource usage (memory, CPU)
- Execution duration
- Error conditions
- Completion status

**Usage:**
```bash
# Manual start/end logging
bash LOADER_TRACER.sh start load_name
bash LOADER_TRACER.sh end load_name [exit_code]

# Run a loader with automatic tracing
bash LOADER_TRACER.sh run ./loadstocksymbols.py

# View execution summary
bash LOADER_TRACER.sh summary
```

**Log Locations:**
- `logs/loader_traces/execution_log.txt` - All runs
- `logs/loader_traces/resource_usage.log` - Memory/CPU over time
- `logs/loader_traces/errors.log` - Errors only
- `logs/loader_traces/[loader_name].log` - Per-loader logs

### 3. **TRACE_AND_LOAD.sh** - Safe Loading with Integrated Tracing
Combines safe sequential loading with comprehensive tracing.

**Usage:**
```bash
# Run all loaders with full tracing
bash TRACE_AND_LOAD.sh
```

Features:
- ✅ Sequential execution (one loader at a time)
- ✅ Memory checks (300MB minimum before each loader)
- ✅ Resource monitoring between loaders
- ✅ Automatic logging
- ✅ Execution summary

## Monitoring Strategy

### Daily Checks
```bash
# Check for crashes since last session
bash SYSTEM_MONITOR.sh

# View recent memory trends
tail -20 logs/system_monitoring/memory_history.log

# Check for any alerts
tail -20 logs/system_monitoring/alerts.log
```

### During Loader Execution
```bash
# Run loaders with full tracing
bash TRACE_AND_LOAD.sh

# Alternatively, monitor continuously in a separate terminal
bash SYSTEM_MONITOR.sh --continuous
```

### After Loader Execution
```bash
# View execution summary
bash LOADER_TRACER.sh summary

# View any errors
cat logs/loader_traces/errors.log

# Check final system state
bash SYSTEM_MONITOR.sh
```

## Key Metrics to Watch

### Memory Usage ⚠️
- **SAFE**: < 60% used (> 1.5GB free on 3.8GB system)
- **WARNING**: 60-80% used (0.8-1.5GB free)
- **CRITICAL**: > 80% used (< 0.8GB free) - STOP and investigate

### System Load 🔴
- **SAFE**: < 4.0 on 8-core system
- **WARNING**: 4.0-8.0
- **CRITICAL**: > 8.0 (system thrashing)

### Free RAM 🟢
- **SAFE**: > 400MB
- **WARNING**: 300-400MB
- **CRITICAL**: < 300MB (automatic alerts)

## Alert Messages

You'll see alerts like:

```
[ALERT] 2026-02-26 15:30:45 - CRASH DETECTED
  System had unclean shutdown. Check logs/system_monitoring/crash_detection.log

[ALERT] 2026-02-26 15:30:45 - HIGH MEMORY USAGE
  Memory usage is 85.2% (3.2GB). Free: 0.6GB
```

**Action Items:**
1. Note the timestamp
2. Check the corresponding log file
3. Look at loader process list: `ps aux | grep python`
4. If needed, kill processes: `pkill -f loadbuyselldaily.py`
5. Review the session log for what happened

## Automated Trace Collection

All monitoring runs automatically create logs in:
```
/home/arger/algo/logs/
├── system_monitoring/
│   ├── crash_detection.log
│   ├── memory_history.log
│   ├── system_health.log
│   ├── alerts.log
│   └── loader_activity.log
└── loader_traces/
    ├── execution_log.txt
    ├── resource_usage.log
    ├── errors.log
    └── [per-loader logs]
```

## Crash Investigation

If a crash occurs again:

1. **Check for crash log:**
   ```bash
   cat logs/system_monitoring/crash_detection.log
   ```

2. **Review memory history before crash:**
   ```bash
   tail -30 logs/system_monitoring/memory_history.log
   ```

3. **Check kernel logs:**
   ```bash
   journalctl -b -1 | grep -i "error\|warn" | tail -20
   ```

4. **Review loader execution:**
   ```bash
   tail -50 logs/loader_traces/execution_log.txt
   ```

5. **Check for unattended-upgrades (should be masked):**
   ```bash
   systemctl status unattended-upgrades
   # Should show: masked (Reason: Unit unattended-upgrades.service is masked.)
   ```

## Next Steps

1. **Initialize baseline:**
   ```bash
   bash SYSTEM_MONITOR.sh
   ```

2. **Run loaders with tracing:**
   ```bash
   bash TRACE_AND_LOAD.sh
   ```

3. **Check results:**
   ```bash
   bash LOADER_TRACER.sh summary
   ```

4. **Set up continuous monitoring (optional):**
   ```bash
   # In a separate terminal
   bash SYSTEM_MONITOR.sh --continuous
   ```

## Protection Summary

You now have:
- ✅ **System crash detection** - Detects unclean shutdowns
- ✅ **Memory monitoring** - Alerts on high usage
- ✅ **Loader tracking** - Logs all loader execution
- ✅ **Resource tracking** - Monitors CPU/Memory during runs
- ✅ **Error logging** - Captures all failures
- ✅ **Alert system** - Warns of critical conditions
- ✅ **Audit trail** - Complete history for debugging

This provides complete visibility into what's happening and will catch any issues early.
