# CI/CD Pipeline — Complete Specification

## Overview

This is the institutional-grade CI/CD pipeline that separates **local development** (fast, no AWS) from **automated validation** (strict, comprehensive).

---

## Pipeline Architecture

```
DEVELOPER
   │
   ├─ Local development (fast)
   │  ├─ Edit code
   │  ├─ Run: pytest tests/unit/ -v (30 sec)
   │  ├─ Run: python algo_backtest.py (optional, 3 min)
   │  └─ Commit locally
   │
   ├─ git push origin feature/branch (no AWS required)
   │  │
   │  └─ GitHub Actions: ci-fast-gates.yml
   │     ├─ Lint + type check (30 sec)
   │     ├─ Unit tests (30 sec)
   │     └─ Edge case tests (30 sec)
   │     │
   │     └─ ✅ All pass? → Merge enabled
   │        ❌ Fails? → Fix locally, push again
   │
   ├─ git merge → main (auto-trigger workflows)
   │  │
   │  ├─ GitHub Actions: ci-backtest-regression.yml (auto-on-merge)
   │  │  ├─ Full backtest on test DB (3 min)
   │  │  ├─ Compare to reference_metrics.json
   │  │  ├─ Integration tests (1 min)
   │  │  └─ Generate coverage report
   │  │
   │  ├─ GitHub Actions: deploy-staging.yml (auto-on-merge)
   │  │  ├─ Deploy to staging environment
   │  │  ├─ Run paper trading for 1 week
   │  │  ├─ Monitor live vs backtest Sharpe
   │  │  └─ Await manual approval for production
   │  │
   │  └─ GitHub Actions: deploy-production.yml (manual approval)
   │     ├─ Deploy to production
   │     ├─ Enable live trading
   │     ├─ Arm kill switch
   │     └─ Enable auto-rollback on anomaly
   │
   └─ 24/7 monitoring
      ├─ CloudWatch metrics
      ├─ Anomaly detection
      ├─ Auto-rollback if Sharpe drops >50%
      └─ Alerts on failures
```

---

## Workflows

### 1. `ci-fast-gates.yml` — Runs on Every Push
**Trigger:** Push to main, PR to main  
**Duration:** ~2 minutes  
**Cost:** Negligible  

**Jobs:**
- `lint-and-type`: Black, isort, flake8, mypy
- `unit-tests`: Parallel test runners (3 modules)
- `edge-case-tests`: Order failures, partial fills, orphans
- `summary`: Aggregate results

**If fails:** Developer fixes locally, pushes again  
**If passes:** PR can be merged to main

**Cost per month:** ~10 minutes (free tier)

---

### 2. `ci-backtest-regression.yml` — Runs on Merge to Main Only
**Trigger:** Push to main (after merge)  
**Duration:** ~4 minutes  
**Cost:** Minimal  

**Jobs:**
- Spin up ephemeral PostgreSQL test database
- Run backtest on fixed date range (2026-01-01 to 2026-04-24)
- Compare all metrics to `reference_metrics.json`
- Validate regression within tolerance (±3-5%)
- Run integration tests
- Generate coverage report

**Metrics checked:**
- Win rate (±3%)
- Sharpe ratio (±0.3)
- Max drawdown (±5%)
- Expectancy (±0.1R)
- Profit factor (±0.25)

**If fails:** Merge reverted, regression investigated  
**If passes:** Staging deployment proceeds

**Cost per month:** ~5 minutes per merge (negligible)

---

### 3. `deploy-staging.yml` — Runs on Merge to Main
**Trigger:** Push to main (after backtest gate passes)  
**Duration:** ~5 minutes  
**Cost:** Staging infrastructure (paper trading)  

**Sequence:**
1. Deploy to staging environment (AWS)
2. Enable paper trading (Alpaca sandbox)
3. Run for minimum 1 week
4. Monitor live vs backtest metrics
5. Await manual approval for production

**Gates before production:**
- Live Sharpe ≥ 70% of backtest Sharpe
- Live win rate within ±5% of backtest
- Live max drawdown ≤ 1.5× backtest
- Zero critical errors in logs
- Execution fill rate ≥ 95%
- Average slippage ≤ 2× backtest assumption

---

### 4. `deploy-production.yml` — Manual Approval Required
**Trigger:** Manual approval via GitHub Actions environment  
**Duration:** ~5 minutes  
**Cost:** Production infrastructure (live trading)  

**Prerequisites:**
- Passed all CI gates
- 1+ week staging validation passed
- Manual code review + 2 approvals

**Deployment:**
1. Deploy to production environment (AWS)
2. Enable LIVE trading with Alpaca
3. Arm kill switch (can halt instantly)
4. Enable auto-rollback on anomaly
5. Enable 24/7 monitoring

**Post-deployment:**
- Monitor Sharpe, win-rate, drawdown hourly
- If Sharpe drops >50%: auto-rollback
- If drawdown exceeds threshold: auto-halt
- Alerts sent to trading team immediately

---

## Environment Configurations

| Env | File | Mode | Database | Alpaca | AWS |
|-----|------|------|----------|--------|-----|
| Local | `.env.development` | dry_run | mock | mock | disabled |
| Test | `.env.test` | paper | test DB | mock | disabled |
| Staging | `.env.staging` | paper | RDS staging | sandbox | enabled |
| Prod | `.env.production` | **live** | RDS prod | **live** | enabled |

---

## Gate Requirements (Mandatory)

### Before PR Merge (Fast Gates — 2 min)
- ✅ Lint passes (black, isort, flake8)
- ✅ Type check passes (mypy)
- ✅ Unit tests pass (mock DB)
- ✅ Edge case tests pass

### Before Staging Deployment (Backtest Regression — 4 min)
- ✅ Backtest Sharpe within ±0.3 of reference
- ✅ Win rate within ±3%
- ✅ Max drawdown within ±5%
- ✅ Integration tests pass
- ✅ Code coverage ≥ 80%

### Before Production Deployment (1 week staging minimum)
- ✅ Live paper Sharpe ≥ 70% of backtest
- ✅ Live win rate within ±5% of backtest
- ✅ Live max DD ≤ 1.5× backtest max DD
- ✅ Execution fill rate ≥ 95%
- ✅ Average slippage ≤ 2× backtest
- ✅ Zero CRITICAL errors in logs
- ✅ Manual trading committee approval
- ✅ Kill switch tested and functional

---

## Rollback Procedures

### Automatic Rollback (Triggered by Monitoring)
**Condition:** Sharpe ratio drops >50% in 1 hour  
**Action:**
1. Halt all new entries (kill switch activated)
2. Close all open positions at market
3. Revert code to previous stable version
4. Alert trading team immediately

**Time to rollback:** <2 minutes

### Manual Rollback (Operator Decision)
```bash
# Halt current algo
aws lambda update-function-code \
  --function-name algo-orchestrator \
  --s3-bucket prod-algo-backup \
  --s3-key algo-prev-stable.zip

# Verify rollback
aws logs tail /aws/lambda/algo-orchestrator --follow
```

### Post-Rollback Investigation
1. Review CloudWatch logs for root cause
2. Check market conditions (VIX, circuit breakers)
3. Validate data integrity
4. Run backtest on rollback period
5. Update model registry with incident details

---

## Local Development — Fast Iteration

### Get Started
```bash
# Clone repo
git clone https://github.com/argie33/algo.git
cd algo

# One-time: install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Load development environment
source .env.development
```

### Daily Workflow
```bash
# 1. Make changes
vim algo_position_sizer.py

# 2. Run fast tests locally (30 seconds)
pytest tests/unit/ -v

# 3. If tests pass, commit
git add algo_position_sizer.py
git commit -m "fix: position sizer multipliers"

# 4. Push to GitHub
git push origin fix/sizer-multipliers

# 5. CI automatically validates
# View results at: https://github.com/argie33/algo/actions

# 6. If CI passes and code review approved:
# Merge to main via GitHub UI

# 7. After merge: staging deployment auto-triggers
# 8. After 1 week staging: request production approval
```

### Optional: Backtest Locally
```bash
# Only if you have local test DB running
python algo_backtest.py --start 2026-01-01 --end 2026-04-24

# If DB unavailable, test skips gracefully
# Development doesn't block
```

---

## Metrics Dashboard (Production)

Real-time monitoring of live algorithm:

```
LIVE PERFORMANCE (Last 24h)
├─ Sharpe Ratio: 1.08 (backtest: 1.15) — ✅ 94% of backtest
├─ Win Rate: 51% (backtest: 52.5%) — ✅ Within tolerance
├─ Max Drawdown: 16% (backtest: 18.5%) — ✅ Better than backtest
├─ Avg Slippage: 1.8 bps (assumption: 2.0 bps) — ✅ Better than expected
├─ Execution Fill Rate: 98.5% — ✅ Healthy
├─ Critical Errors: 0 — ✅ Clean
└─ Kill Switch Status: ARMED — ✅ Ready

ANOMALY DETECTION (Last 1h)
├─ Price feed staleness: 0 days — ✅ Fresh
├─ Circuit breaker violations: 0 — ✅ None
├─ Order rejections: 0 — ✅ None
└─ Rollback eligibility: NO — ✅ Running normally
```

---

## CI/CD Cost Estimate

| Component | Usage | Cost |
|-----------|-------|------|
| GitHub Actions | ~50 min/month | Free (within 3000 min limit) |
| AWS Lambda | Algo orchestrator | ~$0-5/month |
| RDS (staging) | 1 week paper trading | ~$5/month |
| RDS (production) | 24/7 monitoring | $20-30/month |
| S3 | Model artifacts, logs | $1-5/month |
| CloudWatch | Monitoring, alerts | $2-5/month |
| **Total** | | **~$30-50/month** |

---

## Success Criteria

✅ **Phase 2 Complete** when:
1. All unit tests run in <1 minute locally
2. All edge case tests run in <1 minute locally
3. Backtest regression test runs in <4 minutes on merge
4. All GitHub Actions workflows defined and tested
5. Staging environment deployed and validating
6. Production deployment manual gate configured
7. Kill switch and rollback procedures tested
8. Monitoring dashboard live and alerting

---

## Next Steps (Phase 3+)

After Phase 2 is fully operational:
1. **Transaction Cost Analysis (TCA)** — measure slippage per trade
2. **Live Performance Metrics** — continuous Sharpe/win-rate from live trades
3. **Pre-Trade Hard Stops** — independent safety layer
4. **Stress Testing** — validate against crisis scenarios
5. **Model Registry** — governance + reproducibility
6. **Annual Model Review** — SR 11-7 compliance
