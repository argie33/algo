# ============================================================
# Loaders Module - Outputs
# ============================================================

output "loader_task_definition_arns" {
  description = "ARNs of all loader ECS task definitions (keyed by loader name)"
  value       = { for k, v in aws_ecs_task_definition.loader : k => v.arn }
}

output "loader_task_definition_families" {
  description = "Task definition families for all loaders (keyed by loader name)"
  value       = { for k, v in aws_ecs_task_definition.loader : k => v.family }
}

output "loader_task_definition_revisions" {
  description = "Revision numbers of all loader task definitions (keyed by loader name)"
  value       = { for k, v in aws_ecs_task_definition.loader : k => v.revision }
}

output "loader_log_group_names" {
  description = "CloudWatch log group names for all loaders (keyed by loader name)"
  value       = { for k, v in aws_cloudwatch_log_group.loader : k => v.name }
}

output "eventbridge_rules" {
  description = "EventBridge rule names for scheduled loaders"
  value = {
    econdata       = aws_cloudwatch_event_rule.econdata_schedule.name
    feargreed      = aws_cloudwatch_event_rule.fear_greed_schedule.name
    market_indices = aws_cloudwatch_event_rule.market_indices_schedule.name
    sector_ranking = aws_cloudwatch_event_rule.sector_ranking_schedule.name
  }
}

output "eventbridge_targets" {
  description = "EventBridge target ARNs for scheduled loader tasks"
  value = {
    econdata       = aws_cloudwatch_event_target.econdata_target.arn
    feargreed      = aws_cloudwatch_event_target.fear_greed_target.arn
    market_indices = aws_cloudwatch_event_target.market_indices_target.arn
    sector_ranking = aws_cloudwatch_event_target.sector_ranking_target.arn
  }
}

output "eventbridge_role_arn" {
  description = "ARN of EventBridge IAM role for running ECS tasks"
  value       = aws_iam_role.eventbridge_run_task.arn
}

output "all_loader_names" {
  description = "List of all configured loader names"
  value       = keys(local.default_loaders)
}
