# Data Loading Strategy - Optimized Approach

## Current Status (2026-04-24)

### Data Loaded ✓
- **stock_symbols**: 4,969 records
- **price_daily**: 65,555+ records (LOADING IN PROGRESS via loadpricedaily.py)
- **company_profile**: 4,969 records  
- **fear_greed_index**: 254 records (CNN API)
- **naaim**: 9 records (NAAIM exposure index)
- **technical_data_daily**: 24,723 records (being calculated from prices)
- **aaii_sentiment**: 0 records (URL blocked by CAPTCHA - needs manual data or alternative source)

### Data NOT Yet Loaded
- buy_sell_signals_daily (depends on price_daily)
- stock_scores (depends on all metrics)
- analyst_sentiment_analysis (yfinance analyst data)
- Financial statements (income, balance sheet, cash flow)
- Other signals/metrics

---

## Optimal Loading Approach

### Local Development (What We're Doing Now)

**Sequential Loader Dependencies:**
1. **loadstocksymbols.py** - Foundation (4,969 symbols) ✓ DONE
2. **loadpricedaily.py** - All historical prices ✓ IN PROGRESS
   - Currently loading 65,555+ records for ~1000 symbols
   - Parallelizes with `threads=True` in yfinance  
   - No more delays needed between batches with yfinance's internal threading
3. **loadtechnicalindicators.py** - Calculated from prices ✓ IN PROGRESS
   - Very fast (< 2 minutes for all symbols)
   - No external API calls
   - Pure in-database calculation (RSI, MACD, momentum)
4. **loaddailycompanydata.py** - 7 API calls per symbol
   - **BOTTLENECK**: 5,000 symbols × 8-10s each = 11-14 hours
   - Currently sequential only
   - Solution: Add `ThreadPoolExecutor(max_workers=20)` for parallel requests

5. **Financial statements** - Income, balance sheet, cash flow
   - Parallel API calls possible
   - Use `ThreadPoolExecutor` with rate limiting

6. **Market sentiment loaders** (fast, no symbol loops):
   - ✓ loadfeargreed.py - 1 HTTP request, gets all history
   - ✓ loadnaaim.py - 1 HTML request, gets all history  
   - ✗ loadaaiidata.py - CAPTCHA-blocked, needs alternative
   - loadsentiment.py - Per-symbol yfinance calls (integrate with daily company data)

7. **Buy/Sell Signals & Scores** - Final aggregation
   - Depends on prices + technical indicators
   - Can run in parallel across workers

### AWS Production (Best Practice Approach)

Instead of 1 massive sequential process, use **fan-out pattern**:

**Architecture:**
```
Coordinator Lambda/ECS Task
    ↓
    ├─→ Worker ECS Task #1 (symbols A-100)
    ├─→ Worker ECS Task #2 (symbols B-200)
    ├─→ Worker ECS Task #3 (symbols C-300)
    ├─→ ... (50 tasks for 5,000 symbols)
    ↓
Results aggregated in database
```

**Benefits:**
- Split 5,000 symbols into 50 chunks of 100 each
- Each worker task runs 20 parallel threads (ThreadPoolExecutor)
- Total parallelism: 50 tasks × 20 threads = **1,000 concurrent requests**
- Total time: ~5 minutes instead of 14 hours
- Scales: Add more tasks as symbol count grows

**Implementation:**
1. Add `--start-symbol` and `--end-symbol` CLI args to loaders
2. CloudFormation: Launch N ECS tasks with different ranges
3. SQS option: Workers consume symbol batches from queue

---

## Immediate Next Steps

### 1. Let Current Loaders Finish
- `loadpricedaily.py` is running - will take ~1-2 hours for all 5,000 symbols
- `loadtechnicalindicators.py` should auto-run after

### 2. Fix AAII Data (Optional)
AAII website is CAPTCHA-protected. Alternatives:
- Use historical AAII data from public sources (GitHub, Quandl, etc.)
- Manual download from AAII directly
- Skip for now (not critical - Fear & Greed + NAAIM provide sentiment)

### 3. Add ThreadPoolExecutor to loaddailycompanydata.py
See `OPTIMIZATION-PLAN.md` for implementation details.
Expected: Reduce from 14 hours to 30-40 minutes for 5,000 symbols.

### 4. Run Remaining Loaders in Sequence
After price_daily completes:
```bash
# These depend on prices:
python3 loadbuyselldaily.py
python3 loadstockscores.py

# These are independent (with yfinance parallelization):
python3 loadanalystsentiment.py
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py
python3 loadannualcashflow.py
```

---

## Database Connection Setup

**Local development:**
```bash
export DB_PASSWORD='bed0elAn'
python3 run-loaders.py
```

**AWS production:**
- Loaders automatically fetch credentials from Secrets Manager
- Set `DB_SECRET_ARN` environment variable in ECS task definition

---

## Performance Targets

| Phase | Current | With Optimization | AWS Fan-Out |
|-------|---------|-------------------|-------------|
| Symbols | ~5 min | N/A | N/A |
| Prices | ~1-2 hours | ~1 hour | ~10 min (10x faster with 10 parallel tasks) |
| Technical | <2 min | <2 min | <2 min |
| Company Data | 11-14 hours | 30-40 min | 5 min |
| Buy/Sell Signals | ~1 hour | ~20-30 min | 5 min |
| Scores | ~20 min | ~10 min | 2-3 min |
| **TOTAL** | **~16-18 hours** | **~2-3 hours** | **~30 minutes** |

**Conclusion**: Adding parallelism to `loaddailycompanydata.py` reduces total time from ~16 hours to ~2-3 hours locally. AWS fan-out achieves 30 minutes total - production-grade speed.

---

## Files Modified in This Session

1. `webapp/lambda/routes/sentiment.js` - Fixed column name for fear_greed_index query
2. `run-loaders.py` - Added 4 new sentiment loaders, fixed Windows encoding

## Next Optimization: Code Changes Needed

1. **loaddailycompanydata.py** - Add ThreadPoolExecutor(max_workers=20) with connection pooling
2. **run-loaders.py** - Add `--parallel-workers` CLI arg for local testing
3. **AWS**: Create ECS coordinator task that launches N worker tasks with symbol ranges

See `OPTIMIZATION-PLAN.md` for detailed implementation.
