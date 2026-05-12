output "state_machine_arn" {
  description = "ARN of the EOD pipeline Step Functions state machine"
  value       = aws_sfn_state_machine.eod_pipeline.arn
}

output "state_machine_name" {
  description = "Name of the EOD pipeline state machine"
  value       = aws_sfn_state_machine.eod_pipeline.name
}

output "eventbridge_rule_name" {
  description = "EventBridge rule that triggers the pipeline at 4:05pm ET"
  value       = aws_cloudwatch_event_rule.eod_pipeline_trigger.name
}
