# Load Data in 2 Minutes - Complete Your System

Your API and frontend are live. Now populate the database with real data in under 2 minutes.

## Step 1: Go to AWS Console

1. Open: https://console.aws.amazon.com
2. Region: **US East (N. Virginia)**
3. Service: **Elastic Container Service** (search for "ECS")

## Step 2: Run Stock Symbols Loader (Foundation Data)

1. Click **Clusters** → **algo-cluster**
2. Click **Tasks** tab
3. Click **Run new Task**

**Fill in:**
- Launch type: **Fargate**
- Task Definition: **algo-loaders-stocksymbols-dev:1** (or latest)
- Cluster: **algo-cluster**
- Number of tasks: **1**

4. Expand **Networking** section:
   - VPC: **algo-vpc** (or select your VPC)
   - Subnets: (select private subnets)
   - Security groups: (select loader security group)
   - Public IP: **DISABLED**

5. Click **Run Task**

⏳ Wait ~5 minutes for it to complete (watch the task status)

## Step 3: Run Price Loader

When stock symbols task shows **STOPPED**, do the same for:
- Task Definition: **algo-loaders-loadpricedaily-dev:1**

⏳ Wait ~15-20 minutes

## Step 4: Check Your System

While it's running, open your frontend:
- https://d5j1h4wzrkvw7.cloudfront.net

After Tier 0-1 loads complete (~30 min total):
- ✅ Market data will appear
- ✅ Stock charts will render
- ✅ Top movers will populate
- ✅ API will return real data

---

## OR: Use CLI (If You Have AWS Configured)

```bash
# Run stock symbols loader
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-loaders-stocksymbols-dev \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=DISABLED}" \
  --region us-east-1

# After that completes, run price loader
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-loaders-loadpricedaily-dev \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=DISABLED}" \
  --region us-east-1
```

Replace subnet-xxxxx and sg-xxxxx with actual values from your VPC.

---

## What Happens After

**After 30 minutes:**
- ✅ 2000+ stock symbols loaded
- ✅ 100,000+ price records loaded  
- ✅ Indices and breadth data available
- ✅ Technical indicators calculated
- ✅ Top movers and gainers/losers displayed

**Then optional:**
- Run Tier 2 loaders (financials, earnings) - weekly data
- Run Tier 3 loaders (signals) - trading signals
- Set EventBridge to auto-run daily

---

## Verify It's Working

### 1. Check Frontend
Open: https://d5j1h4wzrkvw7.cloudfront.net
- Should show indices on Market Health page
- Charts should have data points
- Top movers list should populate

### 2. Test API
```bash
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/market/indices
```
Should return array of indices with data (not empty).

### 3. Check Logs
```bash
# Watch loader progress
aws logs tail /aws/ecs/algo-loaders --follow

# Watch API for errors
aws logs tail /aws/lambda/algo-api-dev --follow
```

---

## Timeline

| Step | Task | Duration | Status |
|------|------|----------|--------|
| 1 | Run symbols loader | ~5 min | Go now |
| 2 | Run price loader | ~15 min | After step 1 |
| 3 | Check frontend | immediate | Should see data |
| **Total** | **Ready to use** | **~30 min** | **Live** |

---

## Next (Optional)

Once you see data working:

1. **Run additional loaders** for more data:
   - Price aggregates (weekly/monthly)
   - Technical indicators
   - Earnings and financials
   - Trading signals

2. **Set up automation** (EventBridge):
   - Loaders run daily automatically
   - Algo orchestrator runs nightly
   - Alerts on failures

3. **Monitor costs**:
   - ECS tasks: ~$0.10 per run
   - RDS: ~$30/month
   - Total: ~$70/month

---

## Questions?

✓ System is deployed  
✓ API is responding  
✓ Frontend is loading  
✓ Database is ready  

**Just add data via ECS tasks above!**

After data loads, your trading platform is fully operational. 🚀
