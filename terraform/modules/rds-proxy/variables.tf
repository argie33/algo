variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where RDS Proxy will be deployed"
  type        = string
}

variable "vpc_subnet_ids" {
  description = "Subnet IDs for RDS Proxy (must be in same VPC as RDS)"
  type        = list(string)
}

variable "rds_instance_id" {
  description = "RDS instance identifier to proxy"
  type        = string
}

variable "rds_security_group_id" {
  description = "Security group ID of RDS instance"
  type        = string
}

variable "lambda_security_group_id" {
  description = "Security group ID of Lambda functions (allowed to connect)"
  type        = string
}

variable "secrets_manager_secret_arn" {
  description = "ARN of Secrets Manager secret containing DB credentials"
  type        = string
}

variable "max_connections" {
  description = "Maximum number of database connections the proxy can maintain"
  type        = number
  default     = 100
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to connect to proxy (in addition to Lambda)"
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period in days"
  type        = number
  default     = 7
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for alarms (optional)"
  type        = string
  default     = null
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
