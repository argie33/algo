# AWS Deployment Guide - Contact Form Email

## Current Status

✅ **Infrastructure Already Deployed:**
- VPC: `vpc-01bac8b5a4479dad9` (10.0.0.0/16)
- Stack: `stocks-core-stack`
- RDS: `stocks` database instance
- Lambda: `stocks-webapp-api-dev` already exists

## What Needs to be Done

### Step 1: Verify AWS SES Setup

Contact form emails will be sent via AWS SES. Follow these steps:

```bash
# 1. Go to AWS Console → SES (Simple Email Service)
# 2. Verify the sender email:
aws ses verify-email-identity --email-address noreply@bullseyefinancial.com --region us-east-1

# 3. Verify you can see the verification in AWS console
aws ses list-verified-email-addresses --region us-east-1
```

### Step 2: Update Lambda Function Environment Variables

The existing Lambda function needs these environment variables:

```
CONTACT_NOTIFICATION_EMAIL=edgebrookecapital@gmail.com
EMAIL_FROM=noreply@bullseyefinancial.com
AWS_REGION=us-east-1
```

**To set these:**
1. Go to AWS Lambda Console
2. Select function: `stocks-webapp-api-dev`
3. Configuration → Environment variables
4. Add the above three variables
5. Save

### Step 3: Update Lambda IAM Role

The Lambda execution role needs SES permissions:

```bash
# Get the Lambda role name
LAMBDA_ROLE=$(aws lambda get-function-configuration \
  --function-name stocks-webapp-api-dev \
  --query Role --output text)

# Add SES permissions to the role
aws iam put-role-policy \
  --role-name $(echo $LAMBDA_ROLE | awk -F/ '{print $NF}') \
  --policy-name AllowSES \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ],
        "Resource": "*"
      }
    ]
  }'
```

Or through AWS Console:
1. Go to IAM → Roles
2. Find the Lambda execution role
3. Add inline policy "AllowSES" with SES permissions above

### Step 4: Store Email Config in Secrets Manager

```bash
# Create the email config secret
aws secretsmanager create-secret \
  --name stocks-email-config \
  --secret-string '{
    "contact_notification_email": "edgebrookecapital@gmail.com",
    "email_from": "noreply@bullseyefinancial.com"
  }' \
  --region us-east-1

# Grant Lambda role access to read it
LAMBDA_ROLE_ARN=$(aws lambda get-function-configuration \
  --function-name stocks-webapp-api-dev \
  --query Role --output text)

aws secretsmanager add-secret-permission \
  --secret-name stocks-email-config \
  --principal $LAMBDA_ROLE_ARN \
  --operation GetSecretValue \
  --region us-east-1
```

### Step 5: Deploy Updated Code

Option A - If you have CloudFormation permissions:
```bash
cd /home/stocks/algo/webapp/lambda
serverless deploy --stage prod
```

Option B - If you need to use existing function:
```bash
cd /home/stocks/algo/webapp/lambda
npm run package
aws lambda update-function-code \
  --function-name stocks-webapp-api-dev \
  --zip-file fileb://function.zip
```

### Step 6: Get API Gateway URL

```bash
# Get the API Gateway URL for the Lambda function
aws apigateway get-rest-apis --query 'items[0].[id,name]' --output text

# Or find the Function URL if configured
aws lambda get-function-url-config --function-name stocks-webapp-api-dev
```

## Testing

### Test 1: Verify SES is Working

```bash
# Send a test email from AWS SES console
# Or use AWS CLI:
aws ses send-email \
  --from noreply@bullseyefinancial.com \
  --to edgebrookecapital@gmail.com \
  --subject "AWS SES Test" \
  --text "This is a test email from SES" \
  --region us-east-1
```

### Test 2: Test Contact Form in AWS

```bash
# Get the API Gateway endpoint URL
ENDPOINT=$(aws lambda get-function-url-config \
  --function-name stocks-webapp-api-dev \
  --query FunctionUrl --output text)

# Or construct from API Gateway:
ENDPOINT="https://YOUR-API-ID.execute-api.us-east-1.amazonaws.com/YOUR-STAGE"

# Test the contact endpoint
curl -X POST $ENDPOINT/api/contact \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AWS Test",
    "email": "test@example.com",
    "subject": "Testing AWS Email",
    "message": "Testing contact form in AWS"
  }'
```

### Test 3: Verify Email Received

Check inbox at `edgebrookecapital@gmail.com` for the notification email.

### Test 4: Verify Local Still Works

```bash
# Make sure backend is running locally
cd /home/stocks/algo/webapp/lambda
npm start

# Test local API
curl -X POST http://localhost:3001/api/contact \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Local Test",
    "email": "test@example.com",
    "subject": "Local Test",
    "message": "Testing local submission"
  }'
```

## Troubleshooting

### Email Not Sent in AWS

1. **Check CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/stocks-webapp-api-dev --follow
   ```

2. **Verify SES sender is verified:**
   ```bash
   aws ses list-verified-email-addresses
   ```

3. **Check Lambda role has SES permissions:**
   ```bash
   aws iam get-role-policy --role-name LAMBDA-ROLE-NAME --policy-name AllowSES
   ```

### Deployment Failed

- Make sure you have CloudFormation and Lambda permissions
- Or use the `aws lambda update-function-code` method above

### Contact Form Returns Error

1. Check Lambda logs in CloudWatch
2. Verify database connection string in environment
3. Verify email environment variables are set

## Next Steps

1. ✅ **Ask admin to verify AWS SES** - sender email must be verified
2. ✅ **Add environment variables to Lambda**
3. ✅ **Add SES permissions to Lambda role**
4. ✅ **Create email secret in Secrets Manager**
5. ✅ **Deploy updated Lambda code**
6. ✅ **Test contact form in AWS**
7. ✅ **Verify email in inbox**
8. ✅ **Verify local still works**

## Code Changes Ready

The following code changes are already committed and ready:
- ✅ `utils/email.js` - Email service with AWS SES support
- ✅ `routes/contact.js` - Contact form endpoint with email
- ✅ `template-app-stocks.yml` - CloudFormation template with SES permissions
- ✅ `serverless.yml` - Serverless config with email env vars

Just need AWS admin to execute the deployment steps above.
