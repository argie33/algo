# ============================================================
# VPC Module - Input Variables
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

# ============================================================
# Network Configuration
# ============================================================

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid IPv4 CIDR block"
  }
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) >= 2
    error_message = "Must provide at least 2 public subnet CIDR blocks (one per AZ)"
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]

  validation {
    condition     = length(var.private_subnet_cidrs) >= 2
    error_message = "Must provide at least 2 private subnet CIDR blocks (one per AZ)"
  }
}

variable "availability_zones" {
  description = "List of availability zones in region"
  type        = list(string)
}

# ============================================================
# Security & Access Configuration
# ============================================================

variable "bastion_sg_enabled" {
  description = "Whether to create bastion security group"
  type        = bool
  default     = true
}

variable "common_tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
}
