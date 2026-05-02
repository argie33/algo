# Incremental Load Implementation Plan
**Goal**: Daily 2-3 min loads instead of weekly 20 min
**Impact**: 8x faster for daily operations, saves $0.10/week

## Architecture

### Current (Full Reload Every Week)
- Monday: Load ALL 29.7M rows (20 minutes)
- Tuesday-Sunday: Nothing
- Cost: $2.50/week

### New (Daily Incremental + Weekly Full)
- Mon-Sat: Incremental load (only new/changed data) = 2-3 min each
- Sunday: Full reload (consistency check) = 20 min
- Cost: $1.50/week (saves $1/week)

## Implementation Steps

### Phase 1: Add State Tracking (1 hour)
1. Create `load_state.json` file to track last_load_date per table
2. Modify each loader to:
   - Read last_load_date from state
   - Only fetch data newer than last_load_date
   - Update state after successful load

### Phase 2: Modify Phase 2 Loaders (2-3 hours)
1. loadecondata.py: Only fetch FRED data from last_load_date onward
2. loadfactormetrics.py: Recalculate metrics for changed symbols only
3. loadstockscores.py: Recalculate scores for updated metrics

### Phase 3: Modify Phase 3 Loaders (3-4 hours)
1. loadpricedaily.py: Only load prices from last_load_date onward
2. loadanalystsentiment.py: Only fetch updated analyst data
3. loadbuyselldaily.py: Only calculate signals from new price data

### Phase 4: Schedule Setup (1 hour)
1. Daily (Mon-Sat 05:00 UTC): scheduler.py --incremental
2. Weekly (Sunday 02:00 UTC): scheduler.py --full

## Files to Create/Modify

NEW:
- load_state.py (state tracking)
- incremental_helpers.py (shared utilities)

MODIFY:
- loadpricedaily.py (add --incremental flag)
- loadanalystsentiment.py (add --incremental flag)
- loadstockscores.py (add --incremental flag)
- loadfactormetrics.py (add --incremental flag)
- loadecondata.py (add --incremental flag)
- scheduler.py (add incremental scheduling)

## Expected Performance

Daily Incremental (Mon-Sat):
- Phase 2: 2 min → 20 sec
- Phase 3B: 5 min → 30 sec
- Phase 3A: 3 min → 30 sec
- Total: 20 min → 2.5 min (8x faster!)
- Cost: $0.05/day vs $0.50/week

Weekly Full (Sunday):
- Same as current: 20 min
- Cost: $0.50 (once weekly)

## Start Implementation?
