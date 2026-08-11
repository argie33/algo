variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda VPC"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS"
  type        = string
}

variable "task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (ECR pull, CloudWatch logs) - scopes trigger_loaders' iam:PassRole instead of Resource=\"*\""
  type        = string
}

variable "task_role_arn" {
  description = "IAM role ARN for ECS task (S3, Secrets Manager access for loaders) - scopes trigger_loaders' iam:PassRole instead of Resource=\"*\""
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID, used to scope ecs:RunTask to this project's task definitions instead of Resource=\"*\""
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
