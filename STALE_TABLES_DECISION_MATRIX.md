# Stale Tables & Empty Schemas - Decision Matrix (Session 267 Phase 3)

**Status**: AUDIT IN PROGRESS - MAKING DECISIONS ON WHAT TO KEEP/DROP

---

## KEY FINDINGS

### 🚨 The "Cheating" Problem Found

**Deprecated Endpoints Querying Stale Data**:

1. **`/api/signals` endpoint** (DEPRECATED, lines 114-234 in signals.py):
   - Queries `buy_sell_daily` table (last updated 5/19 = 61 days ago)
   - Code comment: "buy_sell_daily table is no longer populated by orchestrator"
   - Reason: "Maintained for backward compatibility with external systems"
   - **Reality**: Dead code querying stale data, waiting to fail

2. **`/api/signals/etf` endpoint** (DEPRECATED, lines 237-309 in signals.py):
   - Code comment: "buy_sell_daily_etf and technical_data_daily were removed from the pipeline"
   - This endpoint was replaced with computation from trend_template_data
   - **But the old endpoint code is still there**

3. **Real Dashboard Uses**:
   - `/api/algo/dashboard-signals` → queries `algo_signals` (FRESH, populated daily)
   - This is the active endpoint, others are legacy

**The Issue**: We're keeping deprecated code that queries abandoned tables "just in case" external systems rely on it. This is exactly the "bypasses and cheats" - we know the data is stale but aren't fixing it or removing it.

---

## STALE TABLES (Decision Matrix)

### Tier 1: ACTIVELY STALE (Known to be stale, but code still queries them)

| Table | Last Updated | Age | Used By | Status | Decision |
|-------|--------------|-----|---------|--------|----------|
| `buy_sell_daily` | 5/19 | 61d | `/api/signals` (DEPRECATED) | QUERIED BUT STALE | **DROP ENDPOINT + STOP MAINTAINING TABLE** |
| `buy_sell_daily_etf` | 5/19 | 61d | `/api/signals/etf` (DEPRECATED) | QUERIED BUT STALE | **DROP ENDPOINT + STOP MAINTAINING TABLE** |
| `buy_sell_monthly` | 5/19 | 61d | Unknown | NOT ACTIVELY QUERIED | **AUDIT THEN DROP** |
| `buy_sell_weekly` | 5/19 | 61d | Unknown | NOT ACTIVELY QUERIED | **AUDIT THEN DROP** |
| `buy_sell_monthly_etf` | 5/19 | 61d | Unknown | NOT ACTIVELY QUERIED | **AUDIT THEN DROP** |
| `buy_sell_weekly_etf` | 5/19 | 61d | Unknown | NOT ACTIVELY QUERIED | **AUDIT THEN DROP** |

### Tier 2: MODERATELY STALE (30-60 days, might be used)

| Table | Last Updated | Age | Used By | Status | Decision |
|-------|--------------|-----|---------|--------|----------|
| `quarterly_balance_sheet` | 5/19 | 61d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `quarterly_income_statement` | 6/28 | 21d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `quarterly_cash_flow` | 6/28 | 21d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `key_metrics` | 5/21 | 59d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `analyst_upgrade_downgrade` | 5/22 | 58d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `options_chains` | 6/20 | 29d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |
| `annual_cash_flow` | 7/1 | 18d | TBD | NEEDS AUDIT | **IF NOT USED: DROP** |

---

## EMPTY TABLES (Decision Matrix)

### Category: TRADING/EXECUTION (All 0 rows)

| Table | Rows | Used | Decision |
|-------|------|------|----------|
| `algo_trades` | 0 | ? | CONFIRM NOT USED → DROP SCHEMA |
| `algo_positions` | 0 | ? | CONFIRM NOT USED → DROP SCHEMA |
| `algo_alerts` | 0 | ? | CONFIRM NOT USED → DROP SCHEMA |
| `algo_reconciliation_log` | 0 | ? | CONFIRM NOT USED → DROP SCHEMA |

### Category: USER MANAGEMENT (All 0 rows)

| Table | Rows | Used | Decision |
|-------|------|------|----------|
| `users` | 0 | No Cognito users table | DROP SCHEMA |
| `user_alerts` | 0 | Not implemented | DROP SCHEMA |
| `user_api_keys` | 0 | Not implemented | DROP SCHEMA |
| `user_dashboard_settings` | 0 | Not implemented | DROP SCHEMA |

### Category: FEATURES (All 0 rows - likely abandoned)

| Table | Rows | Used | Decision |
|-------|------|------|----------|
| `calendar_events` | 0 | Not referenced | DROP SCHEMA |
| `dividend_history` | 0 | Not referenced | DROP SCHEMA |
| `sectors` | 0 | Not referenced | DROP SCHEMA |
| `insider_transactions` | 0 | Not referenced | DROP SCHEMA |
| `commodity_*` (5 tables) | 0 | Not referenced | DROP SCHEMA |
| `stock_correlations` | 0 | Not referenced | DROP SCHEMA |
| `short_interest` | 0 | REPLACED by short_interest_finra | DROP SCHEMA |

### Category: OTHER (All 0 rows)

| Table | Rows | Used | Decision |
|-------|------|------|----------|
| `circuit_breaker_log` | 0 | ? | AUDIT - may be needed for monitoring |
| `algo_model_registry` | 0 | ? | AUDIT - may be needed for ML features |
| 30+ more empty tables | 0 | TBD | BATCH AUDIT AND DROP |

---

## DECISIONS TO MAKE

### PHASE 3A: Immediate Fixes (No Risk)

1. **Drop Deprecated API Endpoints** (signals.py):
   - Remove `/api/signals` endpoint (lines 114-234) - uses stale buy_sell_daily
   - Remove `/api/signals/etf` endpoint (lines 237-309) - uses stale buy_sell_daily_etf
   - Keep `/api/algo/dashboard-signals` (real endpoint dashboard uses)
   - **Reason**: Dead code, no longer maintained, queries stale data

2. **Stop Maintaining These Tables**:
   - buy_sell_daily, buy_sell_daily_etf
   - buy_sell_monthly*, buy_sell_weekly*
   - **Reason**: Not in active use, orchestrator doesn't populate, data stale

3. **Drop Empty User Management Schema**:
   - users, user_alerts, user_api_keys, user_dashboard_settings
   - **Reason**: System uses Cognito, these tables never implemented

### PHASE 3B: Audit-Dependent Decisions

Before dropping, verify NOT used:
- quarterly_* tables (used in financial analysis?)
- key_metrics (used in scoring?)
- analyst_* tables (used in signals?)
- options_chains (used anywhere?)
- 40+ other empty tables

---

## IMPLEMENTATION PLAN

### Step 1: Audit Active Code Paths (ONGOING)
- Use grep to confirm which tables are actually referenced
- Document findings in table matrix above

### Step 2: Drop Dead API Endpoints
```python
# signals.py - REMOVE THESE FUNCTIONS:
- def _get_signals_stocks()  # Lines 114-234
- def _get_signals_etf()     # Lines 237-309

# Keep only:
- Dashboard uses /api/algo/dashboard-signals (queries algo_signals)
```

### Step 3: Stop Populating Stale Tables
- Verify buy_sell_daily loaders are disabled
- Confirm quarterly/analyst/options data loaders don't run
- Document why (data no longer needed or replaced by other sources)

### Step 4: Drop Confirmed Unused Tables
- Once audit confirms no references:
  - DROP TABLE buy_sell_daily, buy_sell_daily_etf
  - DROP TABLE quarterly_*, analyst_*, options_*
  - DROP TABLE users, user_*, calendar_*, dividend_*, sectors, commodities_*
  - DROP INDEX on dropped tables
  - Update schema_version table

### Step 5: Update Documentation
- Document what each dropped table was for
- Document why it was abandoned
- Document when/where it was referenced (historical)

---

## ANTI-CHEATING RULES (Going Forward)

1. **No Dead Code Queries**: If a table isn't actively maintained, remove the code that queries it
2. **No Backward Compatibility Lies**: Don't keep deprecated endpoints "just in case" - migrate external systems or document the timeline
3. **No Silent Fallbacks**: If a table is stale, fail explicitly - don't return empty results and hope nobody notices
4. **Explicit SLAs**: Every table must have an owner and update schedule - if not, delete it
5. **Regular Audits**: Quarterly schema review - delete anything that hasn't been used in 90 days

---

## RISK ASSESSMENT

**Risk of Dropping Deprecated Endpoints**: 
- LOW - They return 503 errors when data is stale (already failing)
- Dashboard doesn't use them (verified)
- External systems should migrate to fresh `/api/algo/dashboard-signals`

**Risk of Dropping Empty Tables**:
- LOW - They have 0 rows, no data loss
- Not referenced in code (will verify with audit)
- Can be restored from git history if needed

**Risk of Dropping Stale Tables**:
- MEDIUM - If external systems rely on them
- But system already acknowledges they're stale (comments in code)
- Better to fail explicitly and migrate than serve stale data

---

## SUCCESS CRITERIA

✅ Session 267 Phase 3 Complete When:
1. [x] Deprecated endpoints identified and documented
2. [x] Stale data sources identified and documented
3. [ ] All active code paths audited (PENDING - agent checking)
4. [ ] Decision matrix complete with YES/NO per table
5. [ ] Unused tables confirmed with grep (PENDING)
6. [ ] Deprecated endpoints removed (TODO)
7. [ ] Stale tables dropped (TODO)
8. [ ] Schema cleaned (TODO)
9. [ ] Documentation updated (TODO)

