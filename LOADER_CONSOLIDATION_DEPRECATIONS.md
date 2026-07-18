# Loader Consolidation & Deprecations

**Status:** Phase 2-4 consolidations complete (Session 209)  
**Date:** July 17, 2026  

---

## Deprecated Loaders (DO NOT USE)

The following loaders have been consolidated into new atomic loaders. **Do not use the old loaders** — they are no longer deployed to AWS and will be removed from the codebase in a future cleanup.

### Phase 2: Market Data Consolidation

**OLD LOADERS (DEPRECATED):**
- `loaders/load_market_health_daily.py` ❌
- `loaders/load_market_exposure_daily.py` ❌
- `loaders/load_market_sentiment.py` ❌

**USE INSTEAD:**
- `loaders/load_market_status_daily.py` ✅

**Why:** Consolidated 3 separate ECS tasks into 1 atomic operation
- All market metrics fetched once
- Outputs to 3 tables atomically (all succeed/fail together)
- Better data integrity
- Saves ~$0.02-0.03/run

**Example:**
```python
# OLD (DEPRECATED - DO NOT USE)
from loaders.load_market_health_daily import MarketHealthDailyLoader
loader = MarketHealthDailyLoader()

# NEW (USE THIS)
from loaders.load_market_status_daily import MarketStatusDailyLoader
loader = MarketStatusDailyLoader()
```

---

### Phase 3: Value/Quality/Growth Consolidation

**OLD LOADERS (DEPRECATED):**
- `loaders/load_yfinance_derived_metrics.py` ❌ (REMOVED - only 1 of 7 outputs was used)
- `loaders/load_quality_growth_metrics.py` ❌ (merged into consolidated loader)

**USE INSTEAD:**
- `loaders/load_value_quality_growth_metrics.py` ✅

**Why:** Consolidated quality + value + growth metrics into single atomic operation
- Uses SEC-audited valuations (better data quality)
- Outputs 3 tables atomically
- Saves ~$0.01-0.02/run
- 5-10 min faster pipeline

---

### Phase 4: Sector/Industry Consolidation

**OLD LOADERS (DEPRECATED):**
- `loaders/load_sector_rankings.py` ❌
- `loaders/load_industry_ranking.py` ❌ (Note: typo in original filename)
- `loaders/load_sector_performance.py` ❌

**USE INSTEAD:**
- `loaders/load_sector_industry_daily.py` ✅

**Why:** Consolidated 3 separate ECS tasks into 1 atomic operation
- All sector/industry metrics fetched once
- Outputs to 3 tables atomically
- Saves ~$0.01-0.02/run

---

## Updated Code References

### Scripts Updated

**scripts/run_loader.py:**
```python
# OLD (removed)
python3 scripts/run_loader.py health          # REMOVED
python3 scripts/run_loader.py metrics         # REMOVED

# NEW (use instead)
python3 scripts/run_loader.py market_status       # Phase 2 consolidated loader
python3 scripts/run_loader.py value_quality_growth # Phase 3 consolidated loader
```

### Tests Updated

**tests/test_fail_fast_patterns.py:**
- Updated to test `MarketStatusDailyLoader` instead of `MarketHealthDailyLoader`

**tests/test_put_call_ratio_yfinance.py:**
- Updated to test `MarketStatusDailyLoader` instead of `MarketHealthDailyLoader`

---

## Migration Checklist

If you encounter code using old loaders:

- [ ] `import MarketHealthDailyLoader` → Change to `import MarketStatusDailyLoader`
- [ ] `import MarketExposureDailyLoader` → Change to `import MarketStatusDailyLoader`
- [ ] `import MarketSentimentLoader` → Change to `import MarketStatusDailyLoader`
- [ ] `import YfinanceDerivedMetricsLoader` → Change to `import ValueQualityGrowthMetricsLoader`
- [ ] `import SectorRankingsLoader` → Change to `import SectorIndustryDailyLoader`
- [ ] `import SectorPerformanceLoader` → Change to `import SectorIndustryDailyLoader`
- [ ] Update terraform references (already done in terraform/modules/pipeline/main.tf)
- [ ] Update orchestrator references (already done)
- [ ] Update morning pipeline (already done - commit 6ae178305)
- [ ] Update EOD pipeline (already done - commit 0eb93ea27)

---

## Loader Status Summary

| Phase | Consolidation | Old Loaders | New Loader | Status |
|-------|---------------|------------|-----------|--------|
| 2 | Market Data | 3 old | `market_status_daily` | ACTIVE ✓ |
| 3 | Value/Quality/Growth | 2 old | `value_quality_growth_metrics` | ACTIVE ✓ |
| 4 | Sector/Industry | 3 old | `sector_industry_daily` | ACTIVE ✓ |

---

## Old Loader Files - Cleanup Plan

The following files exist in the repo but **should NOT be imported or used**:

### To Keep (for reference):
- `loaders/load_market_health_daily.py` - Reference for VIX/breadth/yields logic (now in load_market_status_daily.py)
- `loaders/load_market_exposure_daily.py` - Reference for regime/exposure logic (now in load_market_status_daily.py)
- `loaders/load_market_sentiment.py` - Reference for sentiment logic (now in load_market_status_daily.py)
- `loaders/load_sector_rankings.py` - Reference for sector logic (now in load_sector_industry_daily.py)

### Safe to Remove (completely replaced):
- `loaders/load_yfinance_derived_metrics.py` - COMPLETELY REMOVED (only 1 of 7 outputs used)
- `loaders/load_quality_growth_metrics.py` - Logic merged into load_value_quality_growth_metrics.py
- `loaders/load_sector_performance.py` - Logic merged into load_sector_industry_daily.py
- `loaders/load_industry_ranking.py` - Logic merged into load_sector_industry_daily.py

---

## Why This Matters

### Data Quality
- **Phase 2:** Consolidated market metrics → single source of truth
- **Phase 3:** Using SEC-audited valuations instead of yfinance estimates
- **Phase 4:** Single unified sector data loader

### Performance
- **Atomic Operations:** All succeed or fail together (no partial data)
- **Faster Pipeline:** -12-18 minutes per run (-20%)
- **Lower Cost:** -$80/month (-18%)

### Maintainability
- Single error handler per consolidation (not 3)
- Clear dependencies
- Easier to debug and fix
- Less code to maintain

---

## For Developers

### If You Find Old Loader References

1. **In Source Code:** Update imports to use new consolidated loader
2. **In Tests:** Update test imports and expectations
3. **In Scripts:** Update scripts/run_loader.py choice argument
4. **In Documentation:** Point to new consolidated loader documentation

### When in Doubt

Ask: "Is there a Phase 2, 3, or 4 consolidated loader for this?"
- Phase 2: market_status_daily (market health + exposure + sentiment)
- Phase 3: value_quality_growth_metrics (value + quality + growth)
- Phase 4: sector_industry_daily (sector + industry + performance)

If yes → Use the consolidated loader ✓

---

## Timeline

- **Session 204-208:** Phase 1-4 loaders implemented
- **Session 208:** Phase 3 deployed to terraform, orchestrator updated
- **Session 209:** Phase 2 & 4 deployed to morning pipeline, all references updated
- **Future:** Old loader files can be archived/removed after successful AWS deployment and 2-week validation

---

## Questions?

Refer to:
- `CONSOLIDATION_FINAL_STATUS.md` - Detailed consolidation status
- `SESSION_209_FINAL_LOADING_AUDIT.md` - Verification results
- `LOADING_SITUATION_COMPLETE.md` - Production readiness summary
