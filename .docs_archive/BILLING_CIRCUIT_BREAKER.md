# AWS Billing Circuit Breaker Setup

## Overview

Your billing circuit breaker is a **three-layer defense system** that monitors AWS costs and takes automatic action if spending exceeds budgets.

### Layers

| Layer | Trigger | Action |
|-------|---------|--------|
| **Layer 1: Warning** | 50% of budget ($50) | Email + SMS alert |
| **Layer 2: Aggressive** | 75% of budget ($75) | Email + SMS alert |
| **Layer 3: Critical** | 90% of budget ($90) | Email + SMS alert |
| **Layer 4: Hard Stop** | 100%+ of budget ($100+) | **Deny-all policy attached** → All API calls fail → **No new charges** |

---

## What Gets Deployed

### 1. **SNS Topic** (`BillingAlertTopic`)
- Sends email to: `argeropolos@gmail.com`
- Sends SMS to: `+1-312-307-8620`
- All alerts go to both simultaneously

### 2. **AWS Budget** (`StocksPlatformBudget`)
- Monitors monthly spend: **$100 limit**
- Sends forecasted alerts at 50%, 75%, 90%
- Sends actual alert at 100%+

### 3. **CloudWatch Alarm** (`EstimatedChargesAlarm`)
- Monitors real-time billing data
- Alerts when approaching $80 (before hard stop)
- Checks every hour

### 4. **Circuit Breaker Lambda** (`BillingCircuitBreakerFunction`)
- Triggered automatically when 100% budget is exceeded
- **Phase 1**: Attaches deny-all policy to your Lambda execution role
- **Phase 2**: Sends emergency SMS + email
- **Phase 3**: Logs the incident to CloudWatch

### 5. **EventBridge Rule** (`BudgetAlertRule`)
- Listens for budget alerts from AWS Budgets
- Invokes circuit breaker Lambda at 100%

---

## Deployment Steps

### Step 1: Get Your AWS Account ID
```bash
aws sts get-caller-identity --query Account --output text
```
Expected: `626216981288` (or your actual account ID)

### Step 2: Update Lambda Role ARN
The template needs the ARN of your Lambda execution role. Find it:

```bash
aws iam list-roles --query "Roles[?contains(RoleName, 'stocks-algo-api')]" --output text
```

Look for a role like: `arn:aws:iam::626216981288:role/stocks-algo-api-dev-us-east-1-lambdaRole`

Update in the template parameter if different.

### Step 3: Deploy the Stack
```bash
aws cloudformation deploy \
  --template-file billing-circuit-breaker.yml \
  --stack-name billing-circuit-breaker \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    PhoneNumber=+13123078620 \
    EmailAddress=argeropolos@gmail.com \
    MonthlyBudgetLimit=100 \
    LambdaExecutionRoleArn=arn:aws:iam::626216981288:role/stocks-algo-api-dev-us-east-1-lambdaRole \
  --region us-east-1
```

### Step 4: Confirm SNS Subscriptions
AWS will send confirmation emails to `argeropolos@gmail.com`:
- **1st email**: "AWS Notification - Subscription Confirmation" → Click **Confirm subscription**
- **2nd email**: "AWS SNS Notification" → This will verify SMS is working

---

## What Happens When Circuit Breaker Activates

### Automatic Actions (Instant)
```
[PHASE 1] ✓ Deny-all policy attached
  → All Lambda invocations return "Access Denied"
  → Frontend gets 403 Forbidden
  → API is effectively offline
  → ⚠️ No new AWS charges can accrue

[PHASE 2] ✓ Emergency SMS sent to +1-312-307-8620
           ✓ Emergency email sent to argeropolos@gmail.com
  → Message includes timestamp and incident details
  
[PHASE 3] ✓ Logged to CloudWatch for audit trail
```

### What You See
- **Phone**: `🚨 AWS BILLING HARD STOP ACTIVATED`
- **Email**: Full incident details
- **Frontend**: 403 errors on all API calls
- **AWS Console**: New policy visible in IAM role

---

## Manual Recovery (After Reviewing Costs)

### Option 1: Remove the Deny-All Policy (Recommended)
```bash
# Delete the circuit breaker policy
aws iam delete-role-policy \
  --role-name stocks-algo-api-dev-us-east-1-lambdaRole \
  --policy-name billing-circuit-breaker-deny-all \
  --region us-east-1

# Verify it's gone
aws iam get-role-policy \
  --role-name stocks-algo-api-dev-us-east-1-lambdaRole \
  --policy-name billing-circuit-breaker-deny-all
  # Should return: policy not found ✓
```

### Option 2: Disable the Circuit Breaker (Temporarily)
If you need more time to review:
```bash
# Disable the EventBridge rule
aws events disable-rule \
  --name billing-circuit-breaker-trigger \
  --region us-east-1

# Services will still fail due to deny policy, but auto-stop won't trigger again
# You now have time to debug and understand costs
```

### Option 3: Increase Budget (If Intentional)
```bash
aws budgets update-budget \
  --account-id 626216981288 \
  --budget file://updated-budget.json
```

---

## Testing the Circuit Breaker (Optional)

### Test Notification Flow (Don't Trigger Hard Stop)
```bash
# Send a test message to the SNS topic
aws sns publish \
  --topic-arn arn:aws:sns:us-east-1:626216981288:billing-circuit-breaker-alerts \
  --subject "🧪 BILLING CIRCUIT BREAKER TEST" \
  --message "This is a test. Your circuit breaker is working correctly. No actions were taken."
```

You should receive:
- ✓ Email in 30 seconds
- ✓ SMS in 30 seconds

### Manually Invoke Circuit Breaker (For Testing Only)
```bash
# This will ACTUALLY attach the deny-all policy
aws lambda invoke \
  --function-name billing-circuit-breaker \
  --payload '{}' \
  response.json
```

---

## Monitoring & Alerts

### View Active Alerts
```bash
# Check SNS subscription status
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:626216981288:billing-circuit-breaker-alerts

# Check CloudWatch alarms
aws cloudwatch describe-alarms \
  --alarm-names AWS-Estimated-Charges-Alert
```

### View Circuit Breaker Logs
```bash
# Check if circuit breaker was ever triggered
aws logs tail /aws/lambda/billing-circuit-breaker --follow
```

### View Denied API Calls
```bash
# When the deny policy is active, API calls fail in CloudWatch
aws logs tail /aws/lambda/stocks-algo-api --follow --filter "Access Denied"
```

---

## Troubleshooting

### "SMS not received but email is"
- SMS requires SNS to be enabled in your AWS account
- SMS support may be limited in your region
- Check SNS dashboard for SMS sending limits

### "Policy didn't attach"
- Check IAM role ARN is correct
- Verify CircuitBreakerLambdaRole has proper permissions
- Check CloudWatch logs: `/aws/lambda/billing-circuit-breaker`

### "Budget alerts not triggering"
- AWS Budgets takes ~1 hour to calculate daily costs
- Estimated alerts are calculated nightly
- Actual alerts post 24-48 hours after costs incur

### "Can't remove policy - access denied"
```bash
# If you're locked out, use root account or IAM admin
aws iam list-role-policies --role-name <role-name>
# Find the policy name, then delete it
```

---

## Cost of the Circuit Breaker

- **SNS**: ~$0.01 per month (minimal notifications)
- **AWS Budgets**: Free (included)
- **Lambda**: Free tier (invoked once per month max)
- **CloudWatch**: ~$0.10 per month (alarm)

**Total**: < $1/month

---

## Security Notes

✅ The circuit breaker role has **minimal permissions**:
- Can only modify your Lambda execution role
- Can only send to your SNS topic
- Cannot modify data, databases, or other resources

⚠️ **The deny-all policy is powerful**:
- Once attached, ALL API calls fail
- Only remove if you've reviewed costs
- You are the only person who can remove it

✅ **Manual controls**:
- You must manually restore service
- Gives you time to investigate cost spike
- Not automatic (no risk of service loop)

---

## Next Steps

1. **Deploy the stack** using the command in Step 3
2. **Confirm SNS subscriptions** in your email
3. **Test with a test message** (optional)
4. **Monitor your spending** at https://console.aws.amazon.com/billing
5. **Be alerted** at 50%, 75%, 90%, 100%

Your system is now protected. 🛡️
