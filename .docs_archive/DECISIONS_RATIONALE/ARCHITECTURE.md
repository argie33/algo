# Architecture Decision Framework

## Principle: "Only Best Things"
Every choice maximizes **business value per day of effort**.

---

## Implementation Strategy

### How We Deploy Everything
1. **Infrastructure as Code**: CloudFormation (not manual AWS console)
2. **Migrations**: Lambda custom resources in CloudFormation (not separate scripts)
3. **Automation**: GitHub Actions (not manual deployments)
4. **Local Dev**: Docker Compose (mirrors AWS architecture)

### TimescaleDB Example
```
Timeline: Enable hypertables 10-100x faster, costs $0

❌ Old approach: Run migrations.py manually
✅ New approach: 
  1. Lambda custom resource in CloudFormation
  2. Triggered during deploy-app-infrastructure workflow
  3. Runs TimescaleDB setup on RDS automatically
```

---

## Priority: High ROI Items (Week 1-2)

### 1. Multi-Source Data (Alpaca + SEC EDGAR) - Week 1
- **Impact**: 99.9% uptime vs 95% (yfinance breaks weekly)
- **Effort**: 3-5 days
- **Cost**: $0 (Polygon optional at $50/mo)
- **ROI**: Prevents daily data failures

### 2. TimescaleDB via IaC - Week 1
- **Impact**: 10-100x query speedup, 75% storage reduction
- **Effort**: 1 day (add Lambda custom resource to CloudFormation)
- **Cost**: $0
- **ROI**: Immediate speedup, zero cost

### 3. Incremental Loading (Watermarks) - Week 2
- **Impact**: 20x fewer API calls, 9x faster loads
- **Effort**: 5 days
- **Cost**: $0
- **ROI**: 88% cost reduction per load cycle

### 4. Tiered Compute (Lambda/ECS/Batch) - Week 2-3
- **Impact**: 60% cost reduction, 2x speedup
- **Effort**: 10-15 days across 49 loaders
- **Cost**: $0 (restructuring existing infrastructure)
- **ROI**: $30/month ongoing savings

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Daily load time | 90 min | <5 min |
| Load cost | $1.20/run | <$0.25/run |
| Data reliability | 95% | 99.9% |
| Query speed | Slow | 10-100x faster |

---

## What We Don't Do (Anti-Patterns)
- ❌ Manual deployments or manual database setup
- ❌ Separate migration systems (use IaC)
- ❌ Refactor UI for hypothetical features
- ❌ Over-engineer for future scale
- ❌ Leave security debt (harden as we go)
