# Phase 4: SNS Topic Setup & Alert Routing

## Overview

SNS provides the routing layer between CloudWatch alarms and notification channels:
- **CRITICAL** → PagerDuty/SMS (urgent on-call)
- **WARNING** → Slack #alerts (team awareness)

---

## SNS Topics to Create

### 1. Alerts Topic (WARNING level)

**Topic Name:** algo-alerts-dev (or staging/prod)

**Subscriptions:**
- Slack #alerts channel
- Email to team list

### 2. Critical Topic (CRITICAL level)

**Topic Name:** algo-critical-dev (or staging/prod)

**Subscriptions:**
- PagerDuty integration
- SMS to on-call engineer

---

## Creating SNS Topics

### Via AWS CLI

```bash
# Create alerts topic
ALERTS_TOPIC=$(aws sns create-topic \
  --name "algo-alerts-dev" \
  --query 'TopicArn' \
  --output text)

echo "Created alerts topic: $ALERTS_TOPIC"

# Create critical topic
CRITICAL_TOPIC=$(aws sns create-topic \
  --name "algo-critical-dev" \
  --query 'TopicArn' \
  --output text)

echo "Created critical topic: $CRITICAL_TOPIC"
```

---

## Subscribing to Topics

### Email Subscription

```bash
ALERTS_TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:algo-alerts-dev"

aws sns subscribe \
  --topic-arn "$ALERTS_TOPIC_ARN" \
  --protocol email \
  --notification-endpoint "team@company.com"

# Subscriber must confirm subscription via email
```

### Slack Integration

```bash
# Get Slack webhook URL from your Slack app
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

aws sns subscribe \
  --topic-arn "$ALERTS_TOPIC_ARN" \
  --protocol https \
  --notification-endpoint "$SLACK_WEBHOOK_URL"
```

### PagerDuty Integration

```bash
# Get PagerDuty integration URL from CloudWatch integration
PAGERDUTY_URL="https://events.pagerduty.com/integration/YOUR_KEY/enqueue"

CRITICAL_TOPIC_ARN="arn:aws:sns:us-east-1:ACCOUNT_ID:algo-critical-dev"

aws sns subscribe \
  --topic-arn "$CRITICAL_TOPIC_ARN" \
  --protocol https \
  --notification-endpoint "$PAGERDUTY_URL"
```

### SMS for Critical Alerts

```bash
aws sns subscribe \
  --topic-arn "$CRITICAL_TOPIC_ARN" \
  --protocol sms \
  --notification-endpoint "+1-555-0123"
```

---

## Verify Subscriptions

```bash
# List subscriptions to alerts topic
aws sns list-subscriptions-by-topic \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT_ID:algo-alerts-dev" \
  --query 'Subscriptions[*].[Protocol, Endpoint]' \
  --output table

# List subscriptions to critical topic
aws sns list-subscriptions-by-topic \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT_ID:algo-critical-dev" \
  --query 'Subscriptions[*].[Protocol, Endpoint]' \
  --output table
```

---

## Test SNS Notifications

```bash
# Test alerts topic
aws sns publish \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT_ID:algo-alerts-dev" \
  --subject "Phase 4: Test Alerts Notification" \
  --message "This is a test of the algo-alerts-dev topic."

# Test critical topic
aws sns publish \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT_ID:algo-critical-dev" \
  --subject "CRITICAL: Phase 4 Test Alert" \
  --message "This is a test of the algo-critical-dev topic."
```

---

## Alert Routing Matrix

| Alert | Topic | Subscriptions |
|-------|-------|---------------|
| Data Unavailability | alerts | Slack, Email |
| Validation Errors | alerts | Slack, Email |
| Circuit Breaker Halt | critical | PagerDuty, SMS |
| Data Staleness | alerts | Slack, Email |
| Hardening Errors | alerts | Slack, Email |
| Data Quality Crisis | critical | PagerDuty, SMS |

---

## Production Readiness

Before going live:

- [ ] SNS topics created in prod account
- [ ] All subscriptions confirmed (email, Slack, PagerDuty)
- [ ] SNS test notifications received successfully
- [ ] On-call rotation configured in PagerDuty
- [ ] Slack #alerts channel configured
- [ ] Team trained on alert meanings

---

## Troubleshooting

### Email subscription not confirmed

1. Check spam folder
2. Re-subscribe:
   ```bash
   aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "team@company.com"
   ```

### Slack webhook not receiving messages

1. Verify webhook URL is correct
2. Test webhook manually:
   ```bash
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Test"}' \
     https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

### PagerDuty not receiving alerts

1. Verify integration key is correct
2. Check PagerDuty service configuration
3. Test with direct SNS publish

---

**Last Updated:** 2026-07-04
