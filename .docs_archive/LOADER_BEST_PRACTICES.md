# Loader Best Practices - The ONE TRUE WAY

## Architecture Principles

Every data loader MUST follow this structure:

```python
#!/usr/bin/env python3
"""Loader Purpose - Brief description"""

import sys, logging
from datetime import datetime
from typing import List, Tuple

import psycopg2
import boto3
from db_helper import DatabaseHelper

# ============================================================================
# 1. SETUP: Logging + Config
# ============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_db_config() -> dict:
    """Get DB config from Secrets Manager OR env vars (AWS best practice)"""
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    
    if db_secret_arn:
        try:
            secret = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )
            creds = json.loads(secret["SecretString"])
            return {"host": creds["host"], "port": int(creds.get("port", 5432)), ...}
        except Exception as e:
            logger.warning(f"Secrets Manager failed: {e}")
    
    # Fallback to env vars
    return {"host": os.environ.get("DB_HOST", "localhost"), ...}

# ============================================================================
# 2. DATA FETCHING: Handle errors, retries, edge cases
# ============================================================================
def fetch_data_for_symbol(symbol: str) -> List[Tuple]:
    """
    Fetch data for ONE symbol.
    
    Returns: List of tuples matching column order for DB insert
    Errors: Return [] (empty list) - let main() decide what to do
    """
    try:
        # Your API call here (yfinance, requests, etc)
        data = api.fetch(symbol)
        
        # Transform to tuples: (col1, col2, col3, ...)
        rows = []
        for item in data:
            rows.append((symbol, item.date, item.price, ...))
        
        logger.debug(f"✓ {symbol}: {len(rows)} rows")
        return rows
        
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return []

# ============================================================================
# 3. MAIN: Orchestrate fetch + insert
# ============================================================================
def main():
    """Main execution: fetch all data, then insert once"""
    logger.info("Starting loader...")
    
    db_config = get_db_config()
    
    # Get list of items to load
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM stock_symbols")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    
    # Fetch data for all symbols (serial or parallel)
    logger.info(f"Fetching {len(symbols)} items...")
    all_rows = []
    
    # Serial (simple):
    for symbol in symbols:
        rows = fetch_data_for_symbol(symbol)
        all_rows.extend(rows)
    
    # Or parallel (faster):
    # with ThreadPoolExecutor(max_workers=5) as executor:
    #     futures = {executor.submit(fetch_data_for_symbol, s): s for s in symbols}
    #     for future in as_completed(futures):
    #         try:
    #             rows = future.result()
    #             all_rows.extend(rows)
    #         except Exception as e:
    #             logger.error(f"Task error: {e}")
    
    logger.info(f"Fetched {len(all_rows)} total rows")
    
    # NOW THE MAGIC: DatabaseHelper decides HOW to insert
    # - If USE_S3_STAGING=true AND RDS_ROLE set: Use S3 bulk load (1000x faster)
    # - Otherwise: Use standard inserts (safe, reliable)
    # Loader doesn't need to know or care!
    
    if all_rows:
        db = DatabaseHelper(db_config)
        columns = ['symbol', 'date', 'price', ...]  # Match row tuple order
        
        inserted = db.insert('table_name', columns, all_rows)
        db.close()
        
        logger.info(f"✅ Completed: {inserted} rows inserted")
        return True
    else:
        logger.warning("No data to insert")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

---

## Rules

### 1. **Never mix concerns**
- ❌ Loader should NOT know about S3, IAM roles, or CSV files
- ✅ Loader fetches data, DatabaseHelper handles insertion

### 2. **Always return empty list on errors**
- ❌ Don't raise exceptions in fetch functions
- ✅ Return [] and let main() handle it

### 3. **Use DatabaseHelper for ALL inserts**
- ❌ Don't use S3BulkInsert, S3StagingHelper, execute_values directly
- ✅ Always: `db.insert(table, columns, rows)`

### 4. **Column order MUST match tuple order**
```python
# Row tuple
(symbol, date, open_price, high, low, close, volume)

# Column list (EXACT same order)
columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']

db.insert('price_daily', columns, all_rows)
```

### 5. **Handle Secrets Manager properly**
```python
def get_db_config():
    # Try Secrets Manager first (AWS best practice)
    if AWS_REGION and DB_SECRET_ARN:
        → Load from Secrets Manager
    # Fallback to env vars (local development)
    else:
        → Load from os.environ
```

### 6. **Use appropriate parallelism**
- **Serial:** For small datasets or slow APIs (< 100 items)
- **ThreadPoolExecutor (5 workers):** For large datasets with fast APIs (1000+ items)
- **Never process all in memory at once if > 10M rows** (stream or chunk)

---

## Patterns

### Pattern 1: Simple Serial Loader
```python
for symbol in symbols:
    rows = fetch_for_symbol(symbol)
    all_rows.extend(rows)
```
**Use when:** Data source is slow or requires sequential access

### Pattern 2: Parallel Loader (Recommended for most)
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch_for_symbol, s): s for s in symbols}
    for future in as_completed(futures):
        rows = future.result()
        all_rows.extend(rows)
```
**Use when:** 100+ items AND API supports parallel requests

### Pattern 3: Streaming Loader (For huge datasets)
```python
db = DatabaseHelper(db_config)
batch = []
for symbol in symbols:
    rows = fetch_for_symbol(symbol)
    batch.extend(rows)
    
    if len(batch) >= 5000:  # Flush every 5k rows
        db.insert('table', columns, batch)
        batch = []

if batch:  # Final batch
    db.insert('table', columns, batch)
```
**Use when:** > 1M rows or memory constraints

---

## Checklist

Every loader must have:

- [ ] `get_db_config()` - Secrets Manager → env vars
- [ ] `fetch_*()` function - Returns list of tuples or []
- [ ] `main()` - Orchestrates fetch + insert
- [ ] `DatabaseHelper` for all inserts
- [ ] Proper error logging
- [ ] `if __name__ == "__main__"` block
- [ ] No S3/IAM/CSV logic in loader code
- [ ] Column order matches tuple order
- [ ] Handles empty data gracefully
