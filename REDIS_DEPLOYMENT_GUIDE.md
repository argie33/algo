# Redis ElastiCache Deployment Guide

## Quick Summary
This guide walks through deploying Redis ElastiCache to fix the pricing loader timeout issue (7.5h → 5-10 min).

**Status:** Terraform infrastructure ready, pending deployment  
**Time to deploy:** 15-20 minutes (plus 5-10 min waiting for ElastiCache cluster)  
**Risk:** Low (cache-only, safe to rollback, no data impact)

---

## Prerequisites
- AWS account access (terraform apply permissions)
- AWS CLI configured with correct region
- terraform >= 1.0

---

## Step 1: Verify Terraform Configuration

```bash
# From project root
cd terraform

# Verify the cache module exists
ls -la modules/cache/
# Expected: main.tf, variables.tf, outputs.tf

# Review what will be created
terraform plan -target=module.cache
```

Expected output should show:
- `aws_elasticache_cluster.price_cache` — Redis cluster
- `aws_elasticache_parameter_group.price_cache` — Configuration
- `aws_elasticache_subnet_group.redis_cache` — VPC placement
- `aws_security_group.redis_cache` + rules — Network access
- `aws_cloudwatch_log_group.redis_cache` — Logging

---

## Step 2: Deploy Redis Cluster

```bash
# From terraform directory
terraform apply -target=module.cache

# At prompt, review changes and type 'yes'
```

**What happens:**
- ElastiCache creates Redis cluster on t3.micro (0.5GB)
- Adds security group rules (ECS tasks → Redis port 6379)
- Creates CloudWatch log group for slow queries
- Returns Redis endpoint (e.g., `algo-price-cache-prod.abc123.ng.0001.use1.cache.amazonaws.com`)

**Wait time:** 5-10 minutes for "creating" → "available" status

---

## Step 3: Verify Cluster is Ready

```bash
# Option A: AWS CLI
aws elasticache describe-cache-clusters \
  --cache-cluster-id algo-price-cache-prod \
  --query 'CacheClusters[0].{Status,Engine,CacheNodeType,Endpoint}' \
  --region us-east-1

# Option B: AWS Console
# ElastiCache → Clusters → algo-price-cache-prod
# Status should be "available" (green)
```

Expected output:
```
{
  "Status": "available",
  "Engine": "redis",
  "CacheNodeType": "cache.t3.micro",
  "Endpoint": {
    "Address": "algo-price-cache-prod.abc123.ng.0001.use1.cache.amazonaws.com",
    "Port": 6379
  }
}
```

---

## Step 4: Deploy Updated ECS Task Definition

The `terraform apply` already updated the task definition with REDIS_URL. To force ECS to pick it up:

```bash
# Option A: Restart the stock_prices_daily ECS task (triggers new deployment)
aws ecs update-service \
  --cluster algo-cluster \
  --service algo-loader-stock-prices-daily \
  --force-new-deployment \
  --region us-east-1

# Option B: Wait for next scheduled run (2:15 AM ET or 4:05 PM ET)
```

---

## Step 5: Monitor First Loader Run

**Option 1: Real-time logs**
```bash
# Stream logs (Ctrl+C to stop)
aws logs tail /ecs/algo-cluster/stock_prices_daily --follow --region us-east-1
```

**Option 2: CloudWatch Console**
- CloudWatch → Log Groups → `/ecs/algo-cluster/stock_prices_daily`
- Filter: `PRICE_CACHE` to see cache hits

**What to look for:**
```
[PRICE_CACHE] Connected to Redis for price caching
[PRICE_CACHE] Redis hit for AAPL/1d
[PRICE_CACHE] Redis set for AAPL/1d
```

---

## Step 6: Verify Performance

After the first loader run completes:

```bash
# Check execution time
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=algo-loader-stock-prices-daily \
  --start-time 2026-07-13T02:15:00Z \
  --end-time 2026-07-13T03:00:00Z \
  --period 300 \
  --statistics Average,Maximum \
  --region us-east-1
```

**Expected results:**
- **First run (cache empty):** Still 1-2 hours (fetching all 10,676 symbols)
- **Subsequent runs (within 23h):** 5-10 minutes (cache hits 80%+)

---

## Troubleshooting

### Issue: "Redis unavailable" in logs
**Cause:** ECS task can't reach Redis cluster  
**Fix:**
```bash
# Verify security group rules
aws ec2 describe-security-groups \
  --group-ids sg-xxxxx \
  --query 'SecurityGroups[0].IpPermissions' \
  --region us-east-1

# Should show: protocol=tcp, port=6379, source=ECS task security group
```

### Issue: "Connection refused"
**Cause:** Redis cluster not yet "available" status  
**Fix:** Wait 5-10 more minutes, check cluster status again

### Issue: Loader still timing out
**Cause:** Redis.from_url() failing silently (falls back to local cache)  
**Fix:**
1. Check logs for: `[PRICE_CACHE] Redis unavailable`
2. Verify REDIS_URL env var in task definition:
   ```bash
   aws ecs describe-task-definition \
     --task-definition algo-loader-stock-prices-daily \
     --query 'taskDefinition.containerDefinitions[0].environment' \
     --region us-east-1 | grep -A 2 REDIS_URL
   ```

---

## Performance Baseline (Before → After)

| Metric | Before Redis | After (1st run) | After (2nd+ runs) |
|--------|--------------|-----------------|-------------------|
| **Execution time** | 7.5+ hours | 1-2 hours | 5-10 minutes |
| **API calls** | 11,000+ | 11,000 (cache miss) | ~1,000 (80% hits) |
| **Rate limit errors** | Many (429s) | Some | 0 |
| **Batch reduction** | 500→250→...→1 | 500→250→...→1 | None |

---

## Rollback (if needed)

```bash
# Remove Redis cluster (safe, no data loss)
terraform destroy -target=module.cache

# ECS loaders continue working (REDIS_URL will be empty string)
# Falls back to local in-memory cache (no regression)
```

---

## Post-Deployment Validation

Run this once per week to verify cache is working:

```bash
# Check Redis memory usage
aws elasticache describe-cache-clusters \
  --query 'CacheClusters[0]' \
  --region us-east-1
```

Expected:
- Memory usage: 50-100 MB (not empty, not maxed)
- Hit rate: Check CloudWatch custom metrics or loader logs

---

## Related Documentation

- `LOADER_FIX_STATUS.md` — Detailed roadmap
- `PRICING_LOADER_ANALYSIS.md` — Root cause analysis
- `steering/DATA_LOADERS.md` — Loader architecture

---

## Questions?

Check the logs:
```bash
# Redis cluster logs
aws logs tail /aws/elasticache/algo-price-cache-prod --follow --region us-east-1

# ECS loader logs
aws logs tail /ecs/algo-cluster/stock_prices_daily --follow --region us-east-1
```

Look for error patterns and debug from there.
