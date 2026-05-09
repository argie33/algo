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
resource "aws_iam_role" "eventbridge_run_task" {
  name = "${var.project_name}-svc-eventbridge-run-task-${var.environment}"

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
  role = aws_iam_role.eventbridge_run_task.id

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

# ============================================================
# NOTE: Loader Implementation Status
# ============================================================
# Currently implemented: 7 core loaders (stock symbols, prices, fundamentals,
# market indices, econdata, feargreed, sector ranking)
#
# Missing: 58 additional loaders from template-loader-tasks.yml
# To add remaining loaders, populate the default_loaders map below with
# additional loader definitions and create corresponding EventBridge rules

locals {
  default_loaders = {
    # Stock data loaders
    "stock_symbols"        = { cpu = 256, memory = 512 }
    "stock_prices"         = { cpu = 256, memory = 512 }
    "company_fundamentals" = { cpu = 256, memory = 512 }
    "market_indices"       = { cpu = 256, memory = 512 }
    "econdata"             = { cpu = 256, memory = 512 }
    "feargreed"            = { cpu = 256, memory = 512 }
    "sector_ranking"       = { cpu = 256, memory = 512 }
  }
}

# Placeholder task definitions (stub - to be expanded)
resource "aws_ecs_task_definition" "loader" {
  for_each = local.default_loaders

  family = "${var.project_name}-${each.key}-loader"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-${each.key}"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      cpu       = each.value.cpu
      memory    = each.value.memory
      essential = true

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.loader[each.key].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      secrets = [
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.db_secret_arn}:password::"
        },
        {
          name      = "DB_USER"
          valueFrom = "${var.db_secret_arn}:username::"
        }
      ]

      environment = [
        {
          name  = "LOADER_TYPE"
          value = each.key
        }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.task_execution_role_arn

  tags = var.common_tags
}

# Placeholder log groups for loaders (stub)
resource "aws_cloudwatch_log_group" "loader" {
  for_each = local.default_loaders

  name              = "/ecs/${var.project_name}-${each.key}-loader"
  retention_in_days = 30

  tags = var.common_tags
}

resource "aws_cloudwatch_event_rule" "fear_greed_schedule" {
  name                = "${var.project_name}-fear-greed-evening-schedule"
  description         = "Run fear&greed loader at 7pm ET (11pm UTC)"
  schedule_expression = "cron(0 23 ? * MON-FRI *)"

  tags = var.common_tags
}
