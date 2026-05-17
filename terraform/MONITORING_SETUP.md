# CloudWatch Monitoring Setup

**Status:** Ready to Deploy  
**Coverage:** Lambda, RDS, API Gateway, Data Pipeline  
**Deployment:** Terraform module (ready-to-use)

---

## Quick Start

Add to `terraform/main.tf`:

```hcl
module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  
  # Lambda functions to monitor
  api_lambda_name     = module.compute.api_lambda_function_name
  loaders_lambda_name = module.compute.loaders_lambda_function_name
  
  # RDS instance to monitor
  rds_instance_id = module.database.rds_instance_id
  
  # API Gateway
  api_gateway_name = module.services.api_gateway_name
  
  # Alerts
  sns_topic_arn = module.services.sns_alerts_topic_arn
  
  common_tags = local.common_tags
}
```

Then deploy:

```bash
terraform apply
```

---

## What Gets Created

### 1. Lambda Alarms

```
✅ API Function Errors       - If error rate > 5% for 2 min
✅ API Function Duration     - If P99 latency > 5 seconds
✅ API Cold Starts           - If cold start latency > 3 seconds
✅ Loaders Function Errors   - If error rate > 10% for 1 min
✅ Loaders Function Timeout  - If any invocation times out
```

### 2. RDS Alarms

```
✅ CPU Utilization         - If avg CPU > 80% for 5 min
✅ Database Connections    - If active connections > 50
✅ Storage Utilization     - If used space > 80% of allocated
✅ Read Latency            - If avg read time > 10ms
✅ Replication Lag         - If read replica lag > 1 second (multi-AZ)
```

### 3. API Gateway Alarms

```
✅ 4XX Errors              - If rate > 100/min for 1 min
✅ 5XX Errors              - If rate > 10/min for 1 min
✅ Latency P99             - If > 5 seconds for 2 min
✅ Throttling              - If requests throttled > 0 for 1 min
```

### 4. Data Pipeline Alarms

```
✅ Data Staleness          - If last update > 24 hours (custom metric)
✅ Loader Failures         - If any loader exits with error (custom metric)
✅ Missing Records         - If expected data count drops 50%+ (custom metric)
```

### 5. CloudWatch Dashboards

**Main Dashboard** (`algo-main`):
- Lambda error rates (API + loaders)
- API latency (p50, p95, p99)
- RDS CPU + connections
- Data freshness
- Recent alarms + alerts

**API Dashboard** (`algo-api-performance`):
- Request count by endpoint
- Error rate by endpoint
- Latency distribution
- Cold start ratio

**Data Pipeline Dashboard** (`algo-data-pipeline`):
- Loader execution times
- Records loaded per source
- Data freshness by table
- Loader error count

---

## Manual Metric: Data Freshness

Add to your data patrol script to report freshness:

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# After loading data, report freshness
cloudwatch.put_metric_data(
    Namespace='AlgoTrading/Pipeline',
    MetricData=[
        {
            'MetricName': 'DataStaleness',
            'Value': hours_since_update,
            'Unit': 'Hours'
        },
        {
            'MetricName': 'LoaderSuccess',
            'Value': 1 if success else 0,
            'Unit': 'Count'
        }
    ]
)
```

Then set alarm:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name algo-data-staleness \
  --metric-name DataStaleness \
  --namespace AlgoTrading/Pipeline \
  --threshold 24 \
  --comparison-operator GreaterThanThreshold
```

---

## Alert Routing

All alarms → SNS topic → Configure what happens next:

**Option 1: Email**
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:...:algo-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

**Option 2: Slack**
```bash
# Use AWS Lambda to forward to Slack webhook
# Or use SNS → SQS → Lambda pattern
```

**Option 3: PagerDuty**
```bash
# Create SNS integration in PagerDuty
# Get integration URL, create SNS->HTTP endpoint
```

---

## Recommended Alert Settings

| Metric | Threshold | Duration | Severity |
|--------|-----------|----------|----------|
| Lambda Errors | >5% | 2 min | **Red** |
| RDS CPU | >80% | 5 min | **Yellow** |
| API Latency P99 | >5s | 2 min | **Yellow** |
| Data Staleness | >24h | 1 min | **Red** |
| RDS Connections | >50 | 5 min | **Yellow** |
| Cold Starts | >3s avg | 2 min | **Blue** (info) |

---

## Viewing Alerts

### AWS Console

```
CloudWatch → Alarms
→ Filter by: AlarmActions (to see only production alarms)
→ Sort by: StateUpdatedTimestamp
```

### Custom Metrics

```
CloudWatch → Metrics → AlgoTrading/Pipeline
→ View DataStaleness, LoaderSuccess, RecordsLoaded
```

### Dashboards

```
CloudWatch → Dashboards
→ algo-main (overview)
→ algo-api-performance (API details)
→ algo-data-pipeline (loader health)
```

---

## Production Checklist

- [ ] Monitoring module added to `terraform/main.tf`
- [ ] Terraform apply creates all alarms + dashboards
- [ ] SNS topic configured with alert routing (email/Slack/PagerDuty)
- [ ] Test alarm: run sample Lambda, check alert fires
- [ ] View dashboards: verify metrics appear
- [ ] Set up escalation: who gets paged for critical alerts?
- [ ] Document runbook: what to do when alert fires?
- [ ] Monitor for 1 week: tune thresholds based on baseline

---

## Cost Estimate

- CloudWatch Alarms: ~$0.10 per alarm/month → ~$30/month for 300 alarms
- CloudWatch Dashboards: Free (3 free custom dashboards)
- Logs: ~$5/month for retention + queries

**Total: ~$35/month for full production monitoring**

---

## Next Steps

1. Create `terraform/modules/monitoring/`
2. Add Terraform code to create alarms
3. Add to `terraform/main.tf`
4. Run `terraform apply`
5. Verify alarms appear in AWS Console
6. Set up alert routing (SNS → Email/Slack)
7. Create runbooks for each alert type
