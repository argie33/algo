# ============================================================
# Step Functions Module - Variables
# ============================================================

variable "project_name" {
  description = "Project name for resource naming"
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

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "lambda_signal_worker_arn" {
  description = "ARN of Lambda signal worker function"
  type        = string
}

variable "lambda_signal_worker_name" {
  description = "Name of Lambda signal worker function"
  type        = string
}

variable "lambda_results_aggregator_arn" {
  description = "ARN of Lambda results aggregator function"
  type        = string
}

variable "execution_tracker_table_name" {
  description = "DynamoDB table name for execution tracking"
  type        = string
}

variable "execution_tracker_table_arn" {
  description = "DynamoDB table ARN for execution tracking"
  type        = string
}

variable "map_max_concurrency" {
  description = "Maximum concurrent executions in Map state (1-10000)"
  type        = number
  default     = 1000
  validation {
    condition     = var.map_max_concurrency >= 1 && var.map_max_concurrency <= 10000
    error_message = "Must be between 1 and 10000"
  }
}

variable "execution_schedule_enabled" {
  description = "Enable EventBridge schedule for Step Functions execution"
  type        = bool
  default     = false
}

variable "backfill_days" {
  description = "Number of days to backfill for signal computation"
  type        = number
  default     = 30
}

variable "dlq_arn" {
  description = "Dead Letter Queue ARN for failed executions"
  type        = string
  default     = ""
}

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default     = {}
}
