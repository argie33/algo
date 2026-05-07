# IAM Module - Least-Privilege Roles & Policies

This module defines all IAM roles and policies for the `stocks-analytics` platform with **zero wildcards** and **least-privilege** design.

## Design Principles

1. **No Wildcard Actions**: Each policy specifies exact actions required
2. **Resource Scoping**: All resources reference specific ARNs, not wildcards
3. **Per-Service Roles**: Separate roles for different services (no shared admin role)
4. **Audit Trail**: All policies are version-controlled and reviewable
5. **Minimal Permissions**: Only what's necessary for operation

## Roles Defined

### 1. GitHub Actions Deployment Role (`github_actions_role`)

**Purpose**: Deploy infrastructure from GitHub Actions CI/CD

**Trust Policy**:
- ✅ Trusts GitHub OIDC provider
- ✅ Scoped to THIS repository only (`repo:argeropolos/algo:ref:refs/heads/main`)
- ❌ Not open to other GitHub orgs or repos

**Permissions**:
- CloudFormation: Create/Update/Delete/Describe stacks (scoped to `stocks-*`)
- Terraform State: Read/write S3 state bucket, DynamoDB locking
- IAM PassRole: Pass execution roles to services
- RDS: Describe DB instances (no create/delete without CloudFormation)
- ECS: Describe clusters, services, tasks
- Lambda: Get/describe functions
- S3: Standard bucket operations (scoped to `stocks-*`)
- ECR: GetAuthorizationToken (required for pulling images)
- Secrets Manager: Read secrets (scoped to `stocks-*`)
- KMS: Decrypt (source account scoped)
- CloudWatch Logs: Create log groups/streams

**NOT Allowed**:
- ❌ AdministratorAccess
- ❌ Wildcard `*` actions
- ❌ Create/modify IAM policies
- ❌ Modify security groups (only through CloudFormation)
- ❌ Manual RDS operations (only through CloudFormation)

---

### 2. Bastion Host Role (`bastion_role`)

**Purpose**: Allow bastion EC2 instance to access secrets and logs

**Trust Policy**:
- Trusts `ec2.amazonaws.com` service
- Only for EC2 instances with this role attached

**Permissions**:
- Systems Manager: Session Manager access (SSM Session Manager, EC2 Messages)
- CloudWatch Logs: Log session activity
- Secrets Manager: **Read-only** access to DB credentials
- KMS: Decrypt encrypted secrets

**NOT Allowed**:
- ❌ EC2: TerminateInstances (prevents self-termination)
- ❌ Secrets Manager: Create/Update/Delete secrets
- ❌ RDS: Direct database modifications

---

### 3. ECS Task Execution Role (`ecs_task_execution_role`)

**Purpose**: Allow ECS service to start tasks and manage container runtime

**Trust Policy**:
- Trusts `ecs-tasks.amazonaws.com` service

**Permissions** (plus AWS managed policy `AmazonECSTaskExecutionRolePolicy`):
- CloudWatch Logs: Create log groups, streams, put log events
- Secrets Manager: Read task secrets
- KMS: Decrypt secret values
- ECR: Pull container images (via AWS managed policy)

**Why separate from Task Role?**
- Execution role = permissions the ECS service needs
- Task role = permissions the container needs
- Follows AWS best practices for least-privilege separation

---

### 4. ECS Task Role (`ecs_task_role`)

**Purpose**: Permissions available to containers running in ECS

**Trust Policy**:
- Trusts `ecs-tasks.amazonaws.com` service

**Permissions**:
- Secrets Manager: Read DB credentials and Alpaca keys
- KMS: Decrypt secrets
- S3: Read/write data loading bucket (staging results)

**NOT Allowed**:
- ❌ No direct RDS access (use Secrets Manager for credentials)
- ❌ No IAM, EC2, ECS management
- ❌ No cross-account access

---

### 5. Lambda API Role (`lambda_api_role`)

**Purpose**: Permissions for webapp API Lambda function

**Trust Policy**:
- Trusts `lambda.amazonaws.com` service

**Permissions**:
- VPC: Create/delete/describe network interfaces (if running in VPC)
- Secrets Manager: Read DB credentials
- KMS: Decrypt secrets
- CloudWatch Logs: Create/put log events

**Rationale**:
- VPC permissions needed if Lambda runs inside VPC for database access
- No S3, RDS, EC2 direct access

---

### 6. Lambda Algo Role (`lambda_algo_role`)

**Purpose**: Permissions for algo orchestrator Lambda

**Trust Policy**:
- Trusts `lambda.amazonaws.com` service

**Permissions**:
- VPC: Create/delete/describe network interfaces (for RDS access)
- Secrets Manager: Read credentials
- KMS: Decrypt secrets
- CloudWatch Logs: Create/put log events
- SNS: Publish alerts
- CloudWatch Metrics: Put custom metrics (for `AlgoRunCompleted` metric)

**Key Difference from Lambda API**:
- ✅ Can publish to SNS for alerts
- ✅ Can put custom metrics to CloudWatch
- ✅ Cannot modify other Lambda functions

---

### 7. EventBridge Scheduler Role (`eventbridge_scheduler_role`)

**Purpose**: Allow EventBridge to trigger scheduled tasks

**Trust Policy**:
- Trusts `scheduler.amazonaws.com` service

**Permissions**:
- ECS: RunTask (trigger loader containers)
- IAM PassRole: Pass execution/task roles to ECS
- Lambda: InvokeFunction (trigger algo Lambda)

**NOT Allowed**:
- ❌ Cannot modify schedules (that's done via CloudFormation/Terraform)
- ❌ Cannot manage stacks or infrastructure

---

## Usage in Other Modules

Reference roles by their ARNs or names:

```hcl
module "compute" {
  source = "./modules/compute"

  ecs_task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  ecs_task_role_arn           = module.iam.ecs_task_role_arn
  lambda_api_role_arn         = module.iam.lambda_api_role_arn
  # ...
}
```

## Security Review Checklist

- [x] No role has `*` actions
- [x] No role has `Resource: "*"` (except for scoped conditions)
- [x] GitHub Actions role scoped to this repo only
- [x] Bastion role is read-only for Secrets
- [x] ECS task role cannot modify infrastructure
- [x] Lambda roles are narrowly scoped
- [x] All secrets access goes through Secrets Manager (not env vars)
- [x] All encryption goes through KMS
- [x] Source account conditions on wildcard resources

## Adding New Roles

When adding a new service:

1. Create a new `aws_iam_role` resource
2. Define `data.aws_iam_policy_document` with specific permissions
3. Keep statements to < 10 actions per statement
4. Always include resource ARNs or source account conditions
5. Add outputs for other modules to reference
6. Document the role above

## Migrating from CloudFormation Admin Role

The previous CloudFormation setup used `GitHubActionsDeployRole` with AdministratorAccess. This module replaces it with:

1. **Same trust policy** (GitHub OIDC) but **scoped to one repo**
2. **Specific permissions** instead of `*`
3. **Resource-scoped** instead of wildcards
4. **Audit trail** through CloudFormation/Terraform

### To migrate:

1. Deploy this IAM module (creates new role)
2. Update GitHub Actions to use new role ARN
3. Verify deployments succeed with reduced permissions
4. Delete old `GitHubActionsDeployRole` from AWS Console

---

## Testing & Verification

### Verify GitHub Actions role works:

```bash
# In GitHub Actions workflow:
aws sts get-caller-identity
# Should show: Account, UserId (with :github-actions in it), ARN

# Try a CloudFormation operation:
aws cloudformation describe-stacks --stack-name stocks-core
# Should succeed (if stack exists)

# Try a prohibited operation (should fail):
aws iam list-roles
# Should get Access Denied
```

### Verify Bastion can read secrets:

```bash
# SSH into bastion via SSM Session Manager
aws ssm start-session --target i-INSTANCE_ID

# Inside bastion:
aws secretsmanager get-secret-value --secret-id stocks-db-secrets
# Should succeed

# Try a prohibited operation (should fail):
aws iam delete-role --role-name anything
# Should get Access Denied
```

---

## Future Improvements

- [ ] Add per-service accounts (separate AWS accounts for prod)
- [ ] Add cross-account roles for disaster recovery
- [ ] Add temporary credentials with shorter TTL
- [ ] Add IP restriction conditions to GitHub Actions role
- [ ] Add time-based access policies for critical operations
