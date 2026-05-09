# Phase 1A: Trading Strategy Validation & Infrastructure Decisions

**Date:** May 8, 2026  
**Status:** In Progress

---

## Infrastructure: Security Deferral (Identity-First Approach)

### Decision: RDS Security Hardening → Phase 2+ (Dev→Prod Transition)

**Currently:** RDS is publicly accessible (0.0.0.0/0), Lambda not in VPC.

**Why Deferred Now:**
- System is still in **development mode** (paper trading only, no real capital)
- Identity-based access boundary is sufficient interim control
- Cost/complexity of VPC hardening not justified until moving to production environments

**Current Control:**
- AWS credentials managed via `Secrets Manager`
- Access restricted to authenticated identities only
- No public schema exposure (RDS requires valid credentials)

**When to Address (Dev→Higher Env):**
1. When moving from `dev` → `staging` (pre-production)
2. When connecting real capital/live trading
3. When data contains real P&L metrics

**Planned Hardening (Later):**
- [ ] RDS moved to private subnet (no public access)
- [ ] Lambda in VPC with NAT gateway
- [ ] CloudTrail enabled for AWS API audit logging
- [ ] CloudWatch VPC Flow Logs

**Future Identity Layer (If Needed):**
- If corporate Entra/managed identities required, will be added to Terraform IaC
- AWS IAM roles for Lambda service identity (not just Secrets Manager)
- Service-to-service authentication via IAM policies

---

## Phase 1A: Foundation (This Week)

### Task 1: Backtest vs Live Performance Analysis
**File:** TBD (new analysis document)  
**Purpose:** Detect overfitting; ensure live results ≥ 90% of backtest Sharpe  
**Deliverable:** Comparison report with:
- Backtest Sharpe ratio
- Live paper trading Sharpe ratio
- Max drawdown (both)
- Win rate (both)
- Profit Factor (both)
- Gap analysis + flags if >10% divergence

### Task 2: Daily Performance Dashboard
**Files:**
- `webapp/frontend/src/pages/PerformanceMetrics.jsx` (new)
- `webapp/lambda/routes/metrics.js` (new endpoint)
- `algo_reconciliation.py` (leverage existing daily P&L calculation)

**Metrics to Display:**
- Sharpe Ratio (rolling 30/50/200 day)
- Max Drawdown (cumulative + rolling)
- Win Rate (% trades profitable)
- Calmar Ratio (return / max DD)
- Profit Factor (gross profit / gross loss)
- Trades This Week (count + breakdown by strategy)
- P&L This Week ($)

**Update Frequency:** Daily post-close (after algo runs at 5:30pm ET)

### Task 3: Earnings Blackout Filter
**File:** `algo_filter_pipeline.py`  
**Logic:**
- Before entry signal → check if stock has earnings within ±7 days
- If yes → skip entry (add to skip log with reason)
- Keep exit logic unchanged

**Data Source:** `earnings_estimates` table (populated by existing loader)

### Task 4: Documentation
**File:** This file + update `CLAUDE.md` navigation

---

## Dependencies & Order

```
Task 4 (Steering Docs)
    ↓
Task 1 (Backtest Analysis) ← informs strategy confidence
    ↓
Task 3 (Earnings Blackout) ← low-risk, isolated change
    ↓
Task 2 (Dashboard) ← visualizes Tasks 1-3 results
```

---

## Success Criteria

- [ ] Backtest vs live gap documented; if >10%, flag for review
- [ ] Earnings blackout filter deployed; logs show X signals skipped
- [ ] Dashboard live and updating daily
- [ ] All Phase 1A work in one commit (or linked PRs)

---

## Notes for Future Sessions

When moving to **Phase 2 (Trading Quality Hardening)**, priority becomes:
1. Minervini Stage 2 + RS > 70 filtering
2. Volume breakout confirmation
3. Trendline analysis

And **Phase 3 (Monitoring/Observability)**:
1. P&L leakage detection
2. Stress testing (2008/2020/2022)
3. Parameter sensitivity analysis
