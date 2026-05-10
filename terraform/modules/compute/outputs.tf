# ============================================================
# Compute Module - Outputs
# ============================================================

# ECS Cluster
output "ecs_cluster_name" {
  description = "Name of ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_cluster_id" {
  description = "ID of ECS cluster"
  value       = aws_ecs_cluster.main.id
}

# ECR Registry
output "ecr_repository_url" {
  description = "URL of ECR repository"
  value       = aws_ecr_repository.main.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of ECR repository"
  value       = aws_ecr_repository.main.arn
}

output "ecr_repository_name" {
  description = "Name of ECR repository"
  value       = aws_ecr_repository.main.name
}

# Bastion Host
output "bastion_asg_name" {
  description = "Name of Bastion Auto Scaling Group"
  value       = var.bastion_enabled ? aws_autoscaling_group.bastion[0].name : null
}

output "bastion_launch_template_id" {
  description = "ID of Bastion launch template"
  value       = var.bastion_enabled ? aws_launch_template.bastion[0].id : null
}

output "bastion_shutdown_lambda_arn" {
  description = "ARN of Bastion auto-shutdown Lambda"
  value       = var.bastion_enabled ? aws_lambda_function.bastion_stop[0].arn : null
}

output "bastion_shutdown_lambda_name" {
  description = "Name of Bastion auto-shutdown Lambda"
  value       = var.bastion_enabled ? aws_lambda_function.bastion_stop[0].function_name : null
}

# CloudWatch Logs
output "ecs_log_group_name" {
  description = "CloudWatch log group for ECS cluster"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "bastion_ssm_log_group_name" {
  description = "CloudWatch log group for Bastion SSM sessions"
  value       = var.enable_bastion_cloudwatch_logs && var.bastion_enabled ? aws_cloudwatch_log_group.bastion_ssm[0].name : null
}
