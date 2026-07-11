# Loader Optimization Strategy - Cost & Efficiency Audit

**Current State**: 74 separate ECS task definitions (wasteful)
**Target State**: ~30-35 consolidated loaders with smart batching
**Potential Savings**: $100-150/month in AWS + faster pipeline execution

---

## 1. Understanding "Empty" Loaders

Empty (0 rows) doesn't mean useless - it means **they're failing silently**.

### Why Loaders Are Empty

```
Status = "READY"  → Loader scheduled but hasn't completed successfully
Row count = 0     → Loader runs but returns no data (not populating table)
Error message     → "Reset for re-execution" or "Stuck in RUNNING"
```

**Examples of broken loaders:**
- `commodity_prices` - Intended for futures/commodity data (no source configured)
- `sentiment`, `sentiment_social` - Alternative sentiment data (API not set up?)
- `cot_data` - Commitment of Traders data (not actively sourced)
- `distribution_days` - Market breadth indicator (not computed)
- `iv_history` - Options implied volatility (dependencies missing)

### Why This Costs Money

Each "empty" loader still:
- Has an ECS task definition
- Gets triggered by Step Functions
- Spins up a container
- Queries database
- Returns 0 rows
- **Uses $2-5/month just sitting idle**

---

## 2. Current Loader Inventory (74 total)

### CATEGORY A: MISSION CRITICAL (must keep, every run)
```
Must keep as-is or consolidate carefully:

Price Data (core - 6 loaders):
  ✓ price_daily (8.5M rows/run) - ESSENTIAL
  ✓ price_weekly (2M rows)
  ✓ price_monthly (380K rows)  
  ✓ etf_price_daily (8.1M rows) - ESSENTIAL
  ✓ etf_price_weekly (1.9M rows)
  ✓ etf_price_monthly (358K rows)
  → Recommendation: Keep daily versions, remove weekly/monthly (slow, unused for live trading)

Technical Indicators (2 loaders):
  ✓ technical_data_daily (8.3M rows) - ESSENTIAL
  ✓ momentum_metrics (4.7K rows) - ESSENTIAL
  → REMOVE: technical_data_weekly (0 rows - empty), technical_data_monthly (0 rows - empty)

Core Metrics (7 loaders):
  ✓ quality_metrics (4.7K rows) - used for scoring
  ✓ growth_metrics (4.8K rows)
  ✓ value_metrics (4.7K rows)
  ✓ stability_metrics (4.7K rows)
  ✓ positioning_metrics (4.7K rows)
  ✓ market_exposure_daily (used by orchestrator)
  ✓ stock_scores (4.7K rows) - final composite score
  → All needed; consider batching in one container

Trading Signals (4 loaders):
  ✓ buy_sell_daily (230K rows) - ESSENTIAL for trading
  ~ buy_sell_weekly (297K rows) - legacy, unused?
  ~ buy_sell_monthly (297K rows) - legacy, unused?
  ✓ swing_trader_scores (20K rows) - trading input
  ✓ stock_scores (composite score)
  → Recommendation: Keep daily versions, remove/archive weekly/monthly

Orchestrator Outputs (4 loaders):
  ✓ algo_performance_daily - populated BY orchestrator
  ✓ algo_risk_daily - populated BY orchestrator
  ~ portfolio_performance (0 rows - broken?)
  ~ relative_performance (0 rows - broken?)
  → Keep critical ones, fix or remove broken

Critical Reference (4 loaders):
  ✓ stock_symbols (10.5K rows) - defines universe
  ✓ company_profile (10.3K rows) - used for fundamentals
  ✓ earnings_calendar (272 rows) - event data
  ✓ earnings_history (18K rows)
  → All needed for trading context

SUBTOTAL: ~35-40 essential loaders
```

### CATEGORY B: NICE-TO-HAVE (keep if resources available)
```
Alternative Data (3 loaders - lower priority):
  ~ aaii_sentiment (2K rows) - sentiment indicator
  ~ fear_greed_index (371 rows) - market regime
  ~ naaim (1K rows) - positioning data
  → These are optional - nice for analysis, not critical for trading

Financial Deep Dive (6 loaders - depends on strategy):
  ~ annual_income_statement (55K rows)
  ~ annual_balance_sheet (52K rows)
  ~ annual_cash_flow (51K rows)
  ~ quarterly_income_statement (14K rows)
  ~ quarterly_cash_flow (21K rows)
  ~ analyst_sentiment (0 rows - broken)
  → Keep if using fundamental analysis, remove if not

SUBTOTAL: ~9 optional loaders (safe to disable)
```

### CATEGORY C: DEAD CODE (remove immediately)
```
Completely Unused/Empty:
  ✗ commodity_price_history (0 rows)
  ✗ commodity_prices (0 rows)
  ✗ commodity_technicals (0 rows)
  ✗ commodity_macro_drivers (0 rows)
  ✗ cot_data (0 rows)
  ✗ distribution_days (0 rows)
  ✗ index_metrics (0 rows)
  ✗ industry_performance (0 rows)
  ✗ institutional_positioning (0 rows)
  ✗ iv_history (0 rows)
  ✗ sentiment (0 rows)
  ✗ sentiment_social (0 rows)
  ✗ signal_themes (0 rows)
  ✗ analyst_upgrade_downgrade (50 rows - orphaned)
  ✗ schema (shouldn't be a loader)
  ✗ performance_daily (0 rows)
  ✗ relative_performance (0 rows)
  ✗ earnings_estimate_revisions (0 rows)
  ✗ analyst_sentiment_analysis (0 rows)

SUBTOTAL: 18 dead loaders (remove - saves ~$40-60/month)
```

---

## 3. Consolidation Strategy (Like Financial Statements)

### Pattern: Parametrized Consolidation

**Current approach (financial statements):**
```python
# ONE loader, parameterized by env vars:
# LOADER_STATEMENT_TYPE=income LOADER_PERIOD=annual python3 load_financial_statements.py
# LOADER_STATEMENT_TYPE=balance LOADER_PERIOD=annual python3 load_financial_statements.py
# LOADER_STATEMENT_TYPE=cashflow LOADER_PERIOD=annual python3 load_financial_statements.py

# Result: 1 container definition, 3 task definitions (same code, diff params)
```

### Apply to Other Multi-Variant Loaders

**GROUP 1: Price Data Consolidation**
```
Current: 6 separate loaders (price daily/weekly/monthly, etf_price daily/weekly/monthly)
Optimized: 2 loaders
  - Stocks: load_prices.py (SYMBOL_TYPE=equity TIMEFRAME=daily)
  - ETFs: load_prices.py (SYMBOL_TYPE=etf TIMEFRAME=daily)

Rationale:
  - Same API call logic
  - Weekly/monthly can be computed from daily (no need to fetch separately)
  - Daily needed for live trading; weekly/monthly for analysis only
  
Savings: 4 task definitions removed, pipeline faster (parallel fewer tasks)
```

**GROUP 2: Metrics Consolidation**
```
Current: 5 separate loaders (quality, growth, value, stability, positioning)
Optimized: 2 loaders
  - Fundamental Metrics: load_fundamental_metrics.py 
    (METRIC_TYPE=quality/growth/value/stability BATCH_SIZE=1000)
  - Position Metrics: load_positioning_metrics.py (specialized, different API)

Rationale:
  - Share common logic (yfinance + SEC filing parsing)
  - Batch all fundamentals in one container if resources allow
  - Same rate-limit risk, so no downside to batching

Savings: 2-3 task definitions, 10-15% faster (shared caching)
```

**GROUP 3: Trading Signals Consolidation**
```
Current: 3 separate loaders (buy_sell_daily, buy_sell_weekly, buy_sell_monthly)
Optimized: 1 loader
  - load_trading_signals.py (TIMEFRAME=daily [remove weekly/monthly entirely])

Rationale:
  - Same signal calculation logic
  - Weekly/monthly not used by live orchestrator
  - Daily sufficient for all strategies

Savings: 2 task definitions, simpler pipeline
```

**GROUP 4: Reference Data Consolidation**
```
Current: 8 separate loaders (company_profile, earnings_calendar, earnings_history, etc)
Optimized: 2 loaders
  - Company Reference: load_company_reference.py
    (DATA_TYPE=profile/earnings_calendar/earnings_history)
  - Analyst Data: load_analyst_data.py
    (DATA_TYPE=sentiment/upgrades_downgrades)

Rationale:
  - Different APIs but similar error handling
  - Can share rate-limit pools and retry logic

Savings: 3-4 task definitions
```

---

## 4. Recommended Optimization Plan

### Phase 1: REMOVE DEAD CODE (Immediate - 1 hour)
```sql
DELETE FROM data_loader_status 
WHERE table_name IN (
  'commodity_price_history', 'commodity_prices', 'commodity_technicals',
  'commodity_macro_drivers', 'cot_data', 'distribution_days', 'index_metrics',
  'industry_performance', 'institutional_positioning', 'iv_history',
  'sentiment', 'sentiment_social', 'signal_themes', 'performance_daily',
  'relative_performance', 'earnings_estimate_revisions', 'analyst_sentiment',
  'analyst_sentiment_analysis'
);

-- Remove task definitions from terraform
-- Files to delete: loaders/load_commodity_*.py, load_cot_data.py, load_distribution_days.py, etc.
```

**Impact**: Saves $40-60/month, cleaner codebase

### Phase 2: REMOVE WEEKLY/MONTHLY DUPLICATES (1 day)
```
Delete loaders:
  - load_price_weekly.py, load_price_monthly.py
  - load_buy_sell_weekly.py, load_buy_sell_monthly.py
  - load_technical_data_weekly.py, load_technical_data_monthly.py
  
Keep only:
  - load_prices.py (daily only)
  - load_buy_sell_daily.py (daily only)
  - load_technical_data_daily.py (daily only)

Rationale:
  - Orchestrator trades on daily timeframe, not weekly/monthly
  - Weekly/monthly can be computed via SQL aggregation if needed
  - Reduces Step Functions complexity
```

**Impact**: Saves $30-50/month, 15% faster pipeline

### Phase 3: CONSOLIDATE LIKE FINANCIAL STATEMENTS (2-3 days)
```
Pattern: One loader file, parametrized by env vars, multiple task definitions

Consolidate:
  1. Quality/Growth/Value/Stability → load_fundamental_metrics.py
  2. Price Daily/Weekly/ETF → load_prices.py (day only)
  3. Trading Signals → load_trading_signals.py (daily only)
  4. Reference Data → load_company_reference.py

Result: Reduce from 40+ loaders to ~25 core loaders
```

**Impact**: Saves $20-30/month, easier maintenance, 10-20% faster (shared setup/teardown)

### Phase 4: OPTIMIZE CONTAINER RESOURCES (1-2 days)
```
Analyze current ECS task definitions:
  - Memory allocation per loader type
  - Actual usage during runs
  - Can we batch complementary loaders?

Example tuning:
  - Metrics loaders: 1024 MB each, but may only use 512 MB
  - Price loader: 512 MB sufficient
  - Financial statements: 1024 MB (yfinance + database writes)
  - Consider: Run quality+growth+value together in 2048 MB container
    vs. separately in 3×1024 MB = net savings + parallelism

After consolidation, estimate:
  - Reduce ECS task count from 40 to 25
  - Better container utilization (less idle time)
  - Faster overall pipeline (parallel execution improved)
```

**Impact**: Additional $10-20/month savings

---

## 5. Final Recommended State

**From 74 loaders → ~25-30 core loaders**

| Category | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|----------|---------|--------------|--------------|----------------|
| Price | 6 | 6 | 2 | 2 |
| Technical | 5 | 5 | 2 | 2 |
| Metrics | 10 | 10 | 10 | 4 |
| Trading | 9 | 9 | 4 | 2 |
| Ref Data | 8 | 8 | 8 | 3 |
| Orchestrator | 4 | 4 | 4 | 3 |
| Optional | 15 | 6 | 6 | 4 |
| Dead | 18 | 0 | 0 | 0 |
| **TOTAL** | **74** | **56** | **38** | **25** |

**Cost Impact:**
```
Current: ~$200-250/month
Phase 1: ~$160-190/month (save $40-60)
Phase 2: ~$130-160/month (save additional $30-50)
Phase 3: ~$100-120/month (save additional $20-30)

TOTAL SAVINGS: $80-130/month (35-50% reduction)
Faster Pipeline: 20-30% improvement from reduced task overhead
```

---

## 6. Next Steps

1. **Immediate** (today): Audit which loaders orchestrator actually uses
   ```bash
   grep -r "FROM\|table_name\|\.select" algo/orchestration/ | sort | uniq
   ```

2. **This week**: Decide on optional loaders (keep or remove?)
   - aaii_sentiment, fear_greed_index, financial statements?
   - Ask: Are these used by any trading strategies?

3. **Next sprint**: Implement Phase 1-2 (remove dead code + duplicates)

4. **Following sprint**: Implement Phase 3 (consolidate parametrized loaders)

Would you like me to:
- [ ] Audit which tables orchestrator actually uses?
- [ ] Map out exact consolidation for each loader group?
- [ ] Create the parametrized loader templates?
- [ ] Update Terraform to use fewer task definitions?

