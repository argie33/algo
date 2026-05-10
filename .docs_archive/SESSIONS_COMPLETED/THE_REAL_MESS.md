# The Real Mess — Inventory Confusion

## What We SHOULD Have

Per DATA_LOADING.md:
- **41 official loaders** (Phases 1-10)
- **20 algo-required supplementary loaders**
- **Total: 61 loaders**

Each should use the **generic `Dockerfile.loader`** with a build arg specifying which loader to run.

---

## What We ACTUALLY Have

```
Files on disk:        64 load*.py files
Dockerfiles:          78 Dockerfile* files (individual per loader + generics + duplicates)
CloudFormation:       12 template-*.yml files
Helpers/Base classes: 4+ (optimal_loader.py, watermark_loader.py, bloom_dedup.py, data_source_router.py, etc)
```

### The Discrepancy

**Expected:** 61 loaders (41 official + 20 supplementary)  
**Actual:** 64 loaders on disk

**Extra 3 loaders not in DATA_LOADING.md:**
- `loadearningsestimates.py` — Is this `loadearningsrevisions.py`? Duplicate?
- Maybe others due to inconsistent naming (with/without `load` prefix)

### Dockerfile Chaos

**Expected:** 1-2 generic Dockerfiles (Dockerfile.loader for main)  
**Actual:** 78 Dockerfiles!

```
Dockerfile               (main one)
Dockerfile.loader       (generic loader)
Dockerfile.aaiidata     (per-loader, legacy)
Dockerfile.alpacaportfolio
Dockerfile.analystsentiment
... 75 more individual ones ...
```

**Why?** Historical artifact. Each loader got its own Dockerfile during early development. Now we have a generic `Dockerfile.loader` that should handle all of them, but the old individual ones still exist and are creating confusion.

### Helper Files Mixed In

Some `load*.py` files are actually **helpers**, not loaders:
- `loader_base_optimized.py` — Base class
- `loader_metrics.py` — Metrics helper
- `loader_polars_base.py` — Polars base class
- `loader_safety.py` — Safety wrappers
- `watermark_loader.py` — Watermark framework
- `bloom_dedup.py` — Dedup filter
- `data_source_router.py` — Source routing
- `sec_edgar_client.py` — EDGAR client

These aren't loaders and shouldn't be listed with loaders.

---

## What This Confusion Causes

### 1. Deployment Uncertainty
- `deploy-app-stocks.yml` has a hardcoded list of 45+ "SUPPORTED_LOADERS" 
- That list doesn't match DATA_LOADING.md's 61
- It's unclear what should actually deploy

### 2. Docker Build Complexity
- Should we use individual Dockerfiles or generic?
- 78 files = 78 opportunities for confusion
- No clear "source of truth" for which Dockerfile is canonical

### 3. Configuration Nightmare
- `template-app-ecs-tasks.yml` probably has hardcoded task definitions
- 78 Dockerfiles vs 1 generic means huge CloudFormation template
- No clear way to add a new loader

### 4. Why Data is Stale
The deploy-app-stocks.yml workflow:
1. Detects changed loaders
2. Tries to find matching Dockerfile
3. Tries to build and deploy
4. Uses Phase C/D/E infrastructure (experimental)
5. ❌ **FAILS because the whole thing is confusing**

---

## What Should Exist

### Canonical Structure

```
Loaders (61 total):
  ✅ load*.py (41 official + 20 supplementary)
  ✅ NO individual Dockerfiles per loader
  
Docker:
  ✅ Dockerfile.loader (generic, one file, uses ARG LOADER_SCRIPT)
  ✅ Dockerfile (for main API)
  ❌ DELETE all 78 individual Dockerfile.load*.py

Helpers:
  ✅ optimal_loader.py
  ✅ watermark_loader.py
  ✅ bloom_dedup.py
  ✅ data_source_router.py
  ✅ sec_edgar_client.py
  (These should NOT be in the "loaders" list)

CloudFormation:
  ✅ template-app-ecs-tasks.yml (ONE file defining all 61 task definitions)
  ❌ NOT 78 individual templates

Workflows:
  ✅ ONE clean "run-loader" mechanism
  ❌ NOT three overlapping approaches (deploy-app-stocks, manual-reload, optimize)
```

---

## The Immediate Problem

**You can't run a loader in AWS because:**

1. It's unclear which Dockerfile to use (78 options!)
2. It's unclear which loaders are "real" vs "experimental"
3. The deployment workflow is broken (Phase C/D/E confusion)
4. There's no scheduler (no EventBridge deployed)
5. Manual trigger is hardcoded and fragile (manual-reload-data.yml)

**Result:** Data is stale. Last load: 2026-05-01. Today: 2026-05-04.

---

## Path to Fix

### IMMEDIATE (this session):
1. ✅ **Identify true official loaders** (41 + 20 = 61)
2. ✅ **List what needs to be deleted** (56 extra Dockerfiles, dead workflows, etc)
3. **Plan the cleanup** (which files to delete, which to keep)

### SHORT-TERM (next steps):
1. Delete 56 excess Dockerfiles (keep only Dockerfile.loader + Dockerfile)
2. Delete dead/overlapping workflows (test-automation.yml, manual-reload-data.yml parts)
3. Fix deploy-app-stocks.yml to be simple and clear
4. Deploy EventBridge for scheduling (use template-eventbridge-scheduling.yml)
5. Test one loader end-to-end in AWS

### MEDIUM-TERM:
1. Sync DATA_LOADING.md with reality (add missing loaders or delete them)
2. Simplify CloudFormation (one template for all ECS task definitions)
3. Document "how to add a new loader" — should be one sentence: "add load*.py, nothing else"

---

## Bottom Line

**We accumulated 3+ years of AI-generated infrastructure, half-finished experiments, and overlapping approaches.**

The result: 78 Dockerfiles instead of 1, 13 workflows instead of 3, 12 CloudFormation templates instead of 4, and **no working way to actually run a loader in AWS.**

Data hasn't loaded since 2026-05-01 because nothing is running.
