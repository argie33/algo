# ============================================================
# IAM Module - Input Variables
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

variable "github_org" {
  description = "GitHub organization"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}

# ============================================================
# Service Configuration
# ============================================================

variable "bastion_enabled" {
  description = "Whether to create bastion host and related IAM"
  type        = bool
  default     = true
}

variable "ecs_enabled" {
  description = "Whether to create ECS-related IAM roles"
  type        = bool
  default     = true
}

variable "lambda_enabled" {
  description = "Whether to create Lambda-related IAM roles"
  type        = bool
  default     = true
}

variable "rds_secret_arn" {
  description = "ARN of RDS credentials secret (for policy scoping)"
  type        = string
  default     = null
}

variable "data_bucket_name" {
  description = "Name of data loading S3 bucket (for policy scoping)"
  type        = string
  default     = null
}

variable "artifact_bucket_name" {
  description = "Name of Lambda artifacts S3 bucket (for policy scoping)"
  type        = string
  default     = null
}
