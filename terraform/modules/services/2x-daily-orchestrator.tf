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
# Pre-market Schedule (4:30 AM ET) [OPTIONAL]
# Runs after stock_symbols, before price loads complete
# Uses: signals from night before + previous prices
# Purpose: Early position setup, scout for opportunities
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_premarket" {
  count                        = var.enable_premarket_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-premarket-${var.environment}"
  description                  = "Pre-market algo orchestrator run: 4:30 AM ET (early prep, signals from night before)"
  schedule_expression          = "cron(30 4 ? * MON-FRI *)" # 4:30 AM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
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
# Morning Schedule (9:30 AM ET) [PRIMARY]
# Triggers at market open, after 4 AM price loads complete
# Uses: prices (today) + technicals (yesterday)
# Purpose: Primary trading execution, catch market open momentum
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_morning" {
  count                        = var.enable_morning_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-morning-${var.environment}"
  description                  = "Morning algo orchestrator run: 9:30 AM ET (market open, after price loads)"
  schedule_expression          = "cron(30 9 ? * MON-FRI *)" # 9:30 AM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
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
# Afternoon Schedule (1:00 PM ET)
# Mid-day run to catch missed opportunities and rebalance
# Uses: prices (today, fresh) + same signals as morning
# Purpose: Intraday rebalance, execute missed signal entries, manage positions
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_afternoon" {
  count                        = var.enable_afternoon_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-afternoon-${var.environment}"
  description                  = "Afternoon algo orchestrator run: 1:00 PM ET (mid-day rebalance, same signals as morning)"
  schedule_expression          = "cron(0 13 ? * MON-FRI *)" # 1:00 PM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
  # OPTIMIZED 2026-06-21: Disable intraday runs in dev (not needed, saves compute)
  state = "DISABLED"

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
# Pre-Close Schedule (3:00 PM ET)
# Final trading run before market close (4 PM ET)
# Uses: prices (today, fresh) + same signals as morning
# Purpose: Last-minute position adjustments, final entries/exits BEFORE market close
# SLA: Must finish by 3:15 PM ET to leave 45-min buffer for trade execution
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_preclose" {
  count                        = var.enable_preclose_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-preclose-${var.environment}"
  description                  = "Pre-close algo orchestrator run: 3:00 PM ET (final trades before market close at 4 PM ET)"
  schedule_expression          = "cron(0 15 ? * MON-FRI *)" # 3:00 PM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
  # OPTIMIZED 2026-06-21: Disable pre-close runs in dev (not needed, saves compute)
  state = "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source         = "eventbridge-scheduler"
      run_date       = "now"
      run_identifier = "preclose"
      note           = "Pre-close trading run: final adjustments before 4 PM ET market close, must finish by 3:15 PM"
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

# FIXED Issue #33: Simplified locals by removing ternary logic
# Evening schedule is now explicit and always configured

# Update existing schedule to reflect 2x daily behavior when enabled
resource "aws_scheduler_schedule" "algo_orchestrator" {
  count                        = var.algo_schedule_enabled ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-${var.environment}"
  description                  = var.enable_morning_orchestrator ? "Evening algo orchestrator run: 5:30 PM ET (full pipeline, default)" : "Trigger algo orchestrator Lambda at scheduled time"
  schedule_expression          = var.algo_schedule_expression
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
# Daily Weight Optimization (6:00 PM ET)
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
  schedule_expression          = "cron(0 18 ? * MON-FRI *)" # 6:00 PM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
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

# ============================================================
# Data Patrol Schedule (Handled by Step Functions EOD Pipeline)
# ============================================================
# Data patrol runs as part of the EOD pipeline (4:05 PM ET) in Step Functions,
# validating data quality before the orchestrator runs. No separate scheduler needed.
# The orchestrator Phase 1 checks for CRITICAL findings and can halt trading if detected.
#
# If a pre-market patrol is needed in the future, create a separate EventBridge rule
# that invokes the patrol ECS task directly (not via Lambda, which doesn't handle it).

# ============================================================
# Pre-Warm Schedule (9:25 AM ET) — 5 minutes before market open
# Warms the algo Lambda container so the 9:30 AM trading run gets a pre-initialized
# Python environment (no 15-40s VPC cold start, pre-loaded DB connection, loaded modules).
# dry_run=true: skips all trading phases (lock acquired+released in ~5s).
# No cost beyond Lambda invocation price (~$0.0000002).
# Enable by setting enable_morning_orchestrator = true (reuses same gate).
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_prewarm_morning" {
  count                        = var.enable_morning_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-prewarm-morning-${var.environment}"
  description                  = "Pre-warm algo Lambda 5 min before market open (dry_run, no trades) to avoid 15-40s cold start at 9:30 AM"
  schedule_expression          = "cron(25 9 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
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
      run_identifier = "prewarm"
      dry_run        = true
      note           = "Pre-warm only: warms Lambda container before 9:30 AM market-open run. No trades executed."
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Pre-Warm Schedule (12:55 PM ET) — 5 minutes before 1 PM run
# Prevents cold start on the 1 PM afternoon orchestrator run.
# Without this, the 3+ hour gap from 9:30 AM finish guarantees a cold start (15-40s VPC init).
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_prewarm_afternoon" {
  count                        = var.enable_afternoon_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-prewarm-afternoon-${var.environment}"
  description                  = "Pre-warm algo Lambda 5 min before 1 PM run (dry_run, no trades) to avoid 15-40s cold start"
  schedule_expression          = "cron(55 12 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
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
      run_identifier = "prewarm"
      dry_run        = true
      note           = "Pre-warm only: warms Lambda container before 1:00 PM afternoon run. No trades executed."
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# Pre-Warm Schedule (2:55 PM ET) — 5 minutes before 3 PM pre-close run
# CRITICAL SLA: 3 PM run must finish by 3:15 PM ET to leave 45-min buffer for trade execution.
# Without pre-warm, a 40s cold start + 7 phases running up to 600s blows the SLA.
# This schedule eliminates cold-start risk entirely for the SLA-critical 3 PM run.
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator_prewarm_preclose" {
  count                        = var.enable_preclose_orchestrator ? 1 : 0
  name                         = "${var.project_name}-algo-schedule-prewarm-preclose-${var.environment}"
  description                  = "Pre-warm algo Lambda 5 min before 3 PM SLA-critical run (dry_run, no trades) to guarantee 3:15 PM finish deadline"
  schedule_expression          = "cron(55 14 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"
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
      run_identifier = "prewarm"
      dry_run        = true
      note           = "Pre-warm only: warms Lambda container before 3:00 PM pre-close run (SLA-critical, must finish by 3:15 PM). No trades executed."
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# Cleanup: remove duplicate schedule resource if it exists
# (The original aws_scheduler_schedule.algo_orchestrator is kept for backwards compatibility)
