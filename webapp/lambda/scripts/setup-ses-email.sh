#!/bin/bash
# Setup Amazon SES for Email Services

set -e

REGION="us-east-1"
FROM_EMAIL="noreply@stocksapp.example.com"

echo "📧 Setting up Amazon SES for email services..."

# 1. Verify email address (for sandbox mode)
echo "Verifying sender email address..."
aws ses verify-email-identity \
    --region $REGION \
    --email-address "$FROM_EMAIL" \
    || echo "Email may already be verified"

# 2. Create configuration set
echo "Creating SES configuration set..."
aws ses create-configuration-set \
    --region $REGION \
    --configuration-set Name="stocks-webapp-emails" \
    || echo "Configuration set may already exist"

# 3. Add reputation tracking
echo "Adding reputation tracking..."
aws ses add-configuration-set-reputation-tracking \
    --region $REGION \
    --configuration-set-name "stocks-webapp-emails" \
    --enabled \
    || echo "Reputation tracking may already be enabled"

# 4. Add delivery options
echo "Adding delivery options..."
aws ses add-configuration-set-delivery-options \
    --region $REGION \
    --configuration-set-name "stocks-webapp-emails" \
    --delivery-options TlsPolicy=Require \
    || echo "Delivery options may already be configured"

# 5. Request production access (manual step required)
echo ""
echo "⚠️  MANUAL STEP REQUIRED:"
echo "Request production access for SES to send emails to unverified addresses:"
echo "1. Go to AWS SES Console"
echo "2. Navigate to 'Sending Statistics'"
echo "3. Click 'Request production access'"
echo "4. Fill out the request form"

echo "✅ Amazon SES setup complete!"
echo ""
echo "📝 Update your environment variables:"
echo "export SES_FROM_EMAIL=\"$FROM_EMAIL\""
echo "export SES_CONFIGURATION_SET=\"stocks-webapp-emails\""
echo "export SES_REGION=\"$REGION\""