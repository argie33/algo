# ============================================================
# Loaders Module - ECS Task Definitions (DRY Pattern)
# ============================================================

# ============================================================
# 1. Loader Manifest (Single Source of Truth)
# ============================================================

locals {
  # Hardcoded loader manifest - override via var.loader_manifest if needed
  default_loaders = {
    "stock_scores"        = { description = "Stock scores loader" }
    "factormetrics"       = { description = "Factor metrics loader" }
    "momentum"            = { description = "Momentum loader" }
    "positioning"         = { description = "Positioning loader" }
    "quality_metrics"     = { description = "Quality metrics service" }
    "growth_metrics"      = { description = "Growth metrics service" }
    "benchmarks"          = { description = "Benchmarks loader" }
    "buyselldaily"        = { description = "Buy-sell daily loader" }
    "prices"              = { description = "Price data loader" }
    "financials"          = { description = "Financial data loader" }
    "signals"             = { description = "Trading signals loader" }
    "econdata"            = { description = "Economic data loader" }
    "feargreed"           = { description = "Fear-Greed index loader" }
    "market_indices"      = { description = "Market indices loader" }
    "sector_ranking"      = { description = "Sector ranking loader" }
    "aaiidata"            = { description = "AAII data loader" }
    "naaimdata"           = { description = "NAIM data loader" }
    "revenue_estimate"    = { description = "Revenue estimate loader" }
  }

  # Merge default with provided manifest
  loaders = merge(local.default_loaders, var.loader_manifest)

  # Common environment variables for all loaders
  common_environment = {
    DB_SECRET_ARN         = var.rds_credentials_secret_arn
    DB_ENDPOINT           = var.rds_endpoint
    DB_PORT               = tostring(var.rds_port)
    DB_NAME               = var.rds_database_name
    S3_STAGING_BUCKET     = var.data_loading_bucket_name
    USE_S3_STAGING        = "true"
    AWS_REGION            = var.aws_region
  }
}

# ============================================================
# 2. CloudWatch Log Groups (One per loader)
# ============================================================

resource "aws_cloudwatch_log_group" "loaders" {
  for_each = local.loaders

  name              = "/ecs/${var.project_name}-loader-${each.key}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name   = "${var.project_name}-loader-${each.key}-logs"
    Loader = each.key
  })
}

# ============================================================
# 3. ECS Task Definitions (Dynamic from Manifest)
# ============================================================

resource "aws_ecs_task_definition" "loaders" {
  for_each = local.loaders

  family                   = "${var.project_name}-loader-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(coalesce(each.value.cpu, var.loader_task_cpu))
  memory                   = tostring(coalesce(each.value.memory, var.loader_task_memory))
  execution_role_arn       = var.ecs_task_execution_role_arn
  task_role_arn            = var.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = "${var.ecr_repository_url}:${var.container_image_tag}"
      essential = true

      # Environment variables (non-secret)
      environment = [
        for k, v in merge(local.common_environment, coalesce(each.value.environment, {})) :
        { name = k, value = v }
      ]

      # Secrets from Secrets Manager (DB credentials)
      secrets = [
        {
          name      = "DB_USER"
          valueFrom = "${var.rds_credentials_secret_arn}:username::"
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = "${var.rds_credentials_secret_arn}:password::"
        }
      ]

      # CloudWatch Logs
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.loaders[each.key].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = merge(var.common_tags, {
    Name   = "${var.project_name}-loader-${each.key}-task-def"
    Loader = each.key
  })

  depends_on = [aws_cloudwatch_log_group.loaders]
}

# ============================================================
# 4. EventBridge Rules for Scheduled Loaders (Evening)
# ============================================================

# Scheduled loaders (triggered by EventBridge, not services)
locals {
  scheduled_loaders = {
    "econdata"      = "cron(0 22 ? * MON-FRI *)"       # 6 PM ET
    "feargreed"     = "cron(0 23 ? * MON-FRI *)"       # 7 PM ET
    "market_indices" = "cron(0 21 ? * MON-FRI *)"      # 5 PM ET
    "sector_ranking" = "cron(30 22 ? * MON-FRI *)"     # 6:30 PM ET
  }
}

resource "aws_cloudwatch_event_rule" "loader_schedule" {
  for_each = local.scheduled_loaders

  name                = "${var.project_name}-loader-${each.key}-schedule"
  description         = "Schedule ${each.key} loader"
  schedule_expression = each.value

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "loader_schedule" {
  for_each = local.scheduled_loaders

  rule      = aws_cloudwatch_event_rule.loader_schedule[each.key].name
  target_id = "ECSRunTask"
  arn       = "arn:aws:ecs:${var.aws_region}:${var.aws_account_id}:cluster/${var.ecs_cluster_name}"
  role_arn  = aws_iam_role.eventbridge_run_task.arn

  ecs_target {
    launch_type             = "FARGATE"
    task_definition_arn     = aws_ecs_task_definition.loaders[each.key].arn
    platform_version        = "LATEST"
    task_count              = 1
    enable_ecs_managed_tags = true

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [var.ecs_tasks_security_group_id]
      assign_public_ip = false
    }
  }
}

# ============================================================
# 5. EventBridge IAM Role (for ECS RunTask)
# ============================================================

resource "aws_iam_role" "eventbridge_run_task" {
  name               = "${var.project_name}-eventbridge-run-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "eventbridge_run_task" {
  name   = "${var.project_name}-eventbridge-run-task-policy"
  role   = aws_iam_role.eventbridge_run_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSRunTask"
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [
          aws_ecs_task_definition.loaders["econdata"].arn,
          aws_ecs_task_definition.loaders["feargreed"].arn,
          aws_ecs_task_definition.loaders["market_indices"].arn,
          aws_ecs_task_definition.loaders["sector_ranking"].arn
        ]
      },
      {
        Sid    = "IAMPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          var.ecs_task_execution_role_arn,
          var.ecs_task_role_arn
        ]
      }
    ]
  })
}
