output "state_machine_arn" {
  value = "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-loaders"
  description = "State Machine ARN (placeholder - implement when Step Functions added)"
}
