# ============================================================
# Monitoring Module - Variables
# ============================================================

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
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
  description = "Common tags for all resources"
  type        = map(string)
}

# ============================================================
# API Gateway & Lambda Configuration
# ============================================================

variable "api_lambda_name" {
  description = "API Lambda function name"
  type        = string
}

variable "algo_lambda_name" {
  description = "Algo Lambda function name"
  type        = string
}

variable "api_gateway_name" {
  description = "API Gateway API name"
  type        = string
}

# ============================================================
# Database Configuration
# ============================================================

variable "rds_identifier" {
  description = "RDS DB instance identifier"
  type        = string
}

# ============================================================
# Alarm Configuration
# ============================================================

variable "apigw_5xx_alarm_name" {
  description = "CloudWatch alarm name for API Gateway 5xx errors"
  type        = string
}

variable "api_lambda_errors_alarm_name" {
  description = "CloudWatch alarm name for API Lambda errors"
  type        = string
}

variable "sns_alerts_enabled" {
  description = "Whether SNS alerts are enabled"
  type        = bool
  default     = true
}

variable "sns_alerts_topic_arn" {
  description = "SNS topic ARN for alerts (required when sns_alerts_enabled=true)"
  type        = string
  default     = ""
}

variable "alert_email_address" {
  description = "Email address for circuit breaker and monitoring alerts"
  type        = string
  default     = ""
}

# ============================================================
# Data Freshness Monitoring Configuration
# ============================================================

variable "enable_data_freshness_monitoring" {
  description = "Enable data freshness monitoring Lambda and alarms"
  type        = bool
  default     = true
}

variable "db_host" {
  description = "RDS database host"
  type        = string
}

variable "db_user" {
  description = "RDS database user"
  type        = string
}

variable "db_name" {
  description = "RDS database name"
  type        = string
}

variable "db_port" {
  description = "RDS database port"
  type        = string
  default     = "5432"
}

variable "db_password" {
  description = "RDS database password"
  type        = string
  sensitive   = true
}

variable "rds_proxy_endpoint" {
  description = "RDS Proxy endpoint for secure database connections"
  type        = string
  default     = ""
}

variable "database_secret_arn" {
  description = "ARN of AWS Secrets Manager secret containing database credentials"
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda VPC config"
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "RDS security group ID"
  type        = string
}

variable "python_dependencies_layer_arn" {
  description = "ARN of Lambda layer with Python dependencies (psycopg2, requests, etc.)"
  type        = string
  default     = ""
}

variable "eventbridge_scheduler_role_arn" {
  description = "IAM role ARN for EventBridge Scheduler to invoke Lambda"
  type        = string
  default     = ""
}

# ============================================================
# ECS Loader Monitoring Configuration
# ============================================================

variable "ecs_log_group_name" {
  description = "CloudWatch log group name for ECS loader tasks (optional, enables loader monitoring if set)"
  type        = string
  default     = ""
}

variable "ecs_cluster_arn" {
  description = "ARN of ECS cluster running loaders"
  type        = string
  default     = ""
}

variable "alert_email_to" {
  description = "Email address for SNS alert subscriptions"
  type        = string
  default     = ""
}
