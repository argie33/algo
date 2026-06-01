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

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
