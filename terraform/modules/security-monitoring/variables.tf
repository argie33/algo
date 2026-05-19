variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_id" {
  description = "VPC ID where security resources will be deployed"
  type        = string
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}

variable "cloudtrail_enabled" {
  description = "Enable CloudTrail for audit logging"
  type        = bool
  default     = true
}

variable "guardduty_enabled" {
  description = "Enable GuardDuty for threat detection"
  type        = bool
  default     = true
}

variable "aws_config_enabled" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "vpc_flow_logs_enabled" {
  description = "Enable VPC Flow Logs for network monitoring"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 90
}

variable "notification_email" {
  description = "Email for security notifications"
  type        = string
  default     = ""
}
