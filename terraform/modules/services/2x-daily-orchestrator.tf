/**
 * 2x Daily Orchestrator Execution - Morning (9:30 AM ET) + Evening (5:30 PM ET)
 *
 * Split from single evening run to support swing trading schedule with:
 * - Morning run after price loads (4 AM ET) but before market open
 * - Evening run after all technicals/scores compute (5:30 PM ET)
 *
 * Data flow:
 * 4:00 AM ET  → Price loaders (daily, weekly, monthly)
 * 9:30 AM ET  → ORCHESTRATOR (uses prices, yesterday's technicals) ← MORNING RUN
 * 10:00 AM ET → Technicals compute (parallel with morning orchestrator)
 * 5:00 PM ET  → Metrics compute (after technicals ready)
 * 5:30 PM ET  → ORCHESTRATOR (uses complete dataset) ← EVENING RUN (default)
 */

# ============================================================
# Morning Schedule (9:30 AM ET = 2:30 PM UTC)
# Triggers orchestrator IMMEDIATELY after 4 AM price loads
# Uses: prices (today) + technicals (yesterday)
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_morning" {
  count                        = var.enable_morning_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-morning-${var.environment}"
  description                  = "Morning algo orchestrator run: 9:30 AM ET (after price loads, before market open)"
  schedule_expression          = "cron(30 14 ? * MON-FRI *)" # 9:30 AM ET = 2:30 PM UTC
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source         = "eventbridge-scheduler"
      run_date       = "now"
      run_identifier = "morning"
      note           = "Morning trading run: uses prices (today) + technicals (yesterday)"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Evening Schedule (5:30 PM ET = 10:30 PM UTC)
# Original schedule - full pipeline execution
# Uses: prices (today) + technicals (today) + all computed metrics
# ============================================================

# Original orchestrator schedule renamed for clarity
# Keep as default for backwards compatibility
locals {
  # Determine which schedule to use based on variable
  # Note: cron expressions use UTC timezone for consistency
  orchestrator_schedule = var.enable_morning_orchestrator ? var.algo_schedule_expression : "cron(30 22 ? * MON-FRI *)"
}

# Update existing schedule to reflect 2x daily behavior when enabled
resource "aws_scheduler_schedule" "algo_orchestrator" {
  count                        = var.algo_schedule_enabled ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-${var.environment}"
  description                  = var.enable_morning_orchestrator ? "Evening algo orchestrator run: 5:30 PM ET (full pipeline, default)" : "Trigger algo orchestrator Lambda at scheduled time"
  schedule_expression          = local.orchestrator_schedule
  schedule_expression_timezone = var.algo_schedule_timezone
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source         = "eventbridge-scheduler"
      run_date       = "now"
      run_identifier = var.enable_morning_orchestrator ? "evening" : "default"
      note           = var.enable_morning_orchestrator ? "Evening trading run: full pipeline (prices + technicals + metrics)" : null
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Daily Weight Optimization (6:00 PM ET = 11:00 PM UTC)
# Runs AFTER orchestrator completion to trigger continuous improvement loop
# Invokes: loaders/load_weight_optimization.py via ECS scheduled task
# - Populates signal_trade_performance from closed trades
# - Computes IC (Information Coefficient) per component
# - Adapts swing_score weights based on realized P&L
# - Logs changes to algo_weight_history
# - Weekly: walk-forward backtest validation (Fridays)
# ============================================================

resource "aws_scheduler_schedule" "weight_optimization" {
  name                         = "${var.project_name}-weight-optimization-${var.environment}"
  description                  = "Daily weight optimization: 6:00 PM ET (after orchestrator, continuous improvement loop)"
  schedule_expression          = "cron(0 23 ? * MON-FRI *)" # 6:00 PM ET = 11:00 PM UTC
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  # Target: invoke weight optimization ECS task via Lambda bridge
  # (EventBridge Scheduler doesn't support direct ECS task scheduling in all regions,
  #  so we use Lambda as a bridge to invoke the ECS task)
  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source                              = "eventbridge-scheduler"
      trigger_type                        = "daily_optimization"
      run_date                            = "now"
      lookback_days                       = 7
      dry_run                             = false
      weight_optimization_task_arn        = var.weight_optimization_task_definition_arn
      weight_optimization_cluster_arn     = var.ecs_cluster_arn
      weight_optimization_subnets         = var.private_subnet_ids
      weight_optimization_security_groups = [var.algo_lambda_sg_id]
    })
  }
}

# Cleanup: remove duplicate schedule resource if it exists
# (The original aws_scheduler_schedule.algo_orchestrator is kept for backwards compatibility)
