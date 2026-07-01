# Steering Documentation Index

**Master reference for all project documentation.** Use this to find the right guide for your task.

---

## Quick Start By Task

| Task | Document | TL;DR |
|------|----------|-------|
| **Am I on AWS or local?** | [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md) | Run verification query, see host |
| **Fix production data** | [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md#aws-production-data-fixes-critical) | Run SQL commands against algo-db |
| **Understand system architecture** | [GOVERNANCE.md](GOVERNANCE.md) | Live trading, Minervini strategy, 5 pipelines |
| **Data pipeline details** | [DATA_LOADERS.md](DATA_LOADERS.md) | 40+ loaders, 5 Step Functions, 2:15 AM & 4:05 PM ET |
| **How factor scores work** | [FACTOR_SCORES_DATA_FLOW.md](FACTOR_SCORES_DATA_FLOW.md) | Market data → metrics → loaders → scores |
| **Missing "--" factor scores?** | [DEBUG_MISSING_SCORES.md](DEBUG_MISSING_SCORES.md) | Query database, find root cause |
| **Deploy Lambda changes** | [OPERATIONS.md](OPERATIONS.md#aws-deployment-via-github-actions) | GitHub Actions workflows |
| **Run loaders locally** | [DATA_LOADERS.md](DATA_LOADERS.md) | `python3 loaders/load_*.py` |
| **Check code quality** | [LINT_POLICY.md](LINT_POLICY.md) | `make lint`, `make type-check`, pre-commit hooks |
| **Debug data flow** | [FACTOR_SCORES_DATA_VERIFICATION.md](FACTOR_SCORES_DATA_VERIFICATION.md) | Step-by-step verification queries |

---

## Document Organization

### Architecture & Governance
- **[GOVERNANCE.md](GOVERNANCE.md)** — System architecture, safety rules, data contracts, trading strategy
- **[LINT_POLICY.md](LINT_POLICY.md)** — Type checking, linting, pre-commit enforcement

### Operations & Deployment
- **[OPERATIONS.md](OPERATIONS.md)** — CI/CD pipeline, GitHub Actions, Lambda deployment, monitoring
- **[DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md)** — Database config, AWS/local selection, credentials, production fixes

### Data Flow & Loaders
- **[DATA_LOADERS.md](DATA_LOADERS.md)** — Loader orchestration, 5 pipelines, parallelism, timing
- **[FACTOR_SCORES_DATA_FLOW.md](FACTOR_SCORES_DATA_FLOW.md)** — How data flows into factor scores, verification
- **[FACTOR_SCORES_DATA_VERIFICATION.md](FACTOR_SCORES_DATA_VERIFICATION.md)** — Data verification checklist, coverage queries

### Debugging & Troubleshooting
- **[DEBUG_MISSING_SCORES.md](DEBUG_MISSING_SCORES.md)** — Why "--" appears in factor scores, diagnostic queries
- **[METRIC_LOADER_FIX_VERIFICATION.md](METRIC_LOADER_FIX_VERIFICATION.md)** — Parallelism fix, verification steps
- **[AWS_TESTING_GUIDE.md](AWS_TESTING_GUIDE.md)** — Testing perf_anl changes in AWS

### Status Reports (Historical)
- **[INFRASTRUCTURE_STATUS_2026_07_01.md](INFRASTRUCTURE_STATUS_2026_07_01.md)** — Snapshot of system state on 2026-07-01
- **[PIPELINE_EXECUTION_VERIFICATION_2026_07_01.md](PIPELINE_EXECUTION_VERIFICATION_2026_07_01.md)** — Pipeline execution verification
- **[PERF_ANL_DEPLOYMENT_STATUS.md](PERF_ANL_DEPLOYMENT_STATUS.md)** — perf_anl 503 fix status
- **[AWS_INFRASTRUCTURE_FIX_STEPS.md](AWS_INFRASTRUCTURE_FIX_STEPS.md)** — Infrastructure recovery steps

---

## Common Operations

### Running Data Loaders Locally
```bash
python3 loaders/load_stock_scores.py          # All stocks
python3 loaders/load_quality_metrics.py       # Financial metrics
python3 loaders/load_positioning_metrics.py  # Positioning data
```

**Reference:** [DATA_LOADERS.md](DATA_LOADERS.md)

### Checking Database Connection
```bash
# Verify which database you're on
python3 << 'EOF'
import sys; sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT inet_server_addr() as host, current_database() as db")
    host, db = cur.fetchone()
    print(f"{host}:{db}")
EOF
```

**Reference:** [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md#verify-which-database-youre-connected-to)

### Fixing Production Data
```bash
# See DATABASE_AND_ENVIRONMENTS.md "AWS Production Data Fixes"
psql -h algo-db.xxxxx.us-east-1.rds.amazonaws.com -U postgres -d stocks
# Then run the SQL commands listed in the guide
```

**Reference:** [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md#aws-production-data-fixes-critical)

### Deploying Lambda Changes
```bash
# GitHub Actions
gh workflow run deploy-api-lambda.yml

# Monitor
gh run list | grep deploy-api-lambda
```

**Reference:** [OPERATIONS.md](OPERATIONS.md#aws-deployment-via-github-actions)

### Clearing Dashboard Cache
```bash
pkill -9 python              # Kill dashboard
sleep 2
python -m dashboard -w       # Restart with fresh cache
```

**Why:** Dashboard caches API responses. Restart clears in-memory cache. **Note:** /api/scores endpoint is never cached (2026-07-01 fix).

---

## Critical Rules

### Data Integrity
- ✓ Always verify which database you're on before making changes
- ✓ Local changes don't reach production users
- ✓ Production changes are live immediately
- ✓ No `.env` files with secrets — use AWS Secrets Manager

### Code Quality
- ✓ All code must pass `mypy` (type checking)
- ✓ All code must pass `ruff` (linting)
- ✓ Pre-commit hooks enforce this automatically
- ✓ `make ci-local` simulates full CI pipeline

### Data Contracts
- ✓ Optional data returns explicit `data_unavailable: True` markers
- ✓ Missing critical data logged at ERROR/WARNING level
- ✓ No silent failures with empty defaults

**Full rules:** [GOVERNANCE.md](GOVERNANCE.md)

---

## When to Update Steering

Add/update steering docs when:
- ✓ You discover something that takes 5+ minutes to explain verbally
- ✓ The same question gets asked twice
- ✓ A procedure has changed
- ✓ New infrastructure or credentials added
- ✓ A debugging technique worked and should be saved

This prevents token waste and lets future work reference documented solutions.

---

## Document Maintenance

- **Check dates on status reports** — Older docs may be stale
- **Follow "Related docs" links** — Docs reference each other for context
- **When docs conflict** — Trust GOVERNANCE.md (architecture rules)
- **When you find a gap** — Fill it in steering/ before moving on

---

Last Updated: 2026-07-01
