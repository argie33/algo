# ============================================================
# Credential Rotation Reminders (Issue #8)
# ============================================================
# AWS OIDC credentials rotate automatically via Terraform.
# Manual credentials (Alpaca paper/live, FRED API) need quarterly rotation.
# These reminders ensure rotation doesn't get skipped.
# ============================================================

# Quarterly Alpaca credential rotation reminder (90 days)
# Update the alpaca_credential_rotation_date variable to trigger this
resource "aws_scheduler_schedule" "alpaca_rotation_reminder" {
  count                        = var.sns_alerts_enabled ? 1 : 0
  name                         = "${var.project_name}-alpaca-rotation-reminder-${var.environment}"
  description                  = "REMINDER: Quarterly Alpaca credential rotation due"
  schedule_expression          = var.alpaca_credential_rotation_schedule
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sns_topic.algo_alerts[0].arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      default = "Quarterly credential rotation reminder: Rotate Alpaca API keys in AWS Secrets Manager at /algo/alpaca. Update terraform.tfvars alpaca_credential_rotation_date to acknowledge. See CLAUDE.md → Credential Rotation for steps."
    })
  }

  depends_on = [
    aws_sns_topic.algo_alerts
  ]
}

# Quarterly FRED credential rotation reminder
# Update the fred_credential_rotation_date variable to trigger this
resource "aws_scheduler_schedule" "fred_rotation_reminder" {
  count                        = var.sns_alerts_enabled ? 1 : 0
  name                         = "${var.project_name}-fred-rotation-reminder-${var.environment}"
  description                  = "REMINDER: Quarterly FRED API credential rotation due"
  schedule_expression          = var.fred_credential_rotation_schedule
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sns_topic.algo_alerts[0].arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      default = "Quarterly credential rotation reminder: Rotate FRED API key in AWS Secrets Manager at /algo/fred. Update terraform.tfvars fred_credential_rotation_date to acknowledge. See CLAUDE.md → Credential Rotation for steps."
    })
  }

  depends_on = [
    aws_sns_topic.algo_alerts
  ]
}

# Quarterly Developer IAM key rotation reminder (already exists, documented here for completeness)
# Update developer_key_rotation_date in terraform.tfvars to trigger new reminder schedule
# This is handled via GitHub Actions + Terraform automation
