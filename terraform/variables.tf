# ============================================================
# Root Module - Input Variables
# ============================================================

# ============================================================
# Deployment Configuration
# ============================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "stocks"
  validation {
    condition     = can(regex("^[a-z0-9-]{3,32}$", var.project_name))
    error_message = "Project name must be 3-32 lowercase alphanumeric characters"
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
}

variable "github_repository" {
  description = "GitHub repository in format owner/repo for OIDC trust"
  type        = string
  default     = "argie33/algo"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$", var.github_repository))
    error_message = "Repository must be in format owner/repo"
  }
}

variable "github_ref_path" {
  description = "GitHub ref path for OIDC trust (e.g., refs/heads/main)"
  type        = string
  default     = "refs/heads/main"
  validation {
    condition     = can(regex("^refs/(heads|tags)/", var.github_ref_path))
    error_message = "Ref path must start with refs/heads/ or refs/tags/"
  }
}

variable "notification_email" {
  description = "Email address for CloudWatch alarms and SNS notifications"
  type        = string
  default     = ""
  validation {
    condition     = var.notification_email == "" || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.notification_email))
    error_message = "Must be a valid email address or empty string"
  }
}

# ============================================================
# Network Configuration
# ============================================================

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "Must be a valid CIDR block"
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
  validation {
    condition     = length(var.public_subnet_cidrs) >= 2 && length(var.public_subnet_cidrs) <= 4
    error_message = "Must have 2-4 public subnets"
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
  validation {
    condition     = length(var.private_subnet_cidrs) >= 2 && length(var.private_subnet_cidrs) <= 4
    error_message = "Must have 2-4 private subnets"
  }
}

variable "availability_zones" {
  description = "Availability zones (typically 2 or 3)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints (S3, Secrets Manager, ECR, CloudWatch Logs, SNS, DynamoDB)"
  type        = bool
  default     = true
}

# ============================================================
# RDS Configuration
# ============================================================

variable "rds_username" {
  description = "Master username for RDS database"
  type        = string
  default     = "stocks"
  sensitive   = true
}

variable "rds_password" {
  description = "Master password for RDS database (auto-generated if not provided, must be 8+ characters, no special chars at start/end)"
  type        = string
  sensitive   = true
  default     = "" # Will be generated dynamically by Terraform
  validation {
    condition     = length(var.rds_password) == 0 || length(var.rds_password) >= 8
    error_message = "RDS password must be at least 8 characters long or left empty for auto-generation"
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

variable "rds_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.micro"
  validation {
    condition     = can(regex("^db\\.", var.rds_instance_class))
    error_message = "Must be a valid RDS instance class (e.g., db.t3.micro)"
  }
}

variable "rds_allocated_storage" {
  description = "Initial allocated storage in GB"
  type        = number
  default     = 61
  validation {
    condition     = var.rds_allocated_storage >= 20 && var.rds_allocated_storage <= 65535
    error_message = "Storage must be between 20 and 65535 GB"
  }
}

variable "rds_iops" {
  description = "IOPS for RDS gp3 storage (3000-64000)"
  type        = number
  default     = 3000
  validation {
    condition     = var.rds_iops >= 3000 && var.rds_iops <= 64000
    error_message = "IOPS must be between 3000 and 64000"
  }
}

variable "rds_max_allocated_storage" {
  description = "Maximum auto-scaling storage in GB"
  type        = number
  default     = 100
  validation {
    condition     = var.rds_max_allocated_storage >= 20 && var.rds_max_allocated_storage <= 65535
    error_message = "Max storage must be between 20 and 65535 GB"
  }
}

variable "rds_backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 30
  validation {
    condition     = var.rds_backup_retention_period >= 1 && var.rds_backup_retention_period <= 35
    error_message = "Retention period must be 1-35 days"
  }
}

variable "rds_backup_window" {
  description = "Backup window in UTC (HH:MM-HH:MM, e.g., 03:00-04:00)"
  type        = string
  default     = "03:00-04:00"
  validation {
    condition     = can(regex("^\\d{2}:\\d{2}-\\d{2}:\\d{2}$", var.rds_backup_window))
    error_message = "Backup window must be in format HH:MM-HH:MM"
  }
}

variable "rds_maintenance_window" {
  description = "Maintenance window in UTC (ddd:HH:MM-ddd:HH:MM, e.g., sun:04:00-sun:05:00)"
  type        = string
  default     = "sun:04:00-sun:05:00"
  validation {
    condition     = can(regex("^(mon|tue|wed|thu|fri|sat|sun):\\d{2}:\\d{2}-(mon|tue|wed|thu|fri|sat|sun):\\d{2}:\\d{2}$", var.rds_maintenance_window))
    error_message = "Maintenance window must be in format ddd:HH:MM-ddd:HH:MM"
  }
}

variable "enable_rds_cloudwatch_logs" {
  description = "Enable CloudWatch logs for RDS"
  type        = bool
  default     = true
}

variable "enable_rds_alarms" {
  description = "Enable CloudWatch alarms for RDS (CPU, storage, connections). Set true for any live system."
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Enable RDS deletion protection. Set true for any live system with real data."
  type        = bool
  default     = true
}

variable "rds_log_retention_days" {
  description = "RDS log retention in days"
  type        = number
  default     = 30
}

variable "rds_multi_az" {
  description = "Enable Multi-AZ deployment for RDS high availability. Set true for production (adds standby replica in different AZ). Default false for cost optimization in dev/testing."
  type        = bool
  default     = false
}

# ============================================================
# ECS Configuration
# ============================================================

variable "ecs_cluster_name" {
  description = "ECS cluster name"
  type        = string
  default     = null
}

variable "ecs_capacity_providers" {
  description = "ECS capacity providers (FARGATE, FARGATE_SPOT)"
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
  default     = false # Disabled to avoid ASG conflicts; enable after core infrastructure is stable
}

variable "bastion_instance_type" {
  description = "EC2 instance type for Bastion"
  type        = string
  default     = "t3.micro"
  validation {
    condition     = can(regex("^t[23]\\.", var.bastion_instance_type))
    error_message = "Bastion should use t3 or t4g instance types"
  }
}

variable "bastion_shutdown_hour_utc" {
  description = "Hour (UTC) to shutdown Bastion (0-23)"
  type        = number
  default     = 4
  validation {
    condition     = var.bastion_shutdown_hour_utc >= 0 && var.bastion_shutdown_hour_utc < 24
    error_message = "Hour must be 0-23"
  }
}

variable "bastion_shutdown_minute_utc" {
  description = "Minute (UTC) to shutdown Bastion (0-59)"
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
  default     = null
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
# Storage Configuration
# ============================================================

variable "enable_s3_versioning" {
  description = "Enable versioning on all S3 buckets"
  type        = bool
  default     = true
}

variable "code_bucket_expiration_days" {
  description = "Days before deleting old code artifacts"
  type        = number
  default     = 90
}

variable "data_bucket_expiration_days" {
  description = "Days before deleting old loader staging data"
  type        = number
  default     = 30
}

# ============================================================
# Lambda Configuration
# ============================================================

variable "api_lambda_memory" {
  description = "Memory for API Lambda"
  type        = number
  default     = 256
}

variable "api_lambda_timeout" {
  description = "Timeout for API Lambda"
  type        = number
  default     = 30
}

variable "api_lambda_ephemeral_storage" {
  description = "Ephemeral storage for API Lambda"
  type        = number
  default     = 512
}

variable "algo_lambda_memory" {
  description = "Memory for algo Lambda"
  type        = number
  default     = 512
}

variable "algo_lambda_timeout" {
  description = "Timeout for algo Lambda"
  type        = number
  default     = 300
}

variable "algo_lambda_ephemeral_storage" {
  description = "Ephemeral storage for algo Lambda"
  type        = number
  default     = 2048
}

variable "api_lambda_code_file" {
  description = "Path to API Lambda deployment package (ZIP file)"
  type        = string
  default     = "lambda_api.zip"
  validation {
    condition     = endswith(var.api_lambda_code_file, ".zip")
    error_message = "Lambda code file must be a ZIP file"
  }
}

variable "algo_lambda_code_file" {
  description = "Path to algo Lambda deployment package (ZIP file)"
  type        = string
  default     = "lambda_algo.zip"
  validation {
    condition     = endswith(var.algo_lambda_code_file, ".zip")
    error_message = "Lambda code file must be a ZIP file"
  }
}

# ============================================================
# API Gateway Configuration
# ============================================================

variable "api_gateway_stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "api"
}

variable "api_gateway_logging_enabled" {
  description = "Enable CloudWatch logging for API Gateway"
  type        = bool
  default     = true
}

variable "api_cors_allowed_origins" {
  description = "CORS allowed origins"
  type        = list(string)
  default     = ["http://localhost:5173", "http://localhost:3000"]
}

variable "api_gateway_log_retention_days" {
  description = "API Gateway log retention"
  type        = number
  default     = 7
}

# ============================================================
# CloudFront Configuration
# ============================================================

variable "cloudfront_enabled" {
  description = "Enable CloudFront distribution"
  type        = bool
  default     = true
}

variable "cloudfront_cache_default_ttl" {
  description = "Default CloudFront cache TTL"
  type        = number
  default     = 3600
}

variable "cloudfront_cache_max_ttl" {
  description = "Max CloudFront cache TTL"
  type        = number
  default     = 86400
}

variable "cloudfront_waf_enabled" {
  description = "Enable WAF on CloudFront"
  type        = bool
  default     = false
}

# ============================================================
# Cognito Configuration
# ============================================================

variable "domain_name" {
  description = "Domain name for Cognito configuration (e.g., example.com)"
  type        = string
  default     = "example.com"
}

variable "cloudfront_domain" {
  description = "CloudFront domain name for frontend (e.g., d2u93283nn45h2.cloudfront.net). Used for Cognito callback and logout URLs."
  type        = string
  default     = "d2u93283nn45h2.cloudfront.net"
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "stocks"
    Environment = "dev"
    ManagedBy   = "Terraform"
  }
}

variable "cognito_enabled" {
  description = "Enable Cognito user pool"
  type        = bool
  default     = false
}

variable "cognito_user_pool_name" {
  description = "Cognito user pool name (defaults to project-environment-users)"
  type        = string
  default     = null # Will be set to "${var.project_name}-${var.environment}-users" in module if null
}

variable "cognito_password_min_length" {
  description = "Cognito password minimum length"
  type        = number
  default     = 12
}

variable "cognito_mfa_configuration" {
  description = "Cognito MFA configuration"
  type        = string
  default     = "OPTIONAL"
  validation {
    condition     = contains(["OFF", "OPTIONAL", "REQUIRED"], var.cognito_mfa_configuration)
    error_message = "Must be OFF, OPTIONAL, or REQUIRED"
  }
}

variable "cognito_session_duration_hours" {
  description = "Cognito session duration"
  type        = number
  default     = 24
}

# ============================================================
# Algo Orchestrator Configuration
# ============================================================

variable "algo_schedule_expression" {
  description = "Cron expression for algo execution"
  type        = string
  default     = "cron(0 4 ? * MON-FRI *)"
}

variable "algo_schedule_enabled" {
  description = "Enable algo scheduler"
  type        = bool
  default     = true
}

variable "algo_schedule_timezone" {
  description = "Timezone for algo schedule"
  type        = string
  default     = "America/New_York"
}

variable "enable_morning_orchestrator" {
  description = "Enable 2x daily orchestrator execution (morning 9:30 AM ET + evening 5:30 PM ET)"
  type        = bool
  default     = true
}

# ============================================================
# SNS Configuration
# ============================================================

variable "sns_alerts_enabled" {
  description = "Enable SNS alerts"
  type        = bool
  default     = true
}

variable "sns_alert_email" {
  description = "Email for SNS alerts (set via GitHub Secret ALERT_EMAIL_ADDRESS)"
  type        = string
  default     = ""
  validation {
    condition     = var.sns_alert_email == "" || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.sns_alert_email))
    error_message = "Must be a valid email address or empty string (set via TF_VAR_sns_alert_email)"
  }
}

# ============================================================
# Alpaca Trading Configuration
# ============================================================

variable "alpaca_api_key_id" {
  description = "Alpaca API key ID for paper trading (set to empty string if not using)"
  type        = string
  sensitive   = true
  default     = ""
  validation {
    condition     = var.alpaca_api_key_id == "" || length(var.alpaca_api_key_id) > 10
    error_message = "Alpaca API key must be empty or a valid key (>10 characters)"
  }
}

variable "alpaca_api_secret_key" {
  description = "Alpaca API secret key for paper trading (set to empty string if not using)"
  type        = string
  sensitive   = true
  default     = ""
  validation {
    condition     = var.alpaca_api_secret_key == "" || length(var.alpaca_api_secret_key) > 10
    error_message = "Alpaca API secret must be empty or a valid key (>10 characters)"
  }
}

variable "alpaca_api_base_url" {
  description = "Alpaca API base URL (paper or live)"
  type        = string
  default     = "https://paper-api.alpaca.markets"
}

variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading mode"
  type        = bool
  default     = true
}

# ============================================================
# Loader Configuration
# ============================================================


# ============================================================
# AWS Batch Configuration (buyselldaily Heavy Loader)
# ============================================================

variable "batch_max_vcpus" {
  description = "Maximum vCPUs for Batch compute environment"
  type        = number
  default     = 256
  validation {
    condition     = var.batch_max_vcpus > 0 && var.batch_max_vcpus <= 1024
    error_message = "Must be between 1 and 1024"
  }
}

variable "batch_instance_types" {
  description = "EC2 instance types for Batch Spot Fleet (use current generation: c6i, c7i, m6i, m7i, r6i, r7i)"
  type        = list(string)
  default     = ["c6i.xlarge", "c6i.2xlarge", "c7i.xlarge", "c7i.2xlarge", "m6i.xlarge", "m6i.2xlarge"]
  validation {
    condition     = length(var.batch_instance_types) > 0
    error_message = "Must specify at least one instance type"
  }
  validation {
    condition = alltrue([
      for t in var.batch_instance_types : can(regex("^(t[234]|m[567]|c[567]|r[567]|i[34]|a[12]|t4g|m[67][aig]|c[67][aig]|r[67][aig])\\.", t))
    ])
    error_message = "All instance types must be Spot-compatible (t2/t3/t4, m5+, c5+, r5+, i3+, a1+, t4g, m6i, c6i, r6i, m7i, c7i, r7i, etc)"
  }
}

variable "batch_spot_bid_percentage" {
  description = "Spot price bid percentage (70 = 70% of on-demand price = 30% cost savings)"
  type        = number
  default     = 70
  validation {
    condition     = var.batch_spot_bid_percentage >= 10 && var.batch_spot_bid_percentage <= 100
    error_message = "Must be between 10 and 100"
  }
}

# ============================================================
# Logging Configuration
# ============================================================

variable "cloudwatch_log_retention_days" {
  description = "Default CloudWatch log retention"
  type        = number
  default     = 30
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention_days)
    error_message = "Must be a valid CloudWatch retention period"
  }
}

variable "enable_bastion_cloudwatch_logs" {
  description = "Enable CloudWatch logs for Bastion SSM"
  type        = bool
  default     = true
}

# ============================================================
# Application Configuration (Orchestrator & Monitoring)
# ============================================================

variable "jwt_secret" {
  description = "JWT secret for authentication (auto-generated if empty)"
  type        = string
  sensitive   = true
  default     = ""
  validation {
    condition     = length(var.jwt_secret) == 0 || length(var.jwt_secret) >= 16
    error_message = "JWT secret must be at least 16 characters or left empty for auto-generation"
  }
}

variable "fred_api_key" {
  description = "FRED API key for economic data (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "orchestrator_log_level" {
  description = "Logging level for orchestrator (debug, info, warning, error)"
  type        = string
  default     = "info"
  validation {
    condition     = contains(["debug", "info", "warning", "error"], var.orchestrator_log_level)
    error_message = "Log level must be debug, info, warning, or error"
  }
}

variable "data_patrol_enabled" {
  description = "Enable data patrol monitoring for loader health checks"
  type        = bool
  default     = true
}

variable "data_patrol_timeout_ms" {
  description = "Data patrol timeout in milliseconds"
  type        = number
  default     = 30000
  validation {
    condition     = var.data_patrol_timeout_ms > 0 && var.data_patrol_timeout_ms <= 300000
    error_message = "Timeout must be between 1ms and 300s"
  }
}

# ============================================================
# Frontend Configuration
# ============================================================

variable "frontend_origin" {
  description = "Frontend origin URL for CORS (e.g., http://localhost:3000 or https://example.com)"
  type        = string
  default     = "http://localhost:3000"
  validation {
    condition     = can(regex("^https?://", var.frontend_origin))
    error_message = "Frontend origin must start with http:// or https://"
  }
}

# ============================================================
# Tags
# ============================================================

variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================================
# AWS Configuration
# ============================================================

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "AWS region must be a valid region code"
  }
}

# ============================================================
# Orchestrator Configuration
# ============================================================

variable "execution_mode" {
  description = "Orchestrator execution mode (auto, manual, dry-run)"
  type        = string
  default     = "auto"
  validation {
    condition     = contains(["auto", "manual", "dry-run"], var.execution_mode)
    error_message = "Execution mode must be auto, manual, or dry-run"
  }
}

variable "orchestrator_dry_run" {
  description = "Enable dry-run mode for orchestrator (no actual trades)"
  type        = bool
  default     = false
}

# ============================================================
# Governance & Security Configuration
# ============================================================

variable "enforce_iac_only" {
  description = "Enforce IaC-only resource creation via SCPs (block manual AWS API calls)"
  type        = bool
  default     = true
}

variable "require_terraform_tag" {
  description = "Require terraform:managed tag on all resources"
  type        = bool
  default     = true
}

# ============================================================
# RDS Proxy & KMS Configuration
# ============================================================

variable "enable_rds_proxy" {
  description = "Enable RDS Proxy for connection pooling"
  type        = bool
  default     = true
}

variable "enable_rds_kms_encryption" {
  description = "Enable KMS encryption for RDS (recommended for prod)"
  type        = bool
  default     = false
}

variable "rds_kms_key_alias" {
  description = "KMS key alias for RDS encryption (used if enable_rds_kms_encryption=true)"
  type        = string
  default     = null
}

variable "db_port" {
  description = "PostgreSQL port"
  type        = number
  default     = 5432
}

# ============================================================
# RDS Alarm Thresholds
# ============================================================

variable "rds_cpu_alarm_threshold" {
  description = "RDS CPU alarm threshold (percent)"
  type        = number
  default     = 80
  validation {
    condition     = var.rds_cpu_alarm_threshold > 0 && var.rds_cpu_alarm_threshold <= 100
    error_message = "CPU threshold must be 1-100 percent"
  }
}

variable "rds_storage_alarm_threshold" {
  description = "RDS storage alarm threshold (bytes). Default is 10 GiB"
  type        = number
  default     = 10737418240
}

variable "rds_connections_alarm_threshold" {
  description = "RDS connections alarm threshold"
  type        = number
  default     = 50
}

# ============================================================
# Execution Monitor Configuration
# ============================================================

variable "enable_execution_monitor" {
  description = "Enable execution monitor Lambda (monitors realized vs predicted trades)"
  type        = bool
  default     = true
}

variable "enable_execution_monitor_schedule" {
  description = "Enable execution monitor schedule (runs every 2 hours during trading hours)"
  type        = bool
  default     = true
}

# ============================================================
# Security Monitoring Configuration
# ============================================================

variable "cloudtrail_enabled" {
  description = "Enable AWS CloudTrail"
  type        = bool
  default     = true
}

variable "guardduty_enabled" {
  description = "Enable Amazon GuardDuty threat detection"
  type        = bool
  default     = true
}

variable "aws_config_enabled" {
  description = "Enable AWS Config compliance monitoring"
  type        = bool
  default     = true
}

variable "vpc_flow_logs_enabled" {
  description = "Enable VPC Flow Logs"
  type        = bool
  default     = true
}

variable "security_log_retention_days" {
  description = "CloudWatch log retention for security monitoring (CloudTrail, GuardDuty, Config, VPC Flow Logs)"
  type        = number
  default     = 90
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.security_log_retention_days)
    error_message = "Must be a valid CloudWatch retention period"
  }
}

# ============================================================
# Loader & Orchestrator Configuration
# ============================================================

variable "backfill_days" {
  description = "Number of days to backfill on first loader run"
  type        = number
  default     = 365
}

variable "disable_provenance_tracking" {
  description = "Disable provenance tracking in loaders (useful for cost-saving test runs)"
  type        = bool
  default     = true
}

# ============================================================
# Lambda Configuration
# ============================================================

variable "lambda_runtime" {
  description = "Lambda runtime version (e.g., python3.11, python3.12)"
  type        = string
  default     = "python3.11"
}

variable "lambda_layer_name" {
  description = "Lambda layer name for shared dependencies. If null, computed as project-name-orchestrator-layer"
  type        = string
  default     = null
}

# ============================================================
# Application Environment Configuration
# ============================================================

variable "node_env" {
  description = "Node.js environment (development, production). If empty, inferred from var.environment"
  type        = string
  default     = ""
  validation {
    condition     = var.node_env == "" || contains(["development", "production"], var.node_env)
    error_message = "Must be empty (auto-inferred), 'development', or 'production'"
  }
}

variable "dev_mode" {
  description = "Enable dev mode in orchestrator (no actual trades, verbose logging). If empty, inferred as (var.environment == 'dev')"
  type        = string
  default     = ""
  validation {
    condition     = var.dev_mode == "" || contains(["true", "false"], var.dev_mode)
    error_message = "Must be empty (auto-inferred), 'true', or 'false'"
  }
}

# ============================================================
# Credentials & Notification Configuration
# ============================================================

variable "notification_email_from" {
  description = "Email address to use as 'from' in Secrets Manager metadata (e.g., noreply@company.com). Empty = use default"
  type        = string
  default     = ""
}

variable "cognito_test_user_email" {
  description = "Email for Cognito test user (empty = don't create test user)"
  type        = string
  default     = ""
  validation {
    condition     = var.cognito_test_user_email == "" || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.cognito_test_user_email))
    error_message = "Must be a valid email address or empty"
  }
}

# ============================================================
# Secrets & Rotation Configuration
# ============================================================

variable "developer_key_rotation_date" {
  description = "Date of last developer AWS credential rotation (YYYY-MM-DD format). Update quarterly via rotate-dev-credentials.yml"
  type        = string
  default     = "2026-05-26"
  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-\\d{2}$", var.developer_key_rotation_date))
    error_message = "Must be in YYYY-MM-DD format"
  }
}

variable "secrets_rotation_days" {
  description = "Secrets Manager rotation frequency (days)"
  type        = number
  default     = 30
  validation {
    condition     = var.secrets_rotation_days >= 7 && var.secrets_rotation_days <= 90
    error_message = "Rotation must be 7-90 days"
  }
}

variable "postgres_major_version" {
  description = "PostgreSQL major version (14, 15, 16)"
  type        = string
  default     = "14"
  validation {
    condition     = contains(["14", "15", "16"], var.postgres_major_version)
    error_message = "Must be 14, 15, or 16"
  }
}

# ============================================================
# Batch & Compute Configuration
# ============================================================

variable "batch_vcpus" {
  description = "vCPU request for AWS Batch job containers"
  type        = number
  default     = 4
}

variable "batch_memory_mb" {
  description = "Memory (MB) for AWS Batch job containers"
  type        = number
  default     = 4096
}

variable "ecr_image_count" {
  description = "Number of ECR images to retain (old images auto-deleted)"
  type        = number
  default     = 10
}

