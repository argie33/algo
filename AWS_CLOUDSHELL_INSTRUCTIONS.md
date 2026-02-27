# AWS CloudShell Data Loading - Quick Start

## 🚀 Load All Data to AWS in 5 Steps

### Step 1: Open AWS CloudShell
- Log into **AWS Console**
- Click **CloudShell** icon (top right)
- Wait for terminal to load (pre-configured with your credentials)

### Step 2: Clone Repository
```bash
git clone https://github.com/argie33/algo.git
cd algo
```

### Step 3: Choose Your Loading Method

**Option A: Quick Load (SIGNALS & SCORES ONLY) - 20-30 min**
```bash
bash RUN_SIGNALS_SCORES_AWS.sh
```

**Option B: Complete Load (ALL 58 LOADERS) - 90-120 min**
```bash
bash RUN_DATA_LOADERS_AWS.sh
```

### Step 4: Monitor Progress
The script will:
- ✅ Auto-detect your RDS endpoint
- ✅ Retrieve credentials from AWS Secrets Manager
- ✅ Test database connection
- ✅ Load all data
- ✅ Verify completion

### Step 5: Test Your APIs
Once complete:
```bash
# Test health
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health

# Test stock scores (just loaded)
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores?limit=5

# Test stocks
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=5
```

---

## 📊 What Gets Loaded

### Quick Load (RUN_SIGNALS_SCORES_AWS.sh)
- ✅ Stock Scores (4,988)
- ✅ Daily Buy/Sell Signals (Stocks)
- ✅ Weekly Buy/Sell Signals (Stocks)
- ✅ Monthly Buy/Sell Signals (Stocks)
- ✅ Daily Buy/Sell Signals (ETFs)
- ✅ Weekly Buy/Sell Signals (ETFs)
- ✅ Monthly Buy/Sell Signals (ETFs)
- ✅ Real-time Scores

### Complete Load (RUN_DATA_LOADERS_AWS.sh)
**Everything above, plus:**
- ✅ Stock Symbols (4,988)
- ✅ Daily Prices (22M+)
- ✅ Weekly Prices (2M+)
- ✅ Monthly Prices (681K+)
- ✅ Technical Indicators (4,887)
- ✅ Factor Metrics
- ✅ Earnings Metrics
- ✅ Financial Statements (Annual & Quarterly)
- ✅ Cash Flow Data
- ✅ And 40+ more data sources

---

## ⏱️ Timeline

| Stage | Time | Data |
|-------|------|------|
| Foundation | 2 min | Stock symbols |
| Prices | 30 min | 25M+ records |
| Technical | 10 min | Technical data |
| Signals & Scores | 15 min | **4,988 scores + signals** |
| Fundamentals | 30 min | Earnings, financials |
| **TOTAL** | **~90 min** | Complete dataset |

**Quick Load (Signals & Scores only): ~20-30 minutes**

---

## 🔧 Troubleshooting

### "Connection refused"
- Check your RDS security group allows CloudShell
- Verify RDS is running (AWS Console > RDS)

### "Table already exists"
- Normal! Loaders are idempotent
- They skip existing data
- Safe to re-run

### "Timeout"
- Some loaders take 5-20 minutes
- Script waits up to 30 minutes per loader
- Check logs for errors

### Script hangs
- Kill with Ctrl+C
- Re-run to continue from where it stopped

---

## 📋 Manual Loading (if needed)

```bash
# Load specific loaders
cd algo
export DB_HOST=your-rds-endpoint.rds.amazonaws.com
export DB_USER=stocks
export DB_PASSWORD=bed0elAn
export DB_NAME=stocks

# Run individual loader
python3 loadstockscores.py

# Or run multiple
python3 loadstockscores.py &
python3 loadbuyselldaily.py &
python3 loadbuysellweekly.py &
wait
```

---

## ✅ Success Indicators

After script completes:

1. ✅ **Health Endpoint** returns 200
   ```bash
   curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health
   ```

2. ✅ **Stock Scores** are available
   ```bash
   curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores?limit=1
   ```

3. ✅ **Trading Signals** exist in database
   ```bash
   # In CloudShell (if psql available):
   psql -h $DB_HOST -U stocks -d stocks -c "SELECT COUNT(*) FROM buy_sell_daily"
   ```

---

## 🎯 Next Steps

1. **Run one of the loading scripts** (10 seconds to start)
2. **Wait for data** to load (~20-90 min depending on script)
3. **Test APIs** (2 minutes)
4. **Access Frontend** at CloudFront URL
5. **Celebrate!** 🎉

---

## 📞 Questions?

The scripts are self-contained and handle:
- AWS credential detection
- RDS endpoint auto-discovery
- Database connection validation
- Error handling
- Progress reporting
- Final verification

**Just run the script and let it do the work!**

---

**Created:** 2026-02-26  
**Status:** Ready for production use  
**Support:** Check script output for detailed logs
