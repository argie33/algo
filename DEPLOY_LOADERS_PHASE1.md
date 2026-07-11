# Loader Optimization Phase 1 - Deployment & Verification

**Status:** Ready to Deploy  
**Changes:** Terraform only (18 ECS task definitions)  
**Risk:** Minimal (memory/parallelism only, no logic changes)  
**Downtime:** ~5 minutes (ECS task restart)

---

## Pre-Deployment Checklist

```bash
# 1. Verify git status
git status  # Should show terraform/modules/loaders/main.tf modified

# 2. Review specific changes
git diff terraform/modules/loaders/main.tf | grep -E "^\+" | grep -E "memory|parallelism" | head -30

# Expected output (sample):
# + "value_metrics"       = { cpu = 512, memory = 512, timeout = 1800, parallelism = 1 }
# + "positioning_metrics" = { cpu = 512, memory = 512, timeout = 1800, parallelism = 1 }
# [... 16 more loader reductions ...]

# 3. Verify no parallelism=4 remains (should be empty)
grep "parallelism = 4" terraform/modules/loaders/main.tf
# If this returns nothing, you're good

# 4. Verify all loaders have memory = 512 or higher
grep "memory = 256" terraform/modules/loaders/main.tf
# Should only show market_constituents, market_health_daily, market_sentiment (these are OK)
```

---

## Deployment Steps

### Step 1: Plan the Changes
```bash
cd terraform

# See exactly what will change
terraform plan -target=module.loaders > /tmp/loader-plan.txt 2>&1

# Review the plan
cat /tmp/loader-plan.txt | grep -A 10 "aws_ecs_task_definition"

# Expected output: 18 task definitions will be updated (not destroyed/created)
# Examples:
# ~ aws_ecs_task_definition.loader["value_metrics"] will be updated in-place
# ~ aws_ecs_task_definition.loader["positioning_metrics"] will be updated in-place
# [... 16 more ...]

# Count the changes
grep "will be updated" /tmp/loader-plan.txt | wc -l
# Should show: 18
```

### Step 2: Apply the Changes
```bash
# Apply to loaders module only
terraform apply -target=module.loaders

# When prompted "Do you want to perform these actions?", type: yes

# Watch the output for:
# - aws_ecs_task_definition updates completing
# - No failures
# - Final message: "Apply complete! Resources: 0 added, 18 changed, 0 destroyed."
```

### Step 3: Verify Deployment
```bash
# Verify the changes took effect in AWS
aws ecs describe-task-definition \
  --task-definition algo-value_metrics-loader:latest \
  | jq '.taskDefinition.containerDefinitions[0] | {memory, cpu}'

# Expected output:
# {
#   "memory": 512,
#   "cpu": 512
# }

# Check parallelism in config (should match constraints)
aws dynamodb get-item \
  --table-name algo-loader-config-dev \
  --key '{"loader_name": {"S": "value_metrics"}}'

# Expected: parallelism_override = 1 (or absent, using constraint (1,1))
```

---

## Testing Phase 1 Deployment

### Test Window: Next EOD Pipeline Run

**Timing:** 4:05 PM ET today (or tomorrow if after hours)

**Monitoring Queries:**

```sql
-- 1. Monitor runtime improvement
SELECT 
  loader_name,
  COUNT(*) as runs,
  ROUND(AVG(runtime_seconds)::numeric / 60, 1) as avg_runtime_min,
  MAX(runtime_seconds) / 60 as max_runtime_min
FROM loader_execution_stats
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY loader_name
ORDER BY runtime_seconds DESC;

-- Expected improvement:
-- value_metrics: 45-50 min (was 80-100+ min)
-- positioning_metrics: 45-50 min (was 80-100+ min)
-- Others: minimal change (~5-10% improvement from reduced cascade pressure)

-- 2. Monitor data coverage (completeness)
SELECT 
  loader_name,
  ROUND(AVG(completeness_pct)::numeric, 1) as avg_coverage,
  MIN(completeness_pct) as min_coverage
FROM data_loader_status
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY loader_name
ORDER BY avg_coverage;

-- Expected improvement:
-- value_metrics: 95%+ (was 66-80% during cascades)
-- positioning_metrics: 95%+ (was 66-80% during cascades)

-- 3. Monitor memory usage (should have headroom now)
SELECT 
  loader_name,
  ROUND(MAX(memory_used_mb)::numeric, 0) as peak_memory_mb,
  512 as allocated_mb,
  ROUND(100.0 * MAX(memory_used_mb) / 512, 1) as utilization_pct
FROM loader_execution_stats
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY loader_name
HAVING MAX(memory_used_mb) > 300  -- Only show loaders with >300MB usage
ORDER BY utilization_pct DESC;

-- Expected: All <50% utilization (lots of headroom for spikes)

-- 4. Monitor for errors/timeouts (should be zero)
SELECT 
  loader_name,
  COUNT(*) as error_count,
  STRING_AGG(DISTINCT error_reason, ', ') as error_types
FROM loader_failures
WHERE created_at > NOW() - INTERVAL '1 day'
GROUP BY loader_name;

-- Expected: No new errors (same as before, possibly fewer due to cascade fix)
```

### Dashboard Checks

1. **Step Functions Execution History**
   ```bash
   aws stepfunctions describe-state-machine \
     --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:algo-eod-pipeline-dev \
     | jq '.stateMachineArn'
   
   # Then open AWS Console → Step Functions → algo-eod-pipeline-dev
   # Look for today's execution
   # Timeline should show: all loaders complete in 45-50 min (was 80-100+ min)
   ```

2. **CloudWatch Logs**
   ```bash
   # Check for rate-limit errors (should be fewer/gone)
   aws logs tail /ecs/algo-value_metrics-loader --follow
   
   # Search for: "rate limit" or "429"
   # Expected: None (or much fewer than before)
   ```

3. **Fargate Compute Cost**
   - Should see immediate 20-30% reduction in per-run Fargate cost
   - Check: AWS Billing → EC2 Container Service → Compute (Fargate)

---

## Success Criteria - Phase 1 Complete

✅ **Runtime:** 45-50 min (down from 80-100+ min)  
✅ **Data Coverage:** 95%+ for value_metrics and positioning_metrics (up from 66-80%)  
✅ **Memory Utilization:** <50% for all loaders (was 90%+ waste)  
✅ **Error Rate:** Same or lower (no new failures from changes)  
✅ **Cost:** $350-400/month savings visible in next billing cycle

---

## Rollback Plan (If Issues Occur)

If anything goes wrong, rollback is simple:

```bash
# Revert to previous version
git revert HEAD

# Re-apply terraform
terraform apply -target=module.loaders

# ECS tasks restart with old config (~5 min)
# System returns to previous state
```

---

## What Happens Next (Phase 2)

After Phase 1 verification (3-5 successful runs):

1. **Conservative Batch Sizing** (price_loader.py)
   - Different batch_size for EOD vs morning context
   - 10-15 min savings per run

2. **Parallelize Market Health Fetchers**
   - Market health has 3-4 independent sub-loaders
   - Can run in parallel instead of sequential
   - 5-10 min savings

3. **Batch Fundamental Metrics Writes**
   - Currently writes to 7 tables sequentially
   - Can write to all 7 in parallel
   - 5-10 min savings

**Phase 2 Timeline:** 1-2 weeks after Phase 1 verification  
**Phase 2 Savings:** $100-150/month + 20-30 min runtime

---

## Immediate Action Items

- [ ] Review terraform changes locally (`git diff`)
- [ ] Run `terraform plan` to verify 18 task definitions will update
- [ ] Deploy during next available window (after current trading session)
- [ ] Monitor first 3-5 runs for runtime/coverage/memory improvements
- [ ] Document baseline metrics (before/after comparison)
- [ ] Plan Phase 2 (1-2 weeks out)

---

## Questions During Deployment?

**Q: Can I deploy during trading hours?**  
A: Yes, but recommend after market close (4 PM ET+). Deployment is 5 min, tasks restart, loaders pick up next scheduled run.

**Q: Will this affect today's orchestrator run?**  
A: No, only affects loaders scheduled *after* deployment completes.

**Q: What if a loader fails with new memory allocation?**  
A: Rollback is one command (`git revert HEAD`). But based on profiling, won't happen (allocations are conservative).

**Q: How do I monitor cost savings?**  
A: AWS Billing → EC2 Container Service → Fargate. Should see 20-30% reduction per run starting tomorrow.

---

## Next: Phase 2 Quick Wins

Once Phase 1 is verified stable (3-5 runs), we proceed to:

1. **Price Loader Batch Optimization**
   - Context-aware batch sizing (EOD=50, morning=200)
   - Eliminate retry cascades in EOD context
   - Impact: 10-15 min/run

2. **Market Health Parallelization**
   - Move market health fetchers to parallel branches
   - Impact: 5-10 min/run

3. **Fundamental Metrics Batching**
   - Parallel writes to 7 tables instead of sequential
   - Impact: 5-10 min/run

See `steering/LOADER_AUDIT_2026_07_11.md` for full Phase 2-4 roadmap.
