#!/bin/bash
# Setup GitHub Secrets for SMTP email alerts
# Run this script to configure email alerts via GitHub Secrets

set -e

REPO=${1:-.}  # Default to current repo
OWNER=$(git -C "$REPO" config --get remote.origin.url | sed 's|.*github.com[:/]\([^/]*\)/.*|\1|')
REPO_NAME=$(git -C "$REPO" config --get remote.origin.url | sed 's|.*github.com[:/][^/]*/\([^/]*\)\.git$|\1|')

echo "Repository: $OWNER/$REPO_NAME"
echo ""
echo "=== Gmail SMTP Setup for Email Alerts ==="
echo ""
echo "1. In your Google Account, enable 2-factor authentication:"
echo "   https://myaccount.google.com/security"
echo ""
echo "2. Generate an app-specific password:"
echo "   https://myaccount.google.com/apppasswords"
echo "   - Select 'Mail' and 'Windows Computer'"
echo "   - Google will generate a 16-character password"
echo ""
echo "3. Create GitHub Secret:"
echo "   gh secret set ALERT_SMTP_PASSWORD --repo $OWNER/$REPO_NAME"
echo "   (Paste the 16-character password when prompted)"
echo ""
echo "4. Verify it was set:"
echo "   gh secret list --repo $OWNER/$REPO_NAME | grep ALERT_SMTP_PASSWORD"
echo ""
echo "After setup, email alerts will be sent from argeropolos@gmail.com via SMTP."
echo "Infrastructure alerts continue to work via SNS."
