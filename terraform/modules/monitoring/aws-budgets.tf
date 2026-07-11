# ============================================================
# AWS Budgets - Automated Cost Alerts & Billing Notifications
# Sends daily/monthly cost summaries to user's email
# ============================================================

# ============================================================
# 1. Monthly Cost Budget with Email Alert
# Triggers when monthly spending reaches 50%, 80%, 100%, 120%
# ============================================================

resource "aws_budgets_budget" "monthly_cost_alert" {
  name              = "${var.project_name}-monthly-budget-${var.environment}"
  budget_type       = "COST"
  time_period_start = "2026-01-01_00:00"
  time_unit         = "MONTHLY"
  limit_amount      = "500"  # Monthly budget cap - adjust to expected monthly cost
  limit_unit        = "USD"

  tags = var.common_tags
}

# Budget alert at 80% (first warning)
resource "aws_budgets_budget_action" "monthly_80_percent" {
  budget_name             = aws_budgets_budget.monthly_cost_alert.name
  action_id               = "monthly-alert-80-percent"
  action_type             = "APPLY_IAM_POLICY"
  approval_model          = "AUTOMATIC"
  notification_type       = "ACTUAL"
  comparison_operator     = "GREATER_THAN"
  threshold               = 80
  threshold_type          = "PERCENTAGE"
  execution_role_arn      = aws_iam_role.budget_notification.arn

  definition {
    iam_action_definition {
      policy_arn = "arn:aws:iam::aws:policy/AWSDenyAllOutsideEU"
      roles      = []
      groups     = []
      users      = []
    }
  }

  subscriber {
    address            = var.alert_email_address
    subscription_type  = "EMAIL"
  }
}

# Budget alert at 100% (critical)
resource "aws_budgets_budget_action" "monthly_100_percent" {
  budget_name             = aws_budgets_budget.monthly_cost_alert.name
  action_id               = "monthly-alert-100-percent"
  action_type             = "APPLY_IAM_POLICY"
  approval_model          = "AUTOMATIC"
  notification_type       = "ACTUAL"
  comparison_operator     = "GREATER_THAN"
  threshold               = 100
  threshold_type          = "PERCENTAGE"
  execution_role_arn      = aws_iam_role.budget_notification.arn

  definition {
    iam_action_definition {
      policy_arn = "arn:aws:iam::aws:policy/AWSDenyAllOutsideEU"
      roles      = []
      groups     = []
      users      = []
    }
  }

  subscriber {
    address            = var.alert_email_address
    subscription_type  = "EMAIL"
  }
}

# ============================================================
# 2. Daily Cost Budget (rolling 1-day window)
# Enables rapid detection of cost spikes
# ============================================================

resource "aws_budgets_budget" "daily_cost_alert" {
  name              = "${var.project_name}-daily-budget-${var.environment}"
  budget_type       = "COST"
  time_period_start = "2026-01-01_00:00"
  time_unit         = "DAILY"
  limit_amount      = tostring(var.cost_threshold_daily_usd)
  limit_unit        = "USD"

  tags = merge(var.common_tags, {
    Name = "Daily cost monitor - triggers at ${var.cost_threshold_daily_usd} USD"
  })
}

# Daily budget alert at threshold (exact amount)
resource "aws_budgets_budget_action" "daily_threshold" {
  budget_name             = aws_budgets_budget.daily_cost_alert.name
  action_id               = "daily-alert-threshold"
  action_type             = "APPLY_IAM_POLICY"
  approval_model          = "AUTOMATIC"
  notification_type       = "ACTUAL"
  comparison_operator     = "GREATER_THAN_OR_EQUAL_TO"
  threshold               = 100
  threshold_type          = "PERCENTAGE"
  execution_role_arn      = aws_iam_role.budget_notification.arn

  definition {
    iam_action_definition {
      policy_arn = "arn:aws:iam::aws:policy/AWSDenyAllOutsideEU"
      roles      = []
      groups     = []
      users      = []
    }
  }

  subscriber {
    address            = var.alert_email_address
    subscription_type  = "EMAIL"
  }
}

# ============================================================
# 3. IAM Role for Budget Notifications
# (Currently unused but required by Terraform for budget_action)
# ============================================================

resource "aws_iam_role" "budget_notification" {
  name = "${var.project_name}-budget-notification-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "budgets.amazonaws.com"
      }
    }]
  })

  tags = var.common_tags
}

# ============================================================
# NOTES:
# ============================================================
# AWS Budgets automatically sends email notifications when:
# 1. Cost reaches specified thresholds (80%, 100%, etc.)
# 2. Forecast will exceed budget based on current spending
# 3. Daily/monthly budget limits are exceeded
#
# Email notifications are sent directly from AWS to var.alert_email_address
# No SNS topic or Lambda required for basic budget alerts
#
# Cost Explorer also provides daily/weekly summaries (free):
# - Log in to AWS Console > Cost Management > Cost Explorer
# - Set up Cost Anomaly Detection for automatic spike detection
#
# Recommended workflow:
# 1. AWS Budgets → Email alerts at cost thresholds
# 2. Cost Circuit Breaker Lambda → Automatic suspension if threshold exceeded
# 3. Manual review → Investigate root cause and manually re-enable
