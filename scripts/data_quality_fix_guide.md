# Data Quality Fix Guide - Step-by-Step Implementation

**Status**: Ready for execution  
**Audit Tool**: `scripts/data_quality_audit_runner.py`

---

## Quick Start

Run the audit to identify current issues:
```bash
python scripts/data_quality_audit_runner.py
```

Then follow the fixes below for each issue found.

---

## Fix #1: Missing FRED Series or Stale Economic Data

**If audit shows**: Missing FRED series OR data older than 7 days

### Root Causes
- FRED API unreachable (network/rate limit/key expired)
- load_economic_data.py not running on schedule
- AWS Secrets Manager not accessible

### Fix Steps

**Step 1: Verify FRED API Access**
```bash
python << 'EOF'
import os
from utils.loaders import get_api_key

key = get_api_key("algo/fred", "FRED_API_KEY", required=True)
print(f"FRED API Key configured: {bool(key)}")
print(f"Key length: {len(key) if key else 0}")

# Try to fetch a single series
from loaders.load_economic_data import fetch_from_fred
from datetime import date, timedelta

try:
    records = fetch_from_fred(key, "T10Y2Y", date.today() - timedelta(days=10), date.today())
    print(f"✅ FRED API works: fetched {len(records)} T10Y2Y records")
except Exception as e:
    print(f"❌ FRED API failed: {e}")
EOF
```

**Step 2: Verify Load Schedule**
```bash
# Check loader status
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT table_name, status, last_execution, consecutive_failures
        FROM data_loader_status
        WHERE table_name IN ('economic_data')
    """)
    for row in cur.fetchall():
        print(f"{row[0]}: {row[1]} (last run: {row[2]}, failures: {row[3]})")
EOF
```

**Step 3: If Load Failed, Restart It Manually**
```bash
# Run economic data loader directly
python loaders/load_economic_data.py

# Check if it succeeded
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext
from datetime import date

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT series_id, MAX(date) as latest, COUNT(*) as rows
        FROM economic_data
        WHERE series_id IN ('T10Y2Y', 'FEDFUNDS', 'BAMLH0A0HYM2', 'ICSA', 'DEXUSEU')
        GROUP BY series_id
    """)
    for row in cur.fetchall():
        age_days = (date.today() - row[1]).days if row[1] else None
        status = "✅" if age_days and age_days <= 5 else "❌"
        print(f"{status} {row[0]}: {row[2]} rows (latest: {row[1]}, {age_days}d old)")
EOF
```

---

## Fix #2: Dividend Data Has Duplicates or Low Coverage

**If audit shows**: Duplicate (symbol, ex_dividend_date) pairs OR coverage < 40%

### Root Causes - Duplicates
- Loader ran twice same day, both inserts succeeded
- XBRL fact appears in multiple filings (normal, should be deduplicated by loader)

### Root Causes - Low Coverage
- Loader never ran or only ran recently
- Most companies are non-dividend payers (legitimate)
- SEC XBRL data not available for all companies

### Fix Steps for Duplicates

**Step 1: Identify Duplicate Symbols**
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT symbol, ex_dividend_date, COUNT(*) as count, 
               STRING_AGG(DISTINCT declaration_date::text, ', ') as dates
        FROM dividend_data
        WHERE data_unavailable = FALSE
        GROUP BY symbol, ex_dividend_date
        HAVING COUNT(*) > 1
        LIMIT 20
    """)
    
    print("Duplicates found:")
    for row in cur.fetchall():
        print(f"  {row[0]} on {row[1]}: {row[2]} records (declared: {row[3]})")
EOF
```

**Step 2: Clean Up Duplicates (Keep Earliest Declaration)**
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext("write") as cur:
    # Delete duplicates, keeping earliest-declared ones
    cur.execute("""
        DELETE FROM dividend_data d1
        USING dividend_data d2
        WHERE d1.symbol = d2.symbol
          AND d1.ex_dividend_date = d2.ex_dividend_date
          AND d1.data_unavailable = FALSE
          AND d2.data_unavailable = FALSE
          AND d1.declaration_date > d2.declaration_date
          AND d1.id > d2.id  -- Arbitrary tie-breaker
    """)
    print(f"Cleaned up duplicate dividends")
EOF
```

**Step 3: Verify Coverage Is Reasonable**
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

# Check coverage across different market caps (S&P 500 vs Russell 3000)
with DatabaseContext("read") as cur:
    # S&P 500 constituents with dividends
    cur.execute("""
        SELECT COUNT(DISTINCT d.symbol) as sp500_with_dividends
        FROM dividend_data d
        JOIN market_constituents m ON d.symbol = m.symbol
        WHERE d.data_unavailable = FALSE
          AND m.index_name = 'S&P 500'
          AND m.is_active = TRUE
    """)
    sp500 = cur.fetchone()[0]
    
    print(f"S&P 500 companies with dividend data: {sp500}/500 = {sp500/5:.1f}%")
    # Expected: ~85-90% of S&P 500 pays dividends
    # If < 75%, consider re-running load_dividend_data.py
EOF
```

---

## Fix #3: 8-K Data is Stale or Has Duplicates

**If audit shows**: Latest 8-K > 30 days old OR duplicates found

### Root Causes - Stale
- Loader hasn't run recently
- SEC API is temporarily down
- No material events filed (unlikely if > 30 days)

### Root Causes - Duplicates
- Same filing appeared twice (accession_number bug)
- Loader ran twice same day

### Fix Steps

**Step 1: Verify Latest 8-K Filing Is Recent**
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext
from datetime import date

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT MAX(filing_date) as latest_8k,
               COUNT(DISTINCT symbol) as symbols_with_8k,
               COUNT(*) as total_records
        FROM current_reports_8k
    """)
    latest, sym_count, total = cur.fetchone()
    age = (date.today() - latest).days if latest else None
    
    print(f"Latest 8-K: {latest} ({age} days old)")
    print(f"Symbols with 8-Ks: {sym_count}")
    print(f"Total records: {total}")
    
    if age and age > 30:
        print("⚠️  Data is stale - run load_current_reports_8k.py manually")
EOF
```

**Step 2: If Data is Stale, Reload It**
```bash
# Run 8-K loader
python loaders/load_current_reports_8k.py

# Verify reload succeeded
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext
from datetime import date

with DatabaseContext("read") as cur:
    cur.execute("SELECT MAX(filing_date) FROM current_reports_8k")
    latest = cur.fetchone()[0]
    age = (date.today() - latest).days
    status = "✅" if age <= 5 else "❌"
    print(f"{status} Latest 8-K: {latest} ({age} days old)")
EOF
```

**Step 3: Clean Up Duplicates If Found**
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext("write") as cur:
    # Find and delete duplicates
    cur.execute("""
        DELETE FROM current_reports_8k d1
        USING current_reports_8k d2
        WHERE d1.symbol = d2.symbol
          AND d1.accession_number = d2.accession_number
          AND d1.id > d2.id  -- Keep first occurrence
    """)
    print("Cleaned up duplicate 8-K filings")
EOF
```

---

## Fix #4: Institutional Holdings Coverage is Low (Expected - Incremental Backfill)

**If audit shows**: < 20% coverage

### This is Normal
The 13F CUSIP→Ticker crosswalk is an incremental multi-run backfill. Coverage grows over time.

### Action: Continue Scheduled Runs
- Loader runs on schedule (check terraform)
- Crosswalk cache grows with each run
- No manual fix needed

### To Accelerate (Optional):
```bash
# Schedule additional runs
python loaders/load_institutional_holdings_13f.py  # Run #1
sleep 60
python loaders/load_institutional_holdings_13f.py  # Run #2
sleep 60
python loaders/load_institutional_holdings_13f.py  # Run #3

# Check coverage growth
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT COUNT(DISTINCT symbol) as symbols_with_holdings,
               COUNT(*) as total_records
        FROM institutional_holdings_13f
        WHERE data_unavailable = FALSE
    """)
    symbols, records = cur.fetchone()
    coverage = (symbols / 5461 * 100) if symbols else 0
    print(f"Coverage: {symbols}/5461 symbols = {coverage:.1f}%")
EOF
```

---

## Fix #5: Add Custom Series to FRED If Needed

**If audit shows**: A needed economic series is missing

### Add New FRED Series

**Step 1: Check if FRED has the series**
Visit https://fred.stlouisfed.org/docs/api/ and search for the series ID

**Step 2: Add to loader**
Edit `loaders/load_economic_data.py` lines 46-50:
```python
FRED_SERIES = [
    "T10Y2Y",  # 10Y-2Y spread (recession indicator)
    "FEDFUNDS",  # Federal Funds Rate
    "BAMLH0A0HYM2",  # High Yield OAS
    "ICSA",  # Initial Claims
    "NEW_SERIES_ID",  # Add here
]
```

**Step 3: Run loader**
```bash
python loaders/load_economic_data.py
```

---

## Fix #6: Dividend Data Source Verification

**If audit shows**: Any concerns about dividend accuracy

### Validate Against Known Dividends
```bash
python << 'EOF'
import psycopg2
from utils.db.context import DatabaseContext

# Check AAPL dividends (high-profile, well-documented)
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT ex_dividend_date, dividend_per_share, declaration_date
        FROM dividend_data
        WHERE symbol = 'AAPL' AND data_unavailable = FALSE
        ORDER BY ex_dividend_date DESC
        LIMIT 10
    """)
    
    print("AAPL recent dividends:")
    for row in cur.fetchall():
        print(f"  Ex-date: {row[0]}, Per share: ${row[1]}, Declared: {row[2]}")

    # Cross-reference with known AAPL dividends:
    # 2026 Q4: $0.25/share (typical quarterly)
    # Should see pattern of ~$0.25 every quarter
EOF
```

---

## Verification Checklist

After applying fixes, run full audit again:

```bash
python scripts/data_quality_audit_runner.py
```

Expected results after all fixes:
- [ ] ✅ All FRED series present and recent (< 5 days old)
- [ ] ✅ No duplicate dividends (or cleared)
- [ ] ✅ Dividend coverage >= 40% (85% expected for S&P 500)
- [ ] ✅ No duplicate 8-K filings
- [ ] ✅ 8-K data recent (< 30 days old)
- [ ] ✅ Institutional holdings coverage incrementally improving

---

## Prevention

Add these to production monitoring:

1. **Weekly Check**: Run data quality audit
2. **Alert on Stale Data**: Any series older than 7 days
3. **Alert on Load Failures**: Any loader stuck in RUNNING state
4. **Alert on Duplicates**: Check for duplicate (symbol, date) pairs

---

## Questions?

If a loader keeps failing:
1. Check FRED/SEC API status
2. Verify AWS Secrets Manager has the right credentials
3. Check network connectivity from ECS/Lambda
4. Review loader logs for specific error message
