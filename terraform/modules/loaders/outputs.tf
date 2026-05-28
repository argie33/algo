# ============================================================
# Loaders Module - Outputs (All 40 Loaders)
# ============================================================

output "loader_task_definition_arns" {
  description = "Task definition family names (Step Functions will resolve to latest active revision)"
  value       = { for k, v in aws_ecs_task_definition.loader : k => v.family }
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
  value       = { for k in keys(local.all_loaders) : k => "/ecs/${var.project_name}-${k}-loader" }
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

# ============================================================
# Algo Orchestrator Task Outputs (for Step Functions integration)
# ============================================================

output "algo_orchestrator_task_definition_arn" {
  description = "Family name of the algo orchestrator ECS task definition (Step Functions will resolve to latest active revision)"
  value       = aws_ecs_task_definition.algo_orchestrator.family
}

output "algo_orchestrator_task_definition_family" {
  description = "Family name of the algo orchestrator ECS task definition"
  value       = aws_ecs_task_definition.algo_orchestrator.family
}

output "algo_orchestrator_log_group_name" {
  description = "CloudWatch log group for algo orchestrator"
  value       = "/ecs/${var.project_name}-algo-orchestrator"
}

# ============================================================
# Continuous Monitor Task Outputs
# ============================================================

output "continuous_monitor_task_definition_arn" {
  description = "ARN of the continuous monitor ECS task definition (runs every 15 min)"
  value       = aws_ecs_task_definition.continuous_monitor.arn
}

output "continuous_monitor_task_definition_family" {
  description = "Family name of the continuous monitor ECS task definition"
  value       = aws_ecs_task_definition.continuous_monitor.family
}

output "continuous_monitor_log_group_name" {
  description = "CloudWatch log group for continuous monitor"
  value       = "/ecs/${var.project_name}-continuous-monitor"
}

output "continuous_monitor_event_rule_arn" {
  description = "ARN of EventBridge rule for continuous monitor (every 15 minutes)"
  value       = aws_cloudwatch_event_rule.continuous_monitor.arn
}

# ============================================================
# Data Patrol Task Outputs
# ============================================================

output "data_patrol_task_definition_arn" {
  description = "ARN of the data patrol ECS task definition (invoked by API)"
  value       = aws_ecs_task_definition.data_patrol.arn
}

output "data_patrol_task_definition_family" {
  description = "Family name of the data patrol ECS task definition"
  value       = aws_ecs_task_definition.data_patrol.family
}

output "data_patrol_log_group_name" {
  description = "CloudWatch log group for data patrol"
  value       = "/ecs/${var.project_name}-data-patrol"
}

# ============================================================
# Weight Optimization Task Outputs (Daily Continuous Improvement)
# ============================================================

output "weight_optimization_task_definition_arn" {
  description = "ARN of the weight optimization ECS task definition (invoked daily at 6 PM ET)"
  value       = aws_ecs_task_definition.weight_optimization.arn
}

output "weight_optimization_task_definition_family" {
  description = "Family name of the weight optimization ECS task definition"
  value       = aws_ecs_task_definition.weight_optimization.family
}

output "weight_optimization_log_group_name" {
  description = "CloudWatch log group for weight optimization"
  value       = "/ecs/${var.project_name}-weight-optimization"
}
