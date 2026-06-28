variable "enforce_iac_only" {
  description = "Enable IaC-only enforcement via SCPs"
  type        = bool
  default     = true
}

variable "require_terraform_tag" {
  description = "Require terraform:managed tag on all resources"
  type        = bool
  default     = true
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
