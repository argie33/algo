# Running Custom/Ad-Hoc Loaders in AWS

**Problem:** New or one-off loaders aren't part of scheduled pipelines. How do you run them without adding Terraform infrastructure?

**Solution:** Use ECS `run-task` to execute a loader from local machine or CI/CD.

---

## Method 1: Run via AWS CLI (Recommended)

**Prerequisites:**
- AWS CLI configured with credentials
- Access to `algo-cluster` ECS cluster  
- Developer IAM role with `ecs:RunTask` permission

**Command:**
```bash
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-stock_prices_daily-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0988e8d04bba87486],securityGroups=[sg-xxxxxxxx],assignPublicIp=DISABLED}" \
  --container-overrides "name=algo-loader,command=[python3,loaders/load_dxy_index.py]" \
  --region us-east-1
```

**Explanation:**
- `--task-definition algo-stock_prices_daily-loader` — Use an existing loader task definition (reuse container config)
- `--container-overrides` — Change the entry point command to run `load_dxy_index.py` instead
- Subnets/security groups — VPC networking (must be private for RDS access)

**Get subnet/security group IDs:**
```bash
# Private subnet
cd terraform && terraform output private_subnet_ids

# Security group (RDS access)
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=algo-loader-sg" \
  --query 'SecurityGroups[0].GroupId' \
  --region us-east-1
```

**Monitor the task:**
```bash
# List running tasks
aws ecs list-tasks --cluster algo-cluster --region us-east-1

# Watch logs (replace TASK_ID)
aws logs tail /ecs/algo-cluster/algo-stock_prices_daily-loader --follow --region us-east-1
```

---

## Method 2: Manual ECS Task Setup (For New Loaders)

If the loader needs a dedicated task definition:

1. **Add to Terraform** (`terraform/modules/loaders/loaders.tf`):
```hcl
locals {
  loader_config = {
    load_dxy_index = {
      type = "critical"
      runner_module = "loaders.load_dxy_index"
    }
  }
}
```

2. **Apply Terraform:**
```bash
cd terraform
terraform plan
terraform apply
```

3. **Then use Method 1** with the new task definition ARN.

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `ResourceNotFoundException: Unknown task definition` | Use an existing task definition from `terraform output loader_task_definitions` |
| `InvalidParameterException: No matches for subnet in availability zone` | Subnet may be in wrong AZ; try multiple subnets |
| Task exits immediately | Check logs: `aws logs tail /ecs/algo-cluster/...` |
| Loader can't access RDS | Verify security group allows outbound 5432 to RDS |

---

## For Production Use

**Scheduled loaders:** Use Step Functions (via `DATA_LOADERS.md`)  
**One-off/manual loaders:** Use this guide (Method 1)  
**CI/CD deployments:** Add `aws ecs run-task` to GitHub Actions workflow

