# ============================================================
# Loaders Module - Outputs (All 40 Loaders)
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
  description = "EventBridge rule names for all scheduled loaders"
  value       = { for k, v in aws_cloudwatch_event_rule.scheduled_loader : k => v.name }
}

output "eventbridge_targets" {
  description = "EventBridge target ARNs for all scheduled loader tasks"
  value       = { for k, v in aws_cloudwatch_event_target.scheduled_loader_target : k => v.arn }
}

output "eventbridge_role_arn" {
  description = "ARN of EventBridge IAM role for running ECS tasks"
  value       = aws_iam_role.eventbridge_run_task.arn
}

output "all_loader_names" {
  description = "List of all 40 configured loader names"
  value       = keys(local.all_loaders)
}

output "scheduled_loader_names" {
  description = "List of scheduled loader names (33 loaders)"
  value       = keys(local.scheduled_loaders)
}

output "loader_count" {
  description = "Total number of loaders configured"
  value       = length(local.all_loaders)
}

output "scheduled_loader_count" {
  description = "Total number of scheduled loaders"
  value       = length(local.scheduled_loaders)
}
