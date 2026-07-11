# AWS Billing & Cost Control - Quick Reference

## Receive Billing Emails (2-minute setup)

```
1. Go to: https://console.aws.amazon.com/billing/
2. Click: Billing preferences (left sidebar)
3. Check ✅: Receive Billing Alerts
4. Check ✅: Receive Free Tier Alerts  
5. Check ✅: Receive Cost Anomaly Alerts
6. Email: argeropolos@gmail.com
7. Save → Confirm email subscription → Done!
```

**What you get:** Daily billing summaries + anomaly alerts

---

## Deploy Cost Circuit Breaker (Automatic Suspension)

```bash
# Build Lambda (optional, auto-done by GitHub Actions)
bash scripts/build-cost-circuit-breaker.sh

# Deploy to AWS
cd terraform
terraform apply

# Verify
aws logs tail /aws/lambda/stocks-cost-circuit-breaker-dev --follow
```

**What it does:**
- Checks AWS costs every 6 hours
- If daily cost > $50 → SUSPENDS all services
- Sends email alert to argeropolos@gmail.com
- Requires manual re-enable after reviewing costs

---

## Test Circuit Breaker

```bash
# Run manual check
aws lambda invoke \
  --function-name stocks-cost-circuit-breaker-dev \
  /tmp/result.json && cat /tmp/result.json

# Check logs
aws logs tail /aws/lambda/stocks-cost-circuit-breaker-dev --follow

# Check if suspended (will show DISABLED)
aws scheduler list-schedules --name-prefix="stocks" --query 'Schedules[].State'
```

---

## If Services Get Suspended

```bash
# 1. Check why it triggered
aws logs tail /aws/lambda/stocks-cost-circuit-breaker-dev | grep TRIGGER

# 2. Review AWS costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "-1 day" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE

# 3. Fix root cause (e.g., stop expensive Lambda/ECS/RDS)

# 4. Re-enable services
terraform apply -var="cost_threshold_daily_usd=150"
aws scheduler update-schedule --name algo-cost-breaker-4am-dev --state ENABLED
```

---

## Troubleshoot Email Not Arriving

```bash
# Check SNS subscription
aws sns list-subscriptions | grep email

# Status should be "Confirmed"
# If "PendingConfirmation": Check spam folder for verification email, click link

# Manually resend test alert
aws sns publish \
  --topic-arn $(terraform output -raw sns_alerts_topic_arn) \
  --subject "Test" \
  --message "Test email from cost circuit breaker"
```

---

## Configuration

```bash
# Change daily threshold (default: $50)
terraform apply -var="cost_threshold_daily_usd=100"

# Change monthly budget (edit terraform/modules/monitoring/aws-budgets.tf line ~23)
# Then: terraform apply
```

---

## Files Modified/Added

- ✅ `lambda/cost-circuit-breaker/index.py` - Lambda handler (400 lines)
- ✅ `lambda/cost-circuit-breaker/requirements.txt` - Dependencies
- ✅ `terraform/modules/monitoring/cost-circuit-breaker.tf` - Terraform config
- ✅ `terraform/modules/monitoring/aws-budgets.tf` - Budget alerts
- ✅ `terraform/modules/monitoring/variables.tf` - Cost threshold variable
- ✅ `terraform/variables.tf` - Root variable
- ✅ `terraform/main.tf` - Module integration
- ✅ `.github/workflows/deploy-all-infrastructure.yml` - Build step
- ✅ `scripts/build-cost-circuit-breaker.sh` - Local build script
- ✅ `steering/AWS_BILLING_AND_COST_CONTROLS.md` - Full documentation

---

## Next Steps

1. ✅ Verify code: `ls lambda/cost-circuit-breaker/`
2. ⏳ Deploy: `cd terraform && terraform apply`
3. ⏳ Enable billing emails (AWS Console, 2 min)
4. ⏳ Monitor: `aws logs tail /aws/lambda/stocks-cost-circuit-breaker-dev`
5. ✅ Done! Now protected against runaway AWS costs.

**Full docs:** `steering/AWS_BILLING_AND_COST_CONTROLS.md`
