# ⚡ QUICK START - Get Phase 2 Running NOW

**Goal:** Load data in AWS in 15 minutes, see what works, then optimize

**Skip the theory. Just do this:**

---

## STEP 1: Add GitHub Secrets (5 min)

Go here: https://github.com/argie33/algo/settings/secrets/actions

Add these 4:
```
AWS_ACCOUNT_ID = 626216981288
RDS_USERNAME = stocks
RDS_PASSWORD = bed0elAn
FRED_API_KEY = 4f87c213871ed1a9508c06957fa9b577
```

Click "New repository secret" for each one. Copy name, paste value, save.

---

## STEP 2: Configure AWS in 60 seconds

Run this ONE command in AWS CloudFormation console:

```bash
aws cloudformation create-stack \
  --stack-name github-oidc \
  --template-body file://setup-github-oidc.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

Or paste the YAML from `setup-github-oidc.yml` into CloudFormation console directly.

Wait for it to say `CREATE_COMPLETE`.

---

## STEP 3: Trigger It (1 minute)

```bash
git commit -am "Run Phase 2" --allow-empty
git push origin main
```

Go to: https://github.com/argie33/algo/actions

Watch it run.

---

## STEP 4: Monitor (15-30 min while you wait)

**GitHub Actions tab:**
- Should see a workflow running
- Watch for ✅ green checkmarks

**CloudWatch (AWS Console → Logs):**
- Look for `/ecs/algo-loadsectors`
- Watch the logs stream in real-time

**CloudFormation (AWS Console):**
- Watch stacks deploy

---

## STEP 5: Check Results

When done, query the database:

```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks -c \
"SELECT COUNT(*) FROM sector_technical_data;"
```

If it returns a number > 0: **Data loaded!**

---

## That's It

You now have:
- Phase 2 running in AWS ✅
- Data loading into database ✅
- Real execution time metrics ✅
- Actual costs to measure ✅

Then we decide:
- Is the performance good enough?
- Do we need Phase 3 (S3 + Lambda)?
- What should we actually run and when?

**Let's see what we actually get before optimizing.**
