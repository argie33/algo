output "eod_state_machine_arn" {
  description = "ARN of the EOD pipeline Step Functions state machine"
  value       = aws_sfn_state_machine.eod_pipeline.arn
}

output "eod_state_machine_name" {
  description = "Name of the EOD pipeline state machine"
  value       = aws_sfn_state_machine.eod_pipeline.name
}

output "morning_state_machine_arn" {
  description = "ARN of the morning pipeline Step Functions state machine"
  value       = aws_sfn_state_machine.morning_prep_pipeline.arn
}

output "afternoon_update_state_machine_arn" {
  description = "ARN of the intraday afternoon (1 PM) score update state machine"
  value       = aws_sfn_state_machine.intraday_afternoon_update_pipeline.arn
}

output "preclose_update_state_machine_arn" {
  description = "ARN of the intraday pre-close (3 PM) score update state machine"
  value       = aws_sfn_state_machine.intraday_preclose_update_pipeline.arn
}

output "eventbridge_rule_names" {
  description = "EventBridge Scheduler rules that trigger all data pipelines"
  value = {
    morning_trigger   = aws_scheduler_schedule.morning_pipeline_trigger.name
    afternoon_trigger = aws_scheduler_schedule.afternoon_update_pipeline_trigger.name
    preclose_trigger  = aws_scheduler_schedule.preclose_update_pipeline_trigger.name
    eod_trigger       = aws_scheduler_schedule.eod_pipeline_trigger.name
  }
}

output "ecs_log_group_name" {
  description = "CloudWatch log group name for ECS loaders (passed through from compute module for monitoring)"
  value       = var.ecs_log_group_name
}
