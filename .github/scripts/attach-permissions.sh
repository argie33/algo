#!/bin/bash
set -e

echo "Attaching Terraform permissions to github-actions-role..."

cat > /tmp/policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:*",
        "ec2:*",
        "rds:*",
        "ecs:*",
        "ecr:*",
        "lambda:*",
        "apigateway:*",
        "cloudfront:*",
        "cognito-idp:*",
        "s3:*",
        "dynamodb:*",
        "secretsmanager:*",
        "cloudwatch:*",
        "logs:*",
        "events:*",
        "scheduler:*",
        "sns:*",
        "kms:*",
        "cloudformation:*",
        "autoscaling:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name github-actions-role \
  --policy-name terraform-deployment \
  --policy-document file:///tmp/policy.json

echo "✅ Terraform permissions attached"
