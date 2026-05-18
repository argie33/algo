# Stress Test Quick Start

**Comprehensive system tests in one command (~30 minutes)**

## One-Command Stress Test

```bash
# Get DB_PASSWORD from LOCAL_CRED_SETUP.md, then:
pytest tests/test_stress_comprehensive.py -v --run-db -s
```

Or with loaders + orchestrator:

```bash
# Run: database init → all 40 loaders → stress tests → orchestrator  
# Time: 30 minutes
python run-all-loaders.py
pytest tests/test_stress_comprehensive.py -v --run-db -s
python algo/algo_orchestrator.py --mode paper --dry-run
```

---

## What Gets Tested

| System | Tests | Purpose |
|--------|-------|---------|
| **40 Data Loaders** | Race conditions, completeness, freshness | No conflicts, all data loads |
| **Orchestrator 7 Phases** | All workflow steps with production data | No crashes, deadlocks, hangs |
| **Error Recovery** | Missing data, stale signals, disconnections | Graceful degradation |
| **API Endpoints** | Data completeness for REST routes | Frontend gets what it needs |
| **Database** | Query performance, indexes, locks | <500ms queries, no bottlenecks |
| **Data Integrity** | Consistency, no duplicates, valid ranges | High-quality data |

---

## Expected Results (Success)

```
✓ Stock symbols: 3,500+ loaded
✓ Price daily: 1,000,000+ records, recent
✓ Technical indicators: 100,000+ records
✓ Trading signals: 500,000+ records, current
✓ No race condition duplicates
✓ All 7 orchestrator phases pass
✓ Price queries: <500ms
✓ No data integrity issues
✓ All API endpoints have data

PASS: 80/80 tests
```

---

## If Tests Fail

The output will tell you exactly what's broken:

```
FAILED test_loader_2_prices_daily_volume
  AssertionError: Price data too old: 15 days
```

**Fix:** Run loaders to get current data:
```bash
python run-all-loaders.py
pytest tests/test_stress_comprehensive.py -v --run-db -s
```

---

## Manual Steps

```bash
# 1. Set DB credentials (see LOCAL_CRED_SETUP.md)
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
export DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id algo/db/postgres --query SecretString --output text | jq -r .password)

# 2. Initialize database (one-time)
python init_database.py

# 3. Load all data (~20 min)
python run-all-loaders.py

# 4. Run comprehensive stress tests
pytest tests/test_stress_comprehensive.py -v --run-db -s

# 5. Run orchestrator
python algo/algo_orchestrator.py --mode paper --dry-run
```

---

## Performance Targets

| Operation | Expected | Good | Bad |
|-----------|----------|------|-----|
| All loaders | 15-25 min | <30 min | >30 min |
| Stress tests | 2-5 min | <10 min | >10 min |
| Price query | <500ms | <1000ms | >1000ms |
| Portfolio query | <300ms | <500ms | >500ms |

---

## After Tests Pass

```bash
git add -A
git commit -m "test: comprehensive stress testing complete"
git push origin main  # Auto-deploys
```

Watch deployment: https://github.com/argie33/algo/actions

---

**See:** STRESS_TESTING_GUIDE.md for full documentation
