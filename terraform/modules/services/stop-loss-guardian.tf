/**
 * Stop-Loss Guardian Schedule
 *
 * REAL-MONEY-READINESS FIX (2026-09-05 audit): the full 9-phase orchestrator runs only
 * 5x/day (see 2x-daily-orchestrator.tf's premarket/morning/afternoon/preclose/evening
 * schedules), and Phase 9's stop-loss protection verify/auto-repair check
 * (phase9_reconciliation.py's _verify_open_position_stop_loss_protection_step) is the
 * only thing that catches a live position's stop-loss leg going missing (day-TIF
 * expiry, broker-side glitch, manual intervention). Between orchestrator runs a real
 * gap can sit unprotected for hours during market hours.
 *
 * This invokes the SAME already-deployed orchestrator Lambda (no new function, IAM
 * role, or deployment package to keep in sync - see lambda_function.py's `mode:
 * "stop_loss_guardian"` dispatch) with a payload that runs ONLY that one check, on a
 * much tighter schedule, in between the full runs.
 *
 * NOT ENABLED BY DEFAULT. This is a real, ongoing AWS Scheduler invocation cost and an
 * operational change to what runs against the live Alpaca account - deploying it
 * (terraform apply with enable_stop_loss_guardian = true) needs an explicit go-ahead,
 * not just having the capability exist. The code-level fix (Phase 9 no longer silently
 * failing on its own check - see phase9_reconciliation.py's 2026-09-05 fixes) already
 * ships regardless of whether this schedule is ever turned on.
 */

variable "enable_stop_loss_guardian" {
  description = "Enable the high-frequency stop-loss-only guardian schedule (real, ongoing cost + a live-account behavior change - needs explicit sign-off before enabling, see this file's header comment)"
  type        = bool
  default     = false
}

variable "stop_loss_guardian_schedule_expression" {
  description = "How often the stop-loss guardian check runs during market hours (default: every 15 minutes, 9:30 AM-4:00 PM ET)"
  type        = string
  default     = "cron(0/15 9-16 ? * MON-FRI *)"
}

resource "aws_scheduler_schedule" "stop_loss_guardian" {
  count                        = var.enable_stop_loss_guardian ? 1 : 0
  name                         = "${var.project_name}-stop-loss-guardian-${var.environment}"
  description                  = "High-frequency stop-loss-only check between full orchestrator runs - see stop-loss-guardian.tf header"
  schedule_expression          = var.stop_loss_guardian_schedule_expression
  schedule_expression_timezone = "America/New_York"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.algo_lambda_provisioned_concurrency > 0 ? aws_lambda_alias.algo_live[0].arn : aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      mode = "stop_loss_guardian"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}
