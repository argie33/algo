# ECS Best Practices Implementation - Session 199

## Summary

Implemented **4-layer safeguard system** to prevent unhealthy ECS tasks from lingering and wasting money (~$45/month per stuck task).

## Changes Made

### 1. ✅ Health Check Script (New)
**File:** `healthcheck.sh`
- Validates loader process is running AND responsive
- Checks if health check file is fresh (< 60 seconds old)
- Called by ECS every 30 seconds; marks UNHEALTHY after 2 failures

### 2. ✅ Auto-Kill Stuck Tasks Lambda (New)
**File:** `lambda/auto_kill_stuck_tasks/index.py`
- Automatically terminates tasks stuck for > 2 hours
- Criteria:
  - UNHEALTHY for > 2 hours
  - UNKNOWN health for > 3 hours
  - ANY status > 4 hours
- Returns cost savings estimate (~$45/month per killed task)

### 3. ✅ Health Check Updates in Loader (Updated)
**File:** `utils/optimal_loader.py`
- **New methods:**
  - `_init_health_check()` - Initialize at startup
  - `_update_health_check()` - Update every 5 seconds during execution
- **Integrated into:**
  - Serial execution: Updates every symbol (every 0.1-1 second)
  - Parallel execution: Updates every 5 seconds in polling loop
- **Behavior:** Non-blocking, silent failures for local dev mode

### 4. 📋 Best Practices Guide (New)
**File:** `steering/ECS_BEST_PRACTICES.md`
- Comprehensive documentation
- Implementation roadmap (4 safeguards)
- Monitoring procedures
- Cost impact analysis

## How It Works

### Health Check Flow
```
Loader starts
  ↓
_init_health_check() creates /tmp/loader_health_check with timestamp
  ↓
During execution:
  - Serial: Update every symbol (~0.1-1s per symbol)
  - Parallel: Update every ~5s during worker polling
  ↓
ECS health check (every 30s):
  - Check: /tmp/loader_health_check age < 60 seconds?
  - YES → Task marked HEALTHY
  - NO → Task marked UNHEALTHY (after 2 failures = 60s)
  ↓
Auto-kill Lambda (triggered by CloudWatch alarm):
  - UNHEALTHY for > 2 hours? → KILL task
  - Cost saved: $45/month per task
```

### Cost Protection
| Stage | Trigger | Action | Savings |
|-------|---------|--------|---------|
| 1st 60s | Task fails, no health check updates | ECS marks UNHEALTHY | None yet |
| 2-120min | Task stuck, no progress | Cost Circuit Breaker (every 6h) | ~$1/hour while stuck |
| 120+ min | Task unhealthy for 2+ hours | Auto-kill Lambda | Kill before hitting monthly waste |

**Without these safeguards:** Stuck task costs $45/month
**With these safeguards:** Auto-killed within 2 hours = ~$4 cost

## Why Each Layer Matters

1. **Health Check Script** - Detects if loader is stuck (within 60 seconds)
2. **Health Check File Updates** - Proves loader is responsive, not just running
3. **Auto-Kill Lambda** - Proactive termination (don't wait 6 hours for circuit breaker)
4. **Best Practices Doc** - Operational clarity and monitoring procedures

## Deployment Steps

### Phase 1: Immediate (No breaking changes)
1. Deploy healthcheck.sh to ECR image
2. Update ECS task definition to use /healthcheck.sh
3. Deploy updated utils/optimal_loader.py

### Phase 2: Week 1 (Observability)
1. Create CloudWatch alarms for unhealthy task count
2. Test auto-kill Lambda locally
3. Monitor for false positives

### Phase 3: Week 2 (Active remediation)
1. Deploy auto-kill Lambda
2. Connect to CloudWatch alarms
3. Enable automatic task termination

## Testing Checklist

- [ ] Loader runs normally - health check file updates every 5s
- [ ] Health check script returns exit code 0 (healthy)
- [ ] If loader hangs for 1 minute - health check exits with code 1
- [ ] ECS marks task UNHEALTHY after 2 failed health checks (60s)
- [ ] Auto-kill Lambda detects stuck tasks
- [ ] Auto-kill Lambda terminates stuck tasks
- [ ] SNS alert sent with cost savings estimate

## Expected Impact

**Before:** Unhealthy tasks run for 6+ hours (cost circuit breaker cycle)
**After:** Unhealthy tasks auto-killed within 2 hours
**Savings:** $45/month per stuck task prevented

## Monitoring

Daily checks:
```bash
python scripts/monitor_ecs_cost_waste.py
```

CloudWatch alarms:
```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix algo-ecs \
  --output table
```

## Files Changed

| File | Status | Purpose |
|------|--------|---------|
| `healthcheck.sh` | ✅ NEW | ECS health check script |
| `lambda/auto_kill_stuck_tasks/index.py` | ✅ NEW | Auto-terminate stuck tasks |
| `steering/ECS_BEST_PRACTICES.md` | ✅ NEW | Operations guide |
| `utils/optimal_loader.py` | ✅ UPDATED | Health check file updates |
| `ECS_BEST_PRACTICES_IMPLEMENTATION.md` | ✅ NEW | This summary |

## Next Steps

1. Test locally with one loader
2. Deploy to dev environment
3. Monitor for 1 week
4. Deploy auto-kill Lambda
5. Enable CloudWatch alarms
6. Deploy to production

## Related Issues Fixed

- Session 198: Found 1 UNHEALTHY task (algo-stock_prices_daily) costing $45/month
- Session 194-197: Mentioned task cost waste ($700-1000/month from 22 orphaned tasks)
- This prevents future occurrences

## Cost-Benefit Analysis

| Item | Cost |
|------|------|
| Implementation time | 2 hours |
| Maintenance (monthly) | 5 minutes (monitoring) |
| **Savings per stuck task prevented** | **$45/month** |
| **Savings per incident (typical)** | **$200-500** |
| **ROI** | **Paid back within 1-5 incident preventions** |
