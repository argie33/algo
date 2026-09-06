/**
 * Intraday Risk Monitor Schedule
 *
 * REAL-MONEY-READINESS FIX (documented 2026-09-06 as `intraday_monitoring_architecture_
 * gap`, closed here): algo/risk/var.py's beta/concentration checks and pretrade_checks.py's
 * beta/top5-concentration checks only ever run once/day (Phase 9's end-of-cycle risk
 * report) or at the moment of a NEW candidate entry - nothing re-checks the EXISTING book
 * against those same limits as prices drift intraday. A position can walk past the 2.0
 * beta cap or the top-5-concentration cap purely from price movement, with no new entry
 * involved, and nothing notices until the next Phase 9 run at end of day.
 *
 * This invokes the SAME already-deployed orchestrator Lambda (no new function, IAM role,
 * or deployment package to keep in sync - see lambda_function.py's `mode:
 * "intraday_risk_monitor"` dispatch and algo/risk/intraday_risk_monitor.py) with a payload
 * that runs ONLY that one check, on a tight schedule, in between full orchestrator runs.
 * ALERT-ONLY - see that module's own docstring for why this deliberately does not
 * auto-halt trading; it only guarantees a human is notified promptly instead of only at
 * end of day.
 *
 * NOT ENABLED BY DEFAULT - same reasoning as stop-loss-guardian.tf's own header: this is a
 * real, ongoing AWS Scheduler invocation cost, not just having the capability exist.
 * Deploying it (terraform apply with enable_intraday_risk_monitor = true) needs an
 * explicit go-ahead.
 */

variable "enable_intraday_risk_monitor" {
  description = "Enable the high-frequency intraday risk (beta/concentration) re-check schedule (real, ongoing cost - needs explicit sign-off before enabling, see this file's header comment)"
  type        = bool
  default     = false
}

variable "intraday_risk_monitor_schedule_expression" {
  description = "How often the intraday risk monitor runs during market hours (default: every 15 minutes, 9:30 AM-4:00 PM ET)"
  type        = string
  default     = "cron(0/15 9-16 ? * MON-FRI *)"
}

resource "aws_scheduler_schedule" "intraday_risk_monitor" {
  count                        = var.enable_intraday_risk_monitor ? 1 : 0
  name                         = "${var.project_name}-intraday-risk-monitor-${var.environment}"
  description                  = "High-frequency intraday beta/concentration re-check between full orchestrator runs - see intraday-risk-monitor.tf header"
  schedule_expression          = var.intraday_risk_monitor_schedule_expression
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.algo_lambda_provisioned_concurrency > 0 ? aws_lambda_alias.algo_live[0].arn : aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      mode = "intraday_risk_monitor"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}
