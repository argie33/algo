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
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "api_lambda_security_group_id" {
  description = "Security group ID for API Lambda (dedicated for REST API Lambda)"
  type        = string
}

variable "algo_lambda_security_group_id" {
  description = "Security group ID for Algo Lambda (dedicated for orchestrator Lambda)"
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

variable "rds_proxy_address" {
  description = "RDS Proxy endpoint for connection pooling (host:port)"
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

variable "rds_password" {
  description = "RDS database password for Lambda environment"
  type        = string
  sensitive   = true
}

variable "rds_username" {
  description = "RDS database username for Lambda environment"
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "PostgreSQL port for Lambda connections"
  type        = number
  default     = 5432
  validation {
    condition     = var.db_port > 0 && var.db_port < 65536
    error_message = "Port must be between 1 and 65535"
  }
}

variable "db_ssl_mode" {
  description = "PostgreSQL SSL mode for Lambda connections (disable, allow, prefer, require, verify-ca, verify-full)"
  type        = string
  default     = "require"
  validation {
    condition     = contains(["disable", "allow", "prefer", "require", "verify-ca", "verify-full"], var.db_ssl_mode)
    error_message = "db_ssl_mode must be one of: disable, allow, prefer, require, verify-ca, verify-full"
  }
}

variable "algo_secrets_arn" {
  description = "ARN of algo runtime secrets (Alpaca, FRED, JWT) in Secrets Manager"
  type        = string
}

variable "psycopg2_layer_arn" {
  description = "ARN of psycopg2 Lambda layer for database connectivity"
  type        = string
  default     = ""
}

variable "lambda_layer_name" {
  description = "Name of the shared Lambda layer with dependencies"
  type        = string
  default     = "algo-orchestrator-layer"
}

variable "api_lambda_layer_name" {
  description = "Name of the API Lambda layer with dependencies"
  type        = string
  default     = "algo-api-layer"
}

variable "api_lambda_layer_version" {
  description = "Version number of the API Lambda layer (optional, default: latest)"
  type        = number
  default     = 0 # 0 means use latest
}

variable "api_lambda_layer_enabled" {
  description = "Whether API Lambda layer exists (built by GitHub Actions)"
  type        = bool
  default     = false
}

variable "lambda_layer_version" {
  description = "Version number of the shared Lambda layer (optional, default: latest)"
  type        = number
  default     = 0 # 0 means use latest
}

# ============================================================
# Storage Configuration
# ============================================================

variable "frontend_bucket_name" {
  description = "S3 bucket for frontend assets"
  type        = string
}

variable "frontend_bucket_public_access_block_id" {
  description = "ID of frontend bucket public access block (for dependency ordering)"
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
  description = "Timeout for API Lambda function (seconds). VPC cold-start can take 15-40s. Set higher than worst-case cold start time."
  type        = number
  default     = 120
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

variable "api_lambda_reserved_concurrency" {
  description = "Reserved concurrent executions for API Lambda (prevents 429 rate-limit cascades)"
  type        = number
  default     = 50
  validation {
    condition     = var.api_lambda_reserved_concurrency >= 1 && var.api_lambda_reserved_concurrency <= 1000
    error_message = "Reserved concurrency must be between 1 and 1000"
  }
}

variable "algo_lambda_reserved_concurrency" {
  description = "Reserved concurrent executions for orchestrator Lambda. Must be >1: up to 9 EventBridge Scheduler targets (premarket/morning/afternoon/preclose/evening/weight-optimization/3 prewarms) invoke this function per day, and overlapping invocations (slow run + next prewarm, or manual test + schedule) get throttled and dropped at concurrency=1. Concurrency safety across overlapping runs is already handled by the orchestrator's own DB-based advisory lock (_acquire_run_lock), so this only needs to be high enough to avoid EventBridge dropping legitimate invocations, not to serialize execution."
  type        = number
  default     = 5
  validation {
    condition     = var.algo_lambda_reserved_concurrency >= 1 && var.algo_lambda_reserved_concurrency <= 1000
    error_message = "Reserved concurrency must be between 1 and 1000"
  }
}

variable "api_lambda_provisioned_concurrency" {
  description = "Provisioned concurrent executions for API Lambda (pre-warmed instances to avoid cold starts). Cost: ~$12/month per unit. Set to 0 to disable. CRITICAL FIX: Set to 5 to prevent Lambda 503 errors from VPC cold-start (15-40s) exceeding API Gateway 29s timeout. Prevents dashboard 'data not available' errors."
  type        = number
  default     = 5
  validation {
    condition     = var.api_lambda_provisioned_concurrency >= 0 && var.api_lambda_provisioned_concurrency <= 100
    error_message = "Provisioned concurrency must be between 0 and 100"
  }
}

variable "algo_lambda_provisioned_concurrency" {
  description = "Provisioned concurrent executions for Orchestrator Lambda (pre-warmed instances to avoid cold starts). Cost: ~$12/month per unit. Set to 0 to disable. CRITICAL FIX: Set to 5 to prevent Lambda 503 errors from VPC cold-start (15-40s) exceeding Step Functions timeout. Prevents orchestrator phase timeout errors."
  type        = number
  default     = 5
  validation {
    condition     = var.algo_lambda_provisioned_concurrency >= 0 && var.algo_lambda_provisioned_concurrency <= 100
    error_message = "Provisioned concurrency must be between 0 and 100"
  }
}

# ============================================================
# API Gateway Configuration
# ============================================================

variable "api_gateway_stage_name" {
  description = "API Gateway stage name. Use $default so rawPath preserves /api/ prefix for Lambda routing."
  type        = string
  default     = "$default"
  validation {
    condition     = can(regex("^(\\$default|[a-zA-Z0-9_-]+)$", var.api_gateway_stage_name))
    error_message = "Stage name must be $default or contain only alphanumeric characters, hyphens, and underscores"
  }
}

variable "api_gateway_logging_enabled" {
  description = "Enable CloudWatch logging for API Gateway"
  type        = bool
  default     = true
}

variable "api_cors_allowed_origins" {
  description = "CORS allowed origins for API (computed by root module to be environment-aware). Passed from root locals which automatically adds localhost for dev, removes for prod."
  type        = list(string)
  default     = []
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

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID (from cognito module output)"
  type        = string
  default     = ""
}

variable "cognito_client_id" {
  description = "Cognito User Pool Client ID (from cognito module output)"
  type        = string
  default     = ""
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
    condition     = var.cognito_password_min_length >= 6 && var.cognito_password_min_length <= 256
    error_message = "Minimum password length must be between 6 and 256"
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
  description = "Timeout for algo Lambda function (seconds). Actual execution time: 11-15 minutes (660-900 seconds)."
  type        = number
  default     = 1200
  validation {
    condition     = var.algo_lambda_timeout >= 60 && var.algo_lambda_timeout <= 1200
    error_message = "Timeout must be between 60 and 1200 seconds"
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
  description = "Cron expression for algo execution (5:30 PM ET weekdays, after loaders run, uses America/New_York timezone)"
  type        = string
  default     = "cron(30 17 ? * MON-FRI *)"
  validation {
    condition     = can(regex("^cron\\(", var.algo_schedule_expression))
    error_message = "Must be a valid cron expression starting with 'cron('"
  }
}

variable "enable_premarket_orchestrator" {
  description = "Enable pre-market orchestrator execution (4:30 AM ET, optional early prep)"
  type        = bool
  default     = false
}

variable "enable_morning_orchestrator" {
  description = "Enable morning orchestrator execution (9:30 AM ET at market open, primary execution)"
  type        = bool
  default     = true
}

variable "enable_afternoon_orchestrator" {
  description = "Enable afternoon orchestrator execution (1:00 PM ET, mid-day rebalance, catch missed opportunities)"
  type        = bool
  default     = true
}

variable "enable_preclose_orchestrator" {
  description = "Enable pre-close orchestrator execution (3:00 PM ET, final trades before 4 PM ET market close)"
  type        = bool
  default     = true
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

# NOTE: Loader scheduling is now managed by the loaders module (modules/loaders/main.tf)
# All 40 loaders including price loaders are scheduled via EventBridge rules there
# Removed deprecated price_loader_task_definition_arn, loader_schedule_enabled, etc.

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

variable "alert_email_to" {
  description = "Email recipients for direct SMTP alerts (comma-separated). Requires alert_smtp_* variables for SMTP setup."
  type        = string
  default     = ""
}

variable "alert_webhook_url" {
  description = "Webhook URL for Slack, Teams, or custom integrations. Alerts sent here when loaders/orchestrator have critical issues."
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_smtp_host" {
  description = "SMTP server hostname for email alerts (e.g., smtp.gmail.com)"
  type        = string
  default     = ""
}

variable "alert_smtp_port" {
  description = "SMTP server port (typically 587 for TLS, 465 for SSL)"
  type        = number
  default     = 587
}

variable "alert_smtp_user" {
  description = "SMTP username for email alerts"
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_smtp_password" {
  description = "SMTP password for email alerts"
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_smtp_from" {
  description = "From email address for SMTP alerts"
  type        = string
  default     = ""
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
# Lambda Code Configuration (S3-based)
# ============================================================

variable "api_lambda_s3_bucket" {
  description = "S3 bucket containing API Lambda deployment package"
  type        = string
  default     = ""
}

variable "api_lambda_s3_key" {
  description = "S3 key (path) for API Lambda deployment package"
  type        = string
  default     = "lambda/api_lambda.zip"
}

variable "api_lambda_s3_object_version" {
  description = "S3 object version ID for API Lambda (enables updates via versioning)"
  type        = string
  default     = ""
}

variable "algo_lambda_s3_bucket" {
  description = "S3 bucket containing algo Lambda deployment package"
  type        = string
  default     = ""
}

variable "algo_lambda_s3_key" {
  description = "S3 key (path) for algo Lambda deployment package"
  type        = string
  default     = "lambda/algo_lambda.zip"
}

variable "algo_lambda_s3_object_version" {
  description = "S3 object version ID for algo Lambda (enables updates via versioning)"
  type        = string
  default     = ""
}

# Fallback: local files (for dev/testing)
variable "api_lambda_code_file" {
  description = "Local path to API Lambda deployment package (fallback if S3 not configured)"
  type        = string
  default     = "lambda_api.zip"
}

variable "algo_lambda_code_file" {
  description = "Local path to algo Lambda deployment package (fallback if S3 not configured)"
  type        = string
  default     = "lambda_algo.zip"
}

# ============================================================
# Orchestrator Configuration (passed to algo Lambda env vars)
# ============================================================

variable "alpaca_api_key_id" {
  description = "Alpaca API key ID (passed from root module)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_api_secret_key" {
  description = "Alpaca API secret key (passed from root module)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "alpaca_api_base_url" {
  description = "Alpaca API base URL (passed from root module)"
  type        = string
  default     = "https://api.alpaca.markets"
}

variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading (passed from root module)"
  type        = bool
  default     = false
}

variable "jwt_secret" {
  description = "JWT secret for authentication (passed from root module)"
  type        = string
  sensitive   = true
}

variable "fred_api_key" {
  description = "FRED API key for economic data (passed from root module)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "execution_mode" {
  description = "Algo execution mode (passed from root module)"
  type        = string
  default     = "auto"
}

variable "orchestrator_dry_run" {
  description = "Run orchestrator in dry-run mode (passed from root module)"
  type        = bool
  default     = false
}

variable "orchestrator_log_level" {
  description = "Logging level for orchestrator (passed from root module)"
  type        = string
  default     = "info"
}

variable "orchestrator_locks_table_name" {
  description = "DynamoDB table name for orchestrator distributed locks (passed from root module)"
  type        = string
  default     = "algo-orchestrator-locks"
}

variable "data_patrol_enabled" {
  description = "Enable data patrol monitoring (passed from root module)"
  type        = bool
  default     = true
}

variable "data_patrol_timeout_ms" {
  description = "Data patrol timeout in milliseconds (passed from root module)"
  type        = number
  default     = 30000
}

# ============================================================
# ECS Patrol Task Configuration
# ============================================================

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster for patrol task execution"
  type        = string
  default     = ""
}

variable "patrol_task_definition_arn" {
  description = "ARN of the data patrol ECS task definition"
  type        = string
  default     = ""
}

variable "patrol_task_container_name" {
  description = "Container name in the patrol task definition"
  type        = string
  default     = ""
}

variable "private_subnet_ids_for_patrol" {
  description = "Private subnet IDs for patrol task networking"
  type        = list(string)
  default     = []
}

variable "ecs_tasks_sg_id" {
  description = "Security group ID for ECS tasks (patrol)"
  type        = string
  default     = ""
}

# ============================================================
# Execution Monitor Configuration
# ============================================================

variable "enable_execution_monitor" {
  description = "Enable execution monitor Lambda for querying RDS/Alpaca"
  type        = bool
  default     = false
}

variable "enable_execution_monitor_schedule" {
  description = "Enable scheduled execution monitor (every 2 hours trading hours)"
  type        = bool
  default     = false
}

variable "rds_port" {
  description = "RDS database port"
  type        = string
  default     = "5432"
}

variable "rds_master_username" {
  description = "RDS master username"
  type        = string
  default     = "admin"
}

variable "rds_subnet_ids" {
  description = "Subnet IDs for RDS (for Lambda VPC config)"
  type        = list(string)
  default     = []
}

variable "rds_security_group_id" {
  description = "Security group ID for RDS"
  type        = string
  default     = ""
}

# ============================================================
# Weight Optimization Task Configuration
# ============================================================

variable "weight_optimization_task_definition_arn" {
  description = "ARN of the weight optimization ECS task definition (from loaders module)"
  type        = string
  default     = ""
}

variable "algo_lambda_sg_id" {
  description = "Security group ID for algo Lambda (for ECS task networking)"
  type        = string
  default     = ""
}

variable "node_env" {
  description = "Node.js environment (development, production)"
  type        = string
  default     = "production"
}

variable "dev_mode" {
  description = "Enable dev mode in orchestrator"
  type        = string
  default     = "false"
}

variable "task_execution_role_arn" {
  description = "IAM role ARN for ECS task execution (from IAM module)"
  type        = string
  default     = ""
}

variable "task_role_arn" {
  description = "IAM role ARN for ECS task (from IAM module)"
  type        = string
  default     = ""
}

# ============================================================
# Credential Rotation Schedules
# ============================================================

variable "alpaca_credential_rotation_schedule" {
  description = "Cron expression for Alpaca credential rotation reminder (cron(0 9 ? * MON *))"
  type        = string
  default     = "cron(0 9 ? * MON *)"
}

variable "fred_credential_rotation_schedule" {
  description = "Cron expression for FRED API credential rotation reminder (cron(0 10 ? * MON *))"
  type        = string
  default     = "cron(0 10 ? * MON *)"
}

# ============================================================
# Authentication Configuration
# ============================================================

variable "allow_dev_tokens_test" {
  description = "Enable dev token authentication for testing (e.g., dev-admin, dev-user). For testing only, NOT for production."
  type        = bool
  default     = false
}

# ============================================================
# Step Functions Integration
# ============================================================

variable "eod_pipeline_state_machine_arn" {
  description = "ARN of the EOD pipeline Step Functions state machine (from pipeline module)"
  type        = string
  default     = ""
}
