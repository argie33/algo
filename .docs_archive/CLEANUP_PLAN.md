# Cleanup Plan - Remove Extra/Weird Files

## Files to Remove (All These Are Extra/Broken)

### 1. Shell Scripts (Orchestration - Use CI/CD Instead)
```
AWS_DEPLOYMENT_SETUP.sh
VERIFY_ENDPOINTS.sh
deep-test-apis.sh
final-test.sh
fix-all.sh
load-all-signals-complete.sh
monitor-loader.sh
run-all-loaders.sh
run-critical-loaders.sh
run_all_loaders.sh
run_data_loaders.sh
start-stack.sh
test_all_endpoints.sh
verify-endpoints.sh
wait-for-loader.sh
```

**Why?** Data loading should be orchestrated by CI/CD workflows, not custom shell scripts. These create confusion about "the right way" to load data.

### 2. Fake JavaScript Populate Scripts
```
generate-complete-signals.js
```

**Why?** Already removed populate-all-signals.js, populate-historical-signals.js. This is the last fake one.

### 3. Extra/Duplicate Dockerfiles
All Dockerfile.loadXXX files (renamed duplicates):
```
Dockerfile.loadaaiidata
Dockerfile.loadanalystupgradedowngrade
Dockerfile.loadannualbalancesheet
Dockerfile.loadannualcashflow
Dockerfile.loadannualincomestatement
Dockerfile.loadcalendar
Dockerfile.loaddailycompanydata
Dockerfile.loadearningshistory
Dockerfile.loadearningsrevisions
Dockerfile.loadfeargreed
Dockerfile.loadfundamentalmetrics
Dockerfile.loadindustryranking
Dockerfile.loadmarket
Dockerfile.loadnaaim
Dockerfile.loadnews
Dockerfile.loadpositioningmetrics
Dockerfile.loadquarterlybalancesheet
Dockerfile.loadquarterlycashflow
Dockerfile.loadquarterlyincomestatement
Dockerfile.loadsectorranking
Dockerfile.loadsectors
Dockerfile.loadstocksymbols
Dockerfile.loadsectorranking
(and any others with "load" prefix)
```

Plus all the regular Dockerfile.XXX files that are NOT in use by CI/CD.

**Why?** The CI/CD workflow only uses Dockerfiles WITH the loader name (Dockerfile.aaiidata, not Dockerfile.loadaaiidata). These duplicates cause confusion.

### 4. Extra Python Loaders (Already Removed)
```
loadindustryranking.py
loadsectorranking.py
loadtechnicalindicators_github.py
```

---

## What Should Remain

### Proper Files to Keep

1. **39 Official Python Loaders** (From CI/CD SUPPORTED_LOADERS list)
   - See DATA_LOADING.md for complete list

2. **39 Official Dockerfiles** (One per loader, no "load" prefix)
   - Dockerfile.aaiidata
   - Dockerfile.analystsentiment
   - Dockerfile.alpacaportfolio
   - (etc - see deploy-app-stocks.yml for full list)

3. **CI/CD Workflows** (.github/workflows/)
   - deploy-app-stocks.yml (THE PROPER ORCHESTRATOR)
   - All other workflows

4. **Documentation**
   - CLAUDE.md
   - DATA_LOADING.md
   - LOADER_STATUS.md
   - This file

---

## Why This Matters

### Before Cleanup:
- 15+ shell scripts orchestrating loaders (confusion about "how")
- 53 Python loaders (should be 39)
- 66+ Dockerfiles (should be 39)
- Fake populate scripts creating bad data
- Data quality is 97.8% fake "None" signals

### After Cleanup:
- ONE official way: Use CI/CD (deploy-app-stocks.yml)
- 39 official loaders ONLY
- 39 official Dockerfiles ONLY
- Real data only, no fakes
- Clear rules documented in CLAUDE.md

---

## The Right Way Forward

### For Local Development
```bash
# Load locally using loaders directly
python3 loadstocksymbols.py
python3 loadpricedaily.py
python3 loadbuyselldaily.py
# ... (etc, Phase 1-6 from DATA_LOADING.md)

# Test locally
curl http://localhost:5174
node webapp/lambda/index.js

# Commit fixed code
git add -A
git commit -m "Fix loaders and data quality"
git push origin main
```

### For AWS Deployment
```bash
# CI/CD automatically:
# 1. Detects changed load*.py files
# 2. Triggers deploy-app-stocks.yml
# 3. Builds Docker images (one per loader)
# 4. Runs ECS tasks in proper order
# 5. Validates data
```

---

## Enforcement

**After cleanup:**
- No new shell scripts for loading data (use CI/CD)
- No new loaders without adding to DATA_LOADING.md (39-item list)
- No populate/generate scripts
- No duplicate Dockerfiles
- All data loading via OFFICIAL Python loaders only

This prevents future "sloppy loader mess".
