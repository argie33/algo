# ============================================================
# AWS Batch Module - Variables
# ============================================================

variable "project_name" {
  description = "Project name for resource naming"
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

variable "vpc_id" {
  description = "VPC ID for Batch resources"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for compute environment"
  type        = list(string)
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks/Batch jobs"
  type        = string
}

variable "data_bucket_name" {
  description = "S3 data bucket name for loader output"
  type        = string
}

variable "ecr_repository_uri" {
  description = "ECR repository URI for container images"
  type        = string
}

variable "db_host" {
  description = "RDS database hostname"
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

variable "db_user" {
  description = "RDS database username"
  type        = string
}

variable "rds_secret_arn" {
  description = "ARN of RDS credentials in Secrets Manager"
  type        = string
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "batch_max_vcpus" {
  description = "Maximum vCPUs for Batch compute environment"
  type        = number
  default     = 256
}

variable "batch_instance_types" {
  description = "EC2 instance types for Batch compute environment"
  type        = list(string)
  default     = ["c5.xlarge", "c5.2xlarge", "c6i.xlarge", "c6i.2xlarge", "m5.xlarge", "m5.2xlarge"]
}

variable "batch_instance_root_volume_size" {
  description = "Root volume size in GB for Batch instances"
  type        = number
  default     = 100
}

variable "batch_spot_bid_percentage" {
  description = "Spot price bid percentage (70 = 70% of on-demand price)"
  type        = number
  default     = 70
}

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
