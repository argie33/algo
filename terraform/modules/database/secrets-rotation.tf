# ============================================================
# Secrets Manager Rotation Configuration
# ============================================================
# Automated rotation of all critical secrets via Lambda functions
# and AWS Secrets Manager rotation rules.

# ============================================================
# RDS Credentials Rotation (already configured in main.tf)
# This file documents the rotation strategy and ensures
# all rotation parameters are properly set.
# ============================================================

# Documentation of rotation configuration:
#
# - RDS Master Credentials: Auto-rotates every N days (var.secrets_rotation_days)
#   * Uses AWS Lambda function for PostgreSQL password rotation
#   * Maintains password version history for backward compatibility
#   * CloudWatch alarms alert on rotation failures
#
# - Alpaca API Keys: Manual rotation (not auto-rotated)
#   * Requires user action via AWS Console or AWS CLI
#   * Contains two secrets: api_key_id and secret_key
#   * Updated by scripts/update_alpaca_credentials.sh
#
# - FRED API Key: Manual rotation
#   * Updated by scripts/update_fred_credentials.sh
#
# - Email Config: Manual rotation
#   * Updated by scripts/update_email_config.sh

# ============================================================
# Verify rotation is enabled for RDS credentials
# ============================================================
# This resource is defined in main.tf at line ~817:
#
# resource "aws_secretsmanager_secret_rotation" "rds_credentials" {
#   secret_id           = aws_secretsmanager_secret.rds_credentials.id
#   rotation_lambda_arn = aws_lambda_function.rds_rotation.arn
#
#   rotation_rules {
#     automatically_after_days = var.secrets_rotation_days
#   }
#
#   depends_on = [aws_lambda_permission.rds_rotation_secrets_manager]
# }
#
# Default: secrets_rotation_days = 30 (can be overridden via terraform.tfvars)

# ============================================================
# AWS Access Key Rotation (via GitHub Actions)
# ============================================================
# GitHub Actions workflow handles programmatic key rotation:
# - File: .github/workflows/rotate-aws-credentials.yml
# - Trigger: Monthly on 1st of month OR manual workflow_dispatch
# - Process:
#   1. Create new access key for github-actions IAM user
#   2. Test new key works (S3 + STS calls)
#   3. Update GitHub secrets with new key
#   4. Deactivate old key (after new key is in use)
#   5. After verification period, delete old key
#
# Manual rotation options:
#   - Via GitHub UI: Actions > Rotate AWS Credentials > Run workflow
#   - Via gh CLI: gh workflow run rotate-aws-credentials.yml
#   - Via AWS CLI: aws iam create-access-key --user-name algo-developer

# ============================================================
# Monitoring & Alerts
# ============================================================
# CloudWatch alarms (defined in main.tf ~line 970):
#
# 1. rds-rotation-failed-${environment}
#    - Alerts when rotation Lambda fails
#    - Action: Check RDS rotation Lambda logs in CloudWatch
#
# 2. rds-rotation-slow-${environment}
#    - Alerts when rotation takes >10 minutes
#    - Action: Check if RDS instance is under load

# ============================================================
# Local Development Notes
# ============================================================
# For local development without AWS:
# - Database password stored in .env file (checked into .gitignore)
# - No automatic rotation in local dev
# - Manual password updates: update .env + docker-compose.yml
#
# Transition to production:
# - RDS rotation handled by Terraform + Lambda
# - No manual password management needed
# - GitHub Actions handles AWS key rotation
