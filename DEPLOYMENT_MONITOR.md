# Deployment Monitoring Guide

**Status:** 🟡 Deployment In Progress  
**Triggered:** 2026-05-17 (cleanup + verification scripts commit)  
**Workflow:** [View on GitHub Actions](https://github.com/argie33/algo/actions/workflows/deploy-all-infrastructure.yml)

---

## Deployment Pipeline (Automated via GitHub Actions)

### Phase 1: Infrastructure (Terraform) ✅
- [x] Bootstrap Terraform backend (S3 + DynamoDB)
- [x] Run Terraform apply (165 resources)
- [x] Fix API Gateway route conflict
- [x] Collect infrastructure outputs

### Phase 2a: Docker Image 🟡
- [ ] Build loader Docker image
- [ ] Push to ECR
- **Status:** Building via GitHub Actions

### Phase 2b: Lambda Deployment 🟡
- [ ] Package API Lambda code
- [ ] Deploy API Lambda
- [ ] Package Algo Lambda code  
- [ ] Deploy Algo Orchestrator Lambda
- **Status:** Pending image build completion

### Phase 2c: Frontend Deployment 🟡
- [ ] Build React frontend
- [ ] Sync to S3 bucket
- [ ] Invalidate CloudFront cache
- **Status:** Waiting for infrastructure outputs

### Phase 3: Verification (Manual)
- [ ] Run `verify_rds_connectivity.py`
- [ ] Run `post-deployment-verify.sh`
- [ ] Test API endpoints
- [ ] Run loaders through ECS

---

## How to Monitor

### Check GitHub Actions Status
```bash
# View workflow runs
gh run list --workflow=deploy-all-infrastructure.yml --limit=1

# View specific run
gh run view <RUN_ID> --log

# Watch in real-time
gh run watch <RUN_ID>
```

### Check Infrastructure Status (After Terraform)
```bash
# Get Terraform outputs
aws s3 cp \
  s3://stocks-terraform-state/stocks/terraform.tfstate \
  /tmp/terraform.tfstate

# Extract outputs
jq '.outputs' /tmp/terraform.tfstate
```

### Common Issues & Fixes

**Issue:** "ERROR: could not resolve frontend S3 bucket"
- **Cause:** Terraform output empty/null
- **Fix:** Verify bucket created: `aws s3api list-buckets | grep frontend`

**Issue:** Docker build fails
- **Cause:** Missing dependencies in requirements.txt
- **Fix:** Check `requirements.txt` has all loader dependencies

**Issue:** API Lambda deployment fails
- **Cause:** Lambda code has syntax errors
- **Fix:** Run locally: `python3 lambda/api/lambda_function.py`

**Issue:** Frontend sync fails
- **Cause:** S3 permissions or bucket not accessible
- **Fix:** Verify IAM role has S3 permissions

---

## Next Steps (Once Deployment Completes)

### 1. Verify Infrastructure (5 min)
```bash
bash post-deployment-verify.sh
```

### 2. Test Database Connectivity (2 min)
```bash
# Get RDS endpoint from Terraform outputs
export DB_HOST=<rds-endpoint>
export DB_PASSWORD=<your-password>
python3 verify_rds_connectivity.py
```

### 3. Run Loaders (20 min)
```bash
python3 run-all-loaders.py
```

### 4. Test Orchestrator (5 min)
```bash
python3 algo/algo_orchestrator.py --mode paper --dry-run
```

### 5. Test API (2 min)
```bash
curl https://<api-endpoint>/health
```

---

## Deployment Checklist

- [ ] Terraform outputs all 165 resources successfully
- [ ] frontend_bucket_name output is not null
- [ ] Docker image built and pushed to ECR
- [ ] API Lambda deployed successfully
- [ ] Algo Lambda deployed successfully
- [ ] Frontend built and synced to S3
- [ ] CloudFront invalidation created
- [ ] RDS connectivity verified
- [ ] Database schema present (127 tables)
- [ ] All loaders executable
- [ ] Orchestrator can run in dry-run mode
- [ ] API health check responds

---

## Rollback Instructions

If deployment fails critically:

```bash
# View failed jobs
gh run view <RUN_ID> --log

# Check Terraform state
terraform show

# Rollback to previous commit
git revert HEAD

# Manually destroy infrastructure (careful!)
cd terraform
terraform destroy -auto-approve
```

---

**Last Updated:** 2026-05-17  
**Next Check:** Monitor GitHub Actions for completion (typically 30-45 minutes)
