# ============================================================
# AWS Batch Module - Outputs
# ============================================================

output "compute_environment_name" {
  description = "ARN of the Batch compute environment (used for resource identification)"
  value       = aws_batch_compute_environment.spot.arn
}

output "compute_environment_arn" {
  description = "ARN of the Batch compute environment"
  value       = aws_batch_compute_environment.spot.arn
}

output "job_queue_name" {
  description = "Name of the Batch job queue"
  value       = aws_batch_job_queue.spot.name
}

output "job_queue_arn" {
  description = "ARN of the Batch job queue"
  value       = aws_batch_job_queue.spot.arn
}

output "buyselldaily_job_definition_name" {
  description = "Name of the buyselldaily job definition"
  value       = aws_batch_job_definition.buyselldaily.name
}

output "buyselldaily_job_definition_arn" {
  description = "ARN of the buyselldaily job definition"
  value       = aws_batch_job_definition.buyselldaily.arn
}

output "batch_job_role_arn" {
  description = "ARN of the Batch job IAM role"
  value       = aws_iam_role.batch_job_role.arn
}

output "batch_ecs_instance_role_arn" {
  description = "ARN of the Batch ECS instance role (for EC2 Spot instances)"
  value       = aws_iam_role.batch_ecs_instance_role.arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for Batch jobs"
  value       = aws_cloudwatch_log_group.batch.name
}

output "cloudwatch_log_group_arn" {
  description = "CloudWatch log group ARN for Batch jobs"
  value       = aws_cloudwatch_log_group.batch.arn
}
