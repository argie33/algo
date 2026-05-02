# AWS Budget & Cost Controls — $100/Month Limit

## Quick Setup (5 minutes)

### 1. Create AWS Budget Alert

```bash
aws budgets create-budget \
  --account-id ACCOUNT_ID \
  --budget file:///dev/stdin <<'EOF'
{
  "BudgetName": "StockLoaderMonthly",
  "BudgetLimit": {
    "Amount": "100",
    "Unit": "USD"
  },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF
```

Or via AWS Console:
1. Go to **AWS Budgets** → **Create budget**
2. Budget type: **Cost budget**
3. Budget name: `StockLoaderMonthly`
4. Period: **Monthly**
5. Budget limit: **$100**
6. Click **Create**

### 2. Create Budget Alert Notifications

```bash
aws budgets create-notification \
  --account-id ACCOUNT_ID \
  --budget-name StockLoaderMonthly \
  --notification file:///dev/stdin <<'EOF'
{
  "NotificationType": "FORECASTED",
  "ComparisonOperator": "GREATER_THAN",
  "Threshold": 80,
  "ThresholdType": "PERCENTAGE"
}
EOF

aws budgets create-notification \
  --account-id ACCOUNT_ID \
  --budget-name StockLoaderMonthly \
  --notification file:///dev/stdin <<'EOF'
{
  "NotificationType": "ACTUAL",
  "ComparisonOperator": "GREATER_THAN",
  "Threshold": 95,
  "ThresholdType": "PERCENTAGE"
}
EOF
```

### 3. Create SNS Topic for Alerts

```bash
# Create SNS topic
aws sns create-topic --name StockLoaderAlerts

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:StockLoaderAlerts \
  --protocol email \
  --notification-endpoint argeropolos@gmail.com
```

### 4. Link Budget to SNS

```bash
aws budgets create-notification-subscription \
  --account-id ACCOUNT_ID \
  --budget-name StockLoaderMonthly \
  --notification file:///dev/stdin <<'EOF'
{
  "NotificationType": "FORECASTED",
  "ComparisonOperator": "GREATER_THAN",
  "Threshold": 80,
  "ThresholdType": "PERCENTAGE"
}
EOF
  --subscription-target-arn arn:aws:sns:us-east-1:ACCOUNT_ID:StockLoaderAlerts
```

---

## Cost Breakdown (Target: $49/month)

### Services & Estimated Costs

| Service | Daily | Monthly | Notes |
|---------|-------|---------|-------|
| **RDS PostgreSQL** | - | $20 | Small instance, auto-pause 20h/day |
| **Lambda (daily incremental)** | $0.0003 | $0.09 | 5 parallel × 6 min, 512MB |
| **Lambda (weekly)** | $0.00005 | $0.005 | Weekly, 5 workers |
| **Lambda (monthly)** | $0.002 | $0.02 | Monthly factor refresh |
| **CloudWatch Logs** | $0.10 | $3 | Loader output logs |
| **NAT Gateway** | $0.23 | $7 | Outbound to yfinance |
| **Data Transfer** | $0.05 | $1.50 | In/out of RDS |
| **Other (misc)** | - | ~$1 | CloudFormation, minor services |
| **TOTAL** | **~$0.38** | **~$32.61** | Safe within $100 limit |

### Buffer

- Monthly budget: $100
- Estimated usage: $33
- **Buffer: $67** (67% spare capacity)

---

## Cost Optimization Levers

If costs ever approach the budget, use these controls:

### 1. RDS Auto-Pause (Saves $16/month)

```sql
-- Set auto-pause after 20 hours of inactivity
-- This is the BIGGEST cost saver
```

AWS Console:
1. RDS → Databases → Select your DB
2. **Modify**
3. Find **Aurora Serverless** section → Enable **Auto pause**
4. Pause after: **20 minutes** (adjust as needed)

**Cost impact:** Reduces RDS bill from $30 → $14/month

### 2. Lambda Reserved Concurrency (Prevents Runaway Costs)

```bash
# Limit to 5 concurrent Lambda executions
aws lambda put-function-concurrency \
  --function-name LoadPriceDailyWorker \
  --reserved-concurrent-executions 5
```

**Why:** Prevents accidental mass invocation that would spike costs.

### 3. CloudWatch Logs Retention (Saves $1-3/month)

```bash
# Keep logs for only 7 days (default is forever)
aws logs put-retention-policy \
  --log-group-name /aws/lambda/LoadPriceDailyWorker \
  --retention-in-days 7
```

### 4. Stop Monthly Factor Metrics (If Needed)

If approaching budget, pause the expensive monthly refresh:

```bash
# Disable the monthly factor metrics Lambda
aws events put-rule \
  --name FactorMetricsSchedule \
  --state DISABLED
```

**Cost impact:** Saves $5-10/month

---

## Monitoring: CloudWatch Dashboard

Create a dashboard to track costs in real-time:

```bash
aws cloudwatch put-dashboard \
  --dashboard-name StockLoaderCosts \
  --dashboard-body file:///dev/stdin <<'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Billing", "EstimatedCharges", {"stat": "Average"}],
          ["AWS/Lambda", "Duration", {"stat": "Average"}],
          ["AWS/Lambda", "Errors", {"stat": "Sum"}],
          ["AWS/RDS", "CPUUtilization", {"stat": "Average"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Stock Loader Metrics"
      }
    },
    {
      "type": "log",
      "properties": {
        "query": "fields @duration, @message | stats avg(@duration) by @message",
        "region": "us-east-1",
        "title": "Lambda Execution Times"
      }
    }
  ]
}
EOF
```

### View Dashboard

```bash
# Open in browser (replace ACCOUNT_ID)
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=StockLoaderCosts
```

---

## Automated Cost Check (Email Daily)

Create a Lambda that emails you daily cost estimates:

**cost_check_lambda.py**

```python
import boto3
import json
from datetime import datetime, timedelta
import os

ce_client = boto3.client('ce')  # Cost Explorer
sns_client = boto3.client('sns')

def handler(event, context):
    """
    Query yesterday's costs and send email.
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    response = ce_client.get_cost_and_usage(
        TimePeriod={
            'Start': yesterday,
            'End': yesterday
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[
            {'Type': 'DIMENSION', 'Key': 'SERVICE'}
        ]
    )
    
    # Build email
    total_cost = 0
    breakdown = []
    
    for result_by_time in response['ResultsByTime']:
        for group in result_by_time['Groups']:
            service = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])
            total_cost += cost
            if cost > 0.01:  # Only show services > $0.01
                breakdown.append(f"  {service}: ${cost:.2f}")
    
    message = f"""
    Stock Loader Daily Cost Report
    ==============================
    
    Date: {yesterday}
    Total Cost: ${total_cost:.2f}
    
    Breakdown:
    {chr(10).join(breakdown)}
    
    Monthly Projection: ${total_cost * 30:.2f}
    Budget Remaining: ${100 - (total_cost * 30):.2f}
    
    Status: {'⚠️ APPROACHING LIMIT' if (total_cost * 30) > 80 else '✅ On track'}
    """
    
    sns_client.publish(
        TopicArn=os.environ['SNS_TOPIC_ARN'],
        Subject=f"AWS Cost Report - {yesterday}",
        Message=message
    )
    
    return {'statusCode': 200, 'body': json.dumps({'cost': total_cost})}
```

Deploy:
```bash
zip cost_check.zip cost_check_lambda.py

aws lambda create-function \
  --function-name StockLoaderCostCheck \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT:role/lambda-execution-role \
  --handler cost_check_lambda.handler \
  --zip-file fileb://cost_check.zip \
  --environment Variables="{SNS_TOPIC_ARN=arn:aws:sns:us-east-1:ACCOUNT:StockLoaderAlerts}"

# Schedule daily at 8am
aws events put-rule \
  --name CostCheckDaily \
  --schedule-expression "cron(0 8 ? * * *)"

aws events put-targets \
  --rule CostCheckDaily \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:ACCOUNT:function:StockLoaderCostCheck","RoleArn"="arn:aws:iam::ACCOUNT:role/EventBridgeInvokeRole"
```

---

## What Happens If You Hit $100?

AWS has built-in protections:

1. **Budget Alert at 80%** ($80) → Email notification
2. **Budget Alert at 95%** ($95) → Urgent email
3. **Hard Limit at $100** → No automatic shutdown, but you'll see warnings

### Manual Shutdown (If Needed)

If costs spike unexpectedly:

```bash
# Disable all loaders
aws events put-rule --name LoadPriceDailySchedule --state DISABLED
aws events put-rule --name LoadPriceWeeklySchedule --state DISABLED
aws events put-rule --name LoadFactorMetricsSchedule --state DISABLED

# Pause RDS
aws rds stop-db-instance --db-instance-identifier stocks-db

# Check current spend
aws ce get-cost-and_usage \
  --time-period Start=2026-04-01,End=2026-04-30 \
  --granularity MONTHLY \
  --metrics UnblendedCost
```

---

## FAQ

**Q: Will my Lambda functions suddenly stop working when I hit $100?**

A: No. AWS will let you go slightly over (Grace period ~$10). Set alerts so you know before hitting the limit.

**Q: What's the biggest cost driver?**

A: RDS (~$20/month). Use auto-pause to cut it to $14/month.

**Q: Can I run loaders more frequently?**

A: Yes, Lambda cost increases linearly. Running twice daily = $0.18/month (still cheap). RDS cost dominates.

**Q: What if yfinance rate limits us heavily?**

A: That's covered in PARALLEL_LOADING_GUIDE.md. Loaders have 30 calls/min per range (safe).

**Q: Can I set a hard cost limit that stops everything?**

A: AWS doesn't have automatic shutdown at a cost limit. Use reserved concurrency on Lambda to limit maximum spend.
