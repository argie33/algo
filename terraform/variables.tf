# Global AWS Configuration
variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
  sensitive   = true
}

# Project Configuration
variable "project_name" {
  description = "Project name for tagging and naming"
  type        = string
  default     = "stocks"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# GitHub Configuration
variable "github_org" {
  description = "GitHub organization"
  type        = string
  default     = "argeropolos"
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  default     = "algo"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# Database Configuration
variable "db_name" {
  description = "RDS database name"
  type        = string
  default     = "stocks"
}

variable "db_user" {
  description = "RDS master username"
  type        = string
  default     = "stocks"
}

variable "db_password" {
  description = "RDS master password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 100
}

# ECS Configuration
variable "ecs_instance_type" {
  description = "EC2 instance type for ECS cluster"
  type        = string
  default     = "t3.small"
}

variable "ecs_min_capacity" {
  description = "Minimum ECS cluster size"
  type        = number
  default     = 1
}

variable "ecs_max_capacity" {
  description = "Maximum ECS cluster size"
  type        = number
  default     = 3
}

# Lambda Configuration
variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 300
}

# Cognito Configuration
variable "cognito_callback_urls" {
  description = "Cognito callback URLs"
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "cognito_logout_urls" {
  description = "Cognito logout URLs"
  type        = list(string)
  default     = ["http://localhost:5173"]
}

# Email Configuration
variable "notification_email" {
  description = "Email for CloudWatch notifications"
  type        = string
  default     = "your-email@example.com"
}

# Enable/Disable Stacks
variable "deploy_bootstrap" {
  description = "Deploy OIDC bootstrap stack"
  type        = bool
  default     = true
}

variable "deploy_core" {
  description = "Deploy core infrastructure"
  type        = bool
  default     = true
}

variable "deploy_data_infrastructure" {
  description = "Deploy data infrastructure (RDS, ECS)"
  type        = bool
  default     = true
}

variable "deploy_loaders" {
  description = "Deploy loader tasks"
  type        = bool
  default     = true
}

variable "deploy_webapp" {
  description = "Deploy webapp (Lambda, CloudFront)"
  type        = bool
  default     = true
}

variable "deploy_algo" {
  description = "Deploy algo orchestrator"
  type        = bool
  default     = true
}

# Resource Control Flags
variable "create_ecr_repository" {
  description = "Whether to create ECR repository (set to false if already exists)"
  type        = bool
  default     = false
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
