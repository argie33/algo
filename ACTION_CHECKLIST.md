# 📋 AWS Deployment Action Checklist

**Status:** Code Ready | Commit: ce50fa060 | Last Updated: 2026-02-26

---

## ✅ PHASE 1: Push to GitHub (Do This First)

### Before Push
- [ ] Read this entire checklist
- [ ] Review FIX_SUMMARY.md for context
- [ ] Ensure you have GitHub credentials available
- [ ] Choose ONE push method from below

### Push Methods (Choose ONE)

#### Method A: Windows PowerShell ⭐ EASIEST
```powershell
cd C:\path\to\algo
git push origin main
```
- [ ] Opened PowerShell
- [ ] Navigated to repo
- [ ] Ran push command
- [ ] Saw "main -> main" in output

#### Method B: VS Code
```
Ctrl+Shift+G → Click ⋮ → "Push"
```
- [ ] Opened VS Code
- [ ] Opened Source Control panel
- [ ] Clicked push option
- [ ] Saw confirmation

#### Method C: GitHub Desktop
```
Select repo → Click "Push to origin"
```
- [ ] Opened GitHub Desktop
- [ ] Found "algo" repository
- [ ] Clicked push button
- [ ] Saw completion message

#### Method D: AWS CloudShell
```bash
git clone https://github.com/argie33/algo.git && cd algo
git push origin main
```
- [ ] Opened AWS Console
- [ ] Opened CloudShell
- [ ] Ran clone and push commands
- [ ] Saw successful push message

#### Method E: WSL2 with Credentials
```bash
git config --global credential.helper store
git push origin main
# Enter GitHub username and token
```
- [ ] Configured credential helper
- [ ] Ran push command
- [ ] Entered credentials when prompted
- [ ] Saw successful push message

### Verification
- [ ] Command completed without errors
- [ ] Output shows: `main -> main` or `updated main`
- [ ] No authentication errors
- [ ] Return code: 0 (success)

---

## 📊 PHASE 2: Monitor GitHub Actions (5-10 Minutes)

### During Deployment

1. [ ] Visit GitHub Actions
   - URL: https://github.com/argie33/algo/actions
   - Look for: "deploy-webapp" workflow
   - Status: Should show recent run

2. [ ] Watch Workflow Jobs
   - [ ] `setup` - Environment setup → Should complete (✅ or ❌)
   - [ ] `filter` - Detect changes → Should complete (✅ or ❌)
   - [ ] `deploy_infrastructure` - Lambda & API → Should complete
   - [ ] `deploy_frontend` - React build & deploy → Should complete
   - [ ] `deploy_frontend_admin` - Admin build & deploy → Should complete
   - [ ] `verify_deployment` - Health checks → Should complete

3. [ ] Check Logs
   - Click on any red ❌ job to see error details
   - Look for specific error messages
   - Note any failures for troubleshooting

4. [ ] Wait for Completion
   - Expected time: 5-10 minutes
   - Refresh page every 1-2 minutes
   - Watch for all jobs to show green ✅ or red ❌

### Expected Success
- [ ] All jobs show ✅ (green checkmarks)
- [ ] No red ❌ failures
- [ ] Workflow shows "completed" status
- [ ] Total time: < 15 minutes

### If Failed
- [ ] Note which job failed
- [ ] Check the error message
- [ ] See TROUBLESHOOTING section below

---

## 🔍 PHASE 3: Verify Lambda Deployment

### AWS Console Checks

1. [ ] Check CloudFormation Stack
   - Go to: AWS Console → CloudFormation
   - Stack: `stocks-webapp-dev`
   - Status should be: `CREATE_COMPLETE` or `UPDATE_COMPLETE`
   - If `ROLLBACK_COMPLETE`: Stack failed (see troubleshooting)

2. [ ] Check Lambda Function
   - Go to: AWS Console → Lambda
   - Function: `stocks-webapp-api-dev`
   - Configuration tab:
     - [ ] Memory: **512 MB** (verify NOT 128 MB)
     - [ ] Timeout: **300 seconds** (verify NOT 60 seconds)
     - [ ] Handler: index.handler
     - [ ] Runtime: nodejs18.x or nodejs20.x

3. [ ] Check Environment Variables
   - Go to: Lambda → Function → Configuration → Environment variables
   - [ ] DB_SECRET_ARN: Should have a value
   - [ ] DB_ENDPOINT: Should have a value
   - [ ] ENVIRONMENT: Should be "dev"
   - [ ] COGNITO_USER_POOL_ID: Should have a value
   - [ ] COGNITO_CLIENT_ID: Should have a value

4. [ ] Check CloudWatch Logs
   - Go to: AWS Console → CloudWatch → Log Groups
   - Look for: `/aws/lambda/stocks-webapp-dev-*`
   - [ ] Logs exist (not empty)
   - [ ] Recent entries show (last 1 hour)
   - [ ] Look for successful invocations
   - [ ] No ERROR or FATAL messages

### API Health Test
```bash
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health
```
- [ ] Executed curl command
- [ ] Got response (not timeout)
- [ ] Response code: 200 (not 502, 504, etc.)
- [ ] Response includes: `{"success": true, "data": {...}}`

---

## 🔴 PHASE 4: Troubleshooting (If Needed)

### Issue: GitHub Actions "No changes detected"
- [ ] Go to GitHub Actions page
- [ ] Find the failed workflow
- [ ] Click three dots → "Re-run jobs"
- [ ] Wait for new run to complete

### Issue: CloudFormation Stack Failed
- [ ] Go to AWS Console → CloudFormation
- [ ] Find `stocks-webapp-dev` stack
- [ ] Right-click → "Delete Stack"
- [ ] Wait for deletion
- [ ] Go to GitHub Actions → Re-run workflow
- [ ] Wait for new deployment

### Issue: Lambda Memory/Timeout Not Updated
- [ ] Deployment may have failed silently
- [ ] Check CloudFormation Events tab for errors
- [ ] Check GitHub Actions logs for SAM deployment errors
- [ ] Retry entire deployment if necessary

### Issue: API Returns 502/504 Errors
- [ ] Check CloudWatch logs for error messages
- [ ] Common causes:
  - [ ] Database unreachable (check Secrets Manager)
  - [ ] Timeout too short (but we fixed this to 300s)
  - [ ] Lambda not deployed with fixes
- [ ] Verify Lambda memory and timeout were updated

### Issue: Database Secret Access Failed
- [ ] Check that `stocks-app-dev` stack exists
- [ ] Verify it has outputs: StocksApp-SecretArn
- [ ] Check Lambda execution role has permissions
- [ ] CloudFormation Events tab will show errors

---

## ✅ PHASE 5: Verify Deployment Success

All items in this section should show ✅ (green checks):

### GitHub Actions
- [ ] All workflow jobs show green checkmarks ✅
- [ ] No red ❌ failed jobs
- [ ] Workflow completed in < 15 minutes
- [ ] Latest run shows recent timestamp

### CloudFormation
- [ ] Stack `stocks-webapp-dev` exists
- [ ] Stack status: CREATE_COMPLETE or UPDATE_COMPLETE
- [ ] No ROLLBACK or FAILED states
- [ ] Outputs are populated

### Lambda Function
- [ ] Function `stocks-webapp-api-dev` exists
- [ ] Memory: 512 MB (not 128 MB)
- [ ] Timeout: 300 seconds (not 60 seconds)
- [ ] Environment variables all set
- [ ] Recent invocations show success

### API Endpoint
- [ ] Health endpoint responds: 200 OK
- [ ] Response JSON includes: `"success": true`
- [ ] No timeout errors
- [ ] No connection errors

### CloudWatch
- [ ] Logs exist for the function
- [ ] Recent logs show successful invocations
- [ ] No ERROR, FATAL, or TIMEOUT messages
- [ ] Shows database connection messages

### Summary
- [ ] ALL items above are checked ✅
- [ ] NO items show ❌ or ⚠️
- [ ] Deployment is SUCCESSFUL ✅

---

## 🚀 PHASE 6: Load Data (Next Step)

After verification is complete:

```bash
cd /home/arger/algo
bash /tmp/run_critical_loaders.sh
```

### Data Loading Checklist
- [ ] Stock symbols loader completed
- [ ] Price daily loader completed  
- [ ] Technical indicators loader completed
- [ ] Buy/sell signals loader completed
- [ ] Stock scores loader completed
- [ ] Total time: 45-60 minutes
- [ ] All loaders showed SUCCESS

### Verify Data Loaded
```bash
psql -h localhost -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM stock_symbols;"
```
- [ ] Result: 5000+ (not 0)
- [ ] Database has data ✅

---

## 🎯 PHASE 7: Final Verification

After data loading:

```bash
# Test API with data
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=10"
```
- [ ] Returns JSON array of stocks
- [ ] Stocks include scores and data
- [ ] Response is 200 OK

### Visit Frontend
```
https://stocks-webapp-frontend-dev-626216981288.cloudfront.net
```
- [ ] Frontend loads without errors
- [ ] Dashboard displays stocks
- [ ] Charts render correctly
- [ ] Scores are visible
- [ ] Signals are shown

---

## ✨ COMPLETION CHECKLIST

All of these should be checked ✅:

- [ ] Code pushed to GitHub ✅
- [ ] GitHub Actions deployment succeeded ✅
- [ ] Lambda memory: 512 MB ✅
- [ ] Lambda timeout: 300 seconds ✅
- [ ] API health endpoint responds ✅
- [ ] CloudWatch logs show success ✅
- [ ] Data loaders completed ✅
- [ ] Database has 5000+ stocks ✅
- [ ] API returns stock data ✅
- [ ] Frontend loads and displays data ✅

### 🎉 IF ALL BOXES ARE CHECKED:

**YOUR PLATFORM IS FULLY OPERATIONAL!**

- Stock data is live
- API is responding
- Frontend is functional
- Database is populated
- All fixes are deployed

---

## 📞 Need Help?

**Stuck on:**
- Pushing to GitHub → Read: `PUSH_AND_DEPLOY.sh`
- Monitoring deployment → Read: `GITHUB_DEPLOYMENT_GUIDE.md`
- Understanding fixes → Read: `FIX_SUMMARY.md`
- Loading data → See: `/tmp/run_critical_loaders.sh`
- Any issue → Check: `AWS_FIXES_AND_NEXT_STEPS.md`

---

**Created:** 2026-02-26
**Commit:** ce50fa060
**Status:** ✅ Ready to deploy
