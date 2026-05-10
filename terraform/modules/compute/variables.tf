# ============================================================
# Compute Module - Input Variables
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
# Network Configuration
# ============================================================

variable "vpc_id" {
  description = "VPC ID for compute resources"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for Bastion"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS"
  type        = list(string)
}

variable "bastion_security_group_id" {
  description = "Security group ID for Bastion"
  type        = string
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "bastion_instance_profile_name" {
  description = "IAM instance profile name for Bastion"
  type        = string
}

variable "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of ECS task role (for ECR pull permissions)"
  type        = string
}

variable "lambda_api_role_arn" {
  description = "ARN of Lambda API role (for ECR pull permissions)"
  type        = string
}

variable "lambda_algo_role_arn" {
  description = "ARN of Lambda Algo role (for ECR pull permissions)"
  type        = string
}

# ============================================================
# ECS Configuration
# ============================================================

variable "ecs_cluster_name" {
  description = "Name of ECS cluster"
  type        = string
  default     = null # Will use project-derived name if null
}

variable "ecs_capacity_providers" {
  description = "ECS capacity providers"
  type        = list(string)
  default     = ["FARGATE", "FARGATE_SPOT"]
}

variable "ecs_default_capacity_provider_strategy" {
  description = "Default capacity provider strategy"
  type = list(object({
    capacity_provider = string
    weight            = number
  }))
  default = [
    { capacity_provider = "FARGATE_SPOT", weight = 4 },
    { capacity_provider = "FARGATE", weight = 1 }
  ]
}

# ============================================================
# Bastion Configuration
# ============================================================

variable "bastion_enabled" {
  description = "Whether to create Bastion host"
  type        = bool
  default     = true
}

variable "bastion_instance_type" {
  description = "EC2 instance type for Bastion (Spot pricing)"
  type        = string
  default     = "t3.micro"

  validation {
    condition     = can(regex("^t[23]\\.", var.bastion_instance_type))
    error_message = "Bastion should use t3 or t4g instance types for cost optimization"
  }
}

variable "bastion_ami_filter" {
  description = "SSM parameter path for Bastion AMI"
  type        = string
  default     = "/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-ebs"
}

variable "bastion_shutdown_hour_utc" {
  description = "Hour (UTC) to shutdown Bastion for cost savings (24-hour format)"
  type        = number
  default     = 4

  validation {
    condition     = var.bastion_shutdown_hour_utc >= 0 && var.bastion_shutdown_hour_utc < 24
    error_message = "Hour must be 0-23"
  }
}

variable "bastion_shutdown_minute_utc" {
  description = "Minute (UTC) to shutdown Bastion"
  type        = number
  default     = 59

  validation {
    condition     = var.bastion_shutdown_minute_utc >= 0 && var.bastion_shutdown_minute_utc < 60
    error_message = "Minute must be 0-59"
  }
}

# ============================================================
# ECR Configuration
# ============================================================

variable "ecr_repository_name" {
  description = "ECR repository name"
  type        = string
  default     = null # Will use project-derived name if null
}

variable "ecr_image_scan_enabled" {
  description = "Enable ECR image scanning on push"
  type        = bool
  default     = true
}

variable "ecr_image_tag_mutability" {
  description = "ECR image tag mutability (MUTABLE or IMMUTABLE)"
  type        = string
  default     = "MUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.ecr_image_tag_mutability)
    error_message = "Must be MUTABLE or IMMUTABLE"
  }
}

# ============================================================
# Logging Configuration
# ============================================================

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention for ECS/Bastion"
  type        = number
  default     = 30
}

variable "enable_bastion_cloudwatch_logs" {
  description = "Enable CloudWatch log group for Bastion Session Manager"
  type        = bool
  default     = true
}
