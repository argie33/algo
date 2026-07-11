# Fix: Complete Email Alert Setup

## Current Status

✅ **Lambda:** Deployed and working  
✅ **SNS Topic:** Created (`algo-algo-alerts-dev`)  
✅ **Cost Monitoring:** Active ($15.91/day)  
❌ **Email Subscription:** Pending confirmation (NOT WORKING YET)

## The Problem

AWS SNS requires **manual email confirmation** before sending alerts. When Terraform created the SNS topic subscription, it sent a confirmation email to `argeropolos@gmail.com`. Until you click the confirmation link, the subscription stays in "PendingConfirmation" state and **emails will NOT send**.

## Fix: Confirm Email Subscription (Required)

### Step 1: Find the Confirmation Email

1. Check inbox for email from: `AWS Notification - Subscription Confirmation`
   - From address: `no-reply@sns.amazonaws.com`
   - Subject line contains: "AWS Notification - Subscription Confirmation"

2. **Check spam/promotions folder** if not in inbox

3. **Email might be old** - scroll through your inbox looking for emails with "Subscription Confirmation" from SNS (possibly from 2026-07-11)

### Step 2: Click Confirmation Link

1. Open the email from AWS SNS
2. Find the confirmation link (usually a long URL starting with `https://...`)
3. Click that link (or copy/paste into browser)
4. You should see a page that says: "Subscription confirmed!"

### Step 3: Verify Subscription is Active

After confirming, wait 30 seconds, then run:

```bash
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:us-east-1:626216981288:algo-algo-alerts-dev \
  --attribute-name Subscription
```

Or use the AWS Console:
1. Go to: https://console.aws.amazon.com/sns/
2. Click: "Topics" → "algo-algo-alerts-dev"
3. Scroll to "Subscriptions"
4. You should see your email with Status: **Confirmed** (not "PendingConfirmation")

---

## If Email Confirmation Not Found

### Option A: Resend Confirmation Email (via AWS Console)

1. Go to: https://console.aws.amazon.com/sns/
2. Click: "Subscriptions"
3. Find your email subscription in the list
4. Right-click → "Request confirmation"
5. Check your email again (within 5 minutes)

### Option B: Check Terraform State

If the subscription wasn't created at all by Terraform (due to IAM permissions), manually create it:

```bash
# Create email subscription
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:626216981288:algo-algo-alerts-dev \
  --protocol email \
  --notification-endpoint argeropolos@gmail.com
```

This will send the confirmation email.

---

## Test After Confirming

Once subscription is confirmed, test the email alerts:

```bash
# Manually trigger Lambda to send test alert
aws sns publish \
  --topic-arn arn:aws:sns:us-east-1:626216981288:algo-algo-alerts-dev \
  --subject "Test Alert from Cost Circuit Breaker" \
  --message "If you receive this email, SNS alerts are working correctly!"
```

You should receive the email at `argeropolos@gmail.com` within 1-2 minutes.

---

## Also Enable AWS Billing Alerts

For complete cost visibility, enable AWS native billing emails:

1. Go to: https://console.aws.amazon.com/billing/
2. Click: "Billing Preferences" (left sidebar)
3. Enable these checkboxes:
   - ✅ Receive Billing Alerts
   - ✅ Receive Free Tier Alerts
   - ✅ Receive Cost Anomaly Alerts
4. Verify email: `argeropolos@gmail.com`
5. Click: "Save Preferences"

---

## Timeline

- **Terraform Deployed:** 2026-07-11 14:32 UTC
- **Confirmation Email Sent:** ~2026-07-11 14:32 UTC
- **Need Action By:** User must click confirmation link before alerts work
- **Current Status:** Account safe at $15.91/day vs $50 threshold

---

## Checklist for Full Email Alerts

- [ ] Find SNS confirmation email from AWS
- [ ] Click confirmation link in that email
- [ ] Verify email status shows "Confirmed" (not "PendingConfirmation")
- [ ] Test alert sends and arrives at argeropolos@gmail.com
- [ ] Enable AWS Billing Alerts in AWS Console
- [ ] Monitor first 24 hours for incoming alerts

---

## If You Don't See Confirmation Email

**Most common cause:** Email ended up in spam/promotions folder

1. Check Gmail spam folder (if using Gmail)
2. Check "All Mail" or "Archive"
3. Search Gmail for: `from:no-reply@sns.amazonaws.com`
4. If still not found, re-request confirmation via AWS Console

**Alternative:** Use option B above to manually create subscription, which triggers a new confirmation email.

---

**Goal:** ✅ Circuit breaker deployed  
**Remaining:** ⏳ Confirm email subscription (requires 1 click)

After you click the confirmation link, all email alerts will be fully operational!
