/**
 * Loaders Module - ECS Task Definitions, EventBridge Scheduled Rules
 *
 * Creates:
 * - 40 ECS task definitions (all data loaders)
 * - 33 EventBridge scheduled rules (staggered ET schedule)
 * - IAM roles for EventBridge and ECS task execution
 *
 * All loaders run on Fargate in private subnets with proper resource allocation
 */

# ============================================================
# IAM Roles & Policies
# ============================================================

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

  tags = var.common_tags
}

# EventBridge IAM policy to run ECS tasks
resource "aws_iam_role_policy" "eventbridge_run_task_policy" {
  name = "${var.project_name}-eventbridge-run-task-policy"
  role = aws_iam_role.eventbridge_run_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRunTask"
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:task-definition/${var.project_name}-*:*"
      },
      {
        Sid    = "AllowPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          var.task_execution_role_arn
        ]
      }
    ]
  })
}

# ============================================================
# Scheduled EventBridge Rules - All 40 Loaders
# ============================================================
# Loaders are scheduled to run at optimal times to:
# 1. Respect data dependencies (prices first, then signals)
# 2. Distribute API load across the trading day
# 3. Avoid resource contention
#
# Schedule Map:
# - 3:30am ET (8:30am UTC): stock_symbols
# - 4:00am ET (9am UTC): price loaders (6 parallel)
# - 10:00am ET (3pm UTC): financial statements (8 parallel)
# - 11:00am ET (4pm UTC): earnings data (4 parallel)
# - 12:00pm ET (5pm UTC): market/economic data (10 parallel)
# - 1:00pm ET (6pm UTC): sentiment/analysis (5 parallel)
# - 5:00pm ET (10pm UTC): trading signals (5 parallel)
# - 5:15pm ET (10:15pm UTC): algo metrics (after signals)

locals {
  scheduled_loaders = {
    # 3:30am ET = 8:30am UTC Mon-Fri
    "stock_symbols" = {
      schedule = "cron(30 8 ? * MON-FRI *)"
      description = "Stock symbols reference data - 3:30am ET"
    }

    # 4:00am ET = 9am UTC Mon-Fri
    "stock_prices_daily" = {
      schedule = "cron(0 9 ? * MON-FRI *)"
      description = "Daily stock prices - 4:00am ET"
    }
    "stock_prices_weekly" = {
      schedule = "cron(5 9 ? * MON-FRI *)"
      description = "Weekly stock prices - 4:05am ET"
    }
    "stock_prices_monthly" = {
      schedule = "cron(10 9 ? * MON-FRI *)"
      description = "Monthly stock prices - 4:10am ET"
    }
    "etf_prices_daily" = {
      schedule = "cron(15 9 ? * MON-FRI *)"
      description = "Daily ETF prices - 4:15am ET"
    }
    "etf_prices_weekly" = {
      schedule = "cron(20 9 ? * MON-FRI *)"
      description = "Weekly ETF prices - 4:20am ET"
    }
    "etf_prices_monthly" = {
      schedule = "cron(25 9 ? * MON-FRI *)"
      description = "Monthly ETF prices - 4:25am ET"
    }

    # 10:00am ET = 3pm UTC Mon-Fri
    "financials_annual_income" = {
      schedule = "cron(0 15 ? * MON-FRI *)"
      description = "Annual income statements - 10:00am ET"
    }
    "financials_annual_balance" = {
      schedule = "cron(5 15 ? * MON-FRI *)"
      description = "Annual balance sheets - 10:05am ET"
    }
    "financials_annual_cashflow" = {
      schedule = "cron(10 15 ? * MON-FRI *)"
      description = "Annual cash flow - 10:10am ET"
    }
    "financials_quarterly_income" = {
      schedule = "cron(15 15 ? * MON-FRI *)"
      description = "Quarterly income statements - 10:15am ET"
    }
    "financials_quarterly_balance" = {
      schedule = "cron(20 15 ? * MON-FRI *)"
      description = "Quarterly balance sheets - 10:20am ET"
    }
    "financials_quarterly_cashflow" = {
      schedule = "cron(25 15 ? * MON-FRI *)"
      description = "Quarterly cash flow - 10:25am ET"
    }
    "financials_ttm_income" = {
      schedule = "cron(30 15 ? * MON-FRI *)"
      description = "TTM income statements - 10:30am ET"
    }
    "financials_ttm_cashflow" = {
      schedule = "cron(35 15 ? * MON-FRI *)"
      description = "TTM cash flow - 10:35am ET"
    }

    # 11:00am ET = 4pm UTC Mon-Fri
    "earnings_history" = {
      schedule = "cron(0 16 ? * MON-FRI *)"
      description = "Earnings history - 11:00am ET"
    }
    "earnings_revisions" = {
      schedule = "cron(5 16 ? * MON-FRI *)"
      description = "Earnings revisions - 11:05am ET"
    }
    "earnings_surprise" = {
      schedule = "cron(10 16 ? * MON-FRI *)"
      description = "Earnings surprise - 11:10am ET"
    }
    "earnings_sp500" = {
      schedule = "cron(15 16 ? * MON-FRI *)"
      description = "S&P 500 earnings - 11:15am ET"
    }

    # 12:00pm ET = 5pm UTC Mon-Fri
    "market_overview" = {
      schedule = "cron(0 17 ? * MON-FRI *)"
      description = "Market overview - 12:00pm ET"
    }
    "market_indices" = {
      schedule = "cron(5 17 ? * MON-FRI *)"
      description = "Market indices - 12:05pm ET"
    }
    "sector_performance" = {
      schedule = "cron(10 17 ? * MON-FRI *)"
      description = "Sector performance - 12:10pm ET"
    }
    "relative_performance" = {
      schedule = "cron(15 17 ? * MON-FRI *)"
      description = "Relative performance - 12:15pm ET"
    }
    "seasonality" = {
      schedule = "cron(20 17 ? * MON-FRI *)"
      description = "Seasonality - 12:20pm ET"
    }
    "econ_data" = {
      schedule = "cron(25 17 ? * MON-FRI *)"
      description = "Economic data - 12:25pm ET"
    }
    "aaiidata" = {
      schedule = "cron(30 17 ? * MON-FRI *)"
      description = "AAII data - 12:30pm ET"
    }
    "naaim_data" = {
      schedule = "cron(35 17 ? * MON-FRI *)"
      description = "NAAIM data - 12:35pm ET"
    }
    "feargreed" = {
      schedule = "cron(40 17 ? * MON-FRI *)"
      description = "Fear & Greed Index - 12:40pm ET"
    }
    "calendar" = {
      schedule = "cron(45 17 ? * MON-FRI *)"
      description = "Economic calendar - 12:45pm ET"
    }

    # 1:00pm ET = 6pm UTC Mon-Fri
    "analyst_sentiment" = {
      schedule = "cron(0 18 ? * MON-FRI *)"
      description = "Analyst sentiment - 1:00pm ET"
    }
    "analyst_upgrades" = {
      schedule = "cron(5 18 ? * MON-FRI *)"
      description = "Analyst upgrades - 1:05pm ET"
    }
    "social_sentiment" = {
      schedule = "cron(10 18 ? * MON-FRI *)"
      description = "Social sentiment - 1:10pm ET"
    }
    "factor_metrics" = {
      schedule = "cron(15 18 ? * MON-FRI *)"
      description = "Factor metrics - 1:15pm ET"
    }
    "stock_scores" = {
      schedule = "cron(20 18 ? * MON-FRI *)"
      description = "Stock scores - 1:20pm ET"
    }

    # 5:00pm ET = 10pm UTC Mon-Fri
    "signals_daily" = {
      schedule = "cron(0 22 ? * MON-FRI *)"
      description = "Daily trading signals - 5:00pm ET"
    }
    "signals_weekly" = {
      schedule = "cron(5 22 ? * MON-FRI *)"
      description = "Weekly trading signals - 5:05pm ET"
    }
    "signals_monthly" = {
      schedule = "cron(10 22 ? * MON-FRI *)"
      description = "Monthly trading signals - 5:10pm ET"
    }
    "signals_etf_daily" = {
      schedule = "cron(15 22 ? * MON-FRI *)"
      description = "Daily ETF signals - 5:15pm ET"
    }
    "etf_signals" = {
      schedule = "cron(20 22 ? * MON-FRI *)"
      description = "ETF signals - 5:20pm ET"
    }

    # 5:25pm ET = 10:25pm UTC Mon-Fri (after signals complete)
    "algo_metrics_daily" = {
      schedule = "cron(25 22 ? * MON-FRI *)"
      description = "Algo metrics - 5:25pm ET"
    }
  }
}

resource "aws_cloudwatch_event_rule" "scheduled_loader" {
  for_each = local.scheduled_loaders

  name                = "${var.project_name}-${each.key}-schedule"
  description         = each.value.description
  schedule_expression = each.value.schedule
  state               = "ENABLED"

  tags = var.common_tags
}

locals {
  all_loaders = {
    # Reference data (3:30am ET) - FARGATE: 256 CPU = min 512 MB
    "stock_symbols"          = { cpu = 256, memory = 512, timeout = 300 }

    # Price data loaders (4:00am ET) - HIGH CPU/MEMORY - FARGATE: 512 CPU = 1024-4096 MB
    "stock_prices_daily"     = { cpu = 512, memory = 1024, timeout = 600 }
    "stock_prices_weekly"    = { cpu = 512, memory = 1024, timeout = 600 }
    "stock_prices_monthly"   = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_daily"       = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_weekly"      = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_monthly"     = { cpu = 512, memory = 1024, timeout = 600 }

    # Financial statements (10:00am ET) - FARGATE: 256 CPU = min 512 MB
    "financials_annual_income"     = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_annual_balance"    = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_annual_cashflow"   = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_income"  = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_balance" = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_cashflow" = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_ttm_income"        = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_ttm_cashflow"      = { cpu = 256, memory = 512, timeout = 1200 }

    # Earnings data (11:00am ET) - FARGATE: 256 CPU = min 512 MB
    "earnings_history"   = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_revisions" = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_surprise"  = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_sp500"     = { cpu = 256, memory = 512, timeout = 600 }

    # Market & economic data (12:00pm ET - 6:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "market_overview"    = { cpu = 256, memory = 512, timeout = 300 }
    "market_indices"     = { cpu = 256, memory = 512, timeout = 300 }
    "sector_performance" = { cpu = 256, memory = 512, timeout = 300 }
    "relative_performance" = { cpu = 256, memory = 512, timeout = 300 }
    "seasonality"        = { cpu = 256, memory = 512, timeout = 300 }
    "econ_data"          = { cpu = 256, memory = 512, timeout = 300 }
    "aaiidata"           = { cpu = 256, memory = 512, timeout = 300 }
    "naaim_data"         = { cpu = 256, memory = 512, timeout = 300 }
    "feargreed"          = { cpu = 256, memory = 512, timeout = 300 }
    "calendar"           = { cpu = 256, memory = 512, timeout = 300 }

    # Sentiment & analysis (1:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "analyst_sentiment"  = { cpu = 256, memory = 512, timeout = 600 }
    "analyst_upgrades"   = { cpu = 256, memory = 512, timeout = 600 }
    "social_sentiment"   = { cpu = 256, memory = 512, timeout = 600 }
    "factor_metrics"     = { cpu = 256, memory = 512, timeout = 600 }
    "stock_scores"       = { cpu = 256, memory = 512, timeout = 600 }

    # Trading signals (5:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "signals_daily"      = { cpu = 256, memory = 512, timeout = 900 }
    "signals_weekly"     = { cpu = 256, memory = 512, timeout = 900 }
    "signals_monthly"    = { cpu = 256, memory = 512, timeout = 900 }
    "signals_etf_daily"  = { cpu = 256, memory = 512, timeout = 900 }
    "etf_signals"        = { cpu = 256, memory = 512, timeout = 900 }

    # Algo metrics (5:15pm ET - after signals) - FARGATE: 256 CPU = min 512 MB
    "algo_metrics_daily" = { cpu = 256, memory = 512, timeout = 600 }
  }

  # For backward compatibility
  default_loaders = local.all_loaders
}

# ECS Task Definitions for all 40 data loaders
# NOTE: CPU/memory in container definition are removed - only task-level values matter for Fargate
resource "aws_ecs_task_definition" "loader" {
  for_each = local.all_loaders

  family = "${var.project_name}-${each.key}-loader"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-${each.key}"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
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
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

# CloudWatch Log Groups for all loaders
resource "aws_cloudwatch_log_group" "loader" {
  for_each = local.all_loaders

  name              = "/ecs/${var.project_name}-${each.key}-loader"
  retention_in_days = 30

  tags = var.common_tags
}

# ============================================================
# EventBridge Targets - ECS Task Execution (All 40 Loaders)
# ============================================================

resource "aws_cloudwatch_event_target" "scheduled_loader_target" {
  for_each = local.scheduled_loaders

  rule      = aws_cloudwatch_event_rule.scheduled_loader[each.key].name
  target_id = "${upper(replace(each.key, "_", ""))}Target"
  arn       = var.ecs_cluster_arn
  role_arn  = aws_iam_role.eventbridge_run_task.arn

  ecs_target {
    launch_type         = "FARGATE"
    task_definition_arn = aws_ecs_task_definition.loader[each.key].arn
    task_count          = 1
    platform_version    = "LATEST"

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [var.ecs_tasks_sg_id]
      assign_public_ip = false
    }
  }
}
