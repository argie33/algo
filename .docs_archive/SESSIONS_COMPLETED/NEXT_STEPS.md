# Next Steps: Deploy Terraform via GitHub Actions

Everything is ready. You now have a complete Terraform infrastructure that deploys **entirely from GitHub secrets** - no terraform.tfvars needed.

## Quick Start (5 minutes)

### Step 1: Configure GitHub Secrets
Go to: **GitHub → Your Repo → Settings → Secrets and variables → Actions**

Create 3 new repository secrets:

| Secret Name | Get Value From | Example |
|---|---|---|
| `AWS_ACCOUNT_ID` | `aws sts get-caller-identity --query Account --output text` | `123456789012` |
| `DB_PASSWORD` | Generate with `openssl rand -base64 32` | `Tr0p!cal-P@ssw0rd-2024` |
| `NOTIFICATION_EMAIL` | Your email | `your-email@example.com` |

**Optional:**
- `SLACK_WEBHOOK` - For Slack notifications on deployment

### Step 2: Push to Main
```bash
# You just committed Terraform files
git push origin main

# GitHub Actions workflow automatically triggers
# Watch at: https://github.com/argeropolos/algo/actions
```

### Step 3: Monitor Deployment
```
GitHub → Actions → Deploy Infrastructure with Terraform
```

The workflow will:
1. ✅ Pre-flight checks (verify secrets exist)
2. ✅ Terraform plan (show what will be created)
3. ✅ Terraform apply (deploy to AWS)
4. ✅ Export outputs (show VPC ID, ECR URI, etc.)

## What Gets Deployed

### Phase 1 (Ready Now)
- **Bootstrap:** OIDC provider + GitHub Actions role
- **Core:** VPC, 2 AZs, NAT gateways, S3 buckets, ECR registry

**Time:** ~10 minutes

### Phase 2 (Ready Now)
- **Data Infrastructure:** RDS PostgreSQL, ECS cluster, Secrets Manager, CloudWatch alarms

**Time:** ~15 minutes (RDS is slow)

### Phase 3 (Next Week)
- **Loaders:** 65 ECS task definitions + EventBridge scheduled rules
- **Webapp:** Lambda API, CloudFront, Cognito
- **Algo:** Lambda orchestrator

## If Something Goes Wrong

### Check Workflow Logs
```
GitHub → Actions → Deploy Infrastructure with Terraform → [Failed Job]
```

### Common Issues

**"Missing secret: AWS_ACCOUNT_ID"**
- Verify all 3 secrets are created
- Check spelling (case-sensitive)

**"Invalid AWS credentials"**
- Verify AWS_ACCOUNT_ID is exactly 12 digits
- Confirm credentials have CloudFormation permissions

**"RDS creation timeout"**
- RDS takes 10+ minutes to create
- Safe to re-run workflow if it times out

**"OIDC role not found"**
- Bootstrap must deploy first
- Check that `stocks-github-actions-deploy` role exists in AWS

## Manual Local Deployment (if needed)

```bash
# Initialize Terraform
cd terraform
terraform init

# Create terraform.tfvars with your values:
cat > terraform.tfvars << EOF
aws_account_id     = "YOUR_ACCOUNT_ID"
db_password        = "YOUR_SECURE_PASSWORD"
notification_email = "your-email@example.com"
EOF

# Plan changes
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# View outputs
terraform output
```

## Deployment Phases

After initial deployment, you'll implement remaining modules phase by phase:

### Phase 3: Loaders (3-4 days)
- Extract 65 ECS task definitions from CloudFormation template
- Create Terraform resources (or use dynamic blocks)
- Deploy and test

### Phase 4: Webapp (2-3 days)
- Lambda function for REST API
- API Gateway with CORS
- CloudFront distribution
- Cognito integration

### Phase 5: Algo (1-2 days)
- Lambda orchestrator function
- EventBridge scheduler rule
- Implement algorithm logic

## File Structure

```
Your Repo:
├── terraform/                       ← All Terraform code
│   ├── main.tf                      ← Orchestration
│   ├── variables.tf                 ← Configuration options
│   ├── outputs.tf                   ← Exported values
│   ├── terraform.tfvars.example     ← Local dev template (not in CI/CD)
│   └── modules/
│       ├── bootstrap/               ✅ Ready
│       ├── core/                    ✅ Ready
│       ├── data_infrastructure/     ✅ Ready
│       ├── loaders/                 ⏳ Skeleton
│       ├── webapp/                  ⏳ Skeleton
│       └── algo/                    ⏳ Skeleton
│
├── .github/workflows/
│   └── deploy-terraform.yml         ← GitHub Actions workflow
│
├── TERRAFORM.md                     ← Comprehensive guide
├── TERRAFORM_STATUS.md              ← Implementation checklist
└── GITHUB_SECRETS_SETUP.md          ← Secret configuration guide
```

## Architecture Deployed

```
GitHub Actions (with secrets)
        ↓
   Terraform
        ↓
   AWS (via OIDC)
        ↓
   ┌─────────────────────────┐
   │  bootstrap              │  ✓ OIDC provider
   │  │                       │  ✓ GitHub Actions role
   │  └──→ core              │  ✓ VPC, subnets, networking
   │      │                   │  ✓ Security groups
   │      ├──→ data_infra     │  ✓ RDS PostgreSQL
   │      │   │               │  ✓ ECS cluster
   │      │   │               │  ✓ Secrets Manager
   │      │   ├──→ loaders    │  ⏳ Loader tasks
   │      │   ├──→ webapp     │  ⏳ API + CloudFront
   │      │   └──→ algo       │  ⏳ Orchestrator
   │      └──→ ...
   └─────────────────────────┘
```

## Advantages of This Approach

✅ **No CloudFormation validation hook errors** - Terraform has clean validation
✅ **Secrets-based CI/CD** - No hardcoded values, no terraform.tfvars in git
✅ **Automatic deployment** - Push to main → automatic deploy
✅ **Multi-cloud ready** - Same code for AWS/Azure/GCP
✅ **Better state management** - Portable, version-controlled
✅ **Cleaner error messages** - When something breaks, you see why

## Support & References

- **Terraform Docs:** https://www.terraform.io/docs
- **AWS Provider:** https://registry.terraform.io/providers/hashicorp/aws
- **GitHub Actions:** https://docs.github.com/en/actions

## Timeline

| Phase | What | When | Duration |
|-------|------|------|----------|
| 1 | Bootstrap → Core | Now | 10 min |
| 2 | Data Infrastructure | Now | 15 min |
| 3 | Loaders (65 task defs) | This week | 3-4 days |
| 4 | Webapp | Next week | 2-3 days |
| 5 | Algo | Next week | 1-2 days |
| Total | Full deployment | ~2 weeks | - |

---

**Ready to deploy?**

1. ✅ Create 3 GitHub secrets (AWS_ACCOUNT_ID, DB_PASSWORD, NOTIFICATION_EMAIL)
2. ✅ Workflow auto-triggers on `git push origin main`
3. ✅ Monitor at: https://github.com/argeropolos/algo/actions

Questions? Check:
- `TERRAFORM.md` - Full guide with all commands
- `GITHUB_SECRETS_SETUP.md` - Secret configuration
- `TERRAFORM_STATUS.md` - Implementation checklist

**Go deploy! 🚀**
