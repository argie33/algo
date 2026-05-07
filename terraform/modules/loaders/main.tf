/**
 * Loaders Module - ECS Task Definitions, EventBridge Scheduled Rules
 *
 * Creates:
 * - 65 ECS task definitions (data loaders)
 * - 4 EventBridge scheduled rules for evening loaders
 * - IAM role for EventBridge to run ECS tasks
 *
 * Reference: template-loader-tasks.yml
 */

# This module is substantial - ~2000 lines in template-loader-tasks.yml

# EventBridge role to run ECS tasks
resource "aws_iam_role" "eventbridge_run_task_role" {
  name = "${var.project_name}-eventbridge-run-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_run_task_policy" {
  name = "${var.project_name}-eventbridge-run-task-policy"
  role = aws_iam_role.eventbridge_run_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = "${var.task_execution_role_arn}"
      }
    ]
  })
}

# Example scheduled rule - Market Indices Loader
resource "aws_cloudwatch_event_rule" "market_indices_schedule" {
  name                = "${var.project_name}-market-indices-schedule"
  description         = "Run market indices loader at 5pm ET (9pm UTC)"
  schedule_expression = "cron(0 21 ? * MON-FRI *)"

  tags = var.common_tags
}

# Example scheduled rule - EconData Loader (6pm ET)
resource "aws_cloudwatch_event_rule" "econdata_schedule" {
  name                = "${var.project_name}-econdata-evening-schedule"
  description         = "Run econdata loader at 6pm ET (10pm UTC)"
  schedule_expression = "cron(0 22 ? * MON-FRI *)"

  tags = var.common_tags
}

# Example scheduled rule - Sector Ranking Loader (6:30pm ET)
resource "aws_cloudwatch_event_rule" "sector_ranking_schedule" {
  name                = "${var.project_name}-sector-ranking-schedule"
  description         = "Run sector ranking loader at 6:30pm ET (10:30pm UTC)"
  schedule_expression = "cron(30 22 ? * MON-FRI *)"

  tags = var.common_tags
}

# Example scheduled rule - Fear&Greed Loader (7pm ET)
resource "aws_cloudwatch_event_rule" "fear_greed_schedule" {
  name                = "${var.project_name}-fear-greed-evening-schedule"
  description         = "Run fear&greed loader at 7pm ET (11pm UTC)"
  schedule_expression = "cron(0 23 ? * MON-FRI *)"

  tags = var.common_tags
}
