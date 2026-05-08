# ============================================================
# Database Module - Input Variables
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
# RDS Configuration
# ============================================================

variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.micro"

  validation {
    condition     = can(regex("^db\\.", var.db_instance_class))
    error_message = "Must be a valid RDS instance class (e.g., db.t3.micro)"
  }
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB (current: 61GB, cannot be reduced)"
  type        = number
  default     = 61

  validation {
    condition     = var.db_allocated_storage >= 20
    error_message = "Minimum allocated storage is 20 GB"
  }
}

variable "db_max_allocated_storage" {
  description = "Maximum storage for autoscaling (0 = disabled)"
  type        = number
  default     = 100

  validation {
    condition     = var.db_max_allocated_storage == 0 || var.db_max_allocated_storage >= 100
    error_message = "Max allocated storage must be 0 or >= 100 GB"
  }
}

variable "rds_db_name" {
  description = "Initial database name for RDS"
  type        = string
  default     = "stocks"

  validation {
    condition     = can(regex("^[a-z0-9_]{3,32}$", var.rds_db_name))
    error_message = "DB name must be 3-32 lowercase alphanumeric characters"
  }
}

variable "db_master_username" {
  description = "Master username for RDS"
  type        = string
  sensitive   = true
}

variable "db_master_password" {
  description = "Master password for RDS"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_master_password) >= 8
    error_message = "Password must be at least 8 characters"
  }
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7

  validation {
    condition     = var.db_backup_retention_days >= 1 && var.db_backup_retention_days <= 35
    error_message = "Backup retention must be 1-35 days"
  }
}

variable "enable_rds_kms_encryption" {
  description = "Enable customer-managed KMS key for RDS encryption (recommended for prod)"
  type        = bool
  default     = false
}

variable "rds_kms_key_id" {
  description = "KMS key ID for RDS encryption (only used if enable_rds_kms_encryption=true)"
  type        = string
  default     = null
}

# ============================================================
# Network Configuration
# ============================================================

variable "vpc_id" {
  description = "VPC ID for RDS"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for RDS (must be 2+)"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Must provide at least 2 private subnets for RDS"
  }
}

variable "rds_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
}

# ============================================================
# Secrets Configuration
# ============================================================

variable "notification_email" {
  description = "Email address for alerts and contact form"
  type        = string
  default     = ""
}

variable "alpaca_api_key_id" {
  description = "Alpaca API key ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_api_secret_key" {
  description = "Alpaca API secret key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_api_base_url" {
  description = "Alpaca API base URL"
  type        = string
  default     = "https://paper-api.alpaca.markets"
}

variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading mode"
  type        = string
  default     = "true"
}

# ============================================================
# Monitoring Configuration
# ============================================================

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention_days)
    error_message = "Must be a valid CloudWatch retention period"
  }
}

variable "enable_rds_alarms" {
  description = "Enable CloudWatch alarms for RDS"
  type        = bool
  default     = true
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications (optional)"
  type        = string
  default     = null
}

variable "rds_cpu_alarm_threshold" {
  description = "CPU utilization threshold for RDS alarm (%)"
  type        = number
  default     = 80

  validation {
    condition     = var.rds_cpu_alarm_threshold > 0 && var.rds_cpu_alarm_threshold <= 100
    error_message = "CPU threshold must be 1-100"
  }
}

variable "rds_storage_alarm_threshold" {
  description = "Free storage threshold for RDS alarm (bytes)"
  type        = number
  default     = 10737418240 # 10 GB

  validation {
    condition     = var.rds_storage_alarm_threshold > 0
    error_message = "Storage threshold must be > 0"
  }
}

variable "rds_connections_alarm_threshold" {
  description = "Active connections threshold for RDS alarm"
  type        = number
  default     = 50

  validation {
    condition     = var.rds_connections_alarm_threshold > 0
    error_message = "Connections threshold must be > 0"
  }
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention_days)
    error_message = "Must be a valid CloudWatch retention period"
  }
}
