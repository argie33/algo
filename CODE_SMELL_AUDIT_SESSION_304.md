# Code Smell Audit - Session 304

**Goal:** Identify and address code smell patterns across the codebase.

**Date:** 2026-07-20  
**Reviewed Files:** 12 core modules (performance, health check, loaders, orchestration, scripts)

---

## Critical Smells (Fix Immediately)

### 1. ⚠️ Redundant Self-Assignments (performance.py:170-171)
**File:** `algo/reporting/performance.py:170-171`  
**Severity:** High (code noise, dead code pattern)

```python
win_count = win_count    # Line 170 - No-op assignment
loss_count = loss_count  # Line 171 - No-op assignment
```

**Impact:** Confuses readers; suggests variables are being modified when they're not.  
**Fix:** Delete lines 170-171 entirely. The tuple unpacking on lines 161-169 is sufficient.

---

### 2. ⚠️ Duplicate Database Credential Extraction (check_system_health.py)
**File:** `check_system_health.py:59-70` and `check_system_health.py:248-260`  
**Severity:** Medium (DRY violation, maintenance burden)

**Current:**
- Lines 59-70: Database credential extraction in `check_database()`
- Lines 248-260: **Exact duplicate** in `check_orchestrator()`

```python
# Lines 59-70 (check_database):
db_host = os.getenv("DB_HOST") or "localhost"
db_port = int(os.getenv("DB_PORT") or 5432)
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
if not db_user:
    raise ValueError("DB_USER environment variable not set")
if not db_password:
    raise ValueError("DB_PASSWORD environment variable not set")
if not db_name:
    raise ValueError("DB_NAME environment variable not set")

# Lines 248-260 (check_orchestrator):
# EXACT SAME CODE REPEATED
```

**Impact:** Harder to update credentials logic; risk of inconsistency.  
**Fix:** Extract to a helper function:
```python
def _get_db_credentials() -> dict[str, Any]:
    """Get database credentials, fail-fast on missing required env vars."""
    db_host = os.getenv("DB_HOST") or "localhost"
    db_port = int(os.getenv("DB_PORT") or 5432)
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")
    
    if not db_user:
        raise ValueError("DB_USER environment variable not set")
    if not db_password:
        raise ValueError("DB_PASSWORD environment variable not set")
    if not db_name:
        raise ValueError("DB_NAME environment variable not set")
    
    return {"host": db_host, "port": db_port, "user": db_user, 
            "password": db_password, "name": db_name}
```

Then replace both blocks with:
```python
creds = _get_db_credentials()
conn = psycopg2.connect(
    host=creds["host"],
    port=creds["port"],
    user=creds["user"],
    password=creds["password"],
    database=creds["name"],
    connect_timeout=5,
)
```

---

### 3. ⚠️ Convoluted Status Display Logic (check_system_health.py:359)
**File:** `check_system_health.py:359`  
**Severity:** Low (readability)

**Current:**
```python
status_display = status_icon.replace("OK", "[OK]").replace("FAIL", "[FAIL]").replace("WARN", "[WARN]")
```

**Problem:** Replaces the whole string multiple times inefficiently.

**Fix:**
```python
status_map = {"OK": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "unknown": "[?]"}
status_display = status_map.get(status_icon, status_icon)
```

---

## High-Priority Smells (Should Fix)

### 4. ⚠️ Inefficient Trading Day Loop with Magic Constant (check_system_health.py:152-156)
**File:** `check_system_health.py:152-156`  
**Severity:** High (inefficiency + magic number)

```python
prev_trading_day = today - timedelta(days=1)
for _ in range(10):  # Magic constant "10" - why 10?
    if MarketCalendar.is_trading_day(prev_trading_day):
        break
    prev_trading_day -= timedelta(days=1)
```

**Problems:**
- Magic constant `10` unexplained (what if there's a 11-day holiday?)
- Linear search is inefficient; MarketCalendar likely has better methods

**Fix:** Use existing MarketCalendar methods instead:
```python
from algo.infrastructure.market_calendar import MarketCalendar

prev_trading_day = MarketCalendar.get_trading_days(
    today - timedelta(days=14), 
    today
)[-2] if len(get_trading_days(...)) >= 2 else today

# OR simpler - use get_next_trading_day backwards:
# Check if MarketCalendar has a get_previous_trading_day method
# If not, this is a design smell in MarketCalendar itself
```

---

### 5. ⚠️ Duplicate Staging Table Creation Logic (bulk_insert_manager.py:92-113)
**File:** `utils/bulk_insert_manager.py:92-113`  
**Severity:** High (DRY violation, repeated complex logic)

**Current:**
```python
try:
    cur.execute(
        psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
            psycopg2.sql.Identifier(staging),
            psycopg2.sql.Identifier(self.table_name),
        )
    )
except psycopg2.ProgrammingError as e:
    if e.pgcode == "42P07":  # relation already exists
        # ... cleanup ...
        staging = f"_stage_{self.table_name}_{unique_id}"
        cur.execute(
            psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                psycopg2.sql.Identifier(staging),
                psycopg2.sql.Identifier(self.table_name),
            )
        )  # EXACT DUPLICATE SQL
    else:
        raise
```

**Impact:** Same SQL repeated; hard to update if we change table creation logic.

**Fix:** Extract to helper method:
```python
def _create_staging_table(self, cur: Any, staging: str) -> str:
    """Create staging table, retrying with new UUID if it already exists."""
    try:
        cur.execute(
            psycopg2.sql.SQL("CREATE UNLOGGED TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                psycopg2.sql.Identifier(staging),
                psycopg2.sql.Identifier(self.table_name),
            )
        )
        return staging
    except psycopg2.ProgrammingError as e:
        if e.pgcode == "42P07":  # relation already exists
            try:
                cur.execute(psycopg2.sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    psycopg2.sql.Identifier(staging)
                ))
            except psycopg2.Error as drop_err:
                logger.warning(f"Failed to drop staging table {staging}: {drop_err}")
            
            # Retry with new UUID
            unique_id = str(uuid.uuid4()).replace("-", "")[:12]
            new_staging = f"_stage_{self.table_name}_{unique_id}"
            return self._create_staging_table(cur, new_staging)
        raise
```

Then replace the try-except block with:
```python
staging = self._create_staging_table(cur, staging)
```

---

### 6. ⚠️ Magic Constants for Timeouts and Truncation (various files)
**File:** `scripts/local_loader_scheduler.py:97`, `utils/bulk_insert_manager.py:88`  
**Severity:** Medium

**Examples:**
- Line 97: `timeout=3600` (1 hour) - hardcoded
- Line 88: `[:12]` - UUID truncation to 12 chars unexplained

**Fix:**
```python
# local_loader_scheduler.py
LOADER_TIMEOUT_SECONDS = 3600  # 1 hour - allow loaders to fetch/transform data

# bulk_insert_manager.py
STAGING_TABLE_UUID_LENGTH = 12
unique_id = str(uuid.uuid4()).replace("-", "")[:STAGING_TABLE_UUID_LENGTH]
```

---

## Medium-Priority Smells (Nice to Fix)

### 7. ⚠️ Repetitive Threshold Dictionary Structure (monitor_data_staleness.py:37-87)
**File:** `scripts/monitor_data_staleness.py:37-87`  
**Severity:** Medium (DRY violation, error-prone)

**Current:**
```python
THRESHOLDS = {
    "price_daily": {
        "fresh": 30,
        "stale": 240,
        "critical": 1440,
        "fresh_non_trading": 2880,
    },
    "technical_data_daily": {
        "fresh": 60,  # Different from price_daily!
        "stale": 240,
        "critical": 1440,
        "fresh_non_trading": 2880,
    },
    # ... repeats 10+ times
}
```

**Problems:**
- Same structure repeated for ~10 tables
- Inconsistency risk (typos, missing keys)
- Hard to understand relationships

**Fix:** Create a threshold class hierarchy:
```python
@dataclass
class Thresholds:
    fresh: int
    stale: int
    critical: int
    fresh_non_trading: int | None = None

# Define once per type
PRICE_THRESHOLDS = Thresholds(30, 240, 1440, 2880)
TECHNICAL_THRESHOLDS = Thresholds(60, 240, 1440, 2880)
SCORE_THRESHOLDS = Thresholds(240, 480, 1440)  # No non-trading variant
DAILY_THRESHOLDS = Thresholds(1440, 2160, 2880)

THRESHOLDS = {
    "price_daily": PRICE_THRESHOLDS,
    "technical_data_daily": TECHNICAL_THRESHOLDS,
    "stock_scores": SCORE_THRESHOLDS,
    "market_exposure_daily": SCORE_THRESHOLDS,
    "algo_signals": DAILY_THRESHOLDS,
    # ... etc
}
```

---

### 8. ⚠️ Generic `Any` Type Hints (performance.py:47, config parameter)
**File:** `algo/reporting/performance.py:47`  
**Severity:** Low (type safety)

```python
def __init__(self, config: Any) -> None:  # What fields does config have?
```

**Impact:** No IDE autocomplete; unclear what config should contain.

**Fix:** Create a TypedDict:
```python
class PerformanceConfig(TypedDict, total=False):
    """Configuration for LivePerformance calculations."""
    lookback_days: int
    lookback_trades: int
    risk_free_rate: float

def __init__(self, config: PerformanceConfig) -> None:
    self.config = config
```

---

### 9. ⚠️ Over-Detailed Comments (sec_statements.py:1-16, local_loader_scheduler.py:40-45)
**File:** `utils/external/sec_statements.py:1-16` and `scripts/local_loader_scheduler.py:40-45`  
**Severity:** Low (maintenance burden)

**Current (sec_statements.py):**
```python
"""
Foreign private issuers (20-F/40-F filers - ADRs like ABEV, E, AEG, ACB, IBN) report
under the IFRS taxonomy (facts["ifrs-full"]) instead of, or in addition to, us-gaap.
Many report ZERO us-gaap concepts (e.g. ABEV: 0 us-gaap, 298 ifrs-full), so extracting
only us-gaap silently drops fundamental data SEC EDGAR actually has for these filers.
[... continues for 10+ lines ...]
"""
```

**Problem:** This should be in GOVERNANCE.md, not at the top of a file. It rots and confuses readers about what the module *does* vs why it exists.

**Fix:** Move to docs; keep module docstring brief:
```python
"""SEC EDGAR financial statement extractors with IFRS fallback for foreign filers.

See GOVERNANCE.md: Foreign Private Issuer Data for background on IFRS/GAAP mapping.
"""
```

---

## Design-Level Smells (Architectural)

### 10. ⚠️ MarketCalendar Missing Reverse Lookup (check_system_health.py)
**File:** `check_system_health.py:152-156` (root cause in MarketCalendar design)  
**Severity:** Medium (API incompleteness)

**Symptom:** Code has to write a loop to find the previous trading day:
```python
for _ in range(10):
    if MarketCalendar.is_trading_day(prev_trading_day):
        break
    prev_trading_day -= timedelta(days=1)
```

**Root Cause:** `MarketCalendar` has:
- ✅ `get_next_trading_day(from_date)` 
- ❌ `get_previous_trading_day(from_date)` (missing)

**Impact:** Every caller that needs the previous trading day must write the same inefficient loop.

**Recommendation:** Add to `algo/infrastructure/market_calendar.py`:
```python
@staticmethod
def get_previous_trading_day(from_date: _date | None = None) -> _date | None:
    """Get the most recent trading day before from_date.
    
    Args:
        from_date: Date to search backwards from (default: yesterday)
        
    Returns:
        Previous trading day, or None if none found in last 14 calendar days
    """
    if from_date is None:
        from_date = date.today()
    
    search_start = from_date - timedelta(days=1)
    for offset in range(14):  # Search up to 2 weeks back
        check_date = search_start - timedelta(days=offset)
        if MarketCalendar.is_trading_day(check_date):
            return check_date
    return None
```

---

## Summary Table

| # | Smell | File | Severity | Fix Effort | Impact |
|---|-------|------|----------|-----------|--------|
| 1 | Redundant assignments | performance.py:170-171 | 🔴 | 1 min | Clarity |
| 2 | Duplicate credentials extraction | check_system_health.py | 🟠 | 5 min | Maintenance |
| 3 | Convoluted status display | check_system_health.py:359 | 🟡 | 2 min | Readability |
| 4 | Trading day loop with magic constant | check_system_health.py:152 | 🔴 | 10 min | Efficiency |
| 5 | Duplicate staging table creation | bulk_insert_manager.py:92-113 | 🔴 | 10 min | Maintainability |
| 6 | Hardcoded magic numbers | multiple | 🟡 | 5 min | Maintainability |
| 7 | Repetitive threshold dicts | monitor_data_staleness.py | 🟠 | 15 min | DRY |
| 8 | Generic `Any` types | performance.py:47 | 🟡 | 10 min | Type safety |
| 9 | Over-detailed comments | sec_statements.py, scheduler | 🟡 | 5 min | Maintainability |
| 10 | Missing MarketCalendar API | market_calendar.py | 🟠 | 5 min | Design |

**Total Estimated Fix Time:** ~70 minutes  
**Priority Order:** 1 → 2 → 4 → 5 → 3 → 6 → 7 → 10 → 8 → 9

---

## Recommendations

1. **Immediate (next session):** Fix #1, #2, #4, #5
2. **Follow-up:** Add #10 to MarketCalendar, refactor #7
3. **Documentation:** Move comments from code to GOVERNANCE.md (#9)
4. **CI:** Add linting rules for magic numbers and duplicate code detection

