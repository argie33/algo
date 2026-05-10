# Development Workflow — Local-First, CI-Second

## Philosophy

**You should be able to iterate rapidly locally without AWS overhead.** The CI/CD pipeline runs separately on merge to main, validating everything at scale.

### Three Environments

```
LOCAL (your machine)
  └─ Fast iteration, mocked dependencies, no AWS
     
STAGING (AWS)
  └─ Full infrastructure, paper trading validation, real DB
     
PRODUCTION (AWS)
  └─ Live trading, all circuit breakers active
```

## Local Development (Fast)

### Setup
```bash
# One-time: install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Load local development environment (disables AWS)
source .env.development
# Or Windows: Get-Content .env.development | ForEach-Object { $key, $val = $_ -split '='; $env:$key = $val }
```

### Run Tests Locally
```bash
# Fast unit tests (mocked, no DB required)
pytest tests/unit/ -v

# Fast edge case tests
pytest tests/edge_cases/ -v

# All local tests (fast)
pytest tests/ -v --ignore=tests/integration --ignore=tests/backtest
```

**Expected:** Tests run in <30 seconds on your machine. No AWS, no database required.

### Run Backtest Locally (if you have test DB)
```bash
python algo_backtest.py --start 2026-01-01 --end 2026-04-24 --capital 100000
```

If database is unavailable, test skips gracefully — development doesn't block.

### Commit & Push
```bash
git add .
git commit -m "fix: position sizer multipliers"
git push origin feature/my-feature
```

**Nothing AWS-related happens here.** Push to your feature branch freely.

---

## Continuous Integration (Strict)

### When Does CI Run?

1. **On pull request to main** — full validation, no merge without passing
2. **On merge to main** — deployment pipeline gates

### What CI Does

GitHub Actions runs (`.github/workflows/`):
- `ci-test-and-lint.yml` — lint, type check, unit tests (30 sec)
- `ci-backtest-regression.yml` — full backtest, compare to reference (3 min)
- `ci-deploy-paper.yml` — deploy to paper trading environment (1 min)

### What Gets Deployed

After **all** gates pass on main:
1. Paper trading environment (live data, paper execution)
2. Staging environment (full infrastructure, internal testing)
3. Production environment (with manual approval + kill switch)

### Gates Must Pass

Before code can merge to main:
- ✅ Lint + type check passes
- ✅ All unit tests pass
- ✅ Backtest regression within tolerance (see `tests/backtest/reference_metrics.json`)
- ✅ Edge case tests pass
- ✅ Integration tests pass

If any gate fails, CI blocks merge. Fix locally, push again.

---

## Workflow Example

### Scenario: Fix position sizer bug

```bash
# 1. Create feature branch
git checkout -b fix/sizer-multiplier

# 2. Make changes locally
# Edit algo_position_sizer.py
# Run local tests to validate
pytest tests/unit/test_position_sizer.py -v

# 3. If tests pass, commit
git add algo_position_sizer.py
git commit -m "fix: apply exposure tier multiplier correctly"

# 4. Push to GitHub
git push origin fix/sizer-multiplier

# 5. CI automatically runs on your branch
# - Lint + type check
# - All tests pass locally
# - Backtest runs on branch
# View results at: https://github.com/argie33/algo/actions

# 6. Open PR, CI gates validate, if all pass → merge to main
# After merge: staging/production pipelines run
```

---

## Environment Variables

### Local Development (.env.development)

```env
ENV=development
EXECUTION_MODE=dry_run
DB_MODE=mock                    # Use fixtures, not real DB
ALPACA_MODE=mock                # Mock Alpaca API
AWS_REGION=us-east-1            # Not used locally
LOG_LEVEL=DEBUG
```

### CI/CD Pipeline (.env.ci)

```env
ENV=ci
EXECUTION_MODE=paper            # Paper trading for validation
DB_MODE=test                     # Use test PostgreSQL instance
ALPACA_MODE=test                 # Alpaca sandbox
AWS_REGION=us-east-1
```

### Staging (.env.staging)

```env
ENV=staging
EXECUTION_MODE=paper            # Paper trading, full validation
DB_MODE=real                     # Real RDS instance
ALPACA_MODE=sandbox
AWS_REGION=us-east-1
```

### Production (.env.prod)

```env
ENV=production
EXECUTION_MODE=live             # LIVE TRADING
DB_MODE=real
ALPACA_MODE=live
AWS_REGION=us-east-1
KILL_SWITCH_ENABLED=true
```

---

## Key Principles

### ✅ DO

- Iterate locally without AWS — push often, CI validates
- Run unit tests before committing (fast feedback)
- Use `--dry-run` mode locally to test logic without live trades
- Push feature branches freely — CI gates protect main
- Commit small, focused changes

### ❌ DON'T

- Don't require AWS to run local tests
- Don't push to main without PR (CI gates protect it)
- Don't ignore failing CI checks — they catch real issues
- Don't manually deploy to production — use pipeline
- Don't commit without running local tests

---

## Troubleshooting

### Tests fail locally but passed on CI
- Different environment: Check .env.development vs CI environment variables
- Mocking differences: Unit tests mock; CI tests use real test DB
- Timing: Some tests sensitive to execution time; rerun

### CI passed but code doesn't work in staging
- CI uses mocks; staging uses real Alpaca/DB
- Check CloudWatch logs in AWS console
- Use bastion host to debug RDS connection

### Forgot to pull before pushing
```bash
git pull origin main
git merge origin/main  # resolve conflicts if any
git push origin feature/my-branch
```

---

## For Maintainers: Updating CI

To change CI behavior:
1. Edit `.github/workflows/*.yml`
2. Commit to main
3. Next CI run uses new workflow

Example: to add a new test stage, edit `ci-test-and-lint.yml`, add a step, commit.

---

## Summary

| Activity | Environment | Blocked? | Duration |
|----------|-------------|----------|----------|
| Unit tests | Local (mock DB) | No | <30 sec |
| Integration tests | Local (fixture) | No | <1 min |
| Backtest (optional) | Local (need DB) | Skip if unavailable | 2-3 min |
| Push to feature branch | GitHub | No | Instant |
| **CI runs on PR** | **GitHub + AWS** | **Yes, until gates pass** | **2-3 min** |
| **Merge to main** | **GitHub** | **Only if CI passes** | **Instant** |
| Paper/staging deploy | AWS | No (after merge) | 10 min |
| Production deploy | AWS | Requires manual approval | 5 min |

**You control local development. CI/CD protects production.**
