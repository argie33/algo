# ============================================================
# Services Module - Input Variables
# ============================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens"
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "AWS account ID must be 12 digits"
  }
}

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}

# ============================================================
# Network Configuration
# ============================================================

variable "vpc_id" {
  description = "VPC ID for Lambda functions"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda functions"
  type        = list(string)
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks (Lambda will need this for database access)"
  type        = string
}

# ============================================================
# IAM Configuration
# ============================================================

variable "api_lambda_role_arn" {
  description = "IAM role ARN for API Lambda (from IAM module)"
  type        = string
}

variable "algo_lambda_role_arn" {
  description = "IAM role ARN for Algo Lambda (from IAM module)"
  type        = string
}

variable "eventbridge_scheduler_role_arn" {
  description = "IAM role ARN for EventBridge Scheduler (from IAM module)"
  type        = string
}

# ============================================================
# Database Configuration
# ============================================================

variable "rds_endpoint" {
  description = "RDS database endpoint (host:port)"
  type        = string
}

variable "rds_database_name" {
  description = "RDS database name"
  type        = string
}

variable "rds_credentials_secret_arn" {
  description = "ARN of RDS credentials secret in Secrets Manager"
  type        = string
}

# ============================================================
# Storage Configuration
# ============================================================

variable "frontend_bucket_name" {
  description = "S3 bucket for frontend assets"
  type        = string
}

variable "code_bucket_name" {
  description = "S3 bucket for Lambda code artifacts"
  type        = string
}

variable "data_loading_bucket_name" {
  description = "S3 bucket for data loading staging area"
  type        = string
}

variable "lambda_artifacts_bucket_name" {
  description = "S3 bucket for Lambda deployment packages"
  type        = string
}

# ============================================================
# Lambda API Configuration
# ============================================================

variable "api_lambda_memory" {
  description = "Memory allocation for API Lambda function (MB)"
  type        = number
  default     = 256
  validation {
    condition     = var.api_lambda_memory >= 128 && var.api_lambda_memory <= 10240 && var.api_lambda_memory % 1 == 0
    error_message = "Memory must be between 128 and 10240 MB"
  }
}

variable "api_lambda_timeout" {
  description = "Timeout for API Lambda function (seconds)"
  type        = number
  default     = 30
  validation {
    condition     = var.api_lambda_timeout >= 1 && var.api_lambda_timeout <= 900
    error_message = "Timeout must be between 1 and 900 seconds"
  }
}

variable "api_lambda_ephemeral_storage" {
  description = "Ephemeral storage for API Lambda (/tmp, MB)"
  type        = number
  default     = 512
  validation {
    condition     = var.api_lambda_ephemeral_storage >= 512 && var.api_lambda_ephemeral_storage <= 10240
    error_message = "Ephemeral storage must be between 512 and 10240 MB"
  }
}

# ============================================================
# API Gateway Configuration
# ============================================================

variable "api_gateway_stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "api"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+$", var.api_gateway_stage_name))
    error_message = "Stage name must contain only alphanumeric characters, hyphens, and underscores"
  }
}

variable "api_gateway_logging_enabled" {
  description = "Enable CloudWatch logging for API Gateway"
  type        = bool
  default     = true
}

variable "api_cors_allowed_origins" {
  description = "CORS allowed origins for API (will include CloudFront domain automatically)"
  type        = list(string)
  default     = ["http://localhost:5173", "http://localhost:3000"]
}

# ============================================================
# CloudFront Configuration
# ============================================================

variable "cloudfront_enabled" {
  description = "Whether to create CloudFront distribution"
  type        = bool
  default     = true
}

variable "cloudfront_cache_default_ttl" {
  description = "Default TTL for CloudFront caching (seconds)"
  type        = number
  default     = 3600
}

variable "cloudfront_cache_max_ttl" {
  description = "Max TTL for CloudFront caching (seconds)"
  type        = number
  default     = 86400
}

variable "cloudfront_waf_enabled" {
  description = "Enable WAF on CloudFront (requires WAF module)"
  type        = bool
  default     = false
}

# ============================================================
# Cognito Configuration
# ============================================================

variable "cognito_enabled" {
  description = "Whether to create Cognito user pool for authentication"
  type        = bool
  default     = true
}

variable "cognito_user_pool_name" {
  description = "Cognito user pool name"
  type        = string
  default     = null
}

variable "cognito_password_min_length" {
  description = "Minimum password length for Cognito"
  type        = number
  default     = 12
  validation {
    condition     = var.cognito_password_min_length >= 6
    error_message = "Minimum password length must be at least 6"
  }
}

variable "cognito_mfa_configuration" {
  description = "MFA configuration (OFF, OPTIONAL, or REQUIRED)"
  type        = string
  default     = "OPTIONAL"
  validation {
    condition     = contains(["OFF", "OPTIONAL", "REQUIRED"], var.cognito_mfa_configuration)
    error_message = "MFA must be OFF, OPTIONAL, or REQUIRED"
  }
}

variable "cognito_session_duration_hours" {
  description = "Session duration for Cognito tokens (hours)"
  type        = number
  default     = 24
  validation {
    condition     = var.cognito_session_duration_hours >= 1 && var.cognito_session_duration_hours <= 24
    error_message = "Session duration must be between 1 and 24 hours"
  }
}

# ============================================================
# Algo Orchestrator Configuration
# ============================================================

variable "algo_lambda_memory" {
  description = "Memory allocation for algo orchestrator Lambda (MB)"
  type        = number
  default     = 512
  validation {
    condition     = var.algo_lambda_memory >= 128 && var.algo_lambda_memory <= 10240
    error_message = "Memory must be between 128 and 10240 MB"
  }
}

variable "algo_lambda_timeout" {
  description = "Timeout for algo Lambda function (seconds)"
  type        = number
  default     = 300
  validation {
    condition     = var.algo_lambda_timeout >= 60 && var.algo_lambda_timeout <= 900
    error_message = "Timeout must be between 60 and 900 seconds"
  }
}

variable "algo_lambda_ephemeral_storage" {
  description = "Ephemeral storage for algo Lambda (/tmp, MB)"
  type        = number
  default     = 2048
  validation {
    condition     = var.algo_lambda_ephemeral_storage >= 512 && var.algo_lambda_ephemeral_storage <= 10240
    error_message = "Ephemeral storage must be between 512 and 10240 MB"
  }
}

# ============================================================
# EventBridge Scheduler Configuration
# ============================================================

variable "algo_schedule_expression" {
  description = "Cron expression for algo execution (UTC time)"
  type        = string
  default     = "cron(0 4 ? * MON-FRI *)"
  validation {
    condition     = can(regex("^cron\\(", var.algo_schedule_expression))
    error_message = "Must be a valid cron expression starting with 'cron('"
  }
}

variable "algo_schedule_enabled" {
  description = "Whether the algo orchestrator schedule is enabled"
  type        = bool
  default     = true
}

variable "algo_schedule_timezone" {
  description = "Timezone for algo schedule (e.g., America/New_York)"
  type        = string
  default     = "America/New_York"
}

# ============================================================
# SNS Configuration
# ============================================================

variable "sns_alerts_enabled" {
  description = "Enable SNS topic for algo alerts"
  type        = bool
  default     = true
}

variable "sns_alert_email" {
  description = "Email address for SNS alert subscriptions"
  type        = string
  default     = ""
  validation {
    condition     = var.sns_alert_email == "" || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.sns_alert_email))
    error_message = "Must be a valid email address or empty string"
  }
}

# ============================================================
# Logging Configuration
# ============================================================

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention for Lambda functions (days)"
  type        = number
  default     = 30
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention_days)
    error_message = "Must be a valid CloudWatch log retention period"
  }
}

variable "api_gateway_log_retention_days" {
  description = "CloudWatch log retention for API Gateway (days)"
  type        = number
  default     = 7
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.api_gateway_log_retention_days)
    error_message = "Must be a valid CloudWatch log retention period"
  }
}

# ============================================================
# Lambda Code Configuration
# ============================================================

variable "api_lambda_code_file" {
  description = "Path to API Lambda deployment package (zip file)"
  type        = string
  default     = "lambda_api.zip"
}

variable "algo_lambda_code_file" {
  description = "Path to algo Lambda deployment package (zip file)"
  type        = string
  default     = "lambda_algo.zip"
}
