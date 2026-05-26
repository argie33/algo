/**
 * Multiple Daily Orchestrator Execution (3-4x Daily)
 *
 * Pragmatic approach: keep signals from night before, execute multiple times to catch opportunities:
 * - Pre-market (4:30 AM ET, optional) — early entry prep
 * - Morning (9:30 AM ET) — market open, primary execution
 * - Afternoon (1:00 PM ET) — mid-day rebalance, catch missed opportunities
 * - Evening (5:30 PM ET) — after close, final position management
 *
 * Data flow:
 * Night before (5 PM)  → Signal generation for tomorrow (6h batch) → eod_bulk_refresh pipeline
 * 4:00 AM ET          → Price loaders (daily, weekly, monthly)
 * 4:30 AM ET          → ORCHESTRATOR pre-market (uses prices, signals from night before) [OPTIONAL]
 * 9:30 AM ET          → ORCHESTRATOR morning (uses prices, signals from night before) ← PRIMARY
 * 10:00 AM ET         → Technicals compute (parallel, ready for afternoon run)
 * 1:00 PM ET          → ORCHESTRATOR afternoon (uses prices, same signals, manage positions)
 * 5:00 PM ET          → Metrics compute (final update before evening)
 * 5:30 PM ET          → ORCHESTRATOR evening (full dataset, final position management)
 *
 * Goal: Move towards real-time monitoring; for now, signal recomputation happens only overnight.
 */

# ============================================================
# Pre-market Schedule (4:30 AM ET = 8:30 AM UTC) [OPTIONAL]
# Runs after stock_symbols, before price loads complete
# Uses: signals from night before + previous prices
# Purpose: Early position setup, scout for opportunities
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_premarket" {
  count                        = var.enable_premarket_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-premarket-${var.environment}"
  description                  = "Pre-market algo orchestrator run: 4:30 AM ET (early prep, signals from night before)"
  schedule_expression          = "cron(30 8 ? * MON-FRI *)" # 4:30 AM ET = 8:30 AM UTC
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
      run_identifier = "premarket"
      note           = "Pre-market trading run: signals from night before, early entry opportunities"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Morning Schedule (9:30 AM ET = 2:30 PM UTC) [PRIMARY]
# Triggers at market open, after 4 AM price loads complete
# Uses: prices (today) + technicals (yesterday)
# Purpose: Primary trading execution, catch market open momentum
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_morning" {
  count                        = var.enable_morning_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-morning-${var.environment}"
  description                  = "Morning algo orchestrator run: 9:30 AM ET (market open, after price loads)"
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
      note           = "Morning trading run: uses prices (today) + technicals (yesterday), primary execution"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Afternoon Schedule (1:00 PM ET = 5:00 PM UTC)
# Mid-day run to catch missed opportunities and rebalance
# Uses: prices (today, fresh) + same signals as morning
# Purpose: Intraday rebalance, execute missed signal entries, manage positions
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_afternoon" {
  count                        = var.enable_afternoon_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-afternoon-${var.environment}"
  description                  = "Afternoon algo orchestrator run: 1:00 PM ET (mid-day rebalance, same signals as morning)"
  schedule_expression          = "cron(0 17 ? * MON-FRI *)" # 1:00 PM ET = 5:00 PM UTC
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
      run_identifier = "afternoon"
      note           = "Afternoon trading run: uses fresh prices + same signals as morning, catch missed entries + rebalance"
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
