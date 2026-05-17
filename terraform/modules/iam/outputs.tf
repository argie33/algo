# ============================================================
# IAM Module - Outputs
# ============================================================

# GitHub Actions OIDC & Role
output "github_oidc_provider_arn" {
  description = "ARN of GitHub Actions OIDC provider"
  value       = data.aws_iam_openid_connect_provider.github.arn
}

output "github_actions_role_arn" {
  description = "ARN of GitHub Actions deployment role"
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_role_name" {
  description = "Name of GitHub Actions deployment role"
  value       = aws_iam_role.github_actions.name
}

# Bastion
output "bastion_role_arn" {
  description = "ARN of Bastion host IAM role"
  value       = var.bastion_enabled ? aws_iam_role.bastion[0].arn : null
}

output "bastion_instance_profile_name" {
  description = "Name of Bastion instance profile (for launch template)"
  value       = var.bastion_enabled ? aws_iam_instance_profile.bastion[0].name : null
}

# ECS
output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_execution_role_name" {
  description = "Name of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.name
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_task_role_name" {
  description = "Name of ECS task role"
  value       = aws_iam_role.ecs_task.name
}

# Lambda
output "lambda_api_role_arn" {
  description = "ARN of Lambda API execution role"
  value       = aws_iam_role.lambda_api.arn
}

output "lambda_api_role_name" {
  description = "Name of Lambda API execution role"
  value       = aws_iam_role.lambda_api.name
}

output "lambda_algo_role_arn" {
  description = "ARN of Lambda Algo execution role"
  value       = aws_iam_role.lambda_algo.arn
}

output "lambda_algo_role_name" {
  description = "Name of Lambda Algo execution role"
  value       = aws_iam_role.lambda_algo.name
}

# EventBridge
output "eventbridge_scheduler_role_arn" {
  description = "ARN of EventBridge Scheduler execution role"
  value       = aws_iam_role.eventbridge_scheduler.arn
}

output "eventbridge_scheduler_role_name" {
  description = "Name of EventBridge Scheduler execution role"
  value       = aws_iam_role.eventbridge_scheduler.name
}

# Developer User
output "developer_user_name" {
  description = "Name of developer IAM user (for local CLI access)"
  value       = aws_iam_user.developer.name
}

output "developer_user_arn" {
  description = "ARN of developer IAM user"
  value       = aws_iam_user.developer.arn
}

output "developer_access_key_id" {
  description = "Access key ID for local developer CLI use (read-only verification)"
  value       = aws_iam_access_key.developer.id
  sensitive   = true
}

output "developer_secret_access_key" {
  description = "Secret access key for local developer CLI use (keep secure, SAVE IMMEDIATELY)"
  value       = aws_iam_access_key.developer.secret
  sensitive   = true
}

output "developer_console_login_url" {
  description = "AWS Console login URL for developer user"
  value       = "https://${var.aws_account_id}.signin.aws.amazon.com/console"
}
