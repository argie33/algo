# Loader Concurrency Strategy - CRITICAL

**Problem**: Multiple loaders running concurrently causes:
- Database connection pool exhaustion (max 10 connections)
- yfinance API rate limiting (shared IP)
- Slower execution (contention)
- Database locks

**Solution**: Sequential execution with clear stages

---

## LOADER EXECUTION ORDER (SEQUENTIAL)

### Stage 1: Bulk Price Load (One-Time, ~10 minutes)
```bash
python3 loadpricedaily_fast.py    # FAST bulk loader (50 symbols/batch)
```
**Why one-time**: Populates 22M+ historical price records. Only needed once.

### Stage 2: Company Data (One-Time, ~30-45 minutes)
```bash
python3 loaddailycompanydata.py   # Creates key_metrics table (required by factor metrics)
```

### Stage 3: Financial Statements (Parallel OK, ~2-3 hours total)
```bash
# These can run in parallel - independent data sources
python3 loadannualincomestatement.py &
python3 loadannualbalancesheet.py &
python3 loadannualcashflow.py &
python3 loadquarterlyincomestatement.py &
python3 loadquarterlybalancesheet.py &
python3 loadquarterlycashflow.py &
wait  # Wait for all to complete
```

### Stage 4: Factor Metrics (One-Time, ~1-2 hours)
```bash
python3 loadfactormetrics.py      # Depends on all financials + prices
```

### Stage 5: Stock Scores (One-Time, ~30 minutes)
```bash
python3 loadstockscores.py        # Depends on all metrics
```

### Stage 6: Trading Signals (Parallel OK, ~4-6 hours total)
```bash
# These can run in parallel - process different timeframes
python3 loadbuyselldaily.py &
python3 loadbuysellweekly.py &
python3 loadbuysellmonthly.py &
wait
```

### Stage 7: Market Context (Parallel OK, ~1-2 hours total)
```bash
python3 loadsectorranking.py &
python3 loadindustryranking.py &
python3 loadanalystupgradedowngrade.py &
python3 loadecondata.py &
wait
```

---

## EXECUTION RULES

1. **Only ONE loader running at a time** (unless explicitly marked "Parallel OK")
2. **Check before starting**: `ps aux | grep load` (ensure no other loader running)
3. **Monitor progress**: Check logs for "Inserted X rows" messages
4. **On failure**: Check logs, fix issue, re-run SAME loader (idempotent, won't duplicate)
5. **Kill hung loader**: `pkill -f loadpricedaily.py` (after 2+ hours of no progress)

---

## RECOMMENDATIONS FOR YOUR TEAM

### If Multiple People Want to Load Data:

**Option 1: Designate ONE person** (recommended)
- One person runs all loaders sequentially
- Takes ~10-15 hours total (spread across day/night)
- Reliable, no contention

**Option 2: Divide by Stage**
- Person A: Stages 1-2 (price + company data)
- Person B: Stage 3 (financials - after A completes stage 2)
- Person C: Stage 4-5 (metrics + scores - after B completes)
- Person D: Stage 6-7 (signals + context - after C completes)
- Serial execution, team parallelism

**Option 3: Set Schedule**
```bash
# Run once per week at off-hours (midnight)
crontab -e
# 0 0 * * 0 /home/arger/algo/load_all.sh
```

---

## SHELL SCRIPT FOR FULL SEQUENTIAL LOAD

Save as `load_all.sh` and run once:

```bash
#!/bin/bash
set -e  # Exit on any error

LOG_DIR="/tmp/loader_logs"
mkdir -p $LOG_DIR

log_stage() {
    echo "========================================================================"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
    echo "========================================================================"
}

# Stage 1: Bulk Prices
log_stage "Stage 1/7: Loading bulk price data (10 min)"
python3 loadpricedaily_fast.py | tee "$LOG_DIR/01_prices.log"

# Stage 2: Company Data
log_stage "Stage 2/7: Loading company data (45 min)"
python3 loaddailycompanydata.py | tee "$LOG_DIR/02_company.log"

# Stage 3: Financials (parallel)
log_stage "Stage 3/7: Loading financial statements (2-3 hours)"
python3 loadannualincomestatement.py > "$LOG_DIR/03a_annual_income.log" 2>&1 &
python3 loadannualbalancesheet.py > "$LOG_DIR/03b_annual_bs.log" 2>&1 &
python3 loadannualcashflow.py > "$LOG_DIR/03c_annual_cf.log" 2>&1 &
python3 loadquarterlyincomestatement.py > "$LOG_DIR/03d_qtr_income.log" 2>&1 &
python3 loadquarterlybalancesheet.py > "$LOG_DIR/03e_qtr_bs.log" 2>&1 &
python3 loadquarterlycashflow.py > "$LOG_DIR/03f_qtr_cf.log" 2>&1 &
wait
echo "All financials loaded"

# Stage 4: Factor Metrics
log_stage "Stage 4/7: Calculating factor metrics (1-2 hours)"
python3 loadfactormetrics.py | tee "$LOG_DIR/04_metrics.log"

# Stage 5: Stock Scores
log_stage "Stage 5/7: Calculating stock scores (30 min)"
python3 loadstockscores.py | tee "$LOG_DIR/05_scores.log"

# Stage 6: Signals (parallel)
log_stage "Stage 6/7: Generating trading signals (4-6 hours)"
python3 loadbuyselldaily.py > "$LOG_DIR/06a_signals_daily.log" 2>&1 &
python3 loadbuysellweekly.py > "$LOG_DIR/06b_signals_weekly.log" 2>&1 &
python3 loadbuysellmonthly.py > "$LOG_DIR/06c_signals_monthly.log" 2>&1 &
wait
echo "All signals generated"

# Stage 7: Market Context (parallel)
log_stage "Stage 7/7: Loading market context data (1-2 hours)"
python3 loadsectorranking.py > "$LOG_DIR/07a_sectors.log" 2>&1 &
python3 loadindustryranking.py > "$LOG_DIR/07b_industries.log" 2>&1 &
python3 loadanalystupgradedowngrade.py > "$LOG_DIR/07c_analyst.log" 2>&1 &
python3 loadecondata.py > "$LOG_DIR/07d_econ.log" 2>&1 &
wait
echo "All context data loaded"

log_stage "COMPLETE! All data loaded successfully"
echo "Logs saved in $LOG_DIR"
```

---

## MONITOR LOADER PROGRESS

While loaders running:

```bash
# Watch specific loader
tail -f /tmp/loader_logs/01_prices.log

# Check all loaders
for f in /tmp/loader_logs/*.log; do
    echo "=== $(basename $f) ==="
    tail -3 $f
done

# Check database size
psql -U stocks stocks -c "SELECT SUM(pg_total_relation_size(schemaname||'.'||tablename)) / (1024*1024*1024) as GB FROM pg_tables;"

# Check row counts
python3 << 'EOF'
import psycopg2, os
conn = psycopg2.connect(host='localhost', database='stocks', user='stocks', password=os.getenv('DB_PASSWORD'))
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
for (table,) in cur.fetchall():
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f'{table:40} {count:>12,} rows')
conn.close()
EOF
```

---

## IF SOMETHING GOES WRONG

### Loader hangs for 2+ hours:
```bash
pkill -f loadpricedaily_fast.py
# Check error log
tail -100 /tmp/loadpricedaily_fast.log
# Re-run (loaders are idempotent - won't duplicate)
python3 loadpricedaily_fast.py
```

### Database connection refused:
```bash
# Check if PostgreSQL running
psql -U stocks stocks -c "SELECT 1"

# Check active connections
psql -U stocks stocks -c "SELECT pid, usename, state FROM pg_stat_activity;"

# Kill stuck connections
psql -U stocks stocks -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename='stocks' AND state='idle';"
```

### Duplicate records:
```bash
# Loaders use ON CONFLICT, so safe - duplicates ignored
# But if concerned, clean up:
DELETE FROM price_daily WHERE symbol='AAPL' AND date='2026-04-20';
# Then re-run loader for that symbol
```

---

## SUMMARY

**Fast path**: Run `load_all.sh` once (sequential, 10-15 hours total)  
**No concurrent loaders** - they'll block each other  
**All loaders idempotent** - safe to re-run  
**Monitor progress** - check logs every hour  

