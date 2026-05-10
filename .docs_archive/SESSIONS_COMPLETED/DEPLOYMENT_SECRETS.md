# GitHub Actions Secrets Configuration

## Required Secrets for Terraform Deployment

The `deploy-terraform.yml` workflow requires three secrets to be configured in GitHub repository settings.

### Configuration Steps

1. Go to GitHub repository → Settings → Secrets and variables → Actions
2. Click "New repository secret" for each secret below:

### Secret Details

#### 1. AWS_ACCESS_KEY_ID
- **Description**: AWS IAM user access key for Terraform deployment
- **Value Format**: Alphanumeric string, usually starts with `AKIA`
- **Example**: `AKIAIOSFODNN7EXAMPLE`
- **How to obtain**:
  ```bash
  # Create IAM user with programmatic access
  aws iam create-user --user-name terraform-deployer
  aws iam create-access-key --user-name terraform-deployer
  ```

#### 2. AWS_SECRET_ACCESS_KEY
- **Description**: AWS IAM user secret key (keep confidential)
- **Value Format**: Long random string (40+ characters)
- **Example**: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
- **How to obtain**: Generated together with ACCESS_KEY_ID above

#### 3. RDS_PASSWORD
- **Description**: Master password for RDS PostgreSQL database
- **Requirements**:
  - At least 8 characters
  - Cannot start or end with special characters
  - Recommended: 16+ characters with mix of upper/lowercase/numbers/symbols
- **Example**: `MySecurePass123!`
- **Security**: 
  - Never share or commit this to version control
  - Rotate regularly (every 90 days recommended)
  - Use AWS Secrets Manager for long-term storage

## IAM User Permissions

The IAM user for `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` needs minimal permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:*",
        "dynamodb:*",
        "iam:*",
        "ec2:*",
        "rds:*",
        "lambda:*",
        "apigateway:*",
        "cloudfront:*",
        "cognito-idp:*",
        "ecs:*",
        "ecr:*",
        "batch:*",
        "cloudwatch:*",
        "logs:*",
        "events:*",
        "sns:*",
        "secrets-manager:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Verification

After configuring secrets, verify they're set correctly:

```bash
# List configured secrets (values not shown)
gh secret list --repo argeropolos/algo

# Expected output:
# AWS_ACCESS_KEY_ID
# AWS_SECRET_ACCESS_KEY
# RDS_PASSWORD
```

## Workflow Environment Variables

These secrets are automatically available to the workflow:

```yaml
env:
  TF_VAR_rds_password: ${{ secrets.RDS_PASSWORD }}
```

Other configuration passed via AWS credentials:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1
```

## Troubleshooting

### Secret Not Found Error

```
Error: Secret not found: RDS_PASSWORD
```

**Solution**: Verify secret exists:
```bash
gh secret list --repo argeropolos/algo
```

### Invalid Credentials Error

```
Error: InvalidClientTokenId: The security token included in the request is invalid
```

**Solution**: 
- Verify AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are correct
- Check IAM user has active access keys
- Regenerate keys if needed:
  ```bash
  aws iam delete-access-key --user-name terraform-deployer --access-key-id AKIAIOSFODNN7EXAMPLE
  aws iam create-access-key --user-name terraform-deployer
  ```

## Security Best Practices

1. **Rotate Keys Regularly**: Change AWS keys every 90 days
2. **Rotate RDS Password**: Change password every 90 days via AWS console or CLI
3. **Least Privilege**: Only grant necessary IAM permissions
4. **Audit Access**: Monitor GitHub Actions logs for failed attempts
5. **Store Securely**: Never log or print secret values
6. **Use AWS Secrets Manager**: For production, store RDS password there instead

## Next Steps

After configuring secrets:
1. Verify all three secrets are set: `gh secret list`
2. Trigger deployment: `gh workflow run deploy-terraform.yml --repo argeropolos/algo`
3. Monitor progress: `gh run list --workflow deploy-terraform.yml`
4. Check logs: `gh run view <run-id>`
