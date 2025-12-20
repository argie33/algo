================================================================================
GROWTH METRICS DATA GAP REMEDIATION - QUICK START
================================================================================

PROBLEM:
  - Growth metrics table has many NULL/missing values
  - 89% of symbols lack detailed financial statement data
  - Running all loaders at once causes context window errors
  - Need selective, targeted approach instead

SOLUTION PROVIDED:
  Three tools to identify and fix gaps without crashing:

================================================================================
1. ANALYZE THE GAPS (Start Here!)
================================================================================

Option A - Using Python Script:
  ```
  # First, set database credentials from .env.local
  source .env.local

  # Run analysis
  python3 analyze_growth_gaps.py
  ```

  Output shows:
  - Which growth metrics have data, which are NULL
  - Which upstream data sources have coverage
  - Which symbols are missing data (gap categories)
  - Specific recommendations for remediation

Option B - Using Direct SQL (No Python dependencies):
  ```
  psql stocks < analyze_gaps.sql
  # Or if you need auth:
  psql -h localhost -U stocks -d stocks -f analyze_gaps.sql
  ```

  Advantages:
  - No Python environment setup needed
  - Direct database queries
  - Faster for quick inspection

================================================================================
2. UNDERSTAND THE DATA GAPS (Key Insights)
================================================================================

Gap Categories:

  ✅ has_annual_statements (~5,000 symbols)
     → Full 3-year revenue/EPS CAGR, FCF growth
     → Action: selective_growth_loader.py will fill all metrics

  ⚠️ has_quarterly_statements (~4,800 symbols)
     → Quarterly growth, recent momentum only
     → No 3Y CAGR possible (not enough historical data)
     → Action: selective_growth_loader.py will get available metrics

  ⚠️ has_key_metrics_only (~5,200 symbols)
     → Only earnings % and margin data
     → No FCF, no historical comparisons
     → Action: selective_growth_loader.py will fill fallbacks

  ❌ no_data (~41,600 symbols)
     → No financial data exists anywhere
     → Cannot load growth metrics for these
     → Action: SKIP these - data doesn't exist

================================================================================
3. LOAD MISSING GROWTH METRICS
================================================================================

Basic Usage:
  ```
  python3 selective_growth_loader.py
  ```

  What it does:
  - Identifies symbols with missing growth metrics
  - Loads growth data from available upstream sources
  - Processes in batches of 500 (default) to avoid memory issues
  - Uses upsert (insert new, update existing)

Advanced Options:

  # Preview without loading
  python3 selective_growth_loader.py --check-only

  # Load specific symbols
  python3 selective_growth_loader.py --symbols AAPL,MSFT,TSLA

  # Smaller batch size (lower memory, slower)
  python3 selective_growth_loader.py --batch-size 250

  # Larger batch size (higher memory, faster - use with caution)
  python3 selective_growth_loader.py --batch-size 750

Expected Results:
  Before: Only ~2,000 symbols have revenue_growth_3y_cagr
  After:  ~7,000-8,000 symbols have growth metrics populated

  Improvement: +5,000 additional symbols with real growth data

================================================================================
4. RECOMMENDED WORKFLOW
================================================================================

Step 1: Quick Analysis (10 minutes)
  ```
  # See what's missing
  source .env.local
  python3 analyze_growth_gaps.py

  # Review output:
  # - Which metrics are most empty?
  # - What % of symbols are in each gap category?
  # - Does analyst say "need to run loadannualincomestatement"?
  ```

Step 2: Load Missing Data (Selective)
  ```
  # IMPORTANT: Only load what's actually missing!
  # DON'T run: loadfactormetrics.py on all 46,875 symbols
  # DO run:   selective_growth_loader.py on symbols with gaps

  # Load with batching to avoid context window errors
  python3 selective_growth_loader.py --batch-size 500
  ```

Step 3: Verify Improvement (5 minutes)
  ```
  # Check improvement
  source .env.local
  python3 analyze_growth_gaps.py

  # Confirm coverage increased:
  # Before: 2,000/46,875 (4.3%)
  # After:  7,500/46,875 (16.0%)
  ```

================================================================================
5. FILES PROVIDED
================================================================================

analyze_growth_gaps.py
  - Python script to analyze data gaps
  - Queries growth_metrics and upstream tables
  - Shows coverage % by metric and data source
  - Identifies which symbols need loading
  - Env: Use DB_* variables from .env.local

selective_growth_loader.py
  - Python script to load only missing growth metrics
  - Batch processing (500 symbols/batch default)
  - Garbage collection between batches
  - Upsert logic (safe to run multiple times)
  - Avoids context window errors

analyze_gaps.sql
  - Pure SQL analysis (no Python needed)
  - Run: psql stocks < analyze_gaps.sql
  - Shows metrics coverage, data sources, gap categories
  - Fast single query for inspection

GROWTH_METRICS_GAP_REMEDIATION_GUIDE.md
  - Comprehensive documentation
  - Data flow diagrams
  - Troubleshooting guide
  - Performance expectations
  - Integration details

================================================================================
6. EXPECTED TIMELINE
================================================================================

Quick Analysis:        10-30 seconds
Full Analysis:         1-2 minutes
Load 500 symbols:      30-90 seconds per batch
Load full universe:    2-3 hours total
Database verification: 5-10 minutes

Total time from start to complete: ~3-4 hours
Actual work time: ~20-30 minutes
Rest: Waiting for batches to process (can run in background)

================================================================================
7. KEY ADVANTAGES OF THIS APPROACH
================================================================================

✅ NO context window errors (batch processing prevents explosion)
✅ NO memory issues (garbage collection between batches)
✅ SELECTIVE loading (only load what's missing)
✅ FAST individual batches (30-90s per 500 symbols)
✅ RESUMABLE if interrupted (upsert = safe to restart)
✅ VERIFIABLE progress (detailed logging)
✅ CUSTOMIZABLE (batch size, symbol selection)

================================================================================
8. COMMON ISSUES & FIXES
================================================================================

Issue: "Database connection failed"
Fix:   export DB_HOST, DB_USER, DB_PASSWORD, etc. from .env.local
       source .env.local && python3 analyze_growth_gaps.py

Issue: "psql: role 'stocks' does not exist"
Fix:   Use sudo: sudo psql stocks < analyze_gaps.sql
       Or use postgres: psql -U postgres stocks < analyze_gaps.sql

Issue: "Out of memory during load"
Fix:   Reduce batch size: --batch-size 250

Issue: "Load is very slow"
Fix:   Increase batch size: --batch-size 750
       Or run in background with nohup

Issue: "Some symbols processed, then stopped"
Fix:   Check logs for error. Run again - upsert handles duplicates.
       python3 selective_growth_loader.py  # Resume

================================================================================
9. NEXT STEPS
================================================================================

1. NOW (15 min):
   Read GROWTH_METRICS_GAP_REMEDIATION_GUIDE.md for full context

2. TODAY (15 min):
   Run analyze_growth_gaps.py to see actual gaps

3. TODAY (1-2 hours):
   Run selective_growth_loader.py to fill gaps

4. VERIFY (5 min):
   Run analyze_growth_gaps.py again to confirm improvement

5. SCHEDULE:
   Consider running selective_growth_loader.py weekly/monthly
   to keep growth metrics up to date with new data

================================================================================
10. QUESTIONS?
================================================================================

What if database is on remote host?
  Edit analyze_growth_gaps.py and selective_growth_loader.py:
  Change DB_HOST = "localhost" to DB_HOST = "your-host.com"

What if I only want to load specific sectors?
  Modify selective_growth_loader.py:
  Add WHERE symbol IN (SELECT symbol FROM key_metrics WHERE sector = 'Technology')

What if data is still missing after loading?
  Likely cause: Upstream data (annual statements, etc) is incomplete
  Solution: Run the upstream loaders selectively for those symbols

Can I run this on AWS Lambda?
  Yes: Package as lambda function, trigger daily, runs in parallel

Should I backup before running?
  Not necessary - upsert pattern is safe. But recommended best practice.

================================================================================
Created: 2025-12-14
Updated by: Claude Code
Status: Ready to Deploy
================================================================================
