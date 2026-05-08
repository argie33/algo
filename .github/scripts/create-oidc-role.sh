#!/bin/bash
set -e

OIDC_ARN="$1"

echo "Creating github-actions-role with OIDC trust..."

if aws iam get-role --role-name github-actions-role 2>/dev/null >/dev/null; then
  echo "✅ Role already exists"
else
  # Create trust policy JSON
  TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "$OIDC_ARN"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:argie33/algo:*"
        }
      }
    }
  ]
}
EOF
)

  echo "$TRUST_POLICY" > /tmp/trust.json

  aws iam create-role \
    --role-name github-actions-role \
    --assume-role-policy-document file:///tmp/trust.json

  echo "✅ Role created"
fi
