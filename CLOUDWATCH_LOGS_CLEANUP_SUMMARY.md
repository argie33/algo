# CloudWatch Logs Cost Reduction - Summary

## Current Situation
- **Total Storage**: 16.05 GB
- **Estimated Monthly Cost**: $0.48 storage + $8-10 ingestion = **~$10/month**
- **Main Problem**: Excessive log retention (14 days) causing high ingestion costs

## Biggest Offenders
1. `/ecs/buysellmonthly-loader` - **8.1 GB** (14-day retention)
2. `/ecs/buysellweekly-loader` - **7.7 GB** (14-day retention)
3. `/aws/lambda/stocks-websocket-stack-market-data-broadcaster` - 59 MB (NO retention)
4. `/aws/lambda/financial-dashboard-api-dev` - 42 MB (NO retention)

## Actions Taken

### 1. Updated Infrastructure as Code (IaC) Templates
All CloudFormation templates updated from 14-day to 3-day retention:

- ✅ `template-app-ecs-tasks.yml` - 36 log groups updated
- ✅ `template-webapp-lambda.yml` - 2 log groups updated
- ✅ `template-webapp-unified.yml` - 2 log groups updated
- ✅ `template-webapp.yml` - Updated
- ✅ `template-automated-scheduling.yml` - Updated

### 2. Next Deployment Steps
To apply these changes:

```bash
# 1. Deploy updated CloudFormation stacks
aws cloudformation update-stack --stack-name stocks-app-ecs-tasks --template-body file://template-app-ecs-tasks.yml

# 2. Delete massive log groups manually (they'll recreate with new retention)
aws logs delete-log-group --log-group-name /ecs/buysellmonthly-loader
aws logs delete-log-group --log-group-name /ecs/buysellweekly-loader
```

### 3. Cost Reduction Summary

**Before:**
- Retention: 14 days for most logs, "Never" for some
- Storage: 16.05 GB
- Ingestion: ~8-10 GB/month @ $0.50/GB = $4-5/month
- Storage: 16 GB @ $0.03/GB = $0.48/month
- **Total**: ~$10/month

**After (projected):**
- Retention: 3 days for ALL logs
- Storage: ~3.5 GB (78% reduction)
- Ingestion: Same data volume but shorter retention
- Storage: 3.5 GB @ $0.03/GB = $0.11/month
- **Total**: ~$5-6/month

**Estimated Savings**: ~$4-5/month (40-50% reduction)

## Additional Recommendations

1. **Container Insights**: Consider disabling or reducing frequency
   - `/aws/ecs/containerinsights/stocks-cluster/performance` - 568 KB (1-day retention already set)

2. **Reduce Logging Verbosity**:
   - Check if buysell loaders are logging too much
   - Consider using ERROR level instead of INFO for production

3. **Monitor After Deployment**:
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace AWS/Logs \
     --metric-name IncomingBytes \
     --start-time 2025-10-01T00:00:00Z \
     --end-time 2025-10-14T23:59:59Z \
     --period 86400 \
     --statistics Sum
   ```

## Files Modified
- `/home/stocks/algo/template-app-ecs-tasks.yml`
- `/home/stocks/algo/template-webapp-lambda.yml`
- `/home/stocks/algo/template-webapp-unified.yml`
- `/home/stocks/algo/template-webapp.yml`
- `/home/stocks/algo/template-automated-scheduling.yml`
- `/home/stocks/algo/cleanup_cloudwatch_logs.py` (helper script)

## Next Steps
1. ✅ Update IaC templates (DONE)
2. ⏳ Deploy CloudFormation stack updates
3. ⏳ Manually delete massive log groups (8.1 GB + 7.7 GB)
4. ⏳ Monitor costs over next week
5. ⏳ Consider reducing logging verbosity in loaders
