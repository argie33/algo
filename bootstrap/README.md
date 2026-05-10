# Bootstrap - GitHub OIDC & Deployment

This directory contains the bootstrap infrastructure needed before Terraform can deploy the main application.

## What is Bootstrap?

Bootstrap is a one-time setup process that creates:

1. **GitHub OIDC Provider** - Establishes trust between GitHub Actions and AWS
2. **GitHub Actions IAM Role** - Grants necessary permissions for deployments
3. **AWS Terraform State Backend** - S3 bucket + DynamoDB table for state management

## Files

- `oidc.yml` - CloudFormation template for GitHub OIDC Provider and IAM role
- `deploy.sh` - Automated deployment script (Linux/macOS)
- `deploy.ps1` - Automated deployment script (Windows PowerShell)

## Quick Start

### Option 1: Automated Deployment (Recommended)

**Windows (PowerShell):**
```powershell
cd bootstrap
& .\deploy.ps1
```

**Linux/macOS (Bash):**
```bash
cd bootstrap
bash deploy.sh
```

The script will:
1. Verify AWS CLI and GitHub CLI are installed
2. Check AWS credentials
3. Deploy the OIDC CloudFormation stack
4. Set GitHub secrets
5. Push code and trigger infrastructure deployment

### Option 2: Manual Deployment

**Step 1: Deploy OIDC Stack**
```bash
aws cloudformation deploy \
  --template-file bootstrap/oidc.yml \
  --stack-name stocks-oidc \
  --region us-east-1 \
  --parameter-overrides \
    ProjectName=stocks \
    GitHubOrg=argeropolos \
    GitHubRepo=algo \
  --capabilities CAPABILITY_NAMED_IAM
```

**Step 2: Verify Role Created**
```bash
aws iam get-role --role-name github-actions-role
```

**Step 3: Set GitHub Secrets**
```bash
gh secret set AWS_ACCOUNT_ID --body "626216981288"
gh secret set AWS_ACCESS_KEY_ID --body "your-access-key"
gh secret set AWS_SECRET_ACCESS_KEY --body "your-secret-key"
gh secret set RDS_PASSWORD --body "YourPassword123"
gh secret set SLACK_WEBHOOK --body "https://hooks.slack.com/..." # optional
```

**Step 4: Push Code**
```bash
git add bootstrap/ terraform/
git commit -m "Infrastructure: Bootstrap OIDC setup"
git push origin main
```

The `terraform-apply` GitHub Actions workflow will then automatically deploy all infrastructure.

## What Permissions Are Granted?

The GitHub Actions role has permissions for:

- CloudFormation stack management
- S3 bucket creation and management
- DynamoDB table creation and locking
- IAM role and policy management
- EC2 resource management
- RDS database management
- Lambda function management
- ECS cluster and task management
- ECR repository management
- CloudWatch logs and alarms
- EventBridge rules
- API Gateway and Cognito
- CloudFront and WAF

## Troubleshooting

### Error: "OIDC Provider already exists"

The OIDC provider is account-wide and should only be created once. If it exists, the CloudFormation stack will skip it during updates.

### Error: "github-actions-role not found"

The role wasn't created. Verify the CloudFormation stack deployed successfully:
```bash
aws cloudformation describe-stacks --stack-name stocks-oidc --region us-east-1
```

### Error: "Invalid OIDC configuration"

Check that the GitHub repository is set correctly in the `oidc.yml` template:
```
repo:argeropolos/algo:*
```

## What Happens After Bootstrap?

Once bootstrap is complete:

1. **GitHub Actions Workflow Triggers** - Automatically starts the `terraform-apply` workflow
2. **S3 State Backend Created** - bootstrap.sh creates S3 bucket and DynamoDB table
3. **Terraform Initializes** - Configures remote state in S3
4. **Infrastructure Deployed** - All AWS resources created via Terraform (~15-20 minutes)

You can monitor progress at: https://github.com/argeropolos/algo/actions

## Security Notes

⚠️ **Important Security Considerations:**

- The OIDC role is scoped to `repo:argeropolos/algo:*` - only this repository can assume it
- AWS credentials are stored as GitHub secrets - they're encrypted and only available in workflows
- RDS password is passed via secret and never logged
- S3 state bucket has encryption and versioning enabled
- Never commit AWS credentials to Git

## Support

If you encounter issues:

1. Check the GitHub Actions workflow logs: https://github.com/argeropolos/algo/actions
2. Verify CloudFormation stack events: `aws cloudformation describe-stack-events --stack-name stocks-oidc`
3. Review bootstrap script output for errors
4. Ensure AWS CLI and GitHub CLI are up to date

---

**Status:** Ready for Deployment
**Created:** 2026-05-07
