#!/bin/bash
# Billing Circuit Breaker Deployment Script
# This script deploys AWS Budgets + SNS + Lambda circuit breaker in one command

set -e

echo "🛡️  AWS Billing Circuit Breaker Deployment"
echo "==========================================="
echo ""

# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "✓ AWS Account ID: $ACCOUNT_ID"

# Get region
REGION=${AWS_REGION:-us-east-1}
echo "✓ Region: $REGION"

# Find Lambda role
echo ""
echo "Finding your Lambda execution role..."
ROLE_NAME=$(aws iam list-roles --query "Roles[?contains(RoleName, 'stocks-algo-api')].RoleName" --output text | head -1)

if [ -z "$ROLE_NAME" ]; then
  echo "❌ ERROR: Could not find Lambda role"
  echo "   Expected role name containing 'stocks-algo-api'"
  echo "   Available roles:"
  aws iam list-roles --query "Roles[].RoleName" --output text
  exit 1
fi

LAMBDA_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
echo "✓ Lambda Role: $LAMBDA_ROLE_ARN"

# Prompt for phone number
echo ""
read -p "Enter phone number for SMS alerts [+1-312-307-8620]: " PHONE_NUMBER
PHONE_NUMBER=${PHONE_NUMBER:-+13123078620}

# Prompt for email
echo ""
read -p "Enter email for alerts [argeropolos@gmail.com]: " EMAIL
EMAIL=${EMAIL:-argeropolos@gmail.com}

# Prompt for budget
echo ""
read -p "Enter monthly budget limit in USD [100]: " BUDGET
BUDGET=${BUDGET:-100}

# Confirm deployment
echo ""
echo "📋 Deployment Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Account ID:      $ACCOUNT_ID"
echo "  Region:          $REGION"
echo "  Lambda Role:     $ROLE_NAME"
echo "  Phone Number:    $PHONE_NUMBER"
echo "  Email:           $EMAIL"
echo "  Monthly Budget:  \$$BUDGET"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Proceed with deployment? (y/n) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "❌ Deployment cancelled"
  exit 1
fi

# Deploy
echo ""
echo "⏳ Deploying billing circuit breaker (this takes ~2 minutes)..."
echo ""

aws cloudformation deploy \
  --template-file billing-circuit-breaker.yml \
  --stack-name billing-circuit-breaker \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    PhoneNumber=$PHONE_NUMBER \
    EmailAddress=$EMAIL \
    MonthlyBudgetLimit=$BUDGET \
    LambdaExecutionRoleArn=$LAMBDA_ROLE_ARN \
  --region $REGION \
  --no-fail-on-empty-changeset

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Check your email ($EMAIL)"
echo "   - Confirm SNS subscription (click link in email)"
echo "   - You should see 2 confirmation emails"
echo ""
echo "2. Check your phone ($PHONE_NUMBER)"
echo "   - SMS confirmation will arrive shortly"
echo "   - Reply to confirm (or just wait, it auto-confirms)"
echo ""
echo "3. Test the alert system:"
echo "   aws sns publish \\"
echo "     --topic-arn arn:aws:sns:$REGION:$ACCOUNT_ID:billing-circuit-breaker-alerts \\"
echo "     --subject 'Test Alert' \\"
echo "     --message 'Testing your billing circuit breaker'"
echo ""
echo "4. Monitor your AWS costs:"
echo "   https://console.aws.amazon.com/billing"
echo ""
echo "📚 Documentation:"
echo "   See BILLING_CIRCUIT_BREAKER.md for full details"
echo ""
echo "🚨 When Hard Stop Activates:"
echo "   ✓ Email alert (immediate)"
echo "   ✓ SMS alert (immediate)"
echo "   ✓ API goes offline (403 Forbidden)"
echo "   ✓ No new AWS charges can accrue"
echo ""
echo "✅ Your system is now protected!"
