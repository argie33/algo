# New User Support - Complete Workflow

## Timeline
- **NOW:** GitHub Actions Terraform deployment in progress (~10-15 min)
- **STEP 1:** Deploy completes → Verify SES emails (~2 min)
- **STEP 2:** Check email inboxes for AWS verification links (~2 min)
- **STEP 3:** Click verification links in emails (~1 min)
- **STEP 4:** Test password reset flow (~3 min)
- **STEP 5:** Test signup flow (~3 min)
- **STEP 6:** Request SES production access (~2 min)

**Total: ~25 minutes to get password reset + signup working for any user**

---

## STEP 1: Deploy SES Permissions (When GitHub Actions Completes)

**Goal:** Grant algo-developer user SES permissions to verify emails

**What's happening:**
- GitHub Actions is deploying Terraform changes
- New IAM policy adds SES permissions to algo-developer user
- Once complete, we can verify emails programmatically

**Monitor deployment:**
```powershell
# Check status
gh run view --repo argie33/algo 26859573339 --json status

# Watch logs (when complete)
gh run view --repo argie33/algo 26859573339 --log
```

**Expected output:** `"status":"completed"` and `"conclusion":"success"`

---

## STEP 2: Verify SES Emails (Run After Deploy Completes)

**Goal:** Verify sender and recipient emails in SES

**Command:** Run this PowerShell script
```powershell
scripts/verify-ses-emails-and-test.ps1
```

**What it does:**
1. Verifies `noreply@bullseyetrading.com` (sender)
2. Verifies `argeropolos@gmail.com` (recipient)
3. Lists all verified identities

**Expected output:**
```
✓ Verification request sent to noreply@bullseyetrading.com
  → Check noreply@bullseyetrading.com inbox for AWS verification email
  → Click the verification link to confirm

✓ Verification request sent to argeropolos@gmail.com
  → Check argeropolos@gmail.com inbox for AWS verification email
  → Click the verification link to confirm
```

---

## STEP 3: Verify Emails (Check Inboxes)

**Goal:** Confirm email verification links and complete verification

### For Sender Email (noreply@bullseyetrading.com)

**Check:** noreply@bullseyetrading.com inbox
- Look for email from: AWS Notifications <no-reply@sns.amazonaws.com>
- Subject: AWS Notification - Subscription Confirmation
- Click: Verification link in email
- Expected: AWS confirms email is verified

**Note:** If you don't own this domain, you can:
- Use a different sender (e.g., your Gmail)
- Update terraform.tfvars: `cognito_sender_email = "your-email@gmail.com"`
- Re-deploy

### For Recipient Email (argeropolos@gmail.com)

**Check:** argeropolos@gmail.com inbox (Gmail)
- Look for email from: AWS Notifications <no-reply@sns.amazonaws.com>
- Subject: AWS Notification - Subscription Confirmation
- Click: Verification link (will open AWS console)
- Expected: AWS confirms email is verified

---

## STEP 4: Test Password Reset Flow

**Goal:** Verify password reset emails are sent and received

### Manual Test (via Frontend)

**Open:** https://d2u93283nn45h2.cloudfront.net

1. Click **Login**
2. Click **Forgot Password**
3. Enter: `argeropolos@gmail.com`
4. Click **Send Code**

**Check:**
- Frontend shows: "Reset code sent — check your email"
- Gmail inbox receives email with subject: "Reset Your Bullseye Trading Password"
- Email contains: 6-digit password reset code
- Enter code in frontend to set new password

**CloudWatch Logs:**
```powershell
# View Lambda logs
aws logs tail /aws/lambda/algo-cognito-email-trigger-dev --follow --region us-east-1

# Look for: 
# - "CustomMessage_ForgotPassword for user argeropolos@gmail.com"
# - "Email sent successfully to argeropolos@gmail.com"
```

---

## STEP 5: Test New User Signup Flow

**Goal:** Verify new users can signup and receive confirmation emails

### Manual Test (via Frontend)

**Open:** https://d2u93283nn45h2.cloudfront.net

1. Click **Sign Up**
2. Enter test email: `test+$(date +%s)@gmail.com` (use your Gmail with +alias)
3. Set password (12+ chars, upper, lower, number, symbol)
4. Click **Create Account**

**Check:**
- Frontend shows: "Confirmation code sent to test+...@gmail.com"
- Email inbox receives verification code
- Enter code in frontend to complete signup
- New user can now login

**CloudWatch Logs:**
```powershell
aws logs tail /aws/lambda/algo-cognito-email-trigger-dev --follow --region us-east-1

# Look for:
# - "CustomMessage_SignUp for user test+...@gmail.com"
# - "Email sent successfully to test+...@gmail.com"
```

**Test with Multiple Emails:**
```powershell
# Use Gmail's email aliasing feature to test multiple accounts
test+1@gmail.com
test+2@gmail.com
test+3@gmail.com

# All will deliver to your main inbox
```

---

## STEP 6: Request SES Production Access

**Goal:** Lift SES sandbox restrictions to support unlimited new users

### Option A: AWS Console (Easiest)

**Open:** https://console.aws.amazon.com/ses/home?region=us-east-1

1. Go to **Account provisioning** (in left sidebar under "Sending Limits")
2. Click **"Request production access"** (or "Request sending limit increase")
3. Fill out form:
   - **Use case description:** "Authentication and user password reset emails for stock trading platform"
   - **Website URL:** https://d2u93283nn45h2.cloudfront.net
   - **Requestor email:** argeropolos@gmail.com
   - **How often do you plan to send?** "Several times per user per year (password resets)"
   - **Percent of emails are marketing?** 0% (all are transactional)
4. Click **Submit request**

**Expected:** AWS approves in ~24 hours (usually 1-2 hours)

### Option B: AWS CLI

```powershell
# Check current SES sandbox status
aws ses get-account-sending-enabled --region us-east-1

# After production access granted, verify with:
aws ses list-identities --region us-east-1
```

---

## Verification Checklist

After completing all steps:

### Email Infrastructure
- [ ] Sender email (`noreply@bullseyetrading.com`) verified in SES
- [ ] Recipient email (`argeropolos@gmail.com`) verified in SES
- [ ] CloudWatch logs show successful Lambda invocations
- [ ] No SES errors in Lambda logs

### Password Reset Flow
- [ ] Can trigger password reset from frontend
- [ ] Receive password reset email in inbox
- [ ] Code works and password can be changed
- [ ] New password allows login

### Signup Flow
- [ ] Can signup with new email from frontend
- [ ] Receive signup confirmation email
- [ ] Code works and account is created
- [ ] New account can login

### Production Readiness
- [ ] SES production access approved (or pending)
- [ ] **[NEXT PHASE]** Alpaca account isolation implemented
- [ ] **[NEXT PHASE]** New users cannot see admin portfolio
- [ ] Ready to invite real users

---

## Troubleshooting

### Issue: "Email address is not verified"
**Cause:** Email not yet verified in SES
**Fix:** 
1. Check email inbox for AWS verification link
2. Click link to confirm
3. Retry

### Issue: No email received
**Check:**
1. Gmail spam folder (check filters)
2. CloudWatch logs for Lambda errors: `/aws/lambda/algo-cognito-email-trigger-dev`
3. SES sending statistics: `aws ses get-send-statistics --region us-east-1`

### Issue: Lambda error in CloudWatch
**Common errors:**
- `MessageRejected: Email address is not verified` → Emails not verified (see Step 3)
- `AccessDeniedException: ses:SendEmail` → IAM permissions not updated (wait for deploy, refresh credentials)
- `MessageRejected: Daily rate exceeded` → Hit SES sandbox rate limit (5 emails/day per domain)

### Issue: Forgot Password button doesn't work
**Check:**
1. Frontend is deployed: https://d2u93283nn45h2.cloudfront.net
2. API is accessible: `curl https://d2u93283nn45h2.cloudfront.net/api/health`
3. Cognito pool is accessible: `aws cognito-idp describe-user-pool --user-pool-id us-east-1_XJpLb9SKX --region us-east-1`

---

## Commands Reference

```powershell
# Check deployment status
gh run view --repo argie33/algo 26859573339 --json status

# Verify emails (after deploy)
scripts/verify-ses-emails-and-test.ps1

# Check verified identities
aws ses list-identities --region us-east-1

# View Lambda logs
aws logs tail /aws/lambda/algo-cognito-email-trigger-dev --follow --region us-east-1

# Check SES stats
aws ses get-send-statistics --region us-east-1

# Check Cognito user pool
aws cognito-idp describe-user-pool --user-pool-id us-east-1_XJpLb9SKX --region us-east-1

# List Cognito users
aws cognito-idp list-users --user-pool-id us-east-1_XJpLb9SKX --region us-east-1
```

---

## Next Phase: Alpaca Account Isolation

Once password reset and signup flows work, implement per-user Alpaca isolation:

See: `ALPACA_USER_ISOLATION.md`

**Summary:**
1. Store each user's Alpaca keys in Secrets Manager (scoped by user)
2. Update credential manager to fetch user-specific keys
3. Update orchestrator and API to use user-scoped credentials
4. Verify new users cannot access admin's portfolio

**Timeline:** ~2 weeks to full isolation
