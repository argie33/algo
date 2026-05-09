# ============================================================
# Step Functions Module - Outputs
# ============================================================

output "state_machine_name" {
  description = "Name of the Step Functions state machine"
  value       = aws_sfn_state_machine.massive_parallel_signals.name
}

output "state_machine_arn" {
  description = "ARN of the Step Functions state machine"
  value       = aws_sfn_state_machine.massive_parallel_signals.arn
}

output "execution_tracker_table_name" {
  description = "DynamoDB table name for execution tracking"
  value       = aws_dynamodb_table.execution_tracker.name
}

output "execution_tracker_table_arn" {
  description = "DynamoDB table ARN for execution tracking"
  value       = aws_dynamodb_table.execution_tracker.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for Step Functions"
  value       = aws_cloudwatch_log_group.step_functions.name
}

output "cloudwatch_log_group_arn" {
  description = "CloudWatch log group ARN for Step Functions"
  value       = aws_cloudwatch_log_group.step_functions.arn
}

output "dashboard_url" {
  description = "CloudWatch dashboard URL for monitoring"
  value       = "https://console.aws.amazon.com/cloudwatch/home#dashboards:name=${aws_cloudwatch_dashboard.step_functions_monitor.dashboard_name}"
}

output "eventbridge_rule_name" {
  description = "EventBridge rule name for scheduled execution"
  value       = aws_cloudwatch_event_rule.signal_execution_scheduler.name
}

output "step_functions_role_arn" {
  description = "ARN of Step Functions execution role"
  value       = aws_iam_role.step_functions_role.arn
}
