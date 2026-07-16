/**
 * EventBridge Scheduler for Data Loader Pipelines
 *
 * These are the CRITICAL missing schedulers that were never configured.
 * They trigger Step Functions pipelines to run data loaders on schedule.
 *
 * Architecture:
 * - Morning (2:00 AM ET): Trigger "morning_data_pipeline" Step Functions
 * - EOD (4:05 PM ET): Trigger "eod_data_pipeline" Step Functions
 *
 * Why these times:
 * - 2:00 AM: Before market opens, refresh stock prices and technical indicators
 * - 4:05 PM: After market close, compute all metrics before evening orchestrator run (5:30 PM)
 */

# ============================================================
# Morning Data Pipeline (2:00 AM ET)
# Purpose: Refresh prices and technical indicators before market open
# Loaders: stock_prices_daily → technical_data_daily → market_health_daily
# ============================================================

resource "aws_scheduler_schedule" "data_loaders_morning" {
  name                         = "${var.project_name}-data-pipeline-morning-${var.environment}"
  description                  = "Morning data pipeline: 2:00 AM ET (prices + technicals + market health)"
  schedule_expression          = "cron(0 2 ? * MON-FRI *)" # 2:00 AM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  # Target: Invoke Step Functions state machine to run morning loaders
  target {
    arn      = var.morning_data_pipeline_arn != "" ? var.morning_data_pipeline_arn : "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-morning-prep-pipeline-${var.environment}"
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source              = "eventbridge-scheduler"
      pipeline            = "morning_data_pipeline"
      run_date            = "now"
      note                = "Morning data pipeline: refresh prices and technicals before market open"
      parallelism_default = 4
      timeout_minutes     = 120
    })
  }
}

# ============================================================
# EOD Data Pipeline (4:05 PM ET)
# Purpose: Compute all metrics after market close, before evening orchestrator
# Loaders: yfinance_snapshot → yfinance_derived_metrics → financial_statements →
#          risk_metrics_daily → stock_scores
# Timing: 4:05 PM allows Step Functions to queue tasks immediately after 4:00 PM market close
# ============================================================

resource "aws_scheduler_schedule" "data_loaders_eod" {
  name                         = "${var.project_name}-data-pipeline-eod-${var.environment}"
  description                  = "EOD data pipeline: 4:05 PM ET (metrics + scores before evening orchestrator)"
  schedule_expression          = "cron(5 16 ? * MON-FRI *)" # 4:05 PM ET (America/New_York auto-handles EST/EDT)
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  # Target: Invoke Step Functions state machine to run EOD loaders
  target {
    arn      = var.eod_data_pipeline_arn != "" ? var.eod_data_pipeline_arn : "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-eod-pipeline-${var.environment}"
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source              = "eventbridge-scheduler"
      pipeline            = "eod_data_pipeline"
      run_date            = "now"
      note                = "EOD data pipeline: compute all metrics after market close, before orchestrator (5:30 PM)"
      parallelism_default = 4
      timeout_minutes     = 120
    })
  }
}
