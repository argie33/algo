# Critical E-Tier Issues — Technical Fix Guide
**For:** Immediate implementation (next 4-6 hours)  
**Target:** Market open readiness  

---

## E1: Complete Database Fallback Removal (BLOCKING ISSUE)

### Current State
**Committed:** `fetch_algo_config()` and `fetch_market()` converted to API-only  
**In progress (staged):** AWS boto3 import added  
**Still needed:** 16+ more fetchers

### Step 1: Identify All Remaining DB Fallback Code
**File:** `tools/dashboard/fetchers.py`

**Search for patterns:**
```
db = get_db_connection()  # OLD PATTERN
cursor = db.cursor()      # OLD PATTERN
result = pool.query()     # OLD PATTERN (if using old pool)
```

**Fetchers needing conversion (priority order):**
1. `fetch_perf()` — Line ~144
2. `fetch_positions()` — Line ~192
3. `fetch_signals()` — Line ~?? (need to find)
4. `fetch_portfolio()` — Line ~109
5. `fetch_recent_trades()` — Line ~??
6. `fetch_sector_ranking()` — Line ~??
7. `fetch_health()` — Line ~??
8. `fetch_economic_pulse()` — Line ~??
9. `fetch_algo_metrics()` — Line ~??
10. `fetch_notifications()` — Line ~??
11. `fetch_sentiment()` — Line ~??
12. `fetch_economic_calendar()` — Line ~??
13. `fetch_risk_metrics()` — Line ~??
14. `fetch_perf_analytics()` — Line ~??
15. `fetch_signal_eval()` — Line ~??
16. `fetch_sector_rotation()` — Line ~??
17. `fetch_industry_ranking()` — Line ~??
18. `fetch_exec_history()` — Line ~??
19. `fetch_audit_log()` — Line ~??
20. `fetch_circuit()` — Line ~??
21. `fetch_activity()` — Line ~??

### Step 2: Check What API Endpoints Exist
**File:** `webapp/lambda/routes/algo.js`

**Available endpoints (from code review):**
```
GET /api/algo/status                  ✅
GET /api/algo/evaluate                ✅
GET /api/algo/last-run                ✅
GET /api/algo/positions               ✅
GET /api/algo/portfolio               ✅
GET /api/algo/portfolio-summary       ✅
GET /api/algo/trades                  ✅
GET /api/algo/config                  ✅
GET /api/algo/markets                 ✅
GET /api/algo/swing-scores            ✅
GET /api/algo/swing-scores-history    ✅
GET /api/algo/data-status             ✅
GET /api/algo/exposure-policy         ✅
GET /api/algo/notifications           ✅
GET /api/algo/patrol-log              ✅
POST /api/algo/run                    ✅
POST /api/algo/patrol                 ✅
POST /api/algo/simulate               ✅
```

**Missing endpoints (need to verify or create):**
- Health data → Check if via `/api/algo/status` or separate endpoint
- Economic data → Check if separate endpoint needed
- Risk metrics → Check if separate endpoint needed
- Performance analytics → Check if separate endpoint needed
- Signal evaluation → Check if via `/api/algo/evaluate`
- Sector rotation → Check if separate endpoint needed
- Industry ranking → Check if separate endpoint needed
- Execution history → Check if separate endpoint needed
- Audit log → Check if separate endpoint needed
- Circuit breaker → Check if separate endpoint needed
- Activity log → Check if separate endpoint needed

### Step 3: Pattern for Converting Each Fetcher

**OLD PATTERN (DB fallback):**
```python
def fetch_perf(c):
    """Fetch performance from DB with fallback."""
    try:
        # Try API first
        data = api_call('/api/algo/performance')
        if data.get('_error'):
            # DB fallback
            db = get_db_connection()
            cursor = db.cursor()
            cursor.execute('''
                SELECT ... FROM performance_table
            ''')
            return transform_db_result(cursor.fetchall())
    except Exception:
        return {"_error": str(e), ...defaults...}
```

**NEW PATTERN (API-only):**
```python
def fetch_perf(c):
    """API-only performance data (no local fallback)."""
    try:
        data = api_call('/api/algo/performance')
        if data.get('_error'):
            return {
                "_error": data.get('_error'),
                "n": 0, "w": 0, "l": 0, "wr": 0, "pnl": 0, "streak": 0,
                "sharpe": 0, "maxdd": 0, "avg_win": 0, "avg_loss": 0,
                "profit_factor": 0, "expectancy": 0, "avg_r": 0,
                "equity_vals": [], "recent_rets": []
            }
        perf = data.get('data', {})
        if "_error" in perf or not perf:
            return {"_error": "Performance data unavailable", ...defaults...}
        return {
            "n": safe_int(perf.get("total_trades")),
            "w": safe_int(perf.get("winning_trades")),
            "l": safe_int(perf.get("losing_trades")),
            # ... rest of fields mapped from API response
        }
    except Exception as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        return {"_error": str(e), ...defaults...}
```

**Key differences:**
1. ❌ Remove all `get_db_connection()` calls
2. ❌ Remove all `db.cursor()` / `pool.query()` for DB
3. ✅ Keep `api_call()` as sole data source
4. ✅ Map API response fields → expected output structure
5. ✅ Return error dict with all required fields (for consistent handling)

### Step 4: Verify No Remaining DB Code
**After converting all fetchers, check:**

```bash
grep -r "get_db_connection\|db\.cursor\|pool\.query" tools/dashboard/
# Should return: 0 results
```

### Step 5: Remove Database Connection Code
**Files to clean up:**
- Remove `get_db_connection()` from any utility file
- Remove database import statements
- Remove database connection constants
- Keep API-only imports

---

## E8 & E9: Externalize Hardcoded Configuration

### E8: MIN_QUALITY_SCORE Hardcoded

**Find the hardcoded value:**
```bash
grep -n "MIN_QUALITY_SCORE\|min_quality_score" tools/dashboard/
```

**Current code (estimated line ~2026):**
```python
MIN_QUALITY_SCORE = 70  # Hardcoded threshold
```

**Step 1: Add to algo_config table (if not already there)**
```sql
-- Check if exists
SELECT * FROM algo_config WHERE key = 'min_signal_quality_score';

-- If not exists, insert:
INSERT INTO algo_config (key, value, value_type, description)
VALUES (
    'min_signal_quality_score',
    '70',
    'int',
    'Minimum signal quality score for dashboard display'
);
```

**Step 2: Update fetchers to load from config**

In `fetch_algo_config()`:
```python
def fetch_algo_config(c):
    """AWS-only algo configuration."""
    try:
        data = api_call('/api/algo/config')
        if data.get('_error'):
            return {
                "_error": data.get('_error'),
                "enabled": False,
                "mode": "unknown",
                "min_quality_score": 70,  # Fallback default
                # ... other fields
            }
        cfg = data.get('data', {})
        if "_error" in cfg:
            return {
                "_error": cfg["_error"],
                "enabled": False,
                "min_quality_score": 70,  # Fallback default
                # ... other fields
            }
        return {
            "enabled": cfg.get("algo_enabled", True),
            "mode": cfg.get("trade_mode", "unknown"),
            "min_quality_score": safe_int(cfg.get("min_signal_quality_score", 70)),
            # ... other fields
        }
    except Exception as e:
        logger.error(f"fetch_algo_config: {type(e).__name__}: {e}")
        return {"_error": str(e), "enabled": False, "min_quality_score": 70, ...}
```

**Step 3: Use the config value**

In `panels.py` or wherever filtering happens:
```python
# OLD:
if signal.quality_score < 70:  # Hardcoded
    continue

# NEW:
min_score = cfg.get("min_quality_score", 70)
if signal.quality_score < min_score:
    continue
```

---

### E9: METRICS_MAX_AGE Hardcoded

**Current code (line ~36 in `utilities.py`):**
```python
METRICS_MAX_AGE = 3  # Hardcoded to 3 seconds
```

**Problem:** Too aggressive; causes false "stale" warnings

**Step 1: Make configurable**
```python
# Option A: Use environment variable
METRICS_MAX_AGE = int(os.environ.get("METRICS_MAX_AGE", "10"))

# Option B: Move to algo_config
# (Preferred if want to tune without redeployment)
```

**Step 2: If using algo_config**
```sql
INSERT INTO algo_config (key, value, value_type, description)
VALUES (
    'dashboard_metrics_max_age_seconds',
    '10',
    'int',
    'Maximum age for dashboard metrics to be considered fresh'
);
```

Then load in `utilities.py`:
```python
# Load from config at startup
config = api_call('/api/algo/config')
cfg = config.get('data', {})
METRICS_MAX_AGE = safe_int(cfg.get('dashboard_metrics_max_age_seconds', 10))
```

---

## E10: Win Rate Includes Open Trades

### Current Problem
```python
# Counts only closed trades
win_rate = winning_trades / total_trades
# If 10 closed trades, all wins: 100% win rate
# But 5 open positions with -$50k unrealized loss: IGNORED
```

### Solution: Include Open Positions

**Step 1: Identify where win rate calculated**
```bash
grep -n "win_rate\|winning_trades" tools/dashboard/fetchers.py
```

**Step 2: Update calculation logic**

**Approach A: Calculate in API (recommended)**

In `webapp/lambda/routes/algo.js` `/api/algo/performance` endpoint:
```javascript
router.get('/performance', async (req, res) => {
  try {
    // Fetch closed trades
    const closedTradesResult = await pool.query(`
      SELECT 
        COUNT(*) as total_trades,
        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as winning_trades,
        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losing_trades
      FROM algo_trades
      WHERE status = 'closed'
    `);
    
    // Fetch open positions
    const openResult = await pool.query(`
      SELECT
        COUNT(*) as open_count,
        COUNT(*) FILTER (WHERE unrealized_pnl > 0) as open_wins,
        COUNT(*) FILTER (WHERE unrealized_pnl < 0) as open_losses,
        SUM(unrealized_pnl) as total_unrealized_pnl
      FROM algo_positions
      WHERE status IN ('open', 'partially_closed')
    `);
    
    const closed = closedTradesResult.rows[0];
    const open = openResult.rows[0];
    
    // Calculate win rate including open positions
    const totalTrades = closed.total_trades + open.open_count;
    const totalWins = closed.winning_trades + open.open_wins;
    const win_rate = totalTrades > 0 ? (totalWins / totalTrades * 100).toFixed(2) : 0;
    
    return sendSuccess(res, {
      total_trades: totalTrades,
      closed_trades: closed.total_trades,
      open_positions: open.open_count,
      winning_trades: totalWins,
      closed_wins: closed.winning_trades,
      open_wins: open.open_wins,
      losing_trades: closed.losing_trades + open.open_losses,
      win_rate: parseFloat(win_rate),
      unrealized_pnl: open.total_unrealized_pnl || 0,
      // ... other fields
    });
  } catch (error) {
    logger.error('Error in /algo/performance:', error);
    return sendDatabaseError(res, error, 'Failed to fetch performance');
  }
});
```

**Approach B: Calculate in dashboard (if API not available)**

In `fetchers.py`:
```python
def fetch_perf(c):
    """Include open positions in win rate calculation."""
    try:
        perf = api_call('/api/algo/performance')
        if perf.get('_error'):
            return {
                "_error": perf.get('_error'),
                "n": 0, "w": 0, "l": 0, "wr": 0, ...
            }
        
        data = perf.get('data', {})
        
        # Fetch open positions for inclusion
        pos_data = api_call('/api/algo/positions')
        if not pos_data.get('_error'):
            positions = pos_data.get('items', [])
            open_wins = sum(1 for p in positions if p.get('unrealized_pnl', 0) > 0)
            open_losses = sum(1 for p in positions if p.get('unrealized_pnl', 0) < 0)
            open_count = len(positions)
            
            closed_wins = safe_int(data.get('winning_trades', 0))
            closed_losses = safe_int(data.get('losing_trades', 0))
            
            total_trades = closed_wins + closed_losses + open_count
            total_wins = closed_wins + open_wins
            
            wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
        else:
            # Fallback: use only closed trades
            wr = safe_float(data.get('win_rate', 0))
        
        return {
            "n": safe_int(data.get('total_trades', 0)) + open_count,
            "w": total_wins,
            "l": safe_int(data.get('losing_trades', 0)) + open_losses,
            "wr": wr,
            # ... rest of fields
        }
    except Exception as e:
        logger.error(f"fetch_perf: {type(e).__name__}: {e}")
        return {"_error": str(e), ...}
```

**Step 3: Update display in panels**

In `panels.py` performance display:
```python
# OLD:
wr_color = "bright_green" if perf.get("wr", 0) > 80 else "green"
wr_text = f"[{wr_color}]{perf.get('wr', 0):.1f}%[/] win"

# NEW (make transparent about open trades):
wr = perf.get("wr", 0)
open_count = perf.get("open_count", 0)
wr_color = "bright_green" if wr > 80 else "green"

if open_count > 0:
    wr_text = f"[{wr_color}]{wr:.1f}%[/] ({open_count} open)"
else:
    wr_text = f"[{wr_color}]{wr:.1f}%[/] win"
```

---

## E5: Sector Aggregation Cache (PARTIAL FIX)

### Current Problem
```python
_sector_agg_cache = OrderedDict()

def compute_sector_agg(pos, port):
    # Cache key uses object identity (breaks on recreation)
    cache_key = id(pos)
    if cache_key in _sector_agg_cache:
        return _sector_agg_cache[cache_key]
    
    # Compute aggregation (expensive O(n) operation)
    result = {}
    for p in pos:
        sector = p.get("sector", "Unknown")
        if sector not in result:
            result[sector] = {"count": 0, "value": 0}
        result[sector]["count"] += 1
        result[sector]["value"] += p.get("position_value", 0)
    
    # Cache with broken key
    _sector_agg_cache[cache_key] = result
    return result
```

### Solution: Better Cache Strategy

**Option A: Content-based hashing (simple fix)**
```python
import hashlib

def compute_sector_agg(pos, port):
    """Use content hash instead of object identity for caching."""
    
    # Create content hash of positions
    positions_json = json.dumps(
        [p.get("sector") for p in (pos or [])],
        sort_keys=True
    )
    cache_key = hashlib.md5(positions_json.encode()).hexdigest()
    
    # Check cache
    if cache_key in _sector_agg_cache:
        return _sector_agg_cache[cache_key]
    
    # Compute aggregation
    result = {}
    for p in pos:
        sector = p.get("sector", "Unknown")
        if sector not in result:
            result[sector] = {"count": 0, "value": 0, "alloc_pct": 0}
        result[sector]["count"] += 1
        result[sector]["value"] += p.get("position_value", 0)
    
    # Calculate allocation percentages
    total = sum(s["value"] for s in result.values())
    if total > 0:
        for sector in result:
            result[sector]["alloc_pct"] = (result[sector]["value"] / total * 100)
    
    # Cache with content key
    if len(_sector_agg_cache) >= _sector_cache_maxsize:
        _sector_agg_cache.popitem(last=False)  # Remove oldest
    _sector_agg_cache[cache_key] = result
    
    return result
```

**Option B: Move to API (best solution)**

Create `/api/algo/sector-summary` endpoint:
```javascript
router.get('/sector-summary', async (req, res) => {
  try {
    ensureConnection();
    const pool = getPool();
    
    const result = await pool.query(`
      SELECT 
        sector,
        COUNT(*) as position_count,
        SUM(position_value) as total_value_dollars,
        SUM(position_value) / NULLIF(
          SUM(position_value) OVER (), 0
        ) * 100 as allocation_pct,
        SUM(unrealized_pnl) as total_unrealized_pnl,
        SUM(unrealized_pnl) / NULLIF(
          SUM(unrealized_pnl) OVER (), 0
        ) * 100 as allocation_pct_pnl
      FROM algo_positions
      WHERE status IN ('open', 'partially_closed')
      GROUP BY sector
      ORDER BY allocation_pct DESC
    `);
    
    return sendSuccess(res, {
      sectors: result.rows.map(r => ({
        name: r.sector,
        position_count: r.position_count,
        total_value: r.total_value_dollars,
        allocation_pct: r.allocation_pct,
        unrealized_pnl: r.total_unrealized_pnl,
      }))
    });
  } catch (error) {
    logger.error('Error in /algo/sector-summary:', error);
    return sendDatabaseError(res, error, 'Failed to fetch sector summary');
  }
});
```

Then in dashboard:
```python
def fetch_sector_summary(c):
    """Fetch pre-computed sector aggregation from API."""
    try:
        data = api_call('/api/algo/sector-summary')
        if data.get('_error'):
            return {"_error": data.get('_error'), "items": []}
        return {"items": data.get('sectors', [])}
    except Exception as e:
        logger.error(f"fetch_sector_summary: {e}")
        return {"_error": str(e), "items": []}
```

**Recommendation:** Option B is best (moves calculation to API, removes from dashboard entirely)

---

## Implementation Checklist

### Phase 1: Resolve Git State (30 minutes)
- [ ] Check git status for staged vs working conflicts
- [ ] Decide which version is authoritative
- [ ] Commit or reset appropriately
- [ ] Verify clean working tree

### Phase 2: Complete E1 (1-2 hours)
- [ ] Identify all remaining DB fallback code
- [ ] Verify all required API endpoints exist
- [ ] Convert each fetcher to API-only pattern
- [ ] Remove all database connection code
- [ ] Test: `grep "get_db_connection\|db.cursor" tools/dashboard/` returns 0

### Phase 3: E8 & E9 (1 hour)
- [ ] E8: Add `min_signal_quality_score` to algo_config
- [ ] E8: Update `fetch_algo_config()` to load it
- [ ] E8: Use config value in filtering code
- [ ] E9: Move METRICS_MAX_AGE to environment or config
- [ ] Test: Configuration tunable without code changes

### Phase 4: E10 (1 hour)
- [ ] Update API endpoint to include open positions
- [ ] OR update dashboard calculation to include opens
- [ ] Update display to show open/closed breakdown
- [ ] Test: Win rate reflects open + closed trades

### Phase 5: E5 Optional (30 minutes - 1 hour)
- [ ] Option A: Fix cache key to use content hash
- [ ] Option B: Create `/api/algo/sector-summary` endpoint
- [ ] Test: Sector aggregation works correctly

### Phase 6: Test & Deploy (30 minutes)
- [ ] Run dashboard, verify no errors
- [ ] Check all panels load
- [ ] Verify configuration is tunable
- [ ] Check logs for fallback usage
- [ ] Deploy to production

---

**Total Implementation Time: 4-6 hours**

