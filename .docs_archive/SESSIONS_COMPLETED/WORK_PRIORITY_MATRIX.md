# Work Priority Matrix — Quick Decision Guide

## By Impact × Effort

### Quadrant 1: High Impact, Low Effort (DO FIRST)
Do these immediately — they give you the most value per hour.

| Work | Impact | Effort | Timeline | Owner Ready? |
|------|--------|--------|----------|------------|
| **Lock down RDS (remove 0.0.0.0/0)** | 🔴 Critical security | 1 day | Today | Yes |
| **Remove empty credential defaults** | 🔴 Critical security | 1 day | Today | Yes |
| **Create credential_manager.py** | 🟠 High (enables rotation) | 2 days | This week | Yes |
| **Enable Multi-AZ on RDS** | 🟠 High (fixes single point of failure) | 1 day | This week | Yes |
| **Disaster recovery runbook** (tested once) | 🟠 High (unblocks confidence) | 1 day | This week | Yes |
| **Basic cost tracking dashboard** | 🟡 Medium (visibility) | 1 day | This week | Yes |
| **Migrate all loaders to Secrets Manager** | 🟠 High (consistency) | 1 day | This week | Yes |
| **Audit trail query interface** | 🟡 Medium (ops visibility) | 1 day | Next week | Yes |

**Time Investment:** 9 days → **Get:** Secure, resilient, observable system

---

### Quadrant 2: High Impact, High Effort (PLAN CAREFULLY)
Worth doing but needs more time — do after Quadrant 1.

| Work | Impact | Effort | Timeline | Blocks What |
|------|--------|--------|----------|------------|
| **Move Lambda to VPC** | 🟠 High (security) | 2-3 days | Week 2 | NAT, egress filtering |
| **Structured logging + Grafana** | 🟠 High (debuggability) | 3-4 days | Week 2-3 | Root cause analysis |
| **Continuous order reconciliation** | 🟠 High (catches orphaned orders) | 2-3 days | Week 3 | Manual override interface |
| **Signal backtest integration** | 🟠 High (prevents bad deploys) | 2-3 days | Week 3 | Feature flags |
| **Metrics collection system** | 🟠 High (SLA tracking) | 2-3 days | Week 2-3 | Cost tracking |
| **Canary deployments** | 🟡 Medium (safety) | 2-3 days | Week 4 | Blue-green testing |

**Time Investment:** 16 days → **Get:** Fully observable, safe-to-deploy, catch-errors-automatically system

---

### Quadrant 3: Low Impact, Low Effort (NICE TO HAVE)
Do these to reduce operational friction.

| Work | Impact | Effort | Timeline |
|------|--------|--------|----------|
| **Log alerting rules cleanup** | 🟡 Medium (reduces noise) | 0.5 days | Whenever |
| **Documentation updates** | 🟡 Medium (onboarding) | 1 day | Week 5 |
| **Slippage tracking** | 🟡 Medium (trade quality) | 1 day | Week 4 |
| **Incident response template** | 🟡 Medium (blameless culture) | 0.5 days | Whenever |

**Time Investment:** 3 days → **Get:** Smoother operations, easier onboarding

---

### Quadrant 4: Low Impact, High Effort (SKIP FOR NOW)
Not worth doing right now — revisit if problem arises.

| Work | Why Skip | Revisit If |
|------|----------|-----------|
| **Terraform migration** (from CloudFormation) | IaC works fine as-is | Team grows >5 people or Terraform becomes org standard |
| **Prometheus + full monitoring stack** | CloudWatch + Grafana gets you 80% | You hit CloudWatch query limits |
| **Real-time WebSocket dashboard** | HTTP polling is 95% as good | Latency-sensitive (millisecond trades) |
| **Load shedding system** | System not overloaded yet | ECS tasks consistently timeout |
| **Credential rotation Lambda** | Can rotate manually | Compliance requires automatic rotation |

---

## Suggested 12-Week Execution Plan

### **Week 1: Security Lockdown (Fix Critical Risks)**
```
Mon-Tue: Lock down RDS (remove 0.0.0.0/0, enable encryption)
Wed:     Credential defaults removed + credential_manager.py created
Thu:     All loaders migrated to use credential_manager
Fri:     Disaster recovery runbook (test RDS restore once)
```
**Deliverable:** System is secure, loaders don't have empty password defaults

---

### **Week 2: Resilience & Enable Multi-AZ**
```
Mon-Tue: Enable Multi-AZ on RDS, test failover
Wed-Thu: Basic cost tracking dashboard (CloudWatch query or simple Lambda)
Fri:     AWS Secrets Manager policy review (audit what's currently stored)
```
**Deliverable:** Single points of failure eliminated, cost visibility

---

### **Week 3: Observability Phase 1 (See What's Happening)**
```
Mon-Tue: Structured logging (migrate to JSON, add trace IDs)
Wed-Thu: Prometheus client setup + basic metrics (latency, fills, loader success %)
Fri:     CloudWatch Insights queries for common debugging scenarios
```
**Deliverable:** Can search logs by trace ID, basic metrics collected

---

### **Week 4: Observability Phase 2 (Dashboards & Alerts)**
```
Mon-Tue: Grafana setup + system health dashboard
Wed:     Alert routing rules (critical → SMS, warning → email)
Thu-Fri: Audit trail query interface (web form to search trades by date/symbol)
```
**Deliverable:** Real-time visibility into system health, audit trail queryable

---

### **Week 5: Data Quality (Know Your Data)**
```
Mon-Tue: Unified DataQualityGate class, all loaders use it
Wed:     Loader SLA tracking + "failed loaders" daily report
Thu:     Signal backtest integration (before deploying signal filter)
Fri:     Buffer for testing + fixes
```
**Deliverable:** Data quality measured, loaders self-report health, signals validated

---

### **Week 6: Feature Flags (Safe Deployments)**
```
Mon-Tue: Feature flag system for signal tiers (enable/disable without deploy)
Wed-Thu: A/B testing support in signal pipeline
Fri:     Test: deploy new signal, disable old one, verify without restart
```
**Deliverable:** Can toggle signals live, safe rollback in <10 seconds

---

### **Week 7: Order Management (Full Traceability)**
```
Mon-Tue: Continuous order reconciliation (not just daily)
Wed:     Slippage tracking per symbol
Thu:     Execution audit trail (queryable: "why did we sell TSLA?")
Fri:     Manual override interface (cancel order, force sell)
```
**Deliverable:** Every trade fully audited, can manually intervene if needed

---

### **Week 8: Lambda VPC Migration (Network Security)**
```
Mon-Tue: Move Lambda to private subnets, set up NAT/VPC endpoints
Wed:     Verify outbound API calls work (Alpaca, yfinance, etc.)
Thu:     Security group rules tightened
Fri:     Load test (make sure NAT/endpoints don't bottleneck)
```
**Deliverable:** Lambda isolated, all traffic filtered through VPC endpoints

---

### **Week 9: Canary Deployments (Safe Rolling Updates)**
```
Mon-Tue: Blue-green deployment infrastructure (new code runs in parallel)
Wed:     Auto-compare: new code vs baseline code, alert on divergence
Thu-Fri: Test: deploy buggy algo code, verify auto-rollback
```
**Deliverable:** Bad deploys catch themselves before traders lose money

---

### **Week 10: Runbooks & Operations (Predictable)**
```
Mon:     Runbook: "Data gap recovery" — how to reload missing symbols
Tue:     Runbook: "Stuck order resolution" — how to manually fix orphaned orders
Wed:     Runbook: "Market halt procedure" — what happens if NYSE closes unexpectedly
Thu:     Runbook: "Emergency stop" — how to kill algo in 30 seconds
Fri:     Test each runbook once (not in prod, use staging)
```
**Deliverable:** Team can handle common failures without panic

---

### **Week 11: Incident Response & Culture**
```
Mon:     Post-mortem template + root cause analysis framework
Tue:     Blameless culture doc (how to discuss failures)
Wed-Fri: Chaos engineering (intentionally break things in staging, practice recovery)
```
**Deliverable:** Team trained on incident response, processes documented

---

### **Week 12: Final Polish & Handoff**
```
Mon-Tue: Documentation review, update outdated sections
Wed:     Runbook verification (any missing?)
Thu-Fri: Buffer for testing + late-discovery fixes
```
**Deliverable:** System ready for transfer to ops team or autonomous running

---

## Critical Path (What Must Happen First)

```
Credential Manager (W1) 
    ↓ (unblocks)
Secrets Manager Migration (W1-2)
    ↓ (unblocks)
Runbooks (W10) — can't write safe runbooks without credential mgr
    ↓
Multi-AZ + Disaster Recovery (W2) — can't test recovery without runbooks
    ↓
Canary Deployments (W9) — can't deploy safely without recovery procedures
```

**Bottom Line:** Complete Week 1-2 first, then you can parallelize Weeks 3-12.

---

## Risk If You Don't Do This Work

### Week 1-2 Not Done:
- 🔴 **Someone runs `grep` on production Lambda code** → Credentials leak
- 🔴 **RDS gets brute-forced** → Database corrupted or deleted
- 🔴 **Bad algo code deploys** → Loses all day's trades before anyone notices

### Week 3-4 Not Done:
- 🟠 **Order gets stuck** → You don't know until reconciliation runs (hours later)
- 🟠 **Data loader silently fails** → Algo trades on stale data
- 🟠 **System slowly degrades** → No visibility until it crashes

### Week 5-12 Not Done:
- 🟡 **Team keeps struggling with same issues** → Morale drops, mistakes increase
- 🟡 **New hires can't operate system** → Every change requires your involvement
- 🟡 **Auditors find compliance gaps** → Legal risk if trading real money

---

## How to Use This Matrix

1. **Pick the quadrant you're in:** Are you closer to "need security" or "need visibility"?
2. **Follow the critical path** — don't parallelize Week 1-2
3. **Weekly sync:** Update this matrix as you complete work, reprioritize as needed
4. **Budget buffer:** Add 20% time for unexpected issues (they will arise)

---

**Next:** Pick ONE task from Quadrant 1 and start today. Usually the easiest psychological start is "RDS security lockdown" because it's low-risk, high-visibility win.
