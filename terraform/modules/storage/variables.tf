# ============================================================
# Storage Module - Input Variables
# ============================================================

variable "project_name" {
  description = "Project name for naming convention"
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

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}

# ============================================================
# Bucket Lifecycle Configuration
# ============================================================

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

variable "log_archive_transition_ia_days" {
  description = "Days before transitioning logs to Standard-IA"
  type        = number
  default     = 30
}

variable "log_archive_transition_glacier_days" {
  description = "Days before transitioning logs to Glacier-IR"
  type        = number
  default     = 90
}

variable "log_archive_transition_deep_archive_days" {
  description = "Days before transitioning logs to Deep Archive"
  type        = number
  default     = 365
}

variable "log_archive_expiration_days" {
  description = "Days before deleting archived logs"
  type        = number
  default     = 2555 # ~7 years
}

# ============================================================
# Access & Encryption Configuration
# ============================================================

variable "enable_versioning" {
  description = "Enable S3 versioning on code and artifact buckets"
  type        = bool
  default     = true
}

variable "encryption_kms_key_id" {
  description = "KMS key ID for S3 encryption (if null, use AES256)"
  type        = string
  default     = null
}

variable "log_archive_intelligent_tiering_enabled" {
  description = "Enable Intelligent-Tiering on log archive bucket"
  type        = bool
  default     = true
}
