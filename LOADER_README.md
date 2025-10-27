# Real Data Loader - Safe Execution Guide

## Overview

The data loader system ensures that:
- ✅ **Only ONE loader instance runs at a time** (file-based locking)
- ✅ **REAL DATA ONLY** (no fake defaults, no synthetic data)
- ✅ **Sequential execution** (no parallel conflicts)
- ✅ **Comprehensive validation** (data integrity checks)
- ✅ **Detailed logging** (audit trail for all operations)

---

## Three Ways to Run Loaders

### Option 1: Safe Shell Script (Recommended)

```bash
/home/stocks/algo/load_real_data.sh
```

**What it does:**
- Checks for running loaders (prevents concurrent execution)
- Loads environment variables
- Runs all loaders sequentially with locking
- Verifies real data was loaded
- Generates summary report

**Output:**
- Console output with color-coded messages
- Log file: `/home/stocks/logs/data_load_YYYYMMDD_HHMMSS.log`
- Summary file: `/home/stocks/logs/data_load_summary.txt`

---

### Option 2: Python Safe Loader Runner

```bash
python3 /home/stocks/algo/run_loaders_safe.py
```

**What it does:**
- Acquires exclusive file lock
- Runs loaders in sequence:
  1. loadcompanyprofile.py
  2. loadecondata.py
  3. loadkeymetrics.py
  4. loadtechnicalsdaily.py
  5. loadpositioning.py
  6. loadsentiment.py
  7. loadbuyselldaily.py
  8. loadbuysellweekly.py
  9. loadbuysellmonthly.py
  10. populate_signal_metrics.py
- Logs to: `/home/stocks/algo/loader.log`

---

### Option 3: Verify Data Only

```bash
python3 /home/stocks/algo/verify_real_data.py
```

**What it does:**
- Checks database contains real data
- Validates OHLC invariants
- Checks for fake defaults
- Reports data quality metrics

---

## Database Connection

The loaders need database credentials. Set them before running:

```bash
export DB_HOST=your.database.host
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=postgres
export DB_PASSWORD=your_password
```

Or use AWS:
```bash
export AWS_REGION=us-east-1
export DB_SECRET_ARN=arn:aws:secretsmanager:...
```

Or use local environment file:
```bash
source /home/stocks/algo/.env.local
```

---

## Monitoring Running Loaders

### Check if loaders are running:
```bash
pgrep -f "load.*\.py"
ps aux | grep load | grep -v grep
```

### View live logs:
```bash
tail -f /home/stocks/algo/loader.log
tail -f /home/stocks/logs/data_load_*.log
```

### Kill running loader:
```bash
pkill -f "run_loaders_safe.py"
pkill -f "loadbuyselldaily.py"
```

---

## Lock File

The system uses file-based locking to prevent concurrent execution:

**Lock file location:** `/home/stocks/algo/.loader_lock`

- Created when loader starts
- Deleted when loader completes
- Stale locks (>1 hour) automatically removed
- Contains: PID and start timestamp

---

## Data Integrity Guarantees

### What Gets Loaded:
- ✅ Real company profile data
- ✅ Real price data (OHLC)
- ✅ Real technical indicators (RSI, ADX, ATR, etc.)
- ✅ Real positioning data (institutional, insider, short)
- ✅ Real sentiment data (RSI-based, MACD-based)
- ✅ Real buy/sell signals (with validation)

### What Does NOT Get Loaded:
- ❌ No hardcoded defaults (50, 0, 'Neutral')
- ❌ No fake fallback values
- ❌ No calculated proxies instead of real data
- ❌ No missing data as zeros
- ❌ No NULL values stored as fake 0

### Validation Checks:
1. **OHLC Invariants**: high ≥ low, prices > 0
2. **NaN/Infinity**: All calculations validated
3. **Data Completeness**: Required fields checked
4. **No Defaults**: Missing data = None (not fake 0)
5. **Extreme Outliers**: Volume spikes capped at 5x

---

## Troubleshooting

### "Another loader is already running"
- Check: `ps aux | grep load | grep -v grep`
- Kill: `pkill -f loadbuyselldaily.py`
- Wait 30 seconds
- Try again

### "Database connection failed"
- Verify DB credentials are set
- Check database is running and accessible
- Test: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

### "Loader timeout"
- Each loader has 30-minute timeout
- Check logs: `/home/stocks/logs/data_load_*.log`
- May indicate slow database or API rate limiting

### "Verification checks failed"
- Not necessarily a failure (some data may be loading)
- Check logs for specific failures
- Run `verify_real_data.py` periodically as data loads

---

## Common Commands

```bash
# Run with safe locking (recommended)
/home/stocks/algo/load_real_data.sh

# Run just the Python orchestrator
python3 /home/stocks/algo/run_loaders_safe.py

# Verify data quality
python3 /home/stocks/algo/verify_real_data.py

# View logs
tail -f /home/stocks/algo/loader.log
tail -f /home/stocks/logs/data_load_*.log

# Check for running loaders
pgrep -f "load.*\.py"

# Kill all loaders
pkill -f "load.*\.py"
```

---

## Expected Behavior

### First Run (Complete Data Load)
- Takes 2-6 hours depending on number of stocks
- Creates/updates all tables
- Loads 5000+ stock symbols
- Generates all signals and metrics

### Subsequent Runs (Incremental Update)
- Much faster (15-30 minutes)
- Updates recent data only
- Refreshes technical indicators
- Regenerates today's signals

---

## Support

For issues:
1. Check logs: `/home/stocks/logs/data_load_*.log`
2. Verify database connectivity
3. Ensure API credentials are valid
4. Check database has required tables
5. Review loader documentation

---

**Data Integrity Commitment:**
Every piece of data loaded is real, sourced from authoritative databases, and validated against fake defaults.
