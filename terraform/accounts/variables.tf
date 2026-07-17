# ============================================================
# Account Creation Variables
# ============================================================

variable "new_account_email" {
  description = "Email address for new AWS account (edgebrookelabs)"
  type        = string
  default     = "edgebrookelabs@gmail.com"
}

variable "old_rds_instance_id" {
  description = "RDS instance ID to snapshot for migration"
  type        = string
  default     = "algo-db"
}

variable "old_account_id" {
  description = "Old AWS account ID (for cross-account access)"
  type        = string
  default     = "626216981288"
}

variable "create_account" {
  description = "Set to true to create the new account via Organizations"
  type        = bool
  default     = true
}

variable "snapshot_copy_to_new_account" {
  description = "Set to true to share the RDS snapshot with new account"
  type        = bool
  default     = true
}
