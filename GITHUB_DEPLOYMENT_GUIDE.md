# GitHub Deployment & Monitoring Guide

**Status:** ✅ Commit Ready - Waiting for Push
**Commit:** `ce50fa060`
**Date:** 2026-02-26

---

## 🚀 How to Push (Choose ONE Method)

### Method 1: Windows PowerShell (RECOMMENDED)

```powershell
# Open PowerShell on your Windows machine
cd C:\path\to\algo
git push origin main
```

Expected output:
```
Counting objects: 3, done.
Delta compression using up to 8 threads.
Total 3 (delta 2), reused 0 (delta 0)
remote: Resolving deltas: 100% (2/2), done.
To https://github.com/argie33/algo.git
   8203ad864..ce50fa060  main -> main
```

### Method 2: VS Code

1. Open VS Code with `/home/arger/algo` folder
2. Press `Ctrl+Shift+G` (Source Control)
3. Click three dots (`⋮`)
4. Select "Push"

### Method 3: GitHub Desktop

1. Open GitHub Desktop
2. Find "algo" repository in the list
3. Click "Publish branch" or "Push to origin"
4. Wait for completion

### Method 4: AWS CloudShell (No Local Git Needed)

```bash
# From AWS Console, open CloudShell
git clone https://github.com/argie33/algo.git
cd algo
git push origin main
```

### Method 5: Git Credential Helper (WSL2 Only)

```bash
git config --global credential.helper cache
git push origin main
# Enter GitHub username and personal access token when prompted
```

---

## 📊 What's Being Pushed

**Commit:** `ce50fa060`

### Changes:

```yaml
template-webapp-lambda.yml:
  - Lambda timeout: 60s → 300s
  - Lambda memory: 128MB → 512MB
  - Reserved concurrency: added (10)

webapp/lambda/utils/database.js:
  - Connection pool max: 3 → 10
  - Connection pool min: 1 → 2
```

### Why These Changes:

- **Timeout 60s → 300s**: Complex database queries need more time
- **Memory 128MB → 512MB**: Express.js + database drivers require resources
- **Connection pool 3 → 10**: Match Lambda concurrency, prevent exhaustion
- **Reserved concurrency 10**: Prevents overwhelming the database

---

## 🔍 Monitor Deployment After Push

### Step 1: Watch GitHub Actions

**URL:** https://github.com/argie33/algo/actions

1. Click on the latest workflow run (should say "deploy-webapp")
2. Watch for these jobs to pass:
   - ✓ Setup environment
   - ✓ Detect changed components
   - ✓ Deploy webapp infrastructure
   - ✓ Deploy Frontend to S3
   - ✓ Deploy Admin Frontend to S3
   - ✓ Verify deployment

**Timeline:**
- Build: ~2 minutes
- Deploy: ~3 minutes
- Frontend: ~2 minutes
- Total: ~5-10 minutes

### Step 2: Check Logs for Errors

Click on any failed job to see error details. Look for:

**Common Success Indicators:**
```
✅ SAM deployment completed successfully
✅ Stack outputs retrieved successfully
✅ Frontend build completed
✅ Frontend deployed to S3
✅ CloudFront invalidation created
```

**Common Error Indicators:**
```
❌ SAM deployment failed
❌ Stack is in non-deployable state
❌ Failed to get stack outputs
❌ Build failed
```

### Step 3: Verify Lambda Deployment

```bash
# Test the health endpoint (from any machine with internet)
curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health

# Expected response:
# {"success": true, "data": {"status": "healthy", ...}}
```

### Step 4: Check CloudWatch Logs

**AWS Console → CloudWatch → Log Groups**

Look for: `/aws/lambda/stocks-webapp-dev-*`

Expected to see:
- Successful Lambda invocations
- Database connections established
- Request processing logs

---

## 🔴 Troubleshooting Deployment Failures

### Issue 1: CloudFormation Stack Error

**In GitHub Actions Log:**
```
❌ Stack is in non-deployable state: ROLLBACK_COMPLETE
```

**Solution:**
1. AWS Console → CloudFormation → Stacks → stocks-webapp-dev
2. Delete the failed stack
3. Re-run GitHub Actions workflow (click "Re-run jobs")

### Issue 2: SAM Build Failed

**In GitHub Actions Log:**
```
❌ sam build --template template-webapp-lambda.yml failed
```

**Solution:**
1. Check Node.js version compatibility
2. Verify `template-webapp-lambda.yml` syntax
3. Check `webapp/lambda/package.json` for invalid entries

**To fix:**
```bash
cd /home/arger/algo/webapp/lambda
npm ci
npm run build  # or whatever build script exists
```

### Issue 3: Frontend Build Failed

**In GitHub Actions Log:**
```
❌ npm run build failed
```

**Solution:**
1. Check Node.js version (should be 20.x)
2. Verify frontend dependencies
3. Check for TypeScript errors

**To fix:**
```bash
cd /home/arger/algo/webapp/frontend
npm ci
npm run build
```

### Issue 4: Database Secret Access Failed

**In GitHub Actions Log:**
```
❌ Failed to get database secret ARN from app stack exports
```

**Solution:**
1. Verify `stocks-app-dev` CloudFormation stack exists
2. Check that stack has outputs: `StocksApp-SecretArn`, `StocksApp-DBEndpoint`
3. Verify Lambda execution role has Secrets Manager permissions

**Check stack exports:**
```bash
aws cloudformation list-exports --region us-east-1 | grep StocksApp
```

---

## ✅ Deployment Complete Checklist

After deployment succeeds, verify:

- [ ] GitHub Actions workflow shows all green checkmarks
- [ ] CloudFormation stack status: `UPDATE_COMPLETE` or `CREATE_COMPLETE`
- [ ] Lambda function exists: `stocks-webapp-api-dev`
- [ ] API Gateway stage created: `dev`
- [ ] CloudFront distribution is enabled
- [ ] S3 bucket has frontend files
- [ ] Health endpoint returns 200 response

---

## 🔧 Rollback If Needed

If deployment causes problems:

```bash
# Revert the commit
git reset --hard HEAD~1

# Push to GitHub (triggers rollback deployment)
git push origin main -f
```

This will:
1. Remove the fix commit
2. Re-deploy the previous version
3. Restore previous Lambda configuration

---

## 📝 Next Steps After Successful Deployment

1. **Load Data** (45-60 minutes)
   ```bash
   bash /tmp/run_critical_loaders.sh
   ```

2. **Verify API** (5 minutes)
   ```bash
   curl https://jh28jdhp01.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=10
   ```

3. **Visit Frontend**
   ```
   https://stocks-webapp-frontend-dev-626216981288.cloudfront.net
   ```

---

## 🆘 Getting Help

If deployment fails:

1. Check GitHub Actions logs (most detailed)
2. Check CloudFormation events (AWS Console)
3. Check CloudWatch logs (Lambda execution logs)
4. Check Secrets Manager (database credentials)

All logs should show specific error messages with solutions.

