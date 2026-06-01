output "state_machine_arn" {
  description = "ARN of the EOD pipeline Step Functions state machine"
  value       = aws_sfn_state_machine.eod_pipeline.arn
}

output "state_machine_name" {
  description = "Name of the EOD pipeline state machine"
  value       = aws_sfn_state_machine.eod_pipeline.name
}

output "eventbridge_rule_name" {
  description = "EventBridge Scheduler rule that triggers the EOD pipeline at 4:05pm ET"
  value       = aws_scheduler_schedule.eod_pipeline_trigger.name
}

output "ecs_log_group_name" {
  description = "CloudWatch log group name for ECS loaders (passed through from compute module for monitoring)"
  value       = var.ecs_log_group_name
}
