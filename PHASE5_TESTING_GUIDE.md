# Phase 5: End-to-End Testing Guide

**Status:** Ready for execution once Phases 1-4 complete  
**Prerequisites:**
- Email verification links clicked (Phase 1)
- Password reset tested (Phase 1)
- New user signup tested (Phase 1)
- SES production access requested (Phase 1)
- Database migration applied (Phase 2)
- API routes updated for user scoping (Phase 3)
- User isolation setup script executed (Phase 4)

**Estimated Time:** 10-15 minutes

## Test Plan Overview

Validate that:
1. ✅ Email delivery works for password reset and signup
2. ✅ Admin user has isolated Alpaca credentials
3. ✅ Admin can trade with their account
4. ✅ New users can create accounts independently
5. ✅ New users have isolated portfolios
6. ✅ New users CANNOT see admin's portfolio
7. ✅ Each user trades independently

## Test Setup

### Prerequisites
- Admin email verified in SES: `argeropolos@gmail.com`
- Frontend deployed: `https://d2u93283nn45h2.cloudfront.net`
- Database migrations applied
- API routes updated for user scoping
- `scripts/setup-user-isolation.ps1` executed successfully

### Test Accounts to Create

**Account 1: Test Trader A**
- Email: `test-trader-a+$(date +%s)@gmail.com` (use Gmail alias)
- Password: (set during signup)
- Expected: New portfolio (empty)

**Account 2: Test Trader B**
- Email: `test-trader-b+$(date +%s)@gmail.com` (use Gmail alias)
- Password: (set during signup)
- Expected: New portfolio (empty)

## Test Scenarios

### Scenario 1: Admin Password Reset
**Objective:** Verify admin can reset password and still has isolated Alpaca access

1. Go to: `https://d2u93283nn45h2.cloudfront.net`
2. Click "Forgot Password"
3. Enter: `argeropolos@gmail.com`
4. Check email for reset code
5. Enter code and set new password
6. Log out
7. Log back in with new password
8. **Verify:** Dashboard shows admin's portfolio

**Expected Outcome:** ✅ Password reset works, portfolio loads

### Scenario 2: New User Signup (Trader A)
**Objective:** Verify new user can sign up with isolated portfolio

1. Go to: `https://d2u93283nn45h2.cloudfront.net`
2. Click "Sign Up"
3. Enter email: `test-trader-a+12345@gmail.com`
4. Set password: `TestPassword123!`
5. Check email for confirmation code
6. Enter code to confirm signup
7. You're now logged in as Trader A
8. **Verify:** Dashboard shows empty portfolio (no admin data visible)

**Expected Outcome:** ✅ Signup works, portfolio is isolated

### Scenario 3: Cross-User Data Isolation
**Objective:** Verify users cannot access each other's data

#### Part A: Trader A Signup and Data
1. (Continuing from Scenario 2)
2. Dashboard should be empty
3. Note down Trader A's Cognito sub (if visible in console logs)

#### Part B: New User Signup (Trader B)
1. Click "Logout"
2. Click "Sign Up"
3. Enter email: `test-trader-b+12345@gmail.com`
4. Set password: `TestPassword123!`
5. Confirm signup via email
6. **Verify:** Dashboard empty (Trader A's data not visible)

#### Part C: Admin Login
1. Click "Logout"
2. Click "Login"
3. Enter: `argeropolos@gmail.com`
4. Enter password
5. **Verify:** Dashboard shows admin's portfolio (not Trader A or B data)

**Expected Outcome:** ✅ Complete isolation - each user sees only their own data

### Scenario 4: Alpaca Isolation Validation
**Objective:** Verify each user has isolated Alpaca trading capability

1. For each test user (Admin, Trader A, Trader B):
   - Check that user-scoped Alpaca secret exists in AWS Secrets Manager
   - Command: `aws secretsmanager get-secret-value --secret-id "algo/alpaca/{cognito-sub}" --region us-east-1`
   - Expected: Success if secret exists

**Expected Outcome:** ✅ All users have isolated Alpaca credentials

### Scenario 5: API Endpoint Isolation
**Objective:** Verify API endpoints respect user isolation

#### Test: `/api/algo/positions` Endpoint
```bash
# Get JWT token for Admin (argeropolos@gmail.com)
ADMIN_JWT=$(get-jwt-token admin@example.com)

# Test 1: Admin should see their positions
curl -H "Authorization: Bearer $ADMIN_JWT" \
  https://d2u93283nn45h2.cloudfront.net/api/algo/positions

# Expected: Admin's positions (or empty if no positions)

# Get JWT token for Trader A
TRADER_A_JWT=$(get-jwt-token test-trader-a@example.com)

# Test 2: Trader A should see their positions (empty)
curl -H "Authorization: Bearer $TRADER_A_JWT" \
  https://d2u93283nn45h2.cloudfront.net/api/algo/positions

# Expected: Empty array (no positions)

# Test 3: Admin token should NOT return Trader A data
# (Verify response is different for each user)
```

**Expected Outcome:** ✅ Each user gets only their own data

## Validation Checklist

### Email & Auth
- [ ] Admin password reset works
- [ ] New user signup works (Trader A)
- [ ] New user signup works (Trader B)
- [ ] Users can login with new accounts
- [ ] Invalid credentials rejected (401)

### Portfolio Isolation
- [ ] Admin dashboard shows admin's portfolio
- [ ] Trader A dashboard is empty (no admin data)
- [ ] Trader B dashboard is empty (no admin data)
- [ ] Admin's portfolio NOT visible to Trader A
- [ ] Admin's portfolio NOT visible to Trader B
- [ ] Trader A cannot see Trader B data

### Alpaca Isolation
- [ ] Admin has `algo/alpaca/{admin-sub}` secret
- [ ] Trader A has `algo/alpaca/{trader-a-sub}` secret (or can be created)
- [ ] Trader B has `algo/alpaca/{trader-b-sub}` secret (or can be created)
- [ ] Each secret contains different API keys (for real users)

### API Isolation
- [ ] `/api/algo/positions` returns different data per user
- [ ] `/api/trades` returns different data per user
- [ ] `/api/algo/portfolio-snapshot` returns different data per user
- [ ] Unauthenticated requests get 401 errors
- [ ] Invalid tokens get 401 errors

### CloudWatch Logs
- [ ] No "Email address is not verified" errors
- [ ] Password reset Lambda shows success
- [ ] Signup Lambda shows success
- [ ] API logs show user_id correctly extracted
- [ ] API logs show queries properly scoped

## Failure Scenarios (What to Check If Tests Fail)

### If Email Not Delivered
- Check: CloudWatch logs → `/aws/lambda/algo-cognito-email-trigger-dev`
- Check: SES console for bounce/complaint
- Verify: Both emails verified in SES
- Verify: SES not in sandbox mode or production access approved

### If User Isolation Fails (Users See Each Other's Data)
- Check: Database migrations applied successfully
- Check: API routes updated with `scope_query()`
- Check: `cognito_sub` column populated in database
- Check: API extracting user_id from JWT correctly

### If Alpaca Isolation Fails (Wrong Credentials Used)
- Check: `scripts/setup-user-isolation.ps1` completed successfully
- Check: User-specific secrets created in Secrets Manager
- Check: Credential manager updated to accept user_id parameter
- Check: API calling `get_alpaca_credentials(user_id=user_id)`

## Success Criteria

✅ **FULL NEW USER SUPPORT WORKING** when:
1. At least 2 new test users can sign up independently
2. Each user has isolated portfolio (empty, no admin data visible)
3. Email verification and password reset work
4. No cross-user data access possible
5. CloudWatch logs show no errors
6. All checklist items marked complete

## Rollback Plan

If any test fails:
1. Check error details in CloudWatch logs
2. Identify which component failed
3. Fix the component
4. Re-run affected test scenarios
5. If major issues, can revert to shared-account mode by:
   - Setting `user_id = "admin-user"` in all queries (temporary)
   - Skipping database migration (keeps old schema)

## Post-Testing Actions

Once all tests pass:
1. ✅ Delete test user accounts (keep admin)
2. ✅ Document in `steering/algo.md`:
   - New user support enabled
   - Per-user Alpaca account isolation working
   - How to create new users
3. ✅ Update onboarding guide for new users
4. ✅ Ready for real user invitations

---

**Status: READY FOR EXECUTION**

All infrastructure is in place. Once email links are clicked and API routes are updated, run this test plan to validate complete new user support.
