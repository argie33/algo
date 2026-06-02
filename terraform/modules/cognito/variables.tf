variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Domain name for production environment"
  type        = string
  default     = "example.com"
}

variable "cloudfront_domain" {
  description = "CloudFront domain for OAuth callbacks (e.g., d2u93283nn45h2.cloudfront.net)"
  type        = string
  default     = ""
}

variable "cognito_test_user_email" {
  description = "Email for Cognito test user (empty = don't create test user)"
  type        = string
  default     = ""
}

variable "test_user_password" {
  description = "Temporary password for test user (dev only)"
  type        = string
  default     = "TempPassword123!"
  sensitive   = true
}

variable "cognito_custom_email_enabled" {
  description = "Enable custom message Lambda for Cognito emails (requires SES production access)"
  type        = bool
  default     = false
}

variable "cognito_sender_email" {
  description = "Sender email address for Cognito custom message Lambda (used for SES permission scoping)"
  type        = string
  default     = "noreply@bullseyetrading.com"
}

variable "admin_user_email" {
  description = "Email of the primary admin user to add to the 'admin' Cognito group (empty = skip)"
  type        = string
  default     = ""
}

variable "mfa_configuration" {
  description = "MFA configuration for the user pool: OFF, OPTIONAL, or REQUIRED"
  type        = string
  default     = "OPTIONAL"
  validation {
    condition     = contains(["OFF", "OPTIONAL", "REQUIRED"], var.mfa_configuration)
    error_message = "mfa_configuration must be OFF, OPTIONAL, or REQUIRED."
  }
}

variable "advanced_security_mode" {
  description = "Cognito Advanced Security mode: OFF, AUDIT, or ENFORCED. AUDIT and ENFORCED require Cognito+ plan (extra cost)."
  type        = string
  default     = "OFF"
  validation {
    condition     = contains(["OFF", "AUDIT", "ENFORCED"], var.advanced_security_mode)
    error_message = "advanced_security_mode must be OFF, AUDIT, or ENFORCED."
  }
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
