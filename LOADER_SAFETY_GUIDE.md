# ⚠️ Data Loader Safety Guide

## **NEVER Use These Scripts** (SYSTEM CRASH RISK)
These scripts are **DISABLED** and renamed with `.disabled` extension:
- ❌ `DISABLED_RUN_ALL_LOADERS_WITH_ERRORS.sh` - No memory protection, includes heavy financial loaders
- ❌ `DISABLED_RUN_EVERYTHING.sh` - Starts all services + loaders simultaneously (memory exhaustion)

## **ALWAYS Use This Script** (SAFE)
- ✅ `safe_loaders.sh` - Memory-protected, sequential execution

## Why safe_loaders.sh Works

### System Protection
```
Before starting:
✓ Checks free RAM (minimum 300MB required)
✓ Checks load average (waits if system busy)
✓ Kills any previously stuck loaders

During loading:
✓ Runs loaders ONE AT A TIME (no parallel)
✓ Monitors RAM after each loader
✓ Logs everything to /tmp/*.log
```

### Worker Limits
- Daily prices: 1 instance only
- Weekly prices: 1 instance only
- Monthly prices: 1 instance only
- Signal loader: **3 workers max** (reduced from 5-6)
- Technical indicators: 1 instance only

This prevents memory exhaustion from too many parallel threads.

## Quick Start

```bash
# Check current system memory
free -h

# Run safe loaders (should show 300MB+ available)
bash safe_loaders.sh

# Monitor progress
tail -f /tmp/symbols.log      # Stock symbols
tail -f /tmp/technical.log    # Technical data
tail -f /tmp/price_daily.log  # Daily prices (largest)
tail -f /tmp/signals.log      # Buy/Sell signals
```

## If System Crashes Anyway

1. **Kill stuck loaders**
   ```bash
   pkill -f "python3 load"
   ```

2. **Check memory**
   ```bash
   free -h
   ```

3. **Restart and try again** (with more free RAM)
   ```bash
   bash safe_loaders.sh
   ```

## Memory Requirements

- **System total:** 3.8GB (WSL2)
- **Minimum free for loaders:** 300MB
- **Per worker thread:** ~90MB
- **Safe concurrent threads:** 3 (270MB)

With only 3.8GB total on a Windows machine running WSL2, parallel loading with more than 3 workers per loader will cause crashes.

---

**Last Updated:** Feb 26, 2026 20:40 UTC
**Status:** All dangerous scripts disabled, only safe_loaders.sh available
