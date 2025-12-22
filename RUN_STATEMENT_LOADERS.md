# Statement Loaders - Complete Execution Guide

## Problem Summary
- Need ALL financial statement data for score calculations
- Running loaders simultaneously → yfinance API rate limits
- Must avoid errors and data gaps
- Should be fast but reliable

## Solution: Optimized Orchestration + Monitoring

Based on **yfinance best practices** (research-backed):
- 2-5 second delays between loaders (not 15!)
- Smart error detection and monitoring
- Automatic adjustment if issues detected
- Complete data collection with no rate limit errors

---

## Quick Start (Recommended)

```bash
# Standard execution - balanced speed and safety (3s delays)
# Estimated: 25-30 minutes for all 9 loaders
python3 run_statement_loaders_monitored.py --mode standard

# Or use the original orchestrator:
python3 orchestrate_statement_loaders.py --mode standard
```

**That's it!** Loaders run sequentially with:
- ✅ Rate limit protection (smart delays)
- ✅ Real-time error detection
- ✅ Monitoring and reporting
- ✅ Complete data collection

---

## Execution Modes

All modes based on yfinance best practices research (2-5s optimal):

### 1. **fast** (2 second delays) - Fastest
```bash
python3 run_statement_loaders_monitored.py --mode fast
# Time: ~24-27 minutes
# Use: When you know API is stable, want fastest speed
```

### 2. **standard** (3 second delays) - DEFAULT ⭐ RECOMMENDED
```bash
python3 run_statement_loaders_monitored.py --mode standard
# Time: ~25-30 minutes
# Use: Normal production execution
# Balances speed and reliability
```

### 3. **safe** (5 second delays) - Safer
```bash
python3 run_statement_loaders_monitored.py --mode safe
# Time: ~30-35 minutes
# Use: If seeing occasional rate limit errors
# More robust error recovery
```

### 4. **careful** (10 second delays) - Maximum Safety
```bash
python3 run_statement_loaders_monitored.py --mode careful
# Time: ~40-50 minutes
# Use: If experiencing persistent rate limit errors
# Aggressive rate limit protection
```

---

## What Gets Loaded

9 statement loaders execute sequentially:

| # | Loader | Group | Data |
|---|--------|-------|------|
| 1 | Annual Balance Sheet | annual | Assets, Liabilities, Equity |
| 2 | Quarterly Balance Sheet | quarterly | Quarterly financials |
| 3 | Annual Income Statement | annual | Revenue, Expenses, Profit |
| 4 | Quarterly Income Statement | quarterly | Quarterly earnings |
| 5 | Annual Cash Flow | annual | Operating, Investing, Financing |
| 6 | Quarterly Cash Flow | quarterly | Quarterly cash |
| 7 | TTM Income Statement | ttm | Trailing 12-month earnings |
| 8 | TTM Cash Flow | ttm | Trailing 12-month cash |
| 9 | Earnings History | earnings | Historical EPS data |

**Execution order optimized** to minimize API strain and maximize data collection

---

## How It Works

### Sequential Execution (Not Parallel!)
- Loaders run **one at a time** (not simultaneously)
- Each loader processes stocks in batches of 10-20
- Delays between loaders are only **2-5 seconds** (not 15!)
- This prevents API overload while staying fast

### Within Each Loader
- Batches 10-20 symbols per request
- Uses 1-second pauses between batches (already in loader code)
- Automatically backs off 5 seconds on rate limit errors
- Retries up to 3 times with delays

### Rate Limit Protection
- Monitor detects "429 Too Many Requests" errors
- Automatically handles recoveries
- If errors persist, user can switch to safer mode

---

## Expected Results

### Success Output
```
▶️  STARTING: Annual Balance Sheet
   ✓ Successfully got data using balance_sheet for AAPL
   ✓ Successfully processed AAPL (4 records)
   ...
✅ SUCCESS: Annual Balance Sheet completed in 245.3s

⏳ Waiting 3s before next loader...

▶️  STARTING: Quarterly Balance Sheet
   ...
```

### Final Summary
```
================================================================================
EXECUTION SUMMARY
================================================================================
Start: 2025-12-21 14:00:00
End:   2025-12-21 14:27:35
Duration: 27.6 minutes

Results:
  Total:   9
  ✅ Passed:  9
  ❌ Failed:  0
  Success: 100.0%

✅ ALL LOADERS COMPLETED SUCCESSFULLY
   All statement data loaded without errors!
```

---

## Monitoring During Execution

Watch for these indicators:

### ✅ Good Signs
```
✓ Successfully processed [SYMBOL] (X records)
Processing batch 5/10
```

### ⚠️ Warning Signs (May Self-Recover)
```
rate limited (attempt 1/5), waiting 5s
Timeout (attempt 2/3)
Retrying after rate limit...
```

### ❌ Error Signs (May Need Intervention)
```
429 Too Many Requests (repeating)
Database connection refused
Failed after 3 attempts
```

---

## Run Options

### Run All Loaders (DEFAULT)
```bash
python3 run_statement_loaders_monitored.py --mode standard
```

### Run Only Specific Group
```bash
# Annual statements only (Balance Sheet, Income, Cash Flow)
python3 run_statement_loaders_monitored.py --mode standard --group annual

# Quarterly statements only
python3 run_statement_loaders_monitored.py --mode standard --group quarterly

# TTM only
python3 run_statement_loaders_monitored.py --mode standard --group ttm

# Earnings only
python3 run_statement_loaders_monitored.py --mode standard --group earnings
```

### Preview Without Running
```bash
python3 orchestrate_statement_loaders.py --dry-run --mode standard
# Shows execution plan and estimated time
```

---

## Troubleshooting

### Issue: Rate Limit Errors During Execution

**Solution 1: Switch to Safer Mode**
```bash
# Increase delays and retry
python3 run_statement_loaders_monitored.py --mode safe

# Or maximum safety
python3 run_statement_loaders_monitored.py --mode careful
```

**Solution 2: Run Individual Groups**
```bash
# Run one group at a time with longer delays
python3 run_statement_loaders_monitored.py --mode safe --group annual
# Wait for completion, then:
python3 run_statement_loaders_monitored.py --mode safe --group quarterly
```

**Solution 3: Wait and Retry**
- yfinance has hourly rate limits
- Wait 30-60 minutes and retry
- API should reset limits

### Issue: Database Connection Error

**Solution 1: Verify Database**
```bash
# Check PostgreSQL is running
psql -U postgres -d stocks -c "SELECT 1;"

# Check environment variables
echo $DB_HOST
echo $DB_USER
```

**Solution 2: Check AWS Secrets**
```bash
# If using AWS, verify secret
aws secretsmanager get-secret-value --secret-id $DB_SECRET_ARN
```

### Issue: One Loader Failed, Others Passed

**Solution: Re-run Failed Loader**
```bash
# Check which failed (from summary output)
# Re-run individually with extra delays

# Example: If Annual Income Statement failed:
sleep 30  # Wait 30 seconds
python3 loadannualincomestatement.py
```

### Issue: Loader Timed Out

**Solution 1: Increase System Timeout**
```bash
# Run with longer timeout (if loader supports it)
timeout 3600 python3 loadannualincomestatement.py  # 1 hour
```

**Solution 2: Run in Safer Mode**
```bash
python3 run_statement_loaders_monitored.py --mode careful --group annual
```

---

## Performance Notes

### Typical Execution Times

With ~1000 stocks:
- **fast mode**: 24-27 minutes
- **standard mode**: 25-30 minutes (RECOMMENDED)
- **safe mode**: 30-35 minutes
- **careful mode**: 40-50 minutes

With ~2000+ stocks:
- Times roughly double
- May need careful mode to avoid rate limits

### Factors Affecting Speed

1. **Number of stocks** - More stocks = longer execution
2. **Network latency** - Slower connection = longer execution
3. **yfinance API load** - Busy times may trigger rate limits
4. **System resources** - Limited CPU/memory may slow processing

### Optimization Tips

1. **Run during off-peak hours** (early morning, late night)
   - Less API contention
   - Faster responses

2. **Run only needed groups** (if not doing full load)
   ```bash
   python3 run_statement_loaders_monitored.py --mode standard --group annual
   ```

3. **Monitor system resources**
   - CPU usage should stay <50%
   - Memory usage should stay <30%
   - If maxed out, close other applications

---

## Integration with Score Calculation

After all loaders complete successfully:

```bash
# Now you have all statement data, calculate scores:
python3 calculate_scores.py

# Scores will use complete financial statement data
# No data gaps should exist (or are acceptable due to delisted stocks)
```

---

## Advanced Usage

### Scripting / Automation

```bash
#!/bin/bash
# Run statement loaders and check success

python3 run_statement_loaders_monitored.py --mode standard
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "✅ All loaders passed!"
    python3 calculate_scores.py
else
    echo "❌ Some loaders failed, check logs"
    exit 1
fi
```

### Cron Job (Daily Execution)

```bash
# Run daily at 2 AM (off-peak hours)
0 2 * * * cd /home/stocks/algo && python3 run_statement_loaders_monitored.py --mode careful >> logs/statement_loaders.log 2>&1
```

### Log Monitoring

```bash
# Watch logs in real-time
tail -f logs/statement_loaders.log

# Search for errors
grep "ERROR\|FAILED\|rate limit" logs/statement_loaders.log

# Check success rate
grep "SUCCESS\|✅" logs/statement_loaders.log | wc -l
```

---

## Reference: Two Orchestration Tools

### 1. **orchestrate_statement_loaders.py** (Original)
- Pure orchestration
- No internal monitoring
- Simple execution tracking
- Better for scripting/automation

```bash
python3 orchestrate_statement_loaders.py --mode standard
```

### 2. **run_statement_loaders_monitored.py** (Recommended)
- Real-time error detection
- Detailed monitoring output
- Better visibility into failures
- Recommended for manual execution

```bash
python3 run_statement_loaders_monitored.py --mode standard
```

---

## Summary

| Aspect | Details |
|--------|---------|
| **What** | Run 9 financial statement loaders sequentially |
| **Why** | Need all data for score calculations without API rate limits |
| **How** | Sequential execution with 2-5 second delays (yfinance best practices) |
| **Time** | 25-30 minutes for complete data collection |
| **Command** | `python3 run_statement_loaders_monitored.py --mode standard` |
| **Success** | ✅ All data without rate limit errors |
| **Next** | Run `python3 calculate_scores.py` |

---

## Questions?

Check logs for details:
```bash
# View latest logs
tail -100 run_statement_loaders_monitored.py output

# Search for specific errors
grep "ERROR" run_statement_loaders_monitored.py output

# Check individual loader logs
python3 loadannualbalancesheet.py 2>&1 | tail -50
```
