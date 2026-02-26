#!/bin/bash

cat << 'EOF'
╔════════════════════════════════════════════════════════════════════════════════╗
║                                                                                ║
║              🚀 COMPLETE AWS DEPLOYMENT - PUSH, MONITOR & VERIFY             ║
║                                                                                ║
║                    Get All APIs 100% Populated & Operational                  ║
║                                                                                ║
╚════════════════════════════════════════════════════════════════════════════════╝

════════════════════════════════════════════════════════════════════════════════════
                         📋 COMMITS READY TO PUSH
════════════════════════════════════════════════════════════════════════════════════

4 Commits waiting to push to GitHub:

  1️⃣  1f9862e40 - Require Node 20.19+ for frontend build compatibility
  2️⃣  8e09f86b5 - AWS deployment issues - update Node runtime & bootstrap
  3️⃣  ce50fa060 - Increase Lambda resources & optimize database connection pool
  4️⃣  [Older commits not shown - base already on origin]

Status: READY TO PUSH ✅
Working directory: CLEAN ✅
venv config: REVERTED ✅

════════════════════════════════════════════════════════════════════════════════════
                      ⏭️  STEP 1: PUSH TO GITHUB
════════════════════════════════════════════════════════════════════════════════════

Choose ONE method and execute it ON YOUR WINDOWS/MAC MACHINE:

─────────────────────────────────────────────────────────────────────────────────
METHOD A: Windows PowerShell (⭐ RECOMMENDED)
─────────────────────────────────────────────────────────────────────────────────

  1. Open PowerShell on Windows
  2. Navigate to repo:

     cd C:\path\to\algo

  3. Push ALL commits:

     git push origin main

  4. Wait for completion (should say "main -> main")

─────────────────────────────────────────────────────────────────────────────────
METHOD B: VS Code Source Control
─────────────────────────────────────────────────────────────────────────────────

  1. Open VS Code with algo folder
  2. Click Source Control icon (Ctrl+Shift+G)
  3. Click three dots ⋮ → "Push"
  4. Watch for success message

─────────────────────────────────────────────────────────────────────────────────
METHOD C: GitHub Desktop
─────────────────────────────────────────────────────────────────────────────────

  1. Open GitHub Desktop
  2. Find "algo" repository
  3. Click "Push to origin"
  4. Watch for success

─────────────────────────────────────────────────────────────────────────────────
METHOD D: AWS CloudShell (No local git needed)
─────────────────────────────────────────────────────────────────────────────────

  1. Open AWS Console → CloudShell
  2. Run:

     cd /tmp
     git clone https://github.com/argie33/algo.git
     cd algo
     git push origin main

════════════════════════════════════════════════════════════════════════════════════
                 🔍 STEP 2: MONITOR GITHUB ACTIONS (5-10 minutes)
════════════════════════════════════════════════════════════════════════════════════

AFTER PUSHING, WATCH THE DEPLOYMENT:

  1. Go to: https://github.com/argie33/algo/actions

  2. Find the "deploy-webapp" workflow (most recent)

  3. Watch these jobs COMPLETE (should all show ✅):

     • setup                    - Environment setup
     • filter                   - Detect changes
     • deploy_infrastructure    - Deploy Lambda + API Gateway
     • deploy_frontend          - Build + deploy React frontend
     • deploy_frontend_admin    - Build + deploy admin panel
     • verify_deployment        - Health checks

  4. Expected time: 5-10 minutes total

  5. Status indicators:
     ✅ GREEN = SUCCESS
     ❌ RED = FAILED (check logs)
     ⏳ YELLOW = IN PROGRESS

IF ANY JOB FAILS:
  • Click on the red job
  • Read error message carefully
  • Common errors will show:
    - Missing CloudFormation stack exports
    - Node.js version issues
    - Memory/timeout validation
    - Frontend build errors

════════════════════════════════════════════════════════════════════════════════════
               🔧 STEP 3: VERIFY LAMBDA DEPLOYMENT (AWS Console)
════════════════════════════════════════════════════════════════════════════════════

After GitHub Actions completes successfully:

  1. Go to AWS Console → Lambda

  2. Find function: "stocks-webapp-api-dev"

  3. Check Configuration tab:

     ✓ Memory: 512 MB (NOT 128 MB)
     ✓ Timeout: 300 seconds (NOT 60 seconds)
     ✓ Environment variables all set
     ✓ Recent executions show SUCCESS

  4. Check CloudWatch logs:

     AWS Console → CloudWatch → /aws/lambda/stocks-webapp-dev-*

     Should see:
     ✅ "Database config loaded"
     ✅ "Successfully connected to database"
     ❌ NO "TIMEOUT" or "FATAL" messages

════════════════════════════════════════════════════════════════════════════════════
        🎯 STEP 4: RUN DATA LOADERS (100% POPULATION) - 45-60 MINUTES
════════════════════════════════════════════════════════════════════════════════════

CRITICAL: This is the most important step! Ensures 100% data population.

Run the automated loader script:

  cd /home/arger/algo
  bash /tmp/run_critical_loaders.sh

This will run SEQUENTIALLY (must be in order):

  1. loadstocksymbols.py       (~2 min)   → Loads 5000+ symbols
  2. loadpricedaily.py         (~20 min)  → Loads 1M+ price records
  3. loadtechnicalindicators.py (~5 min)  → Calculates indicators
  4. loadbuysellDaily.py       (~10 min)  → Generates signals
  5. loadstockscores.py        (~5 min)   → Calculates scores

Total time: 45-60 minutes (FIRST RUN ONLY)

MONITOR THE OUTPUT:
  • Watch for ✅ "SUCCESS" messages
  • Each loader shows progress and final count
  • If any FAILS, it will show ERROR with details
  • Partial data is OK - restart script if needed

EXPECTED RESULTS:
  • 5000+ stock symbols
  • 1M+ price records (multiply 5000 symbols × ~200 trading days)
  • Technical indicators for all symbols
  • Buy/sell signals for all symbols
  • Stock scores for all symbols

════════════════════════════════════════════════════════════════════════════════════
       ✅ STEP 5: VERIFY 100% DATA POPULATION IN DATABASE
════════════════════════════════════════════════════════════════════════════════════

After loaders complete, verify data is actually in the database:

  psql -h localhost -U stocks -d stocks

Then run these queries (paste one at a time):

  SELECT COUNT(*) as stock_count FROM stock_symbols;
  SELECT COUNT(*) as price_count FROM price_daily;
  SELECT COUNT(*) as signal_count FROM buy_sell_daily;
  SELECT COUNT(*) as score_count FROM stock_scores;

EXPECTED RESULTS:
  stock_count  | 5000+         ✅
  price_count  | 1000000+      ✅
  signal_count | 500000+       ✅
  score_count  | 5000+         ✅

If counts are 0 or very low:
  • Loaders didn't complete successfully
  • Re-run: bash /tmp/run_critical_loaders.sh
  • Check CloudWatch logs for API errors

════════════════════════════════════════════════════════════════════════════════════
          🌐 STEP 6: TEST ALL APIS - 100% DATA RETURNED
════════════════════════════════════════════════════════════════════════════════════

Test that all APIs return complete data:

API #1: Health Check
────────────────────────────────────────────────────────────────────────────────

  curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

Expected:
  {"success": true, "data": {...}}
  Status: 200

API #2: Get Stocks (Should return 5000+)
────────────────────────────────────────────────────────────────────────────────

  curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=100"

Expected:
  JSON array with 100 stocks
  Each stock has: symbol, scores, data
  Status: 200

API #3: Get Scores (Should return 5000+)
────────────────────────────────────────────────────────────────────────────────

  curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/scores?limit=100"

Expected:
  JSON array of stocks with composite scores
  Status: 200

API #4: Get Signals (Should return 500k+)
────────────────────────────────────────────────────────────────────────────────

  curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/signals?limit=100"

Expected:
  JSON array of buy/sell signals
  Status: 200

API #5: Get Prices (Should return 1M+)
────────────────────────────────────────────────────────────────────────────────

  curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/price/AAPL/daily?limit=100"

Expected:
  JSON array of OHLCV price data
  Status: 200

════════════════════════════════════════════════════════════════════════════════════
              🎨 STEP 7: VERIFY FRONTEND - 100% OPERATIONAL
════════════════════════════════════════════════════════════════════════════════════

Visit the frontend in your browser:

  https://stocks-webapp-frontend-dev-626216981288.cloudfront.net

Verify:
  ✅ Page loads without errors
  ✅ Dashboard shows stocks
  ✅ Charts render with data
  ✅ Scores display for stocks
  ✅ Signals show buy/sell recommendations
  ✅ No "loading" spinners (data is there)
  ✅ Can click through stocks and see details

IF FRONTEND SHOWS "NO DATA":
  • Data loaders may not have completed
  • Check API endpoints directly (Step 6)
  • Verify database population (Step 5)
  • Check CloudWatch logs for API errors

════════════════════════════════════════════════════════════════════════════════════
                      ✨ COMPLETION CHECKLIST
════════════════════════════════════════════════════════════════════════════════════

Mark off each as complete:

Push & GitHub Actions:
  ☐ Step 1: Pushed all 4 commits to GitHub
  ☐ Step 2: GitHub Actions workflow completed (all jobs green ✅)
  ☐ Step 3: Lambda verified in AWS Console (512MB, 300s)

Data Population:
  ☐ Step 4: All loaders completed successfully
  ☐ Step 5: Database verified (5000+ symbols, 1M+ prices)

API Testing:
  ☐ Step 6a: Health API returns 200
  ☐ Step 6b: Stocks API returns 5000+ records
  ☐ Step 6c: Scores API returns data
  ☐ Step 6d: Signals API returns data
  ☐ Step 6e: Price API returns historical data

Frontend:
  ☐ Step 7: Frontend loads and displays all data

FINAL STATUS:
  ☐ ALL steps complete = ✅ AWS PLATFORM 100% OPERATIONAL

════════════════════════════════════════════════════════════════════════════════════
                          🚀 YOU'RE READY!
════════════════════════════════════════════════════════════════════════════════════

Everything is prepared. Now execute:

  1. Choose push method above → Push to GitHub
  2. Monitor GitHub Actions (5-10 min)
  3. Run data loaders (45-60 min)
  4. Test all APIs
  5. Verify frontend works

Total time: ~75 minutes to 100% operational AWS platform

Ready? Push now! 🚀

════════════════════════════════════════════════════════════════════════════════════

EOF
