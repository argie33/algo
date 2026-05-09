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

# ============================================================
# SQS Dead-Letter Queue for EventBridge loader failures
# ============================================================

resource "aws_sqs_queue" "loader_dlq" {
  name                      = "${var.project_name}-loader-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-loader-dlq"
  })
}

resource "aws_sqs_queue_policy" "loader_dlq" {
  queue_url = aws_sqs_queue.loader_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridgeSend"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.loader_dlq.arn
      Condition = {
        ArnLike = {
          "aws:SourceArn" = "arn:aws:events:${var.aws_region}:${var.aws_account_id}:rule/${var.project_name}-*"
        }
      }
    }]
  })
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
          var.task_execution_role_arn,
          var.task_role_arn
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
  # Maps each Terraform loader key to the actual Python script filename.
  # entrypoint.sh reads LOADER_FILE to determine which script to exec.
  loader_file_map = {
    "stock_symbols"              = "loadstocksymbols.py"
    "stock_prices_daily"         = "loadpricedaily.py"
    "stock_prices_weekly"        = "loadpriceweekly.py"
    "stock_prices_monthly"       = "loadpricemonthly.py"
    "etf_prices_daily"           = "loadetfpricedaily.py"
    "etf_prices_weekly"          = "loadetfpriceweekly.py"
    "etf_prices_monthly"         = "loadetfpricemonthly.py"
    "financials_annual_income"   = "loadannualincomestatement.py"
    "financials_annual_balance"  = "loadannualbalancesheet.py"
    "financials_annual_cashflow" = "loadannualcashflow.py"
    "financials_quarterly_income"   = "loadquarterlyincomestatement.py"
    "financials_quarterly_balance"  = "loadquarterlybalancesheet.py"
    "financials_quarterly_cashflow" = "loadquarterlycashflow.py"
    "financials_ttm_income"      = "loadttmincomestatement.py"
    "financials_ttm_cashflow"    = "loadttmcashflow.py"
    "earnings_history"           = "loadearningshistory.py"
    "earnings_revisions"         = "loadearningsrevisions.py"
    "earnings_surprise"          = "loadearningsestimates.py"
    "earnings_sp500"             = "loadearningshistory.py"
    "market_overview"            = "loadmarket.py"
    "market_indices"             = "loadmarketindices.py"
    "sector_performance"         = "loadsectors.py"
    "relative_performance"       = "loadrelativeperformance.py"
    "seasonality"                = "loadseasonality.py"
    "econ_data"                  = "loadecondata.py"
    "aaiidata"                   = "loadaaiidata.py"
    "naaim_data"                 = "loadnaaim.py"
    "feargreed"                  = "loadfeargreed.py"
    "calendar"                   = "loadcalendar.py"
    "analyst_sentiment"          = "loadanalystsentiment.py"
    "analyst_upgrades"           = "loadanalystupgradedowngrade.py"
    "social_sentiment"           = "loadsentiment.py"
    "factor_metrics"             = "loadfactormetrics.py"
    "trend_template_data"        = "load_trend_template_data.py"
    "technicals_daily"           = "loadtechnicalsdaily.py"
    "stock_scores"               = "loadstockscores.py"
    "signals_daily"              = "loadbuyselldaily.py"
    "signals_weekly"             = "loadbuysellweekly.py"
    "signals_monthly"            = "loadbuysellmonthly.py"
    "signals_etf_daily"          = "loadbuysell_etf_daily.py"
    "signals_etf_weekly"         = "loadbuysell_etf_weekly.py"
    "signals_etf_monthly"        = "loadbuysell_etf_monthly.py"
    "etf_signals"                = "loadetfsignals.py"
    "algo_metrics_daily"         = "load_algo_metrics_daily.py"
    "eod_bulk_refresh"           = "load_eod_bulk.py"
  }

  scheduled_loaders = {
    # 3:30am ET = 8:30am UTC Mon-Fri
    "stock_symbols" = {
      schedule    = "cron(30 8 ? * MON-FRI *)"
      description = "Stock symbols reference data - 3:30am ET"
    }

    # 4:00am ET = 9am UTC Mon-Fri
    "stock_prices_daily" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Daily stock prices - 4:00am ET"
    }
    "stock_prices_weekly" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Weekly stock prices - 4:00am ET (parallel with daily)"
    }
    "stock_prices_monthly" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Monthly stock prices - 4:00am ET (parallel with daily)"
    }
    "etf_prices_daily" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Daily ETF prices - 4:00am ET (parallel with stock prices)"
    }
    "etf_prices_weekly" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Weekly ETF prices - 4:00am ET (parallel with stock prices)"
    }
    "etf_prices_monthly" = {
      schedule    = "cron(0 9 ? * MON-FRI *)"
      description = "Monthly ETF prices - 4:00am ET (parallel with stock prices)"
    }

    # 4:15am ET = 9:15am UTC Mon-Fri (after prices, before scores)
    "technicals_daily" = {
      schedule    = "cron(15 9 ? * MON-FRI *)"
      description = "Daily technical indicators - 4:15am ET (parallel with prices)"
    }

    # 10:00am ET = 3pm UTC Mon-Fri
    "financials_annual_income" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Annual income statements - 10:00am ET"
    }
    "financials_annual_balance" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Annual balance sheets - 10:00am ET (parallel)"
    }
    "financials_annual_cashflow" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Annual cash flow - 10:00am ET (parallel)"
    }
    "financials_quarterly_income" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Quarterly income statements - 10:00am ET (parallel)"
    }
    "financials_quarterly_balance" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Quarterly balance sheets - 10:00am ET (parallel)"
    }
    "financials_quarterly_cashflow" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "Quarterly cash flow - 10:00am ET (parallel)"
    }
    "financials_ttm_income" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "TTM income statements - 10:00am ET (parallel)"
    }
    "financials_ttm_cashflow" = {
      schedule    = "cron(0 15 ? * MON-FRI *)"
      description = "TTM cash flow - 10:00am ET (parallel)"
    }

    # 11:00am ET = 4pm UTC Mon-Fri
    "earnings_history" = {
      schedule    = "cron(0 16 ? * MON-FRI *)"
      description = "Earnings history - 11:00am ET"
    }
    "earnings_revisions" = {
      schedule    = "cron(0 16 ? * MON-FRI *)"
      description = "Earnings revisions - 11:00am ET (parallel)"
    }
    "earnings_surprise" = {
      schedule    = "cron(0 16 ? * MON-FRI *)"
      description = "Earnings surprise - 11:00am ET (parallel)"
    }
    "earnings_sp500" = {
      schedule    = "cron(0 16 ? * MON-FRI *)"
      description = "S&P 500 earnings - 11:00am ET (parallel)"
    }

    # 12:00pm ET = 5pm UTC Mon-Fri
    "market_overview" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Market overview - 12:00pm ET"
    }
    "market_indices" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Market indices - 12:00pm ET (parallel)"
    }
    "sector_performance" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Sector performance - 12:00pm ET (parallel)"
    }
    "relative_performance" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Relative performance - 12:00pm ET (parallel)"
    }
    "seasonality" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Seasonality - 12:00pm ET (parallel)"
    }
    "econ_data" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Economic data - 12:00pm ET (parallel)"
    }
    "aaiidata" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "AAII data - 12:00pm ET (parallel)"
    }
    "naaim_data" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "NAAIM data - 12:00pm ET (parallel)"
    }
    "feargreed" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Fear & Greed Index - 12:00pm ET (parallel)"
    }
    "calendar" = {
      schedule    = "cron(0 17 ? * MON-FRI *)"
      description = "Economic calendar - 12:00pm ET (parallel)"
    }

    # 1:00pm ET = 6pm UTC Mon-Fri
    "analyst_sentiment" = {
      schedule    = "cron(0 18 ? * MON-FRI *)"
      description = "Analyst sentiment - 1:00pm ET"
    }
    "analyst_upgrades" = {
      schedule    = "cron(0 18 ? * MON-FRI *)"
      description = "Analyst upgrades - 1:00pm ET (parallel)"
    }
    "social_sentiment" = {
      schedule    = "cron(0 18 ? * MON-FRI *)"
      description = "Social sentiment - 1:00pm ET (parallel)"
    }
    "factor_metrics" = {
      schedule    = "cron(0 18 ? * MON-FRI *)"
      description = "Factor metrics - 1:00pm ET (parallel)"
    }
    "stock_scores" = {
      schedule    = "cron(0 18 ? * MON-FRI *)"
      description = "Stock scores - 1:00pm ET (parallel)"
    }

    # 5:00pm ET = 10pm UTC Mon-Fri
    "signals_daily" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Daily trading signals - 5:00pm ET"
    }
    "signals_weekly" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Weekly trading signals - 5:00pm ET (parallel)"
    }
    "signals_monthly" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Monthly trading signals - 5:00pm ET (parallel)"
    }
    "signals_etf_daily" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Daily ETF signals - 5:00pm ET (parallel)"
    }
    "signals_etf_weekly" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Weekly ETF signals - 5:00pm ET (parallel)"
    }
    "signals_etf_monthly" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "Monthly ETF signals - 5:00pm ET (parallel)"
    }
    "etf_signals" = {
      schedule    = "cron(0 22 ? * MON-FRI *)"
      description = "ETF signals - 5:00pm ET (parallel)"
    }

    # 5:25pm ET = 10:25pm UTC Mon-Fri (after signals complete)
    "algo_metrics_daily" = {
      schedule    = "cron(25 22 ? * MON-FRI *)"
      description = "Algo metrics - 5:25pm ET"
    }

    # 5:00am UTC (midnight ET) next trading day - EOD bulk refresh for all symbols
    # Runs TUE-SAT to cover MON-FRI (US market days)
    "eod_bulk_refresh" = {
      schedule    = "cron(0 5 ? * TUE-SAT *)"
      description = "EOD bulk price refresh - all 5000+ symbols in 5 minutes"
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
    "stock_symbols" = { cpu = 256, memory = 512, timeout = 300 }

    # Price data loaders (4:00am ET) - HIGH CPU/MEMORY - FARGATE: 512 CPU = 1024-4096 MB
    "stock_prices_daily"   = { cpu = 512, memory = 1024, timeout = 600 }
    "stock_prices_weekly"  = { cpu = 512, memory = 1024, timeout = 600 }
    "stock_prices_monthly" = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_daily"     = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_weekly"    = { cpu = 512, memory = 1024, timeout = 600 }
    "etf_prices_monthly"   = { cpu = 512, memory = 1024, timeout = 600 }

    # Technical data (4:15am ET, after prices) - FARGATE: 256 CPU = min 512 MB
    "technicals_daily"    = { cpu = 256, memory = 512, timeout = 300 }

    # Financial statements (10:00am ET) - FARGATE: 256 CPU = min 512 MB
    "financials_annual_income"      = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_annual_balance"     = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_annual_cashflow"    = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_income"   = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_balance"  = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_quarterly_cashflow" = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_ttm_income"         = { cpu = 256, memory = 512, timeout = 1200 }
    "financials_ttm_cashflow"       = { cpu = 256, memory = 512, timeout = 1200 }

    # Earnings data (11:00am ET) - FARGATE: 256 CPU = min 512 MB
    "earnings_history"   = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_revisions" = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_surprise"  = { cpu = 256, memory = 512, timeout = 600 }
    "earnings_sp500"     = { cpu = 256, memory = 512, timeout = 600 }

    # Market & economic data (12:00pm ET - 6:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "market_overview"      = { cpu = 256, memory = 512, timeout = 300 }
    "market_indices"       = { cpu = 256, memory = 512, timeout = 300 }
    "sector_performance"   = { cpu = 256, memory = 512, timeout = 300 }
    "relative_performance" = { cpu = 256, memory = 512, timeout = 300 }
    "seasonality"          = { cpu = 256, memory = 512, timeout = 300 }
    "econ_data"            = { cpu = 256, memory = 512, timeout = 300 }
    "aaiidata"             = { cpu = 256, memory = 512, timeout = 300 }
    "naaim_data"           = { cpu = 256, memory = 512, timeout = 300 }
    "feargreed"            = { cpu = 256, memory = 512, timeout = 300 }
    "calendar"             = { cpu = 256, memory = 512, timeout = 300 }

    # Sentiment & analysis (1:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "analyst_sentiment" = { cpu = 256, memory = 512, timeout = 600 }
    "analyst_upgrades"  = { cpu = 256, memory = 512, timeout = 600 }
    "social_sentiment"  = { cpu = 256, memory = 512, timeout = 600 }
    "factor_metrics"    = { cpu = 256, memory = 512, timeout = 600 }
    "stock_scores"      = { cpu = 256, memory = 512, timeout = 600 }

    # Trading signals (5:00pm ET) - FARGATE: 256 CPU = min 512 MB
    "signals_daily"     = { cpu = 256, memory = 512, timeout = 900 }
    "signals_weekly"    = { cpu = 256, memory = 512, timeout = 900 }
    "signals_monthly"   = { cpu = 256, memory = 512, timeout = 900 }
    "signals_etf_daily"   = { cpu = 256, memory = 512, timeout = 900 }
    "signals_etf_weekly"  = { cpu = 256, memory = 512, timeout = 900 }
    "signals_etf_monthly" = { cpu = 256, memory = 512, timeout = 900 }
    "etf_signals"         = { cpu = 256, memory = 512, timeout = 900 }

    # Algo metrics (5:15pm ET - after signals) - FARGATE: 256 CPU = min 512 MB
    "algo_metrics_daily" = { cpu = 256, memory = 512, timeout = 600 }

    # EOD bulk refresh (5:00am UTC next day) - FARGATE: 512 CPU for threading
    "eod_bulk_refresh" = { cpu = 512, memory = 1024, timeout = 600 }
  }

  # For backward compatibility
  default_loaders = local.all_loaders

  # Loaders that must run on on-demand FARGATE (cannot tolerate interruption)
  critical_loaders = toset([
    "stock_prices_daily", "stock_prices_weekly", "stock_prices_monthly",
    "etf_prices_daily", "etf_prices_weekly", "etf_prices_monthly",
    "signals_daily", "signals_weekly", "signals_monthly", "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly", "etf_signals",
    "algo_metrics_daily", "eod_bulk_refresh"
  ])
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
          name  = "LOADER_FILE"
          value = local.loader_file_map[each.key]
        },
        {
          name  = "LOADER_TYPE"
          value = each.key
        },
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "DB_HOST"
          value = var.db_host
        },
        {
          name  = "DB_PORT"
          value = tostring(var.db_port)
        },
        {
          name  = "DB_NAME"
          value = var.db_name
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

    # Use capacity provider strategy for flexible on-demand/spot selection
    dynamic "capacity_provider_strategy" {
      for_each = contains(local.critical_loaders, each.key) ? [] : [1]
      content {
        capacity_provider = "FARGATE_SPOT"
        weight            = 100
        base              = 0
      }
    }

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [var.ecs_tasks_sg_id]
      assign_public_ip = false
    }
  }

  dead_letter_config {
    arn = aws_sqs_queue.loader_dlq.arn
  }
}
