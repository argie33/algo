# AWS Billing & Cost Controls Setup Guide


**Goal:** Ensure you receive AWS bill notifications at `argeropolos@gmail.com` and prevent runaway costs with automated circuit breaker suspension.

---

## Quick Start (5 minutes)

### 1. **Enable Email Billing Alerts (AWS Console)**

1. Go to **AWS Billing Console** → https://console.aws.amazon.com/billing/
2. Click **Billing preferences** (in left sidebar under "Settings")
3. Check: ✅ **Receive Billing Alerts**
4. Check: ✅ **Receive Free Tier Alerts**
5. Check: ✅ **Receive Cost Anomaly Alerts**
6. Enter email: `argeropolos@gmail.com`
7. Save and confirm email subscription

This enables AWS to send daily/weekly billing summaries to your email.

### 2. **Deploy Cost Circuit Breaker Lambda**

```bash
cd terraform
terraform plan
terraform apply  # Deploys AWS Budgets + Cost Circuit Breaker Lambda
```

The system will then:
- Run cost checks every 6 hours (4 AM, 10 AM, 4 PM, 10 PM UTC)
- Send alerts to `argeropolos@gmail.com` via SNS
- Auto-suspend if daily cost exceeds threshold ($50/day for dev, configurable)

---

## Architecture

### Email Alerts (Multiple Layers)

```
┌─────────────────────────────────────────────────────────────┐
│ AWS BILLING EMAIL ALERTS                                    │
├─────────────────────────────────────────────────────────────┤
│ 1. AWS Native Billing Alerts (AWS Console config)           │
│    └─ Daily cost summaries                                  │
│    └─ Free Tier usage warnings                              │
│    └─ Cost anomaly detection (AI-based spike detection)     │
│                                                             │
│ 2. AWS Budgets (IaC via Terraform)                          │
│    └─ Monthly budget alerts: 80%, 100%, 120% thresholds     │
│    └─ Daily budget alerts: Real-time cost tracking          │
│    └─ Email subscriber: argeropolos@gmail.com               │
│                                                             │
│ 3. SNS Topic Alerts (from Cost Circuit Breaker Lambda)      │
│    └─ Real-time cost alerts every 6 hours                   │
│    └─ Cost breakdown by AWS service                         │
│    └─ Suspension notifications (if threshold exceeded)      │
└─────────────────────────────────────────────────────────────┘
```

### Cost Protection (Automatic Suspension)

```
EventBridge Scheduler (every 6 hours)
    ↓
Cost Circuit Breaker Lambda
    ├─ Query Cost Explorer: "What was my cost in last 24h?"
    ├─ Check threshold: $50/day (dev) or $200/day (prod)
    │
    ├─ IF cost ≤ threshold → Send "OK" alert
    │
    └─ IF cost > threshold → SUSPEND:
        ├─ Disable EventBridge Scheduler rules
        │   └─ Halts all loaders and orchestrator
        ├─ Stop all running ECS tasks
        │   └─ Kills active jobs mid-execution
        ├─ Send CRITICAL email alert
        │   └─ Subject: 🚨 AWS COST CIRCUIT BREAKER TRIGGERED 🚨
        │   └─ Includes: Cost breakdown, suspension details
        └─ Manual recovery only
            └─ Operator reviews costs + fixes root cause
            └─ Operator runs `terraform apply` to re-enable
```

---

## Configuration

### Daily Cost Threshold

**Dev (current):** $50/day
**Production:** $200/day (adjust based on expected infrastructure spend)

To change:

```bash
# Option 1: CLI override
terraform apply -var="cost_threshold_daily_usd=100"

# Option 2: Update dev.tfvars
echo 'cost_threshold_daily_usd = 75.0' >> terraform/dev.tfvars
terraform apply
```

### Monthly Budget Limit

**Current:** $500/month (AWS Budgets)

To change, edit `terraform/modules/monitoring/aws-budgets.tf` line ~19:

```hcl
limit_amount = "500"  # Change to your desired monthly budget
```

---

## Monitoring & Alerts

### What You'll Receive

1. **Daily AWS Billing Summary**
   - From: AWS Billing Console
   - To: argeropolos@gmail.com
   - When: Once per day, typically morning
   - Content: Previous day's costs by service

2. **Cost Anomaly Alerts**
   - From: AWS (if anomaly detection enabled)
   - To: argeropolos@gmail.com
   - When: Immediately upon spike detection
   - Content: ML-detected unusual spending patterns

3. **Monthly Budget Alerts**
   - From: AWS Budgets
   - To: argeropolos@gmail.com
   - When: At 80%, 100%, 120% of monthly budget
   - Content: Budget status + forecast

4. **Cost Circuit Breaker Alerts**
   - From: SNS Topic (algo-dev-sns-alerts-dev)
   - To: argeropolos@gmail.com
   - When: Every 6 hours + immediately if threshold exceeded
   - Content: Current daily cost, threshold, suspension status

---

## Troubleshooting

### "I'm not receiving billing emails"

1. **Check AWS Console email setting:**
   ```
   AWS Console → Billing → Billing preferences
   → Verify email is argeropolos@gmail.com
   → Check spam/promotions folder
   ```

2. **Check SNS subscription confirmation:**
   - Look for "AWS Notification - Subscription Confirmation" email
   - Click the confirmation link (emails won't send until confirmed)

3. **Verify email is in Terraform:**
   ```bash
   grep "alert_email_address\|sns_alert_email" terraform/dev.tfvars
   # Should show: argeropolos@gmail.com
   ```

4. **Re-confirm SNS subscription:**
   ```bash
   aws sns list-subscriptions-by-topic \
     --topic-arn arn:aws:sns:us-east-1:ACCOUNT-ID:algo-dev-sns-alerts-dev
   # Look for subscription with email, check Status = "Confirmed"
   ```

### "Circuit breaker suspended services but I didn't intend it"

1. **Check cost details:**
   ```bash
   aws ce get-cost-and-usage \
     --time-period Start=2026-07-10,End=2026-07-11 \
     --granularity DAILY \
     --metrics UnblendedCost \
     --group-by Type=DIMENSION,Key=SERVICE
   ```

2. **Investigate root cause:**
   - Lambda invocation count spike?
   - RDS disk I/O high?
   - Data Transfer charges?

3. **Re-enable services** (after fixing root cause):
   ```bash
   cd terraform
   terraform apply -var="cost_threshold_daily_usd=HIGHER_VALUE"
   # Then manually re-enable schedules:
   aws scheduler update-schedule --name algo-circuitbreaker-10am-dev --state ENABLED
   aws scheduler update-schedule --name algo-trigger-loaders-morning-dev --state ENABLED
   ```

### "The circuit breaker Lambda is erroring"

Check logs:

```bash
# View recent errors
aws logs tail /aws/lambda/stocks-cost-circuit-breaker-dev --follow

# Check Lambda execution
aws lambda get-function-concurrency \
  --function-name stocks-cost-circuit-breaker-dev
```

**Common issues:**
- Missing IAM permissions (check `cost_circuit_breaker_policy` in Terraform)
- Cost Explorer not yet initialized (wait 24h after first deployment)
- No VPC required (Cost Circuit Breaker runs outside VPC)

---

## Cost Estimates

### Implementation Cost

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| AWS Budgets | $0 | Free |
| Cost Circuit Breaker Lambda | $0.20 | 4 invocations/day × ~256MB × 2s |
| SNS Emails | $0.50 | ~150 emails/month @ $0.003 per alert |
| **Total** | **~$0.70/month** | Minimal overhead |

### Cost Savings

- **Prevents runaway costs:** Early warning + automatic suspension
- **Avoids surprise bills:** $10K+ incidents possible without circuit breaker
- **Dev environment:** $50/day budget prevents runaway loaders

---

## Advanced Configuration

### Slack Integration (Optional)

To send alerts to Slack instead of email:

1. Create Slack Incoming Webhook
2. Update Terraform:
   ```bash
   terraform apply -var="alert_webhook_url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
   ```

### Custom Thresholds by Service

To alert only on specific service costs (e.g., RDS spike):

Edit `lambda/cost-circuit-breaker/index.py`, modify `send_cost_alert()` to check `service_breakdown` dictionary.

### Disable Circuit Breaker (Not Recommended)

```bash
# Temporarily disable (cost checks still run, but won't suspend)
aws lambda update-function-configuration \
  --function-name stocks-cost-circuit-breaker-dev \
  --environment Variables="{ENABLE_SUSPENSION=false}"
```

---

## Checklist

- [ ] AWS Billing Console: Receive Billing Alerts ✅
- [ ] AWS Billing Console: Email set to argeropolos@gmail.com
- [ ] Confirm SNS email subscription (check spam folder)
- [ ] Run `terraform apply` to deploy Cost Circuit Breaker
- [ ] Verify Lambda deployed: `aws lambda get-function --function-name stocks-cost-circuit-breaker-dev`
- [ ] Test manually: `aws lambda invoke --function-name stocks-cost-circuit-breaker-dev /tmp/result.json && cat /tmp/result.json`
- [ ] Check CloudWatch: `/aws/lambda/stocks-cost-circuit-breaker-dev`
- [ ] Monitor SNS alerts for 24 hours to ensure emails arrive

---

## Related Documentation

- [AWS_LAMBDA_503_FIX.md](AWS_LAMBDA_503_FIX.md) - API Lambda troubleshooting
- [GOVERNANCE.md](GOVERNANCE.md) - Infrastructure policy
- [OPERATIONS.md](OPERATIONS.md) - Deployment procedures
