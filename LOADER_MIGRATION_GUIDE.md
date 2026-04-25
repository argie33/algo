# Loader Migration Guide - Remove Schema Duplication

**Status**: Schema files cleaned up ✅  
**Next**: Update loaders to use authoritative schema

---

## What Changed

| Old Way | New Way |
|---------|---------|
| Each loader had CREATE TABLE | Schema defined ONCE in init_database.py |
| 50+ conflicting definitions | Single authoritative definition |
| Silent failures on column mismatch | Clear validation before insert |
| Multiple "source of truth" files | SCHEMA_DEFINITION.md is the reference |

---

## Loaders That Need Updates

### Priority 1: Critical Path (Run Immediately)

These are the ones blocking data population:

#### 1. `loadearningshistory.py`
- **Current Issue**: Creates its own earnings_estimates table with conflicting schema
- **Fix**: Remove CREATE TABLE, verify columns match SCHEMA_DEFINITION.md
- **Columns to insert**: symbol, quarter, fiscal_quarter, fiscal_year, earnings_date, estimated, eps_actual, revenue_actual, eps_estimate, revenue_estimate, (and surprise metrics)
- **Verify**: Don't insert to columns that don't exist in schema

#### 2. `loaddailycompanydata.py`
- **Current Issue**: Creates multiple tables with inconsistent schemas
- **Fix**: Remove all CREATE TABLE statements
- **Tables it affects**: company_profile, positioning_metrics, insider_transactions, earnings_estimates
- **Verify**: Check that all inserted columns exist in authoritative schema

#### 3. `loadanalystupgradedowngrade.py`
- **Current Issue**: Own CREATE TABLE definition
- **Fix**: Remove CREATE TABLE
- **Columns**: symbol, action_date, firm, old_rating, new_rating, action
- **Add column**: company_name (join from company_profile)

#### 4. `loadanalystsentiment.py`
- **Current Issue**: Own CREATE TABLE definition
- **Fix**: Remove CREATE TABLE
- **Columns**: symbol, date, analyst_count, bullish_count, bearish_count, neutral_count, target_price, current_price, upside_downside_percent
- **Verify**: All columns exist in schema

#### 5. `loadbuyselldaily.py`, `loadbuysellweekly.py`, `loadbuysellmonthly.py`
- **Current Issue**: Own CREATE TABLE definitions
- **Fix**: Remove all CREATE TABLE
- **Columns**: symbol, date/week_ending/month_ending, signal, strength, reason
- **Verify**: Table names and columns match schema

---

### Priority 2: Supporting Tables

These populate important but non-critical data:

- `loadpricedaily.py` - Remove CREATE TABLE
- `loadpriceweekly.py` - Remove CREATE TABLE
- `loadpricemonthly.py` - Remove CREATE TABLE
- `loadtechnicalindicators.py` - Remove CREATE TABLE
- `loadfactormetrics.py` - Remove CREATE TABLE (quality, growth, stability, value, positioning)
- `loadstockscores.py` - Remove CREATE TABLE

---

### Priority 3: All Other Loaders

For all remaining loaders:
1. Search for `CREATE TABLE`
2. Delete those statements
3. Keep the INSERT logic
4. Verify column names match SCHEMA_DEFINITION.md

---

## How to Fix Each Loader

### Step 1: Find CREATE TABLE statements

```bash
grep -n "CREATE TABLE" loadearningshistory.py
```

### Step 2: Remove them

Example before:
```python
CREATE TABLE IF NOT EXISTS earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    quarter DATE,
    ...
)

# Then INSERT code
cursor.execute("INSERT INTO earnings_estimates (symbol, quarter, ...) VALUES ...")
```

Example after:
```python
# REMOVED: CREATE TABLE statement
# Table is initialized by: init_database.py

# INSERT code (unchanged)
cursor.execute("INSERT INTO earnings_estimates (symbol, quarter, ...) VALUES ...")
```

### Step 3: Verify column names

Before inserting, check that columns match SCHEMA_DEFINITION.md:

```python
# BAD: Tries to insert into non-existent columns
cursor.execute(
    "INSERT INTO earnings_estimates (symbol, next_earnings_date, eps_estimate) VALUES ..."
)

# GOOD: Uses columns from authoritative schema
cursor.execute(
    "INSERT INTO earnings_estimates (symbol, earnings_date, eps_estimate) VALUES ..."
)
```

### Step 4: Add column validation (optional but recommended)

```python
def validate_columns(table_name, columns):
    """Verify all columns exist in table"""
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = %s
    """, (table_name,))
    
    existing = {row[0] for row in cur.fetchall()}
    missing = set(columns) - existing
    
    if missing:
        raise ValueError(f"Missing columns in {table_name}: {missing}")
    
    return True
```

---

## Files to Remove (if not already done)

```bash
# These are no longer needed
rm initialize-schema.py.OBSOLETE
rm init_schema.py.OBSOLETE

# Old schema can be kept as backup
# .backup_old_schemas/  ← Archive of old definitions
```

---

## Files to Create/Update

✅ Created:
- `SCHEMA_DEFINITION.md` - Authoritative reference
- `init_database_NEW.py` - Authoritative schema initialization

⚠️ Updated:
- `init_database.py` - Replaced with new version
- `run-loaders.py` - Updated to use new schema

📋 Next:
- Update all loaders to remove CREATE TABLE
- Add column validation where appropriate

---

## Testing After Updates

### 1. Test schema initialization

```bash
python3 init_database.py
```

Should output:
```
✓ Schema initialization complete!
  Succeeded: 27
  Failed: 0
```

### 2. Test a loader

```bash
# With new schema in place, loader should work
python3 loadearningshistory.py
```

Should succeed without errors about missing tables.

### 3. Verify data inserted

```bash
curl http://localhost:3001/api/earnings/info?symbol=AAPL
```

Should now return data with non-NULL eps_estimate values.

---

## Common Issues and Solutions

### Issue: "Column does not exist"
**Cause**: Loader trying to insert to column not in schema  
**Fix**: Check column name in schema, update INSERT statement

### Issue: "Relation does not exist"
**Cause**: Loader's CREATE TABLE didn't run  
**Fix**: Delete loader's CREATE TABLE, rely on init_database.py

### Issue: "Unique constraint violation"
**Cause**: Duplicate data being inserted  
**Fix**: Add conflict handling: `INSERT ... ON CONFLICT DO NOTHING`

### Issue: Data still NULL
**Cause**: INSERT succeeded but no actual values  
**Fix**: Check that loader extracts data correctly from yfinance/API

---

## Checklist

### Before running any loaders:

- [ ] init_database.py has been run and succeeded
- [ ] SCHEMA_DEFINITION.md is the authoritative reference
- [ ] initialize-schema.py is marked OBSOLETE
- [ ] init_schema.py is marked OBSOLETE

### For each loader being updated:

- [ ] Remove all CREATE TABLE statements
- [ ] Verify column names match SCHEMA_DEFINITION.md
- [ ] Test INSERT logic with sample data
- [ ] Verify no "column does not exist" errors
- [ ] Verify data is actually inserted (not NULL)

### After all loaders updated:

- [ ] Run complete loader pipeline: `python3 run-loaders.py`
- [ ] Verify data appears in API responses
- [ ] Verify NULL values are gone
- [ ] Frontend shows complete data

---

## Summary

**The Goal**: One authoritative schema, zero duplication, explicit errors instead of silent failures.

**The Work**: Remove CREATE TABLE from ~48 loaders, verify column names.

**The Benefit**: 
- No more mysterious NULL values
- Clear error messages if something's wrong
- Single place to understand table structure
- Easier to add new loaders or modify schema

**Estimated Time**: 2-3 hours to update all loaders systematically
