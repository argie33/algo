#!/bin/bash
# Request SES Production Access for Cognito Email Verification
# This allows password reset emails to be sent to any email address
# Currently SES is in sandbox mode (can only send to verified addresses)

set -e

echo "=== SES Production Access Request ==="
echo ""
echo "Cognito password reset emails require SES production access."
echo "Currently SES is in Sandbox mode (cannot send to unverified addresses)."
echo ""
echo "To enable production email verification:"
echo ""
echo "1. Open AWS SES Console:"
echo "   https://us-east-1.console.aws.amazon.com/ses/home?region=us-east-1"
echo ""
echo "2. Click 'Account dashboard' in left menu"
echo ""
echo "3. Click 'Request production access' button"
echo ""
echo "4. Fill out the form:"
echo "   - Describe your use case: 'Trading platform authentication'"
echo "   - Website URL: 'https://algo.example.com' (or N/A)"
echo "   - Use case category: 'Transactional'"
echo "   - Email type: 'Individual Transactional Emails'"
echo "   - Expected volume: '<1000 emails per day'"
echo "   - Bounce/complaint rate: '<5%'"
echo ""
echo "5. AWS reviews the request (usually ~24 hours)"
echo ""
echo "6. Once approved, Cognito password reset emails will work"
echo "   (no code changes needed - infrastructure is already configured)"
echo ""
echo "Current status: cognito_custom_email_enabled = true in terraform.tfvars"
echo "                SES in Sandbox mode - production access pending"
