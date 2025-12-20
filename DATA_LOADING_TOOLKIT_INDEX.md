# Complete Data Loading Toolkit - File Index

**Purpose**: Load ALL growth metrics for 46,875 symbols in 3-4 hours with zero crashes.

**Current Coverage**: ~2,000 symbols (4%)
**Target Coverage**: ~17,000 symbols (17%)
**Expected Result**: +300% improvement

---

## 📋 Quick Navigation

### 🚀 START HERE (Most Important!)
👉 **`START_HERE_FULL_DATA_LOAD.md`** - Read this first!
- 5-minute quick start
- Copy-paste commands
- Timeline expectations
- Troubleshooting

### 📚 Main Scripts (Ready to Run)
| File | Purpose | Run Time | What It Does |
|------|---------|----------|--------------|
| `run_full_data_load.sh` | ⭐ Main launcher | 3.5 hrs | Runs all 4 stages with one command |
| `load_all_growth_data.py` | Stage orchestrator | Variable | Runs upstream loaders (stages 1-3) |
| `load_all_growth_metrics.py` | Metrics calculator | 30 min | Calculates all growth metrics (stage 4) |
| `monitor_data_load.sh` | Progress monitor | Real-time | Watch load progress in terminal |

### 📖 Documentation (Read for Details)
| File | Content | Length |
|------|---------|--------|
| `FULL_DATA_LOADING_PLAN.md` | Complete reference guide | 40+ pages |
| `GROWTH_METRICS_GAP_REMEDIATION_GUIDE.md` | Deep dive on gaps | 20+ pages |
| `GROWTH_METRICS_REMEDIATION_README.txt` | Original quick ref | 5 pages |
| `analyze_growth_gaps.sql` | SQL-based analyzer | Raw SQL |

### 🔍 Analysis Tools (For Inspection)
| File | Purpose | How to Use |
|------|---------|-----------|
| `analyze_growth_gaps.py` | Python gap analyzer | `python3 analyze_growth_gaps.py` |
| `analyze_gaps.sql` | Direct SQL analysis | `psql stocks < analyze_gaps.sql` |
| `selective_growth_loader.py` | Selective loader | `python3 selective_growth_loader.py --check-only` |

---

## 🎯 Execution Paths

### Path 1: Full Automatic (Simplest) ⭐⭐⭐
```bash
cd /home/stocks/algo
./run_full_data_load.sh all
# Sits back and watches for 3.5 hours
# Answer "yes" to confirm, everything else is automated
```

**Best for**: You want it done with minimal interaction
**Time**: ~3.5 hours total, ~5 minutes of your time
**Effort**: Low

### Path 2: Stage-by-Stage (More Control)
```bash
./run_full_data_load.sh 1    # Annual statements
./run_full_data_load.sh 2    # Quarterly statements
./run_full_data_load.sh 3    # Supporting data
./run_full_data_load.sh 4    # Growth metrics
```

**Best for**: You want to monitor each stage, or need to troubleshoot
**Time**: ~3.5 hours total, ~15 minutes of your time
**Effort**: Medium

### Path 3: Background with Monitoring
```bash
# Terminal 1
nohup bash -c 'source .env.local && python3 load_all_growth_data.py --stage all && python3 load_all_growth_metrics.py --batch-size 500' > load_pipeline.log 2>&1 &

# Terminal 2
watch -n 10 ./monitor_data_load.sh

# Terminal 3
tail -f load_pipeline.log
```

**Best for**: You want to keep working while data loads
**Time**: ~3.5 hours (non-blocking)
**Effort**: Low-Medium

### Path 4: Custom (Advanced)
```bash
# Run individual components
python3 load_all_growth_data.py --stage 1        # Just annual
python3 load_all_growth_metrics.py --batch-size 250  # Custom batch
```

**Best for**: You have specific needs or constraints
**Time**: Variable
**Effort**: High

---

## 📊 What Gets Loaded (4-Stage Pipeline)

### Stage 1: Annual Income Statements
- **Duration**: ~45 minutes
- **Symbols**: ~5,000
- **Data**: Revenue, net income, operating income (4 years)
- **File**: `loadannualincomestatement.py` (existing)
- **Metrics Enabled**: revenue_growth_3y_cagr, eps_growth_3y_cagr, operating_income_growth_yoy, net_income_growth_yoy

### Stage 2: Quarterly Income Statements
- **Duration**: ~45 minutes
- **Symbols**: ~4,800
- **Data**: Quarterly revenue, net income, operating income (8 quarters)
- **File**: `loadquarterlyincomestatement.py` (existing)
- **Metrics Enabled**: quarterly_growth_momentum, recent YoY comparisons

### Stage 3: Supporting Financial Data
- **Duration**: ~45 minutes
- **Symbols**: Mixed (3,500-4,600 each)
- **Components**:
  - `loadannualcashflow.py` - FCF, OCF (4 years)
  - `loadannualbalancesheet.py` - Total assets (2 years)
  - `loadearningshistory.py` - EPS actual/estimate (4 quarters)
- **Metrics Enabled**: fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy

### Stage 4: Growth Metrics Calculation
- **Duration**: ~30 minutes
- **Symbols**: ALL 46,875
- **File**: `load_all_growth_metrics.py` (new, smart orchestrator)
- **Metrics Calculated**: All 13 growth metrics from available data
- **Key Feature**: Multi-tier priority (annual → quarterly → earnings → key_metrics)

---

## 💾 Expected Results

### Coverage Improvement
```
Before:
  revenue_growth_3y_cagr:    2,000/46,875 (4.3%)
  eps_growth_3y_cagr:        2,000/46,875 (4.3%)
  fcf_growth_yoy:            1,500/46,875 (3.2%)
  quarterly_growth_momentum: 5,000/46,875 (10.7%)
  Average: 4.6%

After:
  revenue_growth_3y_cagr:    8,000/46,875 (17.1%)
  eps_growth_3y_cagr:        8,000/46,875 (17.1%)
  fcf_growth_yoy:            6,000/46,875 (12.8%)
  quarterly_growth_momentum: 12,000/46,875 (25.6%)
  Average: 18.2%

Improvement: +14,000 symbols (+300%)
```

### By Symbol Category
```
Large Caps (Annual statements):
  Before: 100% coverage
  After: 100% + quarterly + FCF = Comprehensive

Mid Caps (Quarterly only):
  Before: ~30% coverage
  After: ~80% coverage (recent growth, momentum)

Small Caps (Key metrics only):
  Before: ~10% coverage
  After: ~30% coverage (margins, fallback growth %)

Micro Caps (No data):
  Before: 0% coverage
  After: 0% coverage (can't fix what doesn't exist)
```

---

## 🔧 Configuration & Customization

### Memory Constraints
```bash
# If memory is tight
python3 load_all_growth_metrics.py --batch-size 250    # Uses less RAM

# If you have lots of memory
python3 load_all_growth_metrics.py --batch-size 750    # Faster but more RAM
```

### Running Specific Symbols
```bash
# Edit load_all_growth_metrics.py, add WHERE clause:
# WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL')
```

### Scheduling Recurring Updates
```bash
# Add to crontab for weekly updates
0 2 * * 0 cd /home/stocks/algo && source .env.local && \
  python3 load_all_growth_metrics.py --batch-size 500 >> weekly_load.log 2>&1

# Or daily for maximum freshness
0 3 * * * (same command)
```

---

## ✅ Verification Checklist

After the pipeline completes:

- [ ] No errors in execution.json
- [ ] Growth metrics count increased significantly
- [ ] `analyze_growth_gaps.py` shows improvement
- [ ] Coverage increased from 4% to 17%
- [ ] Database queries return results
- [ ] Dependent jobs still work (scoring, positioning)
- [ ] No data corruption (spot-check a symbol)

---

## 🚨 Troubleshooting Matrix

| Problem | Cause | Solution |
|---------|-------|----------|
| Database connection failed | Wrong credentials | `source .env.local` and verify |
| Out of memory | Batch size too large | Use `--batch-size 250` |
| Process stuck | No output for 5 min | Check `top` or `ps aux` |
| Partial completion | Network issue | Run again (upsert handles duplicates) |
| Slow performance | System overloaded | Run at off-hours |
| Coverage not improved | Upstream data missing | Run stages 1-3 first |
| Only key_metrics loaded | Annual statements missing | Ensure stage 1 completed |

---

## 📈 Monitoring Commands

```bash
# Real-time dashboard (auto-refreshes)
watch -n 10 ./monitor_data_load.sh

# Live logs
tail -f load_pipeline.log

# Database query (manual check)
psql stocks -c "SELECT COUNT(*) FROM growth_metrics WHERE date = CURRENT_DATE;"

# Process status
ps aux | grep load
pgrep -f "python3 load" | wc -l

# System resources
free -h
df -h
```

---

## 📝 File Relationships

```
run_full_data_load.sh (main entry)
  ├── load_all_growth_data.py (orchestrates stages 1-3)
  │   ├── loadannualincomestatement.py (existing, stage 1)
  │   ├── loadquarterlyincomestatement.py (existing, stage 2)
  │   ├── loadannualcashflow.py (existing, stage 3)
  │   ├── loadannualbalancesheet.py (existing, stage 3)
  │   └── loadearningshistory.py (existing, stage 3)
  │
  └── load_all_growth_metrics.py (executes stage 4)
      └── growth_metrics table (target)

Documentation:
  ├── START_HERE_FULL_DATA_LOAD.md (quick start)
  ├── FULL_DATA_LOADING_PLAN.md (complete reference)
  ├── GROWTH_METRICS_GAP_REMEDIATION_GUIDE.md (gap analysis)
  └── DATA_LOADING_TOOLKIT_INDEX.md (this file)

Analysis:
  ├── analyze_growth_gaps.py (Python analysis)
  ├── analyze_gaps.sql (SQL analysis)
  └── selective_growth_loader.py (selective loading)

Monitoring:
  └── monitor_data_load.sh (progress display)
```

---

## 🎯 Success Criteria

You've succeeded when:

1. ✅ **Pipeline completes** - No fatal errors
2. ✅ **Coverage improved** - 4% → 17% (confirmed by analyze_growth_gaps.py)
3. ✅ **All symbols touched** - Even micro-caps have at least key_metrics fallback
4. ✅ **Data accuracy** - No fake defaults (only real data or NULL)
5. ✅ **Downstream works** - Scoring and positioning processes run fine
6. ✅ **Performance stable** - Never exceeded ~400MB RAM

---

## ⏱️ Timeline

| Phase | Duration | What You Do | What Script Does |
|-------|----------|------------|------------------|
| Setup | 2 min | Run `run_full_data_load.sh all` | Check env, show plan |
| Confirm | 1 min | Type "yes" | Begin pipeline |
| Stage 1 | 45 min | Watch logs | Load annual statements |
| Stage 2 | 45 min | Grab coffee | Load quarterly statements |
| Stage 3 | 45 min | Check email | Load supporting data |
| Stage 4 | 30 min | Take a walk | Calculate growth metrics |
| Verify | 5 min | Run `analyze_growth_gaps.py` | Confirm improvement |
| **TOTAL** | **~3.5 hours** | **~10 min active** | **Automated batching** |

---

## 💡 Key Insights

### Why This Works (Why Previous Approaches Failed)
- **Batching**: 500 symbols/batch prevents memory explosion
- **Sequential**: One loader at a time prevents context window errors
- **Staged**: Upstream data loads before metrics calculation
- **Garbage Collection**: Forces cleanup between batches
- **Upsert**: Safe to run multiple times without duplicates

### Data Quality Guarantees
- ✅ Only real financial data is used
- ✅ Metrics calculated from actual numbers
- ✅ Missing data → NULL (not fake defaults)
- ✅ No data corruption from mixing sources

### Performance Characteristics
- Memory: ~200-400MB (stable)
- Time: 30-90 seconds per batch
- Batches: 94 total for all 46,875 symbols
- Total: ~45-90 minutes for metrics calculation

---

## 🎓 Learning Resources

If you want to understand the system deeper:

1. **Growth Metrics Architecture**
   → Read: `GROWTH_METRICS_GAP_REMEDIATION_GUIDE.md`

2. **Data Sources & Priority Chain**
   → Read: `FULL_DATA_LOADING_PLAN.md` (sections "What Gets Loaded")

3. **Batch Processing Design**
   → Read: `load_all_growth_metrics.py` (comments explain logic)

4. **Gap Analysis**
   → Run: `python3 analyze_growth_gaps.py` then review output

---

## 🚀 FINAL COMMAND

```bash
cd /home/stocks/algo
./run_full_data_load.sh all
```

That's it. Everything else is automated. See you in 3-4 hours! ☕

---

**Toolkit Version**: 1.0
**Created**: 2025-12-14
**Status**: Production Ready
**Expected Outcome**: 300% improvement in growth metrics coverage

**Important**: Read `START_HERE_FULL_DATA_LOAD.md` before running!
