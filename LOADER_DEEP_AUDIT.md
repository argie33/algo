# Deep Loader Audit - What We Know vs. What's Confusing

## The Mystery: 74 Database Entries vs. Single Python Files

### What the CODE has (Python files in loaders/):
```
1 load_prices.py
1 load_buy_sell_daily.py
1 load_technical_data_daily.py
6 metric loaders (quality, growth, value, stability, positioning, momentum)
1 load_financial_statements.py (consolidated - handles all statement types)
+ Others (reference data, sentiment, economic, etc.)

Total: ~40 loader SCRIPTS
```

### What the DATABASE has (data_loader_status table):
```
74 loader ENTRIES, including:
- price_daily, price_weekly, price_monthly (3 entries)
- etf_price_daily, etf_price_weekly, etf_price_monthly (3 entries)
- buy_sell_daily, buy_sell_weekly, buy_sell_monthly, buy_sell_daily_etf, buy_sell_weekly_etf, buy_sell_monthly_etf (6 entries)
- technical_data_daily, technical_data_weekly, technical_data_monthly (3 entries)
- etc.

Total: ~74 database entries
```

### The Disconnect:
**~40 Python files creating 74 database entries = something is generating variants from single scripts**

Likely source:
- Terraform creates multiple ECS task definitions from same Python file (with different env vars)
- Step Functions calls different task definitions with different parameters
- Each call updates a different entry in data_loader_status table

Example (Financial Statements - CONFIRMED PATTERN):
```python
# Single file: load_financial_statements.py
# Env vars set by Terraform:
  LOADER_STATEMENT_TYPE=income LOADER_PERIOD=annual   → updates "annual_income_statement" table
  LOADER_STATEMENT_TYPE=balance LOADER_PERIOD=annual  → updates "annual_balance_sheet" table
  LOADER_STATEMENT_TYPE=income LOADER_PERIOD=quarterly → updates "quarterly_income_statement" table
  etc. (8 variants from 1 file)
```

**HYPOTHESIS: Same pattern should exist for price_daily and buy_sell_daily, but Terraform may be outdated or Step Functions may be calling tasks with env vars we haven't found yet.**

---

## Part 1: CONFIRMED FACTS (Not Duplicates, Real Patterns)

### Price Data - REAL NEED FOR MULTIPLE TIMEFRAMES?

```
Loaded: price_daily, price_weekly, price_monthly (stocks + ETFs = 6 total)

Use cases:
  - price_daily:     Used by technical_data_daily, orchestrator, live trading
  - price_weekly:    Used by... ??? (grep for usage)
  - price_monthly:   Used by... ??? (grep for usage)

Question: Are weekly/monthly CALCULATED from daily, or FETCHED separately?
```

### Buy/Sell Signals - REAL NEED FOR MULTIPLE TIMEFRAMES?

```
Loaded: buy_sell_daily, buy_sell_weekly, buy_sell_monthly (stocks + ETFs = 6 total)

Use cases:
  - buy_sell_daily:     Used by orchestrator (verified)
  - buy_sell_weekly:    Used by... ??? (0 evidence found)
  - buy_sell_monthly:   Used by... ??? (0 evidence found)

Question: Are these LEGACY from old trading strategies, or actively used?
```

### Metrics - 6 SEPARATE LOADERS (confirmed necessary)

```
quality_metrics, growth_metrics, value_metrics, stability_metrics, positioning_metrics, momentum_metrics

All populate ~4,700 rows
All used by stock_scores calculation
All have different data sources (yfinance, SEC, etc.)

Assessment: Could potentially be consolidated into 1 parametrized loader 
(like financial_statements.py does it), but ONLY if:
  - They don't have independent schedules
  - Batching them doesn't increase failure risk
  - The shared setup/teardown saves meaningful time
```

---

## Part 2: CONFIRMED DUPLICATES / DEAD CODE

### Financial Statements - MIXED PATTERNS

```
OLD WAY (still in code?):
  load_income_statement.py
  load_balance_sheet.py
  load_cash_flow.py
  
NEW WAY (consolidated):
  load_financial_statements.py (1 file, 8 variants via env vars)
  
Status: BOTH exist? Are the old ones still being called?
  grep for references to old files...
```

### Sentiment Loaders - MULTIPLE SIMILAR ONES

```
load_aaii_sentiment.py          → aaii_sentiment (2,028 rows - used)
load_analyst_sentiment_analysis.py → analyst_sentiment_analysis (0 rows - broken?)
load_market_sentiment.py         → market_sentiment (possibly duplicates others?)

Question: Do we need all 3, or are they overlapping?
```

### Reference Data - CLEAN BUT COULD CONSOLIDATE

```
load_company_profile.py
load_earnings_calendar.py
load_earnings_history.py
load_analyst_upgrade_downgrade.py

All have different APIs, different error modes.
Assessment: Safe to run in parallel, but probably shouldn't merge into one.
```

---

## Part 3: WHAT TO INVESTIGATE

Before any changes, need answers to:

### 1. WHERE ARE THE WEEKLY/MONTHLY VARIANTS CREATED?

```bash
# Find this:
grep -r "price_weekly\|price_monthly" terraform/ loaders/ | grep -v ".tf~"
# Check: Are they env-var based? Separate tasks? Legacy in database?
```

### 2. DO WE ACTUALLY USE WEEKLY/MONTHLY DATA?

```bash
# Find all references:
grep -r "price_weekly\|price_monthly\|buy_sell_weekly\|buy_sell_monthly" \
  algo/ api-pkg/ dashboard/ | grep -v "__pycache__"
# If zero results → they're NOT used → safe to delete
```

### 3. ARE OLD FINANCIAL STATEMENT FILES STILL BEING USED?

```bash
# Check if old files are referenced:
grep -r "load_income_statement\|load_balance_sheet\|load_cash_flow" \
  terraform/ loaders/ | grep -v "load_financial_statements"
# If found → they're active (duplicate!)
# If not found → they're dead code (delete them)
```

### 4. WHICH LOADERS ACTUALLY POPULATE ZERO ROWS (BROKEN)?

```
From database audit, these are 0 rows:
  - commodity_prices, commodity_price_history, commodity_technicals, commodity_macro_drivers
  - sentiment, sentiment_social (vs aaii_sentiment which HAS data)
  - cot_data, distribution_days, index_metrics, industry_performance
  - iv_history, analyst_sentiment (different from analyst_sentiment_analysis)
  - earnings_estimate_revisions, signal_themes, institutional_positioning
  - performance_daily (vs algo_performance_daily which is orchestrator output)

Need to check: Are these INTENTIONALLY empty (awaiting data source setup)?
Or are they just orphaned code?
```

---

## Part 4: RECOMMENDATION - MINIMAL RISK AUDIT STEPS

### Step 1: Direct the Investigation (1 hour)

```bash
# 1. Find weekly/monthly source
grep -r "TIMEFRAME\|PERIOD\|weekly\|monthly" terraform/modules/pipeline/ | head -50

# 2. Verify weekly/monthly usage
grep -r "price_weekly\|buy_sell_monthly" algo/ api-pkg/ dashboard/ --include="*.py" | wc -l

# 3. Check old financial statement files
find loaders/ -name "load_income_statement.py" -o -name "load_balance_sheet.py" -o -name "load_cash_flow.py"

# 4. Identify intentional vs. orphaned empty loaders
# (Ask: Are you actively working on commodity data? Sentiment data? etc.)
```

### Step 2: Map Actual Usage (2 hours)

For each "suspicious" loader:
- Find where it's called in terraform/pipeline
- Trace to Step Functions state machine
- Check if data is actually used downstream

### Step 3: Find the Quick Wins (no risk)

```
Definitely remove:
  - Files that exist but aren't referenced anywhere in terraform/pipeline
  - Database entries with 0 rows where the loader file doesn't exist
  - Any load_*.py file that has no corresponding task definition

Probably consolidate:
  - load_financial_statements.py is already done right - follow that pattern
  - Metrics might be consolidatable if they're independent
  
Definitely keep:
  - price_daily, technical_data_daily, stock_scores (core trading)
  - buy_sell_daily (trading signals)
  - stock_symbols, company_profile (universe definition)
```

---

## The Right Way Forward

**DON'T assume weekly/monthly are duplicates until we verify:**
1. Where they're created
2. Whether they're used
3. Whether removing them breaks something

**DO look for:**
1. Load scripts with no terraform references (dead code)
2. Database entries pointing to non-existent load files
3. Broken data sources (0 rows for months)
4. Load scripts that are referenced but never called

**THEN consolidate conservatively:**
- Follow the financial_statements.py pattern (parametrized loaders)
- Only merge things with same API/error modes
- Test removal on dev environment first

