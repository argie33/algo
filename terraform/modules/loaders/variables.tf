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

variable "db_ssl_mode" {
  description = "PostgreSQL SSL mode for ECS loader connections (disable, allow, prefer, require, verify-ca, verify-full)"
  type        = string
  default     = "require"
  validation {
    condition     = contains(["disable", "allow", "prefer", "require", "verify-ca", "verify-full"], var.db_ssl_mode)
    error_message = "db_ssl_mode must be one of: disable, allow, prefer, require, verify-ca, verify-full"
  }
}

variable "db_name" {
  description = "RDS database name"
  type        = string
}

variable "db_user" {
  description = "RDS database username"
  type        = string
  default     = "stocks"
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

variable "fred_api_key" {
  description = "FRED API key for economic data (free at fred.stlouisfed.org) - DEPRECATED: use algo_secrets_arn instead"
  type        = string
  default     = ""
  sensitive   = true
}

variable "algo_secrets_arn" {
  description = "ARN of algo runtime secrets (Alpaca, FRED, JWT) in Secrets Manager"
  type        = string
}

variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading mode (true for testing, false for live)"
  type        = bool
  default     = true
}

variable "alpaca_api_base_url" {
  description = "Alpaca API base URL (https://paper-api.alpaca.markets for paper, https://api.alpaca.markets for live)"
  type        = string
  default     = "https://paper-api.alpaca.markets"
}

variable "execution_mode" {
  description = "Orchestrator execution mode (auto, manual, dry-run)"
  type        = string
  default     = "auto"
}

variable "orchestrator_dry_run" {
  description = "Enable dry-run mode for orchestrator (no actual trades)"
  type        = bool
  default     = false
}

variable "orchestrator_log_level" {
  description = "Logging level for orchestrator (debug, info, warning, error)"
  type        = string
  default     = "info"
}

variable "backfill_days" {
  # See root variables.tf: 365 here made every loader run a full-year refetch;
  # 0 enables the watermark-incremental path. Nonzero only for explicit recovery.
  description = "Days to force-refetch on EVERY loader run (0 = watermark-incremental; nonzero only for recovery)"
  type        = number
  default     = 0
}

variable "disable_provenance_tracking" {
  description = "Disable provenance tracking in loaders"
  type        = bool
  default     = true
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

variable "rds_resource_id" {
  description = "RDS resource ID for IAM database auth (e.g., cluster-ABCD1234)"
  type        = string
  default     = "stocks-cluster"
}

variable "rds_proxy_endpoint" {
  description = "RDS Proxy endpoint for Lambda connections (connection pooling)"
  type        = string
  default     = ""
}

variable "db_security_group_id" {
  description = "Security group ID for database access"
  type        = string
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 30
}

variable "redis_endpoint_address" {
  description = "ElastiCache Redis endpoint address (hostname only, no port)"
  type        = string
  default     = ""
}

variable "redis_port" {
  description = "ElastiCache Redis port"
  type        = number
  default     = 6379
}
