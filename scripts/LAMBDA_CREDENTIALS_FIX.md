# Lambda Credentials Configuration

## Current Status
- [x] Alpaca credentials exist in AWS Secrets Manager: `algo/alpaca`
- [x] Credentials are valid: api_key (26 chars), api_secret (44 chars)
- [x] Credential manager can load them from AWS
- [ ] Lambda functions have IAM permission to read the secret
- [ ] Lambda functions have ALGO_SECRETS_ARN configured
- [ ] Lambda functions have ALPACA_PAPER_TRADING=true

## Required Terraform Changes

The orchestrator Lambda needs:

1. **IAM Permission to read algo/alpaca secret**
   ```hcl
   resource "aws_iam_role_policy" "algo_lambda_secrets" {
     name = "algo-lambda-secrets"
     role = aws_iam_role.algo_lambda.id
     
     policy = jsonencode({
       Version = "2012-10-17"
       Statement = [{
         Effect = "Allow"
         Action = [
           "secretsmanager:GetSecretValue",
           "secretsmanager:DescribeSecret"
         ]
         Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:algo/alpaca*"
       }]
     })
   }
   ```

2. **Environment variable in Lambda**
   ```hcl
   environment {
     variables = {
       # ... existing vars ...
       ALGO_SECRETS_ARN = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:algo/alpaca"
       ALPACA_PAPER_TRADING = "true"
     }
   }
   ```

## Verification Checklist

After Terraform apply:

```bash
# 1. Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name algo-orchestrator \
  --region us-east-1 \
  --query Environment.Variables | grep ALGO_SECRETS_ARN

# Expected: arn:aws:secretsmanager:us-east-1:...:secret:algo/alpaca

# 2. Verify credentials are working
aws lambda invoke \
  --function-name algo-orchestrator \
  --region us-east-1 \
  response.json && cat response.json | jq

# Should show successful phase execution

# 3. Check CloudWatch logs
aws logs tail /aws/lambda/algo-orchestrator \
  --follow \
  --region us-east-1 \
  --since 2m

# Should show:
# - Phase 1: Data freshness check SUCCESS
# - Phase 2: Circuit breakers SUCCESS
# - ...
# - Phase 7: Signal generation with trades
# - Phase 8: Entry execution with BUY orders
```

## Summary

The Alpaca credentials are already in AWS. The system just needs:
1. IAM permission for Lambda to read them
2. Environment variables pointing to the secret
3. Terraform apply to deploy these changes

Once deployed, trades will execute immediately.
