#!/bin/bash
# Fix IAM permissions for reader user to access AWS Secrets Manager
# This allows loaders to work in both local and AWS environments

set -e

echo "🔑 Fixing IAM permissions for 'reader' user..."
echo "=================================================="

# Create the policy JSON
cat > /tmp/reader-secrets-policy.json << 'POLICY'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSecretsManagerReadAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret*",
        "arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets*"
      ]
    }
  ]
}
POLICY

echo "📋 Policy created. Now applying it to 'reader' user..."
echo ""

# Apply the policy
aws iam put-user-policy \
  --user-name reader \
  --policy-name AllowSecretsManagerAccess \
  --policy-document file:///tmp/reader-secrets-policy.json

echo "✅ IAM policy applied successfully!"
echo ""
echo "Verifying policy..."
aws iam get-user-policy \
  --user-name reader \
  --policy-name AllowSecretsManagerAccess \
  --output json | grep -E "AllowSecretsManagerAccess|secretsmanager" || true

echo ""
echo "✅ Reader user can now access Secrets Manager!"
echo ""
echo "Next steps:"
echo "1. Restart the loaders: bash start_loaders.sh"
echo "2. Check logs for successful data loading"
