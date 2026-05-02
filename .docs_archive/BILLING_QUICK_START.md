# Billing Circuit Breaker - Quick Start

## Deploy in 1 Command

```bash
bash deploy-billing-circuit-breaker.sh
```

That's it. The script will:
- ✅ Find your AWS account
- ✅ Find your Lambda role
- ✅ Ask for phone/email/budget
- ✅ Deploy the circuit breaker
- ✅ Set up SMS + email alerts

Takes ~2 minutes.

---

## After Deployment

### Check Your Email
AWS sends 2 confirmation emails:
1. "AWS Notification - Subscription Confirmation" → **Click CONFIRM**
2. Confirmation should happen auto

### Check Your Phone
SMS confirmation arrives (click reply or just wait)

### Test It Works
```bash
aws sns publish \
  --topic-arn arn:aws:sns:us-east-1:626216981288:billing-circuit-breaker-alerts \
  --subject "🧪 Test" \
  --message "If you got this email AND SMS, circuit breaker is working!"
```

You should receive **both email + SMS** in ~30 seconds.

---

## Alert Thresholds

| Spend | Alert Type | What You Get |
|-------|-----------|---|
| $50 | 🟡 Warning | Email + SMS |
| $75 | 🟠 Aggressive | Email + SMS |
| $90 | 🔴 Critical | Email + SMS |
| $100+ | 🚨 HARD STOP | Email + SMS + API DISABLED |

---

## When Hard Stop Activates

### Your API:
```
GET /api/stocks → 403 Forbidden
POST /api/trades → 403 Forbidden
Any request → 403 Forbidden
```

### Your costs:
```
✅ STOPPED - no new charges
```

### Recovery:
```bash
# Delete the deny policy (removes hard stop)
aws iam delete-role-policy \
  --role-name stocks-algo-api-dev-us-east-1-lambdaRole \
  --policy-name billing-circuit-breaker-deny-all

# Service comes back online immediately
```

---

## Monitoring

### View all alerts
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:626216981288:billing-circuit-breaker-alerts
```

### View if circuit breaker ever triggered
```bash
aws logs tail /aws/lambda/billing-circuit-breaker --follow
```

### View denied API calls
```bash
aws logs tail /aws/lambda/stocks-algo-api --filter "Access Denied"
```

---

## Your Numbers

- **Phone**: +1-312-307-8620
- **Email**: argeropolos@gmail.com
- **Budget**: $100/month
- **Hard stop**: At $100+

---

## Full Documentation

See `BILLING_CIRCUIT_BREAKER.md` for:
- Architecture details
- Troubleshooting
- Manual recovery steps
- Cost of the circuit breaker
- Security notes

---

## Questions?

Check the CloudWatch Logs:
```bash
aws logs tail /aws/lambda/billing-circuit-breaker --follow
```

Or review AWS Budgets in the console:
https://console.aws.amazon.com/billing
