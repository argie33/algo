# ============================================================
# Bootstrap Module - One-Time Infrastructure Setup
# ============================================================
# This module creates the minimal infrastructure needed to run Terraform:
# - S3 backend bucket for state
# - DynamoDB table for state locking
# - GitHub OIDC provider for CI/CD authentication
#
# Usage (one-time):
#   cd terraform/bootstrap
#   terraform init
#   terraform apply
#   # Copy terraform.tfstate to safe location
#   # Then update root backend config with bucket/key from outputs

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# ============================================================
# S3 Bucket for Terraform State
# ============================================================

resource "aws_s3_bucket" "terraform_state" {
  bucket = var.terraform_state_bucket_name

  tags = {
    Name        = "Terraform State"
    Environment = "bootstrap"
    ManagedBy   = "Terraform"
  }
}

# Enable versioning for state protection
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ============================================================
# DynamoDB Table for State Locking
# ============================================================

resource "aws_dynamodb_table" "terraform_locks" {
  name           = var.terraform_lock_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name        = "Terraform Locks"
    Environment = "bootstrap"
    ManagedBy   = "Terraform"
  }
}

# ============================================================
# GitHub OIDC Provider for CI/CD
# ============================================================

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]

  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0ef0285805e27a516",  # backup thumbprint
  ]

  tags = {
    Name        = "GitHub Actions OIDC"
    Environment = "bootstrap"
    ManagedBy   = "Terraform"
  }
}

# ============================================================
# Outputs for Backend Configuration
# ============================================================
# Use these to configure root module backend.tf
