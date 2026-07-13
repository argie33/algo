variable "project_name" {
  description = "Project name (used for resource naming)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be 'dev', 'staging', or 'prod'"
  }
}

variable "vpc_id" {
  description = "VPC ID where ElastiCache cluster will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ElastiCache subnet group"
  type        = list(string)
  validation {
    condition     = length(var.private_subnet_ids) > 0
    error_message = "At least one private subnet ID must be provided"
  }
}

variable "ecs_task_security_group_id" {
  description = "Security group ID of ECS tasks that need to access Redis"
  type        = string
}

variable "redis_node_type" {
  description = "ElastiCache Redis node type (cache.t3.micro for dev, cache.t3.small for prod)"
  type        = string
  default     = "cache.t3.micro" # t3.micro = 0.5 GB memory (sufficient for price cache)
}

variable "kms_key_id" {
  description = "KMS key ARN for at-rest encryption (optional, defaults to AWS-managed)"
  type        = string
  default     = ""
}

variable "cloudwatch_log_group_name" {
  description = "CloudWatch log group name for Redis slow log"
  type        = string
}

variable "sns_alerts_enabled" {
  description = "Whether to send SNS notifications for ElastiCache events"
  type        = bool
  default     = true
}

variable "sns_alerts_topic_arn" {
  description = "SNS topic ARN for cache alerts"
  type        = string
  default     = ""
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
