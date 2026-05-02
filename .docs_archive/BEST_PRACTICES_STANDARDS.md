# Best Practices Standards
### The Rules We Never Break

**Philosophy:** There is a RIGHT way and a WRONG way. We always do it RIGHT.  
**Rule:** If you're deviating from best practice, you'd better have a damn good reason.  
**Default:** When in doubt, do what's BEST - not what's easy.

---

## What "BEST" Means

### BEST = Optimal Combination Of:
```
1. SPEED         (How fast can it go?)
2. COST          (What's the minimum spend?)
3. RELIABILITY   (Will it work when we need it?)
4. SCALABILITY   (Can it grow without breaking?)
5. MAINTAINABILITY (Can we understand it in 6 months?)
```

### Never Sacrifice Reliability For Speed
### Never Sacrifice Scalability For Cost
### Always Choose Maintainable Code

---

## Data Loading Best Practices

### LOCAL DEVELOPMENT (Your Machine)

#### BEST PRACTICE #1: Always Use DatabaseHelper
```python
❌ WRONG:
conn = psycopg2.connect(...)  # Direct connection
cur.execute("INSERT INTO ...")
cur.execute("INSERT INTO ...")
conn.commit()

✓ RIGHT:
db = DatabaseHelper(config)
db.insert(table, columns, rows)
db.close()
```
**Why:** Abstraction handles S3 vs standard automatically, connection pooling, error handling

---

#### BEST PRACTICE #2: Always Batch Inserts (Minimum 1000)
```python
❌ WRONG:
for row in rows:
    insert(row)  # Individual inserts = N database roundtrips

✓ RIGHT:
for i in range(0, len(rows), 1000):
    batch = rows[i:i+1000]
    insert_batch(batch)  # Fewer roundtrips, 10-50x faster
```
**Why:** 1000-row batches = 1000x fewer database roundtrips

---

#### BEST PRACTICE #3: Always Deduplicate Before Insert
```python
❌ WRONG:
rows = fetch_all_data()
insert_all(rows)  # Some symbols might be duplicated

✓ RIGHT:
rows = fetch_all_data()
unique = deduplicate_by_symbol(rows)  # Keep latest per symbol
insert_all(unique)
```
**Why:** Prevents duplicate key errors, data integrity

---

#### BEST PRACTICE #4: Always Validate Data Before Insert
```python
❌ WRONG:
rows = fetch_from_api()
insert(rows)  # Hope the data is good

✓ RIGHT:
rows = fetch_from_api()
validate(rows)  # Check for bad data
insert(rows)  # Confidence that data is good
```
**Validation Rules:**
- Type checking (string, float, int, date)
- Range checking (prices > 0, dates reasonable)
- Key column validation (symbol not null)
- Minimum row count (don't insert partial data)

---

#### BEST PRACTICE #5: Always Handle Errors Gracefully
```python
❌ WRONG:
try:
    fetch_data()
except:
    raise  # Crash and give up

✓ RIGHT:
try:
    fetch_data()
except TransientError as e:
    retry_with_backoff()  # Try again
except PermissionError as e:
    log_error_and_skip()  # Skip this part
except Exception as e:
    raise  # Only crash on unexpected errors
```
**Error Hierarchy:**
1. Transient errors (timeout, rate limit) → Retry with backoff
2. Partial errors (some symbols failed) → Log and continue
3. Fatal errors (auth failed) → Fail the whole loader

---

#### BEST PRACTICE #6: Always Log Comprehensively
```python
❌ WRONG:
print("Loading data...")  # Vague
insert_data()
print("Done")  # No metrics

✓ RIGHT:
logger.info(f"Loading {count} rows...")
start = time.time()
insert_data()
elapsed = time.time() - start
logger.info(f"Inserted {count} rows in {elapsed:.1f}s ({count/elapsed:.0f} rows/sec)")
logger.debug(f"Memory: {memory_mb}MB, CPU: {cpu_percent}%")
```
**What To Log:**
- Progress (every 50 symbols/batches)
- Performance (time, throughput)
- Data quality (rows inserted, deduplicated, skipped)
- Errors (what failed, why, retrying?)

---

### AWS CLOUD (Production)

#### BEST PRACTICE #7: Always Use ECS Fargate (Serverless)
```
❌ WRONG: EC2 instances (you manage, costs 24/7)
❌ WRONG: Lambda (limited to 15 min timeout)

✓ RIGHT: ECS Fargate (pay per second, no size limit)
```
**Why:** Best cost/performance for batch jobs 10-60 minutes

---

#### BEST PRACTICE #8: Always Use RDS Proxy for Connections
```
❌ WRONG: Direct connection per loader
         (30+ loaders × 5 connections = 150 open)

✓ RIGHT: RDS Proxy manages connection pool
         (30+ loaders share 20 connections)
```
**Why:** Connection pooling = 5-10% faster, less resource waste

---

#### BEST PRACTICE #9: Always Use S3 For Bulk Loading
```
❌ WRONG:
for row in 1_000_000_rows:
    insert(row)  # 1M individual inserts, 60 minutes

✓ RIGHT:
write_to_csv(rows)
upload_to_s3(csv)
postgresql_copy_from_s3(csv)  # 1M rows in 30 seconds
```
**When To Use:**
- >100,000 rows → Use S3 COPY
- <100,000 rows → Use batch inserts

**Speedup:** 10-20x for bulk operations

---

#### BEST PRACTICE #10: Always Use Step Functions For Orchestration
```
❌ WRONG: Run loaders manually (error-prone, slow)
❌ WRONG: Run from local machine (intermittent)

✓ RIGHT: Step Functions (automatic, reliable, scheduled)
```
**Structure:**
```
EventBridge (Schedule) 
  ↓
Step Functions (Orchestrate)
  ├→ Stage 1: Core data (symbols, profiles)
  ├→ Stage 2: Parallel price/signals (10 concurrent)
  ├→ Stage 3: Earnings/financial (API work)
  └→ Verify: Data quality check
```

**Why:** No manual intervention, automatic retry, complete visibility

---

#### BEST PRACTICE #11: Always Use CloudWatch Logs
```
❌ WRONG: Log to files (not accessible from cloud)
❌ WRONG: Print to stdout only (lost when task stops)

✓ RIGHT: Log to CloudWatch (always accessible, searchable)
```
**Implementation:**
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Also to CloudWatch
    ]
)
```

---

#### BEST PRACTICE #12: Always Monitor Data Freshness
```
❌ WRONG: No monitoring (data can be stale for weeks)

✓ RIGHT: Hourly freshness check + alert if >1 day old
```
**Implementation:**
```
CloudWatch Event (Hourly)
  ↓
Lambda: check_data_freshness()
  ↓
SNS Alert: If data >1 day old
```

**What to check:**
- price_daily < 1 day old
- buy_sell_daily < 1 day old
- earnings < 7 days old
- stock_scores < 1 day old

---

### NEVER DEVIATE (Unless You Have A Signed Waiver)

#### NEVER #1: Never Ignore Errors
```
❌ NEVER:
try:
    something()
except:
    pass  # Silently ignore
```
**Why:** Silent failures hide problems for weeks

**Exception:** Only for optional/non-critical operations

---

#### NEVER #2: Never Skip Data Validation
```
❌ NEVER:
rows = fetch_from_untrustworthy_api()
insert_directly(rows)  # What if data is garbage?
```
**Why:** Bad data propagates, corrupts database

**Exception:** Only for data you generate/trust 100%

---

#### NEVER #3: Never Run Loaders Manually in Production
```
❌ NEVER:
aws ecs run-task ...  # Manual one-off execution
```
**Why:** Unreliable, no logging, no retry, human error

**When Acceptable:** Local testing only, never production

---

#### NEVER #4: Never Use Hardcoded Credentials
```
❌ NEVER:
DB_PASSWORD = "password123"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
```
**Why:** Credentials in code = security breach

**Always:** Use AWS Secrets Manager or environment variables

---

#### NEVER #5: Never Deploy Without Testing
```
❌ NEVER:
git push main
# Immediately deploy to production
# Hope it works
```
**Why:** Untested code breaks production

**Always:**
1. Test locally
2. Test in staging
3. Manual verification
4. Then deploy

---

#### NEVER #6: Never Commit Breaking Changes Without Migration
```
❌ NEVER:
Change database schema
Deploy new code
Oops, old code can't run with new schema

✓ RIGHT:
1. Deploy code that works with BOTH old and new schema
2. Run migration
3. Remove old code in next release
```
**Why:** Allows safe rollback if needed

---

## Best Practices Trade-off Matrix

### When To Deviate (And When NOT To)

```
                     LOCAL           AWS CLOUD
Speed              GOOD (fine)      BEST (must be fast)
Cost               ACCEPTABLE       BEST (minimize $)
Reliability        GOOD             BEST (must be 99.9%)
Code Complexity    SIMPLE           COMPLEX OK (if necessary)
Testing            QUICK            COMPREHENSIVE (required)
```

### Decision Framework

**If you're deviating, ask:**

1. **Is there NO other way?**
   - If yes → OK to deviate
   - If no → Do it the BEST way

2. **Will this hurt in 6 months?**
   - If yes → Don't deviate
   - If no → OK

3. **Can it be fixed later easily?**
   - If yes → OK to deviate (temporary)
   - If no → Don't deviate

4. **Would I be OK if I broke it?**
   - If yes → Risky, don't deviate
   - If no → OK to deviate

---

## Code Review Checklist (NEVER Pass Without These)

```
[ ] All errors handled (no bare except:)
[ ] All data validated (type/range/key checks)
[ ] All inserts batched (minimum 1000 rows)
[ ] All duplicates deduplicated (by unique key)
[ ] All progress logged (every 50 items)
[ ] All performance measured (time/throughput)
[ ] No hardcoded credentials
[ ] No direct database connections (use DatabaseHelper)
[ ] Tested locally with real data
[ ] Tested with edge cases (0 rows, 1 row, 1M rows)
```

**If ANY of these are missing: REJECT the PR**

---

## Documentation Standards (For Every Loader)

Every loader must document:

```python
"""
LoadXyz - Load [description]

WHAT IT DOES:
- Fetch [data source]
- Validate [what validations]
- Deduplicate [by what key]
- Insert into [table]

PERFORMANCE:
- Typical runtime: [X minutes]
- Typical throughput: [X rows/sec]
- Typical cost: $[X]

DEPENDENCIES:
- Requires: [tables/data needed first]
- Blocks: [what depends on this]

ERROR HANDLING:
- Transient errors: Retry 3x with exponential backoff
- Rate limits: Wait and retry
- Bad data: Log and skip
- Fatal errors: Fail the entire loader

MONITORING:
- Success: Logs "Inserted N rows"
- Failure: Logs error with full traceback
- Metrics: Time, throughput, memory
"""
```

---

## The Hierarchy of Rules

```
TIER 1 (NEVER BREAK):
- Security (credentials, auth)
- Reliability (error handling, validation)
- Data integrity (deduplication, validation)

TIER 2 (ALMOST NEVER BREAK):
- Performance (batching, caching)
- Scalability (architecture decisions)
- Cost (right tool for the job)

TIER 3 (CAN BREAK IF JUSTIFIED):
- Code style (consistent formatting)
- Naming conventions (clear names)
- Documentation (complete comments)
```

---

## When To Escalate

If you're considering deviating from best practices:

1. **STOP** - Don't just do it
2. **DOCUMENT** - Why you're deviating
3. **DISCUSS** - Talk to team
4. **DECIDE** - Make conscious choice
5. **IMPLEMENT** - Do it with full knowledge
6. **MONITOR** - Watch for side effects
7. **REMOVE** - Fix it properly later

---

## Measuring Adherence to Best Practices

Every week, audit:

```
Code Quality:
  ✓ Error handling
  ✓ Data validation  
  ✓ Batching
  ✓ Deduplication
  ✓ Logging

Performance:
  ✓ Within expected time
  ✓ Expected throughput
  ✓ Memory reasonable

Reliability:
  ✓ Error rate < 0.5%
  ✓ Retry working
  ✓ Monitoring active

Cost:
  ✓ Within budget
  ✓ Using optimal tool
  ✓ No unnecessary spend
```

If any check fails: **FIX IT IMMEDIATELY**

---

## Summary: The Rules

1. **Always use best practice** (don't deviate without reason)
2. **Always validate data** (before it touches database)
3. **Always batch operations** (1000+ rows at a time)
4. **Always handle errors** (gracefully, with retry)
5. **Always log progress** (so we know what's happening)
6. **Always optimize cost** (while maintaining reliability)
7. **Always test first** (locally, before deploying)
8. **Always monitor** (data freshness, error rates)
9. **Always document** (why, not what)
10. **Always improve** (find one thing better every week)

---

**THIS IS HOW WE BUILD SYSTEMS THAT LAST.**

Not quick hacks. Not "good enough." Not "it works."

**BEST. EVERY. TIME.**
