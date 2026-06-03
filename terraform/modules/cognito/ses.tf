# SES Configuration for Cognito Custom Email Lambda
# Manages email identity verification for password reset emails

# Verify sender email identity in SES
resource "aws_ses_email_identity" "cognito_sender" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  email = var.cognito_sender_email

  tags = var.common_tags
}

# Alternative: Verify noreply@bullseyetrading.com as secondary sender
resource "aws_ses_email_identity" "noreply" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  email = "noreply@bullseyetrading.com"

  tags = var.common_tags
}

# Verify argeropolos@gmail.com so admin can receive password reset emails during testing
resource "aws_ses_email_identity" "admin_email" {
  count = var.cognito_custom_email_enabled ? 1 : 0
  email = "argeropolos@gmail.com"

  tags = var.common_tags
}

# Note: SES Production Access Request
# ====================================
# AWS SES starts in Sandbox mode, which prevents sending emails to unverified addresses.
# Password reset requires sending to any user email, so Sandbox mode blocks the feature.
#
# MANUAL STEP REQUIRED:
# This Terraform configuration verifies sender emails above, but AWS SES Production Access
# must be requested manually in the AWS Console:
#
# 1. Go to: https://console.aws.amazon.com/ses/home?region=us-east-1#account-provisioning
# 2. Click: "Request production access"
# 3. Fill form:
#    - Email: argeropolos@gmail.com
#    - Use Case: Authentication and password reset emails for stock trading platform
#    - Website: https://d2u93283nn45h2.cloudfront.net
#    - Volume: 50,000 emails/day
# 4. Submit → AWS approves in ~24 hours
# 5. Sandbox mode automatically lifts
#
# Why not automated?
# - AWS SES Production Access is a one-time approval process per account
# - No AWS API exists to programmatically request it (console-only)
# - Requires AWS manual review for abuse prevention
# - Only needs to be done once per account/region
#
# After production access is approved:
# - This Terraform configuration manages email identities
# - Cognito Lambda sends password reset emails to any address
# - Users can successfully reset passwords via email
# - No further manual SES configuration needed

output "ses_identities" {
  description = "SES verified email identities"
  value = var.cognito_custom_email_enabled ? {
    sender     = try(aws_ses_email_identity.cognito_sender[0].email, null)
    noreply    = try(aws_ses_email_identity.noreply[0].email, null)
    admin      = try(aws_ses_email_identity.admin_email[0].email, null)
  } : null
}

output "ses_production_access_status" {
  description = "Status of SES production access"
  value = var.cognito_custom_email_enabled ? "REQUIRES MANUAL AWS CONSOLE ACTION: Request production access at https://console.aws.amazon.com/ses/home?region=us-east-1#account-provisioning" : "SES email not enabled"
}
