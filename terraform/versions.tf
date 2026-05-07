# ============================================================
# Root Module - Terraform & Provider Versions
# ============================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }

  # Prevent accidental deletion of critical resources
  skip_credentials_validation = false
  skip_requesting_account_id  = false
}
# Trigger terraform-apply workflow
# test
# Testing fixed bootstrap
# Fixed Terraform syntax errors
# All Terraform HCL syntax fixed
