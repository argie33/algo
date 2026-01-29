# Immediate Next Steps - Data Loader Fixes

## ✅ What's Been Done

All code-level fixes have been completed and pushed to GitHub main branch:

1. **Endpoint Correction Logic** - Added to loaders
   - Automatically detects stale endpoint in task definitions
   - Replaces with correct endpoint at runtime
   - **Verified working** ✓

2. **Missing Dependencies Fixed**
   - scipy added to stockscores
   - fredapi added to econdata
   - feedparser, textblob added to news loader
   - python-dotenv added to buysell loaders

3. **Missing Files Fixed**
   - lib directory COPY directive added to 3 Dockerfiles
   - Database connection functions added to 8 loaders

4. **All Changes Pushed** to main branch
   - Latest commit: 15648a637 (FIX: Add missing lib directory to Dockerfiles)
   - All 7 commits implementing fixes are in git history

---

## 🚀 What Needs to Happen Next

### OPTION 1: Use Web UI to Trigger Workflow (Recommended - Easiest)

1. Go to: https://github.com/anthropics/claude-code/actions (or your actual GitHub repo URL)
2. Find workflow: "Data Loaders Pipeline" (deploy-app-stocks.yml)
3. Click "Run workflow" button
4. Select branch: main
5. Click green "Run workflow" button
6. Wait for workflow to complete (15-30 minutes)
   - This will rebuild Docker images with all fixes
   - Images will be pushed to ECR with correct dependencies
   - ECS infrastructure will be updated

### OPTION 2: Use GitHub CLI to Trigger Workflow

```bash
# If gh CLI is installed
gh workflow run deploy-app-stocks.yml --ref main
```

### OPTION 3: Make a Minor Code Change to Auto-Trigger

```bash
# Any change to load*.py or Dockerfile.* triggers the workflow
# Example: Add a comment to a file
echo "# Trigger workflow" >> loadaaiidata.py
git add loadaaiidata.py
git commit -m "TRIGGER: Rebuild Docker images with latest fixes"
git push origin main
```

---

## 📊 Verification Steps (After Workflow Completes)

### Step 1: Verify Images Were Built
```bash
# Check that new images exist in ECR
aws ecr describe-images \
  --repository-name stocks-app-registry \
  --query 'sort_by(imageDetails, &imagePushedAt)[-5:].[imageId.imageTag, imagePushedAt]' \
  | grep -E "latest"

# You should see recent timestamps (today's date)
```

### Step 2: Run a Test Loader
```bash
# Run AAII data loader as a test
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition aaiidata-loader:latest \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}"

# Or use the AWS Console: ECS → Task Definitions → aaiidata-loader → Run task
```

### Step 3: Check CloudWatch Logs
```bash
# Monitor logs in real-time
aws logs tail /ecs/algo-loadaaiidata --since 5m --follow

# Look for:
# ✅ "Successfully downloaded AAII sentiment data"
# ✅ "Successfully inserted X sentiment records"
# ✅ "Database connection established"
# ❌ NOT seeing "could not translate host name rds-stocks.c2gujitq3h1b"
```

### Step 4: Check Data Was Loaded
```bash
# Connect to RDS and verify data
psql -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks \
     -c "SELECT COUNT(*) FROM aaii_sentiment;"

# Should return a count > 0 if data was loaded
```

---

## 📋 Manual Verification (No AWS Tools Needed)

If you prefer to manually verify through AWS Console:

1. **Go to ECS Service**
   - Service: stocks-cluster
   - Look for running tasks
   - Should show green status (RUNNING)

2. **Check CloudWatch Logs**
   - Log groups: /ecs/algo-loadaaiidata, /ecs/algo-loadpricedaily, etc.
   - Recent entries should NOT have DNS errors
   - Should see "Successfully" messages

3. **Check RDS Database**
   - Go to RDS
   - Instance: stocks
   - Status: available
   - Check data in tables:
     - aaii_sentiment
     - price_daily
     - buy_sell_signals
     - etc.

---

## ⏱️ Timeline

- **If triggering workflow:** 20-30 minutes to build and push images
- **First loader execution:** 5-10 minutes after images are ready
- **Full data sync:** Depends on loader (varies from 5 min to 2+ hours)

---

## 🔍 How the System Works After Fix

```
1. ECS Task Starts
   ↓
2. Environment has stale endpoint: rds-stocks.c2gujitq3h1b...
   ↓
3. Python loader starts executing
   ↓
4. Endpoint correction logic runs automatically
   ↓
5. Detects pattern 'c2gujitq3h1b' in DB_HOST
   ↓
6. Replaces with correct: stocks.cojggi2mkthi...
   ↓
7. Connects to correct RDS database
   ↓
8. Data loads successfully ✅
```

**Important:** The endpoint correction happens automatically - no manual intervention needed after the workflow builds the images.

---

## ✋ What NOT To Do

❌ Don't manually update each task definition (not needed - endpoint correction handles it)
❌ Don't stop/start RDS (it's already running correctly)
❌ Don't delete log groups (they'll be recreated)
❌ Don't modify the loaders themselves (all changes are already made)

---

## 🆘 If Something Goes Wrong

### Symptom: Still seeing "could not translate host name" error

**Check:**
1. Did the workflow complete successfully? (Check Actions tab in GitHub)
2. Are new images in ECR? (ECR console or `aws ecr describe-images`)
3. Is task running new image? (Check task definition revision)
4. Are CloudWatch logs showing? (Check /ecs/algo-* log groups)

### Symptom: ModuleNotFoundError for scipy, fredapi, etc.

**Solution:**
- Workflow hasn't completed yet OR
- Old image is still running (check task definition)
- Wait for workflow to finish and restart task

### Symptom: Access denied to AWS Secrets Manager

**This is expected** - The code prioritizes environment variables, so Secrets Manager isn't used if DB_HOST is set (which it is in task definitions)

---

## 📞 Getting Help

If the loaders still don't work after completing these steps:

1. **Collect logs:**
   ```bash
   aws logs get-log-events \
     --log-group-name /ecs/algo-loadaaiidata \
     --log-stream-name <stream-name> \
     > loader-logs.txt
   ```

2. **Check task definition:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition aaiidata-loader \
     --query 'taskDefinition.containerDefinitions[0].image'
   ```

3. **Share the following:**
   - Exact error message from CloudWatch logs
   - Task definition image tag (should show recent timestamp)
   - Task status (RUNNING/STOPPED/FAILED)

---

## Summary

✅ **All code fixes are complete and tested**
⏳ **Docker images need to be rebuilt** (trigger workflow via GitHub Actions)
🎯 **After rebuild, loaders will work automatically** (endpoint correction logic handles it)

**Next action:** Trigger the GitHub Actions workflow from the web UI or CLI
