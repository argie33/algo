# IaC Audit Report - AWS Deployment Issues (2026-05-17)

## CRITICAL ISSUES FOUND

### 🔴 Issue #1: Missing Patrol Task Configuration in Services Module

**Severity:** CRITICAL - API `/api/algo/patrol` endpoint will fail at runtime

**Location:** `terraform/main.tf` line 173-237 (services module call)

**Problem:**
- Services module declares variables for patrol task execution (lines 531-553 in variables.tf)
- These variables are NEVER passed from the loaders module output
- API Lambda has code to invoke patrol task, but Terraform doesn't wire the connection

**Missing Variables:**
```terraform
# NOT passed to services module:
patrol_task_definition_arn     = module.loaders.data_patrol_task_definition_arn
patrol_task_container_name     = "${var.project_name}-data-patrol"
private_subnet_ids_for_patrol  = module.vpc.private_subnet_ids
ecs_tasks_sg_id                = module.vpc.ecs_tasks_security_group_id
ecs_cluster_arn                = module.compute.ecs_cluster_arn
```

**Impact:** API deployment succeeds, but `/api/algo/patrol` endpoint will error when called (missing environment variables in Lambda).

---

### 🔴 Issue #2: Loader Task Definition ARNs Not Available to Services

**Severity:** HIGH - Some API endpoints may reference loader tasks

**Problem:**
- Loaders module outputs `loader_task_definition_arns` (map of all 40 loaders)
- Services module never receives this (may need it for status/management endpoints)
- If any API endpoint tries to reference loader tasks, it will fail

**Affected Code:**
- `terraform/modules/services/main.tf` - API Lambda environment (line 82-100)
- May need `LOADER_TASK_ARNS` environment variable

---

### 🟡 Issue #3: Continuous Monitor Task Not Integrated with Monitoring Module

**Severity:** MEDIUM - CloudWatch alarms may not monitor the right tasks

**Problem:**
- Loaders module creates `continuous_monitor` ECS task definition
- Monitoring module doesn't reference or monitor this task
- No output for continuous monitor task ARN

**Missing:**
- Output in loaders/outputs.tf for `continuous_monitor_task_definition_arn`
- Monitoring configuration for continuous monitor CloudWatch logs

**Fix Required:**
```terraform
# Add to loaders/outputs.tf
output "continuous_monitor_task_definition_arn" {
  value       = aws_ecs_task_definition.continuous_monitor.arn
}
```

---

### 🟡 Issue #4: SNS Alert Topic ARN Reference Issue

**Severity:** LOW - Alert notifications may not route correctly

**Problem:**
- Main.tf line 254 uses: `coalesce(module.services.sns_alerts_topic_arn, "")`
- If services module doesn't output sns_alerts_topic_arn, coalesce returns empty string
- EventBridge dead-letter queues won't send alerts

**Check Required:**
- Verify services module outputs `sns_alerts_topic_arn`
- Verify pipeline module has SNS topic ARN available

---

## DEPLOYMENT WORKFLOW ISSUES

### 🔴 Issue #5: Loader Deployment Order and Dependencies

**Severity:** HIGH

**Problem:**
1. **LoaderFile Mapping Missing** - loaders/main.tf has `loader_file_map` but doesn't validate files exist
2. **No loader validation** - Terraform doesn't check if Python loader files are present before deploying
3. **ECR image assumed present** - Task definitions reference ECR image but don't verify it's built/pushed

**Missing Validation:**
```terraform
# loaders/main.tf should add:
- Check that each loader Python file exists in the codebase
- Verify ECR image URI is valid and accessible
- Validate all loader environment variable requirements
```

---

### 🟡 Issue #6: Lambda Function Code Package Handling

**Severity:** MEDIUM

**Problem:**
- Services module has S3-based Lambda deployment code (lines 43-71)
- Falls back to local file stub if S3 not configured
- No validation that S3 bucket/keys are correct

**Risk:**
- If S3 upload fails in CI, Lambda gets deployed with stub code
- Deployment succeeds but API returns 503 errors

**Deploy.tfvars Configuration:**
- Check that `api_lambda_s3_bucket` is set correctly
- Check that `algo_lambda_s3_bucket` is set correctly
- Verify object versions are tracked (enables safe updates)

---

## LOADERS IN AWS - SPECIFIC ISSUES

### 🔴 Issue #7: Calendar Loader Configuration

**Severity:** CRITICAL

**Location:** `terraform/modules/loaders/main.tf` line 157 and line 402

**Problem:**
```
"calendar" = "loadcalendar.py"
```

But STATUS.md states: "Removed loadcalendar.py (returns empty stub data, never completed)"

**Fix Required:**
1. Delete the calendar loader from scheduled_loaders
2. Remove from loader_file_map
3. Remove from all_loaders config
4. Deploy to delete unused ECS task definition

---

### 🟡 Issue #8: Loader Parallelism Not Always Respected in AWS

**Severity:** MEDIUM

**Problem:**
- ECS task definitions set `LOADER_PARALLELISM` environment variable (line 487)
- But Python loaders may not respect this when deployed in ECS Fargate
- Loader entrypoint script doesn't check LOADER_PARALLELISM

**Check Required:**
- Verify `terraform/modules/compute/user_data.sh` or similar reads LOADER_PARALLELISM
- Verify each Python loader reads this env var and adjusts thread pool

---

### 🟡 Issue #9: EventBridge DLQ Configuration Correct but Not Monitored

**Severity:** MEDIUM

**Location:** `terraform/modules/loaders/main.tf` lines 47-74, 790-809

**Status:** ✅ DLQ created and alarmed, BUT:
- Alarm only triggers when DLQ has messages (threshold >= 1)
- No dashboard showing DLQ status
- Manual investigation required to find failed loaders

**Recommendation:**
- Add CloudWatch dashboard showing loader health
- Add SNS alert topic (already exists but needs explicit subscription)

---

## MISSING INFRASTRUCTURE

### 🟡 Issue #10: No Health Check Endpoints for Loaders

**Severity:** MEDIUM

**Problem:**
- API has `/health` endpoint (services/main.tf line 187)
- No loader health check endpoint
- No way to query which loaders are running/healthy

**Missing:**
- `/api/loaders/health` endpoint in API Lambda
- CloudWatch dashboard for loader execution status
- Metrics export from loaders

---

## FIXES REQUIRED (Priority Order)

### P0 - CRITICAL (Deploy will work but API will error)

1. **Fix patrol task wiring in main.tf** - Add missing patrol variables to services module call
2. **Remove calendar loader** - Delete unused loadcalendar.py scheduler
3. **Verify Lambda S3 packages** - Ensure api_lambda_s3_bucket/algo_lambda_s3_bucket are set

### P1 - HIGH (Degraded functionality)

4. **Add continuous monitor output** - Export task ARN for monitoring
5. **Add loader validation** - Check loader files exist before Terraform applies
6. **Verify loader entrypoint** - Ensure LOADER_PARALLELISM is respected

### P2 - MEDIUM (Observability)

7. **Create loader health dashboard** - CloudWatch dashboard for loader status
8. **Fix SNS alert routing** - Verify DLQ alerts reach correct SNS topic
9. **Add loader health endpoints** - `/api/loaders/health` endpoint

---

## VERIFICATION CHECKLIST

Before next deployment, verify:

- [ ] All 40 loaders have Python files in codebase
- [ ] Calendar loader is removed from Terraform
- [ ] Patrol task variables passed to services module
- [ ] ECR image is built and pushed
- [ ] Lambda S3 packages are built and uploaded
- [ ] terraform validate passes
- [ ] terraform plan shows no unexpected resource deletions
- [ ] All 40+ loader task definitions created
- [ ] 33 EventBridge rules scheduled
- [ ] SQS DLQ created with alarm
- [ ] Continuous monitor task created
- [ ] API Lambda has patrol configuration
- [ ] Orchestrator ECS task ready
- [ ] Data patrol ECS task ready

---

## AWS DEPLOYMENT STATUS

**Current State (based on Terraform code):**

| Component | Status | Notes |
|-----------|--------|-------|
| RDS PostgreSQL | ✅ Ready | Encrypted, backed up, monitoring enabled |
| ECS Cluster | ✅ Ready | Fargate + spot capacity providers |
| 40 Loaders | ⚠️ Partial | Calendar loader should be removed |
| EventBridge | ✅ Ready | 33 scheduled loaders, DLQ configured |
| API Lambda | ❌ Missing Input | Patrol task variables not wired |
| Orchestrator ECS | ✅ Ready | 7-phase task definition ready |
| Data Patrol ECS | ✅ Ready | Task definition ready, but API can't call it |
| Step Functions | ✅ Ready | EOD pipeline DAG configured |
| CloudWatch | ✅ Ready | Logs, alarms, metrics configured |
| SNS Alerts | ✅ Ready | Topic created, DLQ alarm set up |

---

## NEXT STEPS

1. Fix critical Terraform issues (Issues #1, #2, #7)
2. Run `terraform plan` to verify no breaking changes
3. Deploy to staging AWS account
4. Test API endpoints that depend on loaders
5. Verify all 40 loaders execute successfully
6. Check CloudWatch logs for any startup errors
