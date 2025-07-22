#!/bin/bash
# Setup S3 Bucket for File Storage

set -e

REGION="us-east-1"
ENVIRONMENT="dev"
BUCKET_NAME="stocks-webapp-storage-$ENVIRONMENT"

echo "🪣 Setting up S3 bucket for file storage..."

# 1. Create S3 bucket
echo "Creating S3 bucket..."
aws s3 mb "s3://$BUCKET_NAME" --region $REGION || echo "Bucket may already exist"

# 2. Enable versioning
echo "Enabling S3 versioning..."
aws s3api put-bucket-versioning \
    --bucket "$BUCKET_NAME" \
    --versioning-configuration Status=Enabled

# 3. Set bucket policy for Lambda access
echo "Setting bucket policy..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > bucket-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "LambdaAccess",
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::$BUCKET_NAME/*",
            "Condition": {
                "StringEquals": {
                    "aws:SourceAccount": "$ACCOUNT_ID"
                }
            }
        }
    ]
}
EOF

aws s3api put-bucket-policy \
    --bucket "$BUCKET_NAME" \
    --policy file://bucket-policy.json

# 4. Configure lifecycle policy
echo "Setting lifecycle policy..."
cat > lifecycle-policy.json << EOF
{
    "Rules": [
        {
            "ID": "TestResultsCleanup",
            "Status": "Enabled",
            "Prefix": "test-results/",
            "Expiration": {
                "Days": 30
            }
        },
        {
            "ID": "LogsCleanup", 
            "Status": "Enabled",
            "Prefix": "logs/",
            "Expiration": {
                "Days": 90
            }
        }
    ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
    --bucket "$BUCKET_NAME" \
    --lifecycle-configuration file://lifecycle-policy.json

# 5. Enable server-side encryption
echo "Enabling server-side encryption..."
aws s3api put-bucket-encryption \
    --bucket "$BUCKET_NAME" \
    --server-side-encryption-configuration '{
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                }
            }
        ]
    }'

# 6. Block public access
echo "Blocking public access..."
aws s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Clean up temporary files
rm -f bucket-policy.json lifecycle-policy.json

echo "✅ S3 bucket setup complete!"
echo ""
echo "📝 Update your environment variables:"
echo "export S3_BUCKET_NAME=\"$BUCKET_NAME\""
echo "export S3_REGION=\"$REGION\""