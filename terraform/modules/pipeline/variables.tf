variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev/prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster where loader tasks run"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Fargate task networking"
  type        = list(string)
}

variable "ecs_tasks_sg_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "task_execution_role_arn" {
  description = "ECS task execution role ARN (for Step Functions PassRole)"
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (for Step Functions PassRole)"
  type        = string
}

variable "loader_task_definition_arns" {
  description = "Map of loader name → task definition ARN (from loaders module output)"
  type        = map(string)
}

variable "algo_lambda_arn" {
  description = "ARN of the algo orchestrator Lambda function"
  type        = string
}

variable "sns_alert_topic_arn" {
  description = "SNS topic ARN for pipeline failure alerts"
  type        = string
  default     = ""
  validation {
    condition     = var.sns_alert_topic_arn == "" || can(regex("^arn:aws:sns:", var.sns_alert_topic_arn))
    error_message = "sns_alert_topic_arn must be a valid SNS ARN (arn:aws:sns:...) or empty string."
  }
}

variable "common_tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
