# Session 22: SQL INTERVAL Configuration Foundation

**Status:** ✅ Foundation Complete (Configuration System Ready)  
**Effort Level:** Medium (foundation), Low-Medium (implementation when needed)  
**Impact:** Enables replacement of 80+ hardcoded SQL INTERVAL values with config-driven values

## Summary

Established infrastructure to replace hardcoded SQL INTERVAL values throughout the codebase with configuration-driven lookback periods. This enables operators to tune query lookback windows without code changes.

## Completed

### 1. Configuration Schema (config_schema.py)
Added 10 new configuration keys with validation rules:
- `sql_interval_1d_days` (int: 1-30, default: 1)
- `sql_interval_7d_days` (int: 7-30, default: 7)
- `sql_interval_14d_days` (int: 14-30, default: 14)
- `sql_interval_24h_days` (float: 0.5-2.0, default: 1.0)
- `sql_interval_30d_days` (int: 30-100, default: 30)
- `sql_interval_50d_days` (int: 50-100, default: 50)
- `sql_interval_60d_days` (int: 60-100, default: 60)
- `sql_interval_90d_days` (int: 90-180, default: 90)
- `sql_interval_365d_days` (int: 365-400, default: 365)
- `sql_interval_52w_days` (int: 350-380, default: 364)

### 2. Configuration Defaults (main.py)
Added all 10 keys to AlgoConfig.DEFAULTS with:
- Default values matching validation ranges
- Descriptions for operator reference
- Category: "SQL Query Configuration"

### 3. Helper Module (sql_intervals.py)
Created utility functions to convert config values to SQL INTERVAL strings:

```python
from algo.infrastructure.config.sql_intervals import get_interval_sql

# In SQL queries:
cur.execute(f"""
    SELECT * FROM table 
    WHERE created_at > NOW() - {get_interval_sql('7d')}
""")
```

Functions provided:
- `get_interval_sql(key, config)` → Returns "INTERVAL 'N days'" string
- `get_interval_days(key, config)` → Returns numeric day value

### 4. Database Migration (1010_add_sql_interval_configuration.sql)
Migration populates all 10 new config keys in algo_config table.

Run with:
```bash
python migrations/run.py up 1010
```

## Hardcoded INTERVAL Statistics

From comprehensive grep scan of 109 Python files:

| Interval | Count | Config Key |
|----------|-------|-----------|
| 1 day | 124 | sql_interval_1d_days |
| 7 days | 101 | sql_interval_7d_days |
| 30 days | 66 | sql_interval_30d_days |
| 14 days | 44 | sql_interval_14d_days |
| 90 days | 30 | sql_interval_90d_days |
| 365 days | 24 | sql_interval_365d_days |
| 50 days | 24 | sql_interval_50d_days |
| 60 days | 19 | sql_interval_60d_days |
| 24 hours | 17 | sql_interval_24h_days |
| 52 weeks | 12 | sql_interval_52w_days |
| Others | ~44 | (parametric or one-time uses) |
| **Total** | **505** | |

## Next Steps (When Ready to Implement)

### Phase 1: Priority Files (Highest Impact)
Replace hardcoded INTERVAL values in top 20 files by frequency:
- [ ] algo/infrastructure/reconciliation.py (multiple uses)
- [ ] loaders/load_stock_scores.py
- [ ] algo/trading/exit_engine.py
- [ ] lambda/api/routes/*.py (API endpoints)

**Implementation Pattern:**
```python
# OLD
cur.execute("SELECT * FROM table WHERE date > NOW() - INTERVAL '7 days'")

# NEW
from algo.infrastructure.config.sql_intervals import get_interval_sql
cur.execute(f"SELECT * FROM table WHERE date > NOW() - {get_interval_sql('7d')}")
```

### Phase 2: Bulk Replacement (Remaining 89 Files)
Systematic replacement in:
- API route handlers (lambda/api/routes/)
- Data loaders (loaders/)
- Dashboard API (api-pkg-manual/routes/)
- Risk/monitoring modules

### Phase 3: Parametric Patterns
Refactor cases using Python string formatting:
- `f"INTERVAL '{days}' days"` → `get_interval_sql()`
- `f"INTERVAL '{%d} days"` → config-driven with placeholder

### Phase 4: Validation & Testing
- Unit tests for get_interval_sql() function
- Integration test: verify queries still work after replacement
- No functional change expected (same lookback periods)

## Migration Safety

✅ **Non-Breaking Change**
- Default config values match current hardcoded values
- No existing queries change behavior
- Config system has full validation
- Fail-fast on invalid interval values

✅ **Rollback Safe**
- If needed, revert migration with: `python migrations/run.py down 1010`
- Code falls back to defaults if config keys missing

✅ **Gradual Rollout**
- Can migrate files incrementally
- Mix hardcoded and config-driven queries during transition
- No coordination needed across teams

## Technical Design

**Why Configuration Over Environment Variables:**
- Interval values are operationally tuned (not deployment-specific)
- Need hot-reload capability (change without Lambda redeploy)
- Fail-closed safety gates prevent zero/invalid values
- Database persistence for audit trails

**Why Separate Helper Module:**
- Centralized INTERVAL construction logic
- Easy to find all SQL INTERVAL generation
- Testable without full query context
- Single place to add future INTERVAL formats (if needed)

**Backward Compatibility:**
- No changes to existing config keys
- New keys sit alongside existing lookback configs (lookback_price_*, lookback_ranking_*)
- Naming convention: `sql_interval_` prefix prevents conflicts

## Files Changed

1. **algo/infrastructure/config_schema.py** — Added 10 validation rules
2. **algo/infrastructure/config/main.py** — Added 10 defaults
3. **algo/infrastructure/config/sql_intervals.py** — NEW helper module
4. **migrations/1010_add_sql_interval_configuration.sql** — NEW migration

## Testing

**Pre-Deployment Verification:**
```bash
# 1. Check config system still works
python -c "from algo.infrastructure.config import get_config; c = get_config(); print(c.get('sql_interval_7d_days'))"

# 2. Test helper functions
python -c "from algo.infrastructure.config.sql_intervals import get_interval_sql; print(get_interval_sql('7d'))"
# Expected: INTERVAL '7 days'

# 3. Run config validation
python algo/infrastructure/config/main.py
```

**Post-Migration Checklist:**
- [ ] Migration 1010 applied (python migrations/run.py up 1010)
- [ ] Config keys readable (python -c "from algo.infrastructure.config import get_config; print(get_config().get('sql_interval_1d_days'))")
- [ ] Dashboard/orchestrator start without errors
- [ ] Log shows "10 from database" in config sources audit

## Why This Matters

Hardcoded INTERVAL values create operational friction:

❌ **Before (Hardcoded)**
- Want to extend lookback from 7 to 14 days? Edit code, redeploy.
- Risk of inconsistency (some loaders use 7d, others 14d for same metric)
- No visibility into what lookback windows are active
- Configuration buried in 109 files

✅ **After (Config-Driven)**
- Change lookback in database: `UPDATE algo_config SET value='14' WHERE key='sql_interval_7d_days'`
- Takes effect immediately (no Lambda redeploy)
- Centralized visibility (single algo_config table)
- Audit trail of who changed what when

## Cost Analysis

**Implementation Effort:** ~4-6 hours
- Phase 1: 2-3 hours (priority files)
- Phase 2: 1-2 hours (bulk replacement)
- Phase 3: 0.5-1 hour (parametric cleanup)
- Phase 4: 0.5 hour (validation)

**Value:** Medium
- Improves operational flexibility (hot-tuning lookback windows)
- Reduces code maintenance (fewer hardcoded magic values)
- Enables experimentation (A/B test different lookback periods)

**Risk:** Very Low
- Non-breaking change (all defaults match current values)
- Fail-safe configuration validation
- Can rollback if needed
- Can migrate incrementally

## Notes for Future Work

1. **Parametric Intervals:** Some files use dynamic INTERVAL values (e.g., `f"INTERVAL '{lookback_days} days'"`). These already have flexibility but should be refactored to use config keys instead (reduces special cases).

2. **Consistency Opportunity:** Multiple files define their own lookback periods independently. Using centralized config ensures consistent windows across all data operations.

3. **Monitoring Enhancement:** Could add telemetry to log which interval keys are most-used, helping optimize configuration tuning.

4. **Testing:** Add unit tests for sql_intervals.py in test suite (e.g., verify edge cases like boundary values).

---

**Session Status:** ✅ Complete (Foundation Ready)  
**Next Action When Needed:** Pick Phase 1 files and implement replacement pattern  
**Estimated Completion Time:** 4-6 hours for full implementation  
**Priority:** Medium (operational convenience, not blocking)
