# Code Quality Audit - 2026-05-18

## DEAD CODE (Zero imports - 100% safe to delete)

### 6 Unused Algo Modules:
```
algo/algo_connection_monitor.py
algo/algo_earnings_blackout.py
algo/algo_liquidity_checks.py
algo/algo_retry.py
algo/algo_sector_rotation.py
algo/algo_trendline_support.py
```
**Status**: Not imported by orchestrator, tests, or API. Safe to delete.

---

## DUPLICATE CODE

### RSI/MACD Implementations (5 places):
- loaders/loadbuyselldaily.py
- loaders/loadbuysell_etf_daily.py
- loaders/loadstockscores.py
- loaders/load_buysell_aggregate.py
- loaders/load_buysell_etf_aggregate.py

**Status**: Same functions duplicated 5 times. Should consolidate into loaders/technical_indicators.py

### Reconciliation (2 competing implementations):
- algo/algo_reconciliation.py (Phase 3a: position reconciliation)
- algo/algo_daily_reconciliation.py (Phase 7: daily reconciliation + P&L)

**Status**: Both are used, but may overlap. Need to audit.

### Market Exposure (2 modules):
- algo/algo_market_exposure.py
- algo/algo_market_exposure_policy.py

**Status**: Both imported, purpose needs clarification.

---

## LOADERS - NEEDS VERIFICATION

### Loaders likely DEAD (not queried anywhere):
- loadfeargreed.py
- loadseasonality.py
- loadanalystsentiment.py
- loadearningsrevisions.py
- loadmarketindices.py

### Loaders likely USED (queried by filters):
- loadaaiidata.py (aaii_sentiment)
- loadecondata.py (economic_data)
- loadnaaim.py (naaim)
- loadearningshistory.py (earnings_history)
- loadearningsestimates.py (earnings_estimates) - used by data_patrol

### Problem: SAFE_TABLES Mismatch
Some loaders populate tables NOT in algo_sql_safety.py SAFE_TABLES whitelist:
- economic_data
- naaim
- analyst_upgrade_downgrade

These need to be added to SAFE_TABLES or queries fail.

---

## MISSING CRITICAL LOADERS

Phase 1 halts if these tables empty - but NO LOADERS exist:
1. technical_data_daily
2. market_health_daily
3. trend_template_data
4. signal_quality_scores

**Action**: CREATE ASAP

---

## STATUS/DIAGNOSTIC FILES (Already deleted):
- test_credentials_pipeline.py ✓
- scripts/verify-credentials.py ✓
- sync-credentials-local.ps1 ✓
- .env.local ✓

---

## CLEANUP PRIORITY

**Phase 1 (Do immediately)**:
1. Delete 6 unused algo modules
2. Consolidate 5 duplicate indicator implementations
3. Add missing tables to SAFE_TABLES whitelist
4. Create 4 missing critical loaders

**Phase 2 (Audit first)**:
1. Reconciliation modules (audit if overlap)
2. Market exposure modules (clarify responsibilities)
3. Dead loaders (verify which are truly unused)
4. Signal/filter modules (clarify consolidation)
