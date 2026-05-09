# ============================================================
# Bootstrap Module - Input Variables
# ============================================================

variable "aws_region" {
  description = "AWS region for bootstrap resources"
  type        = string
  default     = "us-east-1"
}

variable "terraform_state_bucket_name" {
  description = "S3 bucket name for Terraform state (must be globally unique)"
  type        = string
  default     = "stocks-terraform-state"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.terraform_state_bucket_name)) && length(var.terraform_state_bucket_name) >= 3 && length(var.terraform_state_bucket_name) <= 63
    error_message = "Bucket name must be 3-63 characters, lowercase letters, numbers, hyphens only (no leading/trailing hyphens)"
  }
}

variable "terraform_lock_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  type        = string
  default     = "stocks-terraform-locks"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_.-]+$", var.terraform_lock_table_name)) && length(var.terraform_lock_table_name) >= 3 && length(var.terraform_lock_table_name) <= 255
    error_message = "Table name must be 3-255 characters, letters, numbers, hyphens, underscores, periods only"
  }
}
