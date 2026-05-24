# Quick Start: Live Trading in 3 Steps

## Status Check
- ✅ Code: Working  
- ✅ API: Tested, returns real data
- ✅ Frontend: Running on http://localhost:5173
- ❌ Data: 2 days old (May 22 → needs refresh)
- ⏳ Live Trading: Ready (pending your confirmation)

---

## Step 1: Refresh Data (5 minutes)

**Go to GitHub Actions and trigger loaders:**
```
https://github.com/argie33/algo/actions
→ Workflow: "Manual - Invoke Loaders"  
→ Run workflow → all loaders
→ Wait 5 minutes
```

**Or verify data locally after:**
```powershell
# In PowerShell
$env:DB_HOST; $env:DB_USER  # Check creds are set
psql -h $env:DB_HOST -U $env:DB_USER -d stocks -c "SELECT MAX(date) FROM price_daily;"
# Should show today's date (2026-05-24)
```

---

## Step 2: Verify Frontend Sees Data

**Start API + Frontend:**
```bash
# Terminal 1
cd lambda/api && python3 dev_server.py

# Terminal 2  
cd webapp/frontend && npm run dev

# Terminal 3: Browser
# Open http://localhost:5173
# Should see real stocks with today's data (not "-" symbols)
```

---

## Step 3: Enable Live Trading

**IMPORTANT:** Only do this if:
- [ ] Data is fresh (Step 1 verified)
- [ ] You understand this executes REAL trades
- [ ] Alpaca account is LIVE (not paper)
- [ ] You have $1,000+ buying power

**In PowerShell, set:**
```powershell
$env:ALPACA_PAPER_TRADING = "false"
$env:ALGO_LIVE_TRADING = "I_UNDERSTAND_REAL_MONEY"  
$env:APCA_API_BASE_URL = "https://api.alpaca.markets"

# Verify
echo $env:ALPACA_PAPER_TRADING  # should print: false
echo $env:ALGO_LIVE_TRADING      # should print: I_UNDERSTAND_REAL_MONEY
```

**Test with one trade:**
```
GitHub Actions → "Manual - Test Orchestrator"
→ Run workflow
→ Wait 2 minutes
→ Check Alpaca dashboard: Should show 1-5 share order
```

**If test succeeded, enable automated trading:**
```
AWS Console → EventBridge
→ Enable rule: algo-morning-trading (9:30A ET)
→ Enable rule: algo-evening-trading (5:30P ET)
```

---

## STOP: Emergency Disable

```powershell
# Disable trading immediately
$env:ALGO_LIVE_TRADING = ""

# Then:
# 1. AWS Console → EventBridge → Disable trading rules
# 2. Alpaca → Close all positions manually
# 3. GitHub → Open issue with error logs
```

---

## Verify It's Working

```bash
# Check database has today's data
SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;  # > 0

# Check API returns real data
curl -s http://localhost:3001/api/algo/swing-scores | jq '.data[0]'

# Check last orchestrator run
SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 1;
```

---

## Common Issues

**"Database unavailable"**
- Check: `echo $env:DB_HOST` returns hostname
- Fix: Reload PowerShell profile

**No data on frontend**  
- Check: Loaders completed in Step 1
- Run: SELECT MAX(date) FROM price_daily;
- Wait: Loaders may still be running

**Trades not placing**
- Check: ALPACA_PAPER_TRADING = "false" (not "true")
- Check: Alpaca account is LIVE (not Paper)
- Check: API keys recently rotated

---

## Next: Deploy to AWS

When ready for production (skip if testing locally):
```bash
# Push code (deploys automatically)
git push main

# To deploy infrastructure too:
# GitHub Actions → "Deploy All Infrastructure" → Run manually
```

---

**See full details:** `SYSTEM_ACTIVATION_GUIDE.md`  
**Configuration:** `steering/algo.md`
