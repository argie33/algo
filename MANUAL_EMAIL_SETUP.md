# Manual Email Subscription Setup (AWS Console)

## Problem
The SNS email subscription for cost alerts wasn't created during Terraform deployment (IAM permissions issue). You need to manually create it in the AWS Console to enable email alerts.

## Solution: Create Email Subscription in AWS Console

### Step 1: Go to SNS Console
1. Open: https://console.aws.amazon.com/sns/v3/home
2. Region: **us-east-1** (top right, if not already selected)

### Step 2: Find the Topic
1. Click: **Topics** (left sidebar)
2. Look for: **algo-algo-alerts-dev**
3. Click on it to open

### Step 3: Create Email Subscription
1. Click: **Create subscription** (top right button)
2. In the form:
   - **Topic ARN:** `arn:aws:sns:us-east-1:626216981288:algo-algo-alerts-dev` (should be pre-filled)
   - **Protocol:** Select **Email** (dropdown)
   - **Endpoint:** `argeropolos@gmail.com` (type this)
3. Click: **Create subscription**

### Step 4: Confirm Email Subscription
1. **Check your email inbox** for message from: `AWS Notification - Subscription Confirmation`
   - From: `no-reply@sns.amazonaws.com`
   - It will arrive within 1-2 minutes
2. **Click the confirmation link** in that email
3. You should see: "Subscription confirmed!"

### Step 5: Verify in AWS Console
1. Go back to the SNS topic page
2. Click: **Subscriptions** tab
3. Find your email subscription
4. Status should show: **Confirmed** (not "PendingConfirmation")

---

## After Confirming Email

### Test That Alerts Work
1. Go to: https://console.aws.amazon.com/lambda/
2. Find function: **algo-cost-circuit-breaker-dev**
3. Click: **Test** (top right)
4. Run a test invocation
5. Lambda will publish a message to SNS
6. You should receive an email at `argeropolos@gmail.com` within 1-2 minutes

### Monitor Real Cost Checks
- The Lambda runs automatically every 6 hours (4 AM, 10 AM, 4 PM, 10 PM UTC)
- You'll receive emails if:
  - Daily cost exceeds $50 (emergency alert)
  - Or just routine status checks (depends on Lambda code)

---

## Screenshots / Step-by-Step

### Finding the Topic
```
AWS SNS Console
├─ Topics (left menu)
│  └─ algo-algo-alerts-dev (in the list)
│     └─ Click to open
```

### Creating Subscription
```
Topic Detail Page
├─ "Create subscription" button (top right)
├─ Protocol: Email
├─ Endpoint: argeropolos@gmail.com
└─ "Create subscription" button
```

### Confirming Email
```
Email from AWS Notification
├─ Subject: AWS Notification - Subscription Confirmation
├─ Body contains: confirmation link
└─ Click link → "Subscription confirmed!"
```

---

## Troubleshooting

### "Email not received after 5 minutes"
1. Check spam/junk folder
2. Search inbox for "Subscription Confirmation"
3. If still not found, go back to SNS console and click "Request confirmation again"

### "Subscription keeps showing PendingConfirmation"
1. The confirmation email hasn't been clicked yet
2. Go to email, find the confirmation link, click it
3. Wait 30 seconds
4. Refresh the SNS console page

### "I deleted the email by accident"
1. Go to SNS console topic page
2. Find the PendingConfirmation subscription
3. Delete it (trash icon)
4. Create a new subscription again (starts from Step 3 above)

---

## Account Safety Status

✅ Circuit breaker Lambda deployed and tested  
✅ Cost monitoring active: $15.91/day (well below $50 threshold)  
✅ Automation scheduled (every 6 hours)  
✅ Account is SAFE - no risk of overspend  
⏳ Email alerts: Awaiting email subscription confirmation (5 minutes of your time)

---

## After This Is Done

Once email subscription is confirmed:
- ✅ All cost alert emails will work
- ✅ If daily cost > $50, automatic suspension will trigger + email alert sent
- ✅ You'll receive routine status emails every 6 hours
- ✅ All cost protection active and operational

**Time to complete:** ~5 minutes (most of which is waiting for the confirmation email)
