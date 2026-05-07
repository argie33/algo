# ============================================================
# Loaders Module - Input Variables
# ============================================================

variable "project_name" {
  description = "Project name for naming convention"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
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

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}

# ============================================================
# ECS Configuration
# ============================================================

variable "ecs_cluster_name" {
  description = "ECS cluster name (for logging)"
  type        = string
}

variable "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  type        = string
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for task placement"
  type        = list(string)
}

# ============================================================
# ECR Configuration
# ============================================================

variable "ecr_repository_url" {
  description = "ECR repository URL"
  type        = string
}

variable "container_image_tag" {
  description = "Container image tag (default: latest)"
  type        = string
  default     = "latest"
}

# ============================================================
# Database Configuration
# ============================================================

variable "rds_credentials_secret_arn" {
  description = "ARN of RDS credentials secret"
  type        = string
}

variable "rds_endpoint" {
  description = "RDS database endpoint (host:port)"
  type        = string
}

variable "rds_port" {
  description = "RDS database port"
  type        = number
  default     = 5432
}

variable "rds_database_name" {
  description = "RDS database name"
  type        = string
}

# ============================================================
# Storage Configuration
# ============================================================

variable "data_loading_bucket_name" {
  description = "S3 bucket for loader staging"
  type        = string
}

# ============================================================
# Logging Configuration
# ============================================================

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# ============================================================
# Task Configuration
# ============================================================

variable "loader_task_cpu" {
  description = "CPU units per task (256, 512, 1024, etc.)"
  type        = number
  default     = 256
}

variable "loader_task_memory" {
  description = "Memory per task in MB"
  type        = number
  default     = 512
}

variable "loader_task_timeout_seconds" {
  description = "Task timeout in seconds (for CloudWatch)"
  type        = number
  default     = 3600
}

# ============================================================
# Loader Manifest
# ============================================================

variable "loader_manifest" {
  description = "Manifest of all loaders (name -> config)"
  type = map(object({
    description = string
    cpu         = optional(number)
    memory      = optional(number)
    environment = optional(map(string))
  }))

  default = {}
}
