/**
 * Trade Update Listener - Always-On Alpaca `trade_updates` Websocket Consumer
 *
 * REAL-MONEY-READINESS ARCHITECTURE REBUILD (2026-09-06, see
 * memory/intraday_monitoring_architecture_gap_20260906.md for the audit that found this
 * gap and algo/execution/trade_update_listener.py for the consumer code): order/fill
 * state today is 100% REST polling (reconciliation_fill_and_account.py/
 * reconciliation_exit_fills.py), invoked only when the orchestrator runs - nothing reacts
 * to a fill in real time between runs.
 *
 * This is a genuinely NEW infrastructure pattern for this repo: every other compute
 * resource here is either Lambda (short jobs, 15-min limit) or a scheduled/triggered ECS
 * Fargate TASK (run-to-completion batch work, like aws_ecs_task_definition.algo_orchestrator
 * above) - there is no existing always-on process. `desired_count = 1` with no schedule
 * makes this an `aws_ecs_service`, not a task invoked via EventBridge/Step Functions like
 * everything else in this file.
 *
 * Placed in the `loaders` module (not `compute`, despite the ECS cluster resource itself
 * living in `compute`) because this module already receives every variable the container
 * needs (db_secret_arn, algo_secrets_arn, ecs_cluster_arn, public_subnet_ids,
 * ecs_tasks_sg_id, task_execution_role_arn, task_role_arn) - adding those to `compute`
 * would be new cross-module wiring for no benefit, since `ecs_cluster_arn` is already
 * threaded through here for exactly this purpose.
 *
 * SAFETY DESIGN (see algo/execution/trade_update_listener.py's own docstring for detail):
 * this listener is purely a LATENCY ACCELERANT, never the sole source of fill truth - the
 * existing REST reconciliation keeps running unchanged. If this service is down, fills
 * are recorded a few minutes late via REST instead of instantly; they are never lost. The
 * CloudWatch alarm below exists because - unlike everything else in this repo's
 * infrastructure - a crashed desired_count=1 service does NOT self-heal on the next
 * schedule, so a human needs to be paged if it stays down.
 *
 * NOT ENABLED BY DEFAULT - a new, ongoing Fargate compute cost (runs 24/7, not just
 * market hours, since websocket reconnect/backoff needs a live process even overnight)
 * and a new infrastructure pattern for this repo. Deploying it (terraform apply with
 * enable_trade_update_listener = true) needs an explicit go-ahead.
 */

variable "enable_trade_update_listener" {
  description = "Enable the always-on Alpaca trade_updates websocket listener (new ongoing Fargate cost + new infrastructure pattern for this repo - needs explicit sign-off, see this file's header comment)"
  type        = bool
  default     = false
}

resource "null_resource" "ensure_trade_update_listener_log_group" {
  count = var.enable_trade_update_listener ? 1 : 0
  provisioner "local-exec" {
    command = "aws logs create-log-group --log-group-name /ecs/${var.project_name}-trade-update-listener --region ${var.aws_region} 2>/dev/null || true"
  }
}

resource "aws_ecs_task_definition" "trade_update_listener" {
  count      = var.enable_trade_update_listener ? 1 : 0
  depends_on = [null_resource.ensure_trade_update_listener_log_group]

  family = "${var.project_name}-trade-update-listener"
  container_definitions = jsonencode([
    {
      name      = "${var.project_name}-trade-update-listener"
      image     = "${var.ecr_repository_uri}:${var.environment}-latest"
      essential = true

      # Long-running websocket consumer, not a batch script - see
      # algo/execution/trade_update_listener.py's own `if __name__ == "__main__":` loop.
      command = ["algo/execution/trade_update_listener.py"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-trade-update-listener"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${var.db_secret_arn}:password::" },
        { name = "DB_USER", valueFrom = "${var.db_secret_arn}:username::" },
        { name = "APCA_API_KEY_ID", valueFrom = "${var.algo_secrets_arn}:APCA_API_KEY_ID::" },
        { name = "APCA_API_SECRET_KEY", valueFrom = "${var.algo_secrets_arn}:APCA_API_SECRET_KEY::" }
      ]

      environment = [
        { name = "AWS_EXECUTION_ENV", value = "ECS_FARGATE" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_SECRET_ARN", value = var.db_secret_arn },
        { name = "ALGO_SECRETS_ARN", value = var.algo_secrets_arn },
        { name = "DB_SSL", value = var.db_ssl_mode },
        { name = "ALPACA_PAPER_TRADING", value = tostring(var.alpaca_paper_trading) },
        { name = "APCA_API_BASE_URL", value = var.alpaca_api_base_url },
        { name = "PYTHONPATH", value = "/app" }
      ]
    }
  ])

  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  tags = var.common_tags
}

resource "aws_ecs_service" "trade_update_listener" {
  count           = var.enable_trade_update_listener ? 1 : 0
  name            = "${var.project_name}-trade-update-listener"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.trade_update_listener[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_tasks_sg_id]
    assign_public_ip = true
  }

  # No deployment circuit breaker rollback disable here - a failed deploy should roll back
  # automatically rather than leave a bad revision as the only running task for a
  # desired_count=1 always-on service.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "trade_update_listener_down" {
  count               = var.enable_trade_update_listener ? 1 : 0
  alarm_name          = "${var.project_name}-trade-update-listener-down"
  alarm_description   = "Trade update listener (Alpaca trade_updates websocket consumer) has fewer than 1 running task - unlike scheduled infrastructure elsewhere in this repo, a crashed desired_count=1 service does not self-heal on the next schedule and needs a human to investigate. REST reconciliation still independently catches fills while this is down (see algo/execution/trade_update_listener.py's docstring) - this is a latency-degradation alarm, not a trading-halt condition."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    ClusterName = split("/", var.ecs_cluster_arn)[1]
    ServiceName = aws_ecs_service.trade_update_listener[0].name
  }

  alarm_actions = var.sns_alert_topic_arn != "" ? [var.sns_alert_topic_arn] : []
  ok_actions    = var.sns_alert_topic_arn != "" ? [var.sns_alert_topic_arn] : []

  tags = var.common_tags
}
