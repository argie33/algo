# IAM Permission Model

## Principle: Reader-Only + Invoke/Run Tasks

This codebase enforces a **zero-trust infrastructure-as-code (IaC) model**:
- **Developers**: Read-only access + ability to test (invoke Lambda, run ECS tasks)
- **Terraform/IaC**: Only deployment mechanism for infrastructure changes
- **GitHub Actions**: Only entity that can modify AWS infrastructure via Terraform
- **No manual AWS console access** for infrastructure changes

---

## Users & Roles

### 1. Developer IAM User (`algo-developer`)

**Purpose**: Local CLI access for monitoring, testing, and debugging  
**Scope**: All `algo-*` resources in the account  
**Key Permissions**:

#### Read-Only (Inspection)
- ✅ CloudWatch logs (read/query)
- ✅ Lambda functions (describe, list)
- ✅ ECS tasks/clusters (describe, list)
- ✅ RDS database (describe-only)
- ✅ DynamoDB tables (read items, query, scan)
- ✅ Secrets Manager (read secrets only)
- ✅ Cognito (read-only, no user creation/deletion)
- ✅ S3 buckets (list, get objects only)
- ✅ EC2 resources (describe only)

#### Limited Write (Testing Only)
- ✅ Lambda invocation (sync + async)
- ✅ ECS task execution (run, stop, describe)
- ✅ Cognito user attributes (enable/disable, MFA, attributes only — NOT passwords or user creation)
- ✅ DynamoDB (read/write orchestrator state for testing)
- ✅ CloudFront invalidation (cache clearing)
- ✅ CloudWatch Logs Insights (query logs)

#### Explicitly Denied
- ❌ Terraform state access (S3 PutObject, DynamoDB writes to `.tflock`)
- ❌ Cognito user creation/deletion
- ❌ Cognito password resets
- ❌ RDS modifications
- ❌ Database schema changes
- ❌ KMS key creation/modification
- ❌ IAM role/policy creation
- ❌ EventBridge rule modifications
- ❌ Any resource modification requiring Terraform

**Why?** Prevents accidental or malicious infrastructure changes. All changes must go through Terraform → GitHub Actions CI/CD.

---

### 2. GitHub Actions OIDC Role (`algo-svc-github-actions-dev`)

**Purpose**: Automated infrastructure deployments via CI/CD  
**Trust**: OIDC federation with GitHub Actions (not IAM keys)  
**Scope**: Only main branch (`repo:anthropics/algo:ref:refs/heads/main`)  
**Key Permissions**:

#### Full Write Access (Controlled by Terraform)
- ✅ All EC2, VPC, Lambda, ECS resources
- ✅ RDS, DynamoDB, S3, Secrets Manager
- ✅ IAM roles and policies (scoped to `algo-*` prefix)
- ✅ CloudWatch alarms, logs, EventBridge rules
- ✅ KMS key management

**Why?** Terraform needs full permissions to manage infrastructure. OIDC federation prevents key rotation risk and leaks.

**Security Controls**:
- ✅ OIDC trust only for `main` branch (staging branch intentionally excluded)
- ✅ Trust policy verified in code
- ✅ No long-lived API keys

---

### 3. Service Roles (Lambda, ECS, etc.)

**Lambda API Role** (`algo-lambda-api-dev`)
- ✅ Secrets Manager: database credentials only
- ✅ KMS: decrypt project keys only
- ✅ CloudWatch: logs + metrics
- ✅ VPC access (ENI management)
- ✅ ECS: run data patrol task only

**Lambda Algo Role** (`algo-lambda-algo-dev`)
- ✅ All above, plus:
- ✅ DynamoDB: orchestrator locks, halt flags, watermarks
- ✅ ECS: run/list/stop tasks (for loader management)
- ✅ SNS: publish notifications
- ✅ Secrets Manager: database + trading credentials

**ECS Task Roles**
- ✅ Secrets Manager: database, Alpaca, FRED credentials
- ✅ S3: read/write data loading buckets
- ✅ DynamoDB: halt flags, locks, watermarks
- ✅ CloudWatch: logs + metrics

---

## Credential Rotation

### Developer Credentials
- **Rotation**: Quarterly (automated)
- **Storage**: AWS Secrets Manager (`algo/developer-credentials`)
- **Managed by**: Terraform (no manual key management)
- **Last rotation**: 2026-05-28

### Service Credentials
- **Type**: IAM roles (no keys)
- **Storage**: Assumed via STS (temporary, auto-expiring)
- **Rotation**: Automatic by AWS

---

## Audit Trail

All IAM actions are logged in CloudTrail:
```bash
# Find developer access
aws cloudtrail lookup-events --lookup-attributes AttributeKey=Username,AttributeValue=algo-developer

# Monitor infrastructure changes
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=PutRolePolicy
```

---

## Common Tasks & Required Permissions

### "I want to read logs from Lambda"
**Command**: `aws logs tail /aws/lambda/algo-orchestrator --follow`  
**Permissions**: CloudWatch Logs read-only ✅ (you have this)

### "I want to run the orchestrator locally"
**Command**: `aws lambda invoke --function-name algo-orchestrator`  
**Permissions**: lambda:InvokeFunction ✅ (you have this)

### "I want to test a data loader"
**Command**: `aws ecs run-task --cluster algo-cluster --task-definition algo-data-loader`  
**Permissions**: ecs:RunTask, iam:PassRole ✅ (you have this)

### "I want to update a database value directly"
❌ **Not allowed.** Reason: This bypasses Terraform and creates drift.  
**Correct approach**: Update `steering/terraform.tfvars`, commit, push, merge to `main`.

### "I want to create a new Cognito user for testing"
❌ **Not allowed.** Reason: Privilege escalation risk.  
**Correct approach**: Modify `terraform/cognito.tf`, commit, push, merge to `main`.

### "I want to rotate developer credentials"
**Automation**: Quarterly via GitHub Actions (check workflow logs)  
**Manual rotation**: Change `developer_key_rotation_date` in `terraform/variables.tf`, commit to main.

---

## Troubleshooting

### Error: "User is not authorized to perform: terraform:*"
**Cause**: Developer user cannot run `terraform apply`.  
**Fix**: This is intentional. Push your branch to GitHub; CI/CD will run Terraform.

### Error: "AccessDenied on s3:PutObject to terraform state lock"
**Cause**: Developer user cannot access Terraform state bucket.  
**Fix**: This is intentional security control. Only GitHub Actions can modify state.

### Error: "User is not authorized to perform: iam:PassRole"
**Cause**: Developer tried to run an ECS task without proper role passing.  
**Example**: `aws ecs run-task ... --task-role-arn <invalid-role>`  
**Fix**: Use only pre-defined task roles (see ECS task definitions).

---

## Emergency Procedures

### "Infrastructure is broken, need manual fix"
1. **DO NOT** use AWS console to manually fix
2. Create a fix in Terraform:
   - `terraform/main.tf` or relevant module
   - `steering/INCIDENT_LOG.md` with reason + fix explanation
3. Commit, push, merge to `main`
4. CI/CD will apply the fix automatically

### "Developer credentials compromised"
1. Rotate immediately: Change `developer_key_rotation_date` in variables
2. Push to `main`, GitHub Actions applies the key rotation
3. Old key is deactivated within 1 minute
4. No manual console access needed

---

## See Also
- `steering/GOVERNANCE.md` — Architecture and fail-fast patterns
- `steering/OPERATIONS.md` — CI/CD and deployment workflows
