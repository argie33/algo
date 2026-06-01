variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev/prod)"
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

variable "ecs_cluster_arn" {
  description = "ARN of the ECS cluster where loader tasks run"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Fargate task networking"
  type        = list(string)
}

variable "ecs_tasks_sg_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "task_execution_role_arn" {
  description = "ECS task execution role ARN (for Step Functions PassRole)"
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (for Step Functions PassRole)"
  type        = string
}

variable "eventbridge_scheduler_role_arn" {
  description = "EventBridge Scheduler role ARN (for executing Step Functions state machines)"
  type        = string
}

variable "loader_task_definition_arns" {
  description = "Map of loader name → task definition ARN (from loaders module output)"
  type        = map(string)
}

variable "algo_orchestrator_task_definition_arn" {
  description = "ARN of the algo orchestrator ECS task definition (from loaders module output)"
  type        = string
}

variable "algo_orchestrator_container_name" {
  description = "Container name within the algo orchestrator task definition"
  type        = string
  default     = "algo-orchestrator" # Will be: project_name-algo-orchestrator
}

variable "orchestrator_locks_table_name" {
  description = "Name of the DynamoDB table for distributed orchestrator locking"
  type        = string
}

variable "sns_alert_topic_arn" {
  description = "SNS topic ARN for pipeline failure alerts"
  type        = string
  default     = ""
  validation {
    condition     = var.sns_alert_topic_arn == "" || can(regex("^arn:aws:sns:", var.sns_alert_topic_arn))
    error_message = "sns_alert_topic_arn must be a valid SNS ARN (arn:aws:sns:...) or empty string."
  }
}

variable "sns_alerts_enabled" {
  description = "Enable SNS alerts for pipeline failures"
  type        = bool
  default     = false
}

variable "common_tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch log retention for Step Functions"
  type        = number
  default     = 30
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

variable "loader_failure_handler_arn" {
  description = "ARN of the Lambda function for handling loader failures (from services module)"
  type        = string
  default     = ""
}

# Database configuration variables (needed for Step Functions container overrides)
variable "db_host" {
  description = "Database host (RDS endpoint or RDS Proxy endpoint)"
  type        = string
}

variable "db_port" {
  description = "Database port"
  type        = number
  default     = 5432
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "stocks"
}

variable "orchestrator_log_level" {
  description = "Log level for orchestrator"
  type        = string
  default     = "INFO"
}

variable "alpaca_paper_trading" {
  description = "Whether to use Alpaca paper trading mode"
  type        = bool
  default     = true
}

variable "ecs_log_group_name" {
  description = "CloudWatch log group name for ECS loader tasks (for monitoring)"
  type        = string
  default     = ""
}
