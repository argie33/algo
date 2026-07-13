# ============================================================
# AWS Budgets - Cost Tracking (Email via AWS Console + Lambda)
# Creates budget definitions for Cost Explorer dashboard
# ============================================================

# Monthly Cost Budget - $500/month limit
resource "aws_budgets_budget" "monthly_cost" {
  name              = "${var.project_name}-monthly-budget-${var.environment}"
  budget_type       = "COST"
  time_period_start = "2026-01-01_00:00"
  time_unit         = "MONTHLY"
  limit_amount      = "500"
  limit_unit        = "USD"

  tags = merge(var.common_tags, {
    Name = "monthly-budget-500-usd"
  })
}

# Daily Cost Budget - Configurable threshold ($50 dev, $200 prod)
resource "aws_budgets_budget" "daily_cost" {
  name              = "${var.project_name}-daily-budget-${var.environment}"
  budget_type       = "COST"
  time_period_start = "2026-01-01_00:00"
  time_unit         = "DAILY"
  limit_amount      = tostring(var.cost_threshold_daily_usd)
  limit_unit        = "USD"

  # Email notification when threshold is exceeded
  notification {
    comparison_operator        = "GREATER_THAN"
    notification_type          = "FORECASTED"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = ["argeropolos@gmail.com"]
  }

  tags = merge(var.common_tags, {
    Name = "daily-budget-threshold"
  })
}

# Email Alerts Delivery:
# 1. AWS Console: Billing → Billing Preferences → "Receive Billing Alerts"
# 2. Cost Circuit Breaker Lambda: SNS emails every 6 hours + on threshold breach
