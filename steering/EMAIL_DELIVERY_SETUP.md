# Password Reset Email Setup Guide

This guide walks you through enabling password reset emails so users can receive reset codes and manage passwords independently.

## Current Status

✓ **Frontend:** Password reset UI complete (login → Forgot password? → email input → reset code + password form)  
✓ **Backend:** AWS Cognito + Lambda custom email trigger configured  
❌ **Email Delivery:** BLOCKED by AWS SES sandbox restrictions

## The Problem

AWS SES starts in **sandbox mode** to prevent abuse. In sandbox mode:
- ✓ Can send emails from verified sender addresses
- ✗ Can ONLY send to pre-verified recipient addresses
- ✗ Cannot send to new/unverified users

**Result:** Password reset codes don't reach users because they're not yet in the verified recipient list.

## Solution: 3 Steps to Enable Email

### Step 1: Verify Sender Email (1 minute)

The custom Lambda sends emails from `noreply@bullseyetrading.com`. This address must be verified in SES.

**In AWS Console:**
1. Go to **SES** → **Verified senders**
2. Click **Create identity** → **Email address**
3. Enter: `noreply@bullseyetrading.com`
4. Check your email for verification link
5. Click the link to verify

**Verify it worked:** You should see `noreply@bullseyetrading.com` with status **Verified**

### Step 2: Verify Test Recipients (Dev - 2 minutes)

While in sandbox mode, add your email so you can test password resets.

**In AWS Console:**
1. Go to **SES** → **Verified senders**
2. Click **Create identity** → **Email address**
3. Enter your email (e.g., `argeropolos@gmail.com`)
4. Check email for verification link and click it

**Test password reset:**
1. Go to http://localhost:5173/login
2. Click **"Forgot password?"**
3. Enter your verified email
4. Click **"Send Reset Code"**
5. Check email inbox → You should receive code in 30 seconds!

### Step 3: Request SES Production Access (Production - 24 hours)

To send to ANY user (not just verified ones), request production access.

**In AWS Console:**
1. Go to **SES** → **Account dashboard**
2. Click **"Request production access"** or find **"Send limit"** section
3. Fill form:
   - **Use case:** "Authentication and user password reset emails"
   - **Daily limit:** 50,000
   - **Email type:** Transactional
4. Click **Submit**
5. **AWS approves within 24 hours** (usually same day)

After approval, SES can send to any email without whitelist.

## Key Files

- Frontend: `webapp/frontend/src/components/auth/ForgotPasswordForm.jsx`
- Email Lambda: `lambda/cognito-email-trigger/lambda_function.py`
- Cognito config: `terraform/modules/cognito/main.tf`
- Settings: `terraform/terraform.tfvars` (line 41)

## Troubleshooting

**Email not arriving?**
1. Check AWS Console → SES → Verified senders → Is sender verified?
2. Check AWS Console → SES → Verified senders → Is recipient verified? (sandbox only)
3. Check email spam folder
4. Check CloudWatch: `/aws/lambda/algo-cognito-email-trigger-dev` for errors
