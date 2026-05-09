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
  description = "SNS topic ARN for alerts"
  type        = string
  default     = ""
}
