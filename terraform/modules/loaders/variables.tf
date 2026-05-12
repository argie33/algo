variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "ecr_repository_uri" {
  description = "ECR repository URI for loader container images"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for loader resources"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS task placement (requires 2+ for Fargate)"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Must provide at least 2 private subnets for Fargate HA."
  }
}

variable "ecs_cluster_name" {
  description = "ECS cluster name where loaders will run"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of Secrets Manager secret containing DB credentials (username:password)"
  type        = string
  sensitive   = true
}

variable "db_host" {
  description = "RDS database host address"
  type        = string
}

variable "db_port" {
  description = "RDS database port"
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "RDS database name"
  type        = string
}

variable "ecs_tasks_sg_id" {
  description = "Security group ID for ECS tasks (must allow egress to RDS + internet)"
  type        = string
}

variable "task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (ECR pull, CloudWatch logs)"
  type        = string
}

variable "task_role_arn" {
  description = "IAM role ARN for ECS task (S3, Secrets Manager access for loaders)"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
}

variable "sns_alert_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarm notifications"
  type        = string
  default     = ""
}
