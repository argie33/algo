/**
 * Unified Risk Monitor Schedule
 *
 * REAL-MONEY-READINESS CONSOLIDATION (2026-09-06): replaces 4 previously uncoordinated
 * intraday mechanisms with one 5-minute check, algo/risk/unified_risk_monitor.py::
 * check_unified_risk (see that module's docstring for the full architecture rationale):
 *
 *   1. lambda/circuit-breaker/index.py's own separately-packaged Lambda (3 fixed daily
 *      schedules: 10am/12pm/3pm, portfolio P&L variance only).
 *   2. lambda/execution-monitor/index.py's own separately-packaged Lambda (every 2h,
 *      read-only reporting, no action).
 *   3. intraday-risk-monitor.tf's schedule (algo/risk/intraday_risk_monitor.py, live
 *      beta/top-5 concentration re-check, deliberately alert-only).
 *   4. stop-loss-guardian.tf's schedule (Phase 9's stop-loss verify/repair step run on
 *      its own tighter cadence).
 *
 * Unlike (3) above, this consolidated check ACTS on a sustained, re-confirmed breach
 * (automated halt, then automated reduce/flatten if the breach persists past the halt -
 * see unified_risk_monitor.py's CONSECUTIVE_BREACH_RUNS_TO_HALT/_ACT) rather than only
 * alerting - a deliberate, user-directed decision superseding intraday-risk-monitor.tf's
 * original alert-only stance.
 *
 * The 4 old schedules/Lambdas are NOT deleted by this file - per the rollout plan, this
 * is deployed disabled first, soaked in paper mode alongside the old mechanisms running
 * in shadow for direct comparison, and only after a clean soak are the old
 * circuit-breaker.tf/execution-monitor.tf/stop-loss-guardian.tf/intraday-risk-monitor.tf
 * resources deleted, in a separate change.
 *
 * NOT ENABLED BY DEFAULT - real, ongoing AWS Scheduler invocation cost, and this schedule
 * both halts trading and can submit real exit orders automatically. Deploying it
 * (terraform apply with enable_unified_risk_monitor = true) needs an explicit go-ahead.
 */

variable "enable_unified_risk_monitor" {
  description = "Enable the consolidated 5-minute intraday risk monitor (real, ongoing cost + automated halt/reduce-flatten action on a sustained breach - needs explicit sign-off before enabling, see this file's header comment)"
  type        = bool
  default     = false
}

variable "unified_risk_monitor_schedule_expression" {
  description = "How often the unified risk monitor runs during market hours (default: every 5 minutes, 9:30 AM-4:00 PM ET)"
  type        = string
  default     = "cron(0/5 9-16 ? * MON-FRI *)"
}

resource "aws_scheduler_schedule" "unified_risk_monitor" {
  count                        = var.enable_unified_risk_monitor ? 1 : 0
  name                         = "${var.project_name}-unified-risk-monitor-${var.environment}"
  description                  = "Consolidated 5-minute portfolio variance / live beta+concentration / stop-loss protection / live intraday market-health check - see unified-risk-monitor.tf header"
  schedule_expression          = var.unified_risk_monitor_schedule_expression
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.algo_lambda_provisioned_concurrency > 0 ? aws_lambda_alias.algo_live[0].arn : aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      mode = "unified_risk_monitor"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}
