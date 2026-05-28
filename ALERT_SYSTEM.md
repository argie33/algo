# Alert System Configuration

**Issue:** #31 (COMPREHENSIVE_ISSUES.md)  
**Status:** 🟢 RESOLVED  
**Date:** 2026-05-28

---

## Overview

The alert system is fully configured with SNS as the primary notification channel. Alerts are triggered when:

- **Phase 1 Halt:** Market data is stale (no fresh data within SLA)
- **Phase 2 Circuit Breaker:** Market volatility exceeds threshold
- **Phase 7 Reconciliation Errors:** Alpaca account mismatch
- **Pipeline Failures:** Morning/EOD data loaders fail
- **Data Patrol:** Critical data quality issues detected

---

## Current Configuration

### SNS Topic (Primary)
- **Location:** `terraform/modules/pipeline/main.tf` (lines 687-698)
- **Resource:** `aws_sns_topic.alerts`
- **State:** Enabled via `var.sns_alerts_enabled`

**Alerts published to SNS:**
- EOD pipeline orchestrator failed
- Morning pipeline failed
- CloudWatch alarms trigger SNS

### Email / Webhook Configuration
**Variables:** `terraform/terraform.tfvars`

```hcl
alert_email_to    = ""           # "admin@example.com,ops@example.com"
alert_webhook_url = ""           # "https://hooks.slack.com/..."
```

---

## Setup Instructions

### Option 1: SNS Email Subscriptions (Recommended)

Subscribe email addresses directly to the SNS topic:

```bash
# Get SNS topic ARN
TOPIC_ARN=$(aws sns list-topics --query 'Topics[?contains(TopicArn, `algo`)].TopicArn' --output text | grep alert)

# Subscribe email address
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint admin@example.com
```

### Option 2: Slack Integration

Create a Slack incoming webhook and configure in tfvars:

```bash
alert_webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

terraform apply
```

---

## Alert Types

### Phase 1: Data Freshness
**Trigger:** Market health data > 1 trading day stale  
**Response:** Check data loaders, verify ECS tasks running

### Phase 2: Circuit Breaker
**Trigger:** Market volatility (VIX > 50) or circuit breaker tripped  
**Response:** Trading halted automatically, review market conditions

### Phase 7: Reconciliation Error
**Trigger:** Alpaca account balance mismatch > threshold  
**Response:** Verify account access, check trade execution logs

### Pipeline Failures
**Trigger:** ECS loader task or Step Functions state fails  
**Response:** Check CloudWatch logs, verify task definition

---

**Summary:** Alert system configured via SNS with email/Slack support. Configure `alert_email_to` or `alert_webhook_url` in tfvars and deploy to enable notifications.
