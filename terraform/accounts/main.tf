# ============================================================
# AWS Organizations - Account Creation for edgebrookelabs
# ============================================================
# This module creates a new AWS account within the organization
# and sets up cross-account access for infrastructure deployment

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Root account provider (for Organizations)
provider "aws" {
  alias = "root"
  # Uses AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from environment
  # or configured in ~/.aws/credentials [root] profile
  region = "us-east-1"
}

# New account provider (assumes cross-account role after creation)
provider "aws" {
  alias = "new_account"
  region = "us-east-1"

  assume_role {
    role_arn = aws_iam_role.cross_account_deployment.arn
  }

  depends_on = [
    aws_organizations_account.edgebrookelabs,
    aws_iam_role.cross_account_deployment
  ]
}

# ============================================================
# 1. CREATE NEW AWS ACCOUNT
# ============================================================

resource "aws_organizations_account" "edgebrookelabs" {
  provider  = aws.root
  email     = var.new_account_email
  account_name = "EdgeBrook Labs (Production)"

  tags = {
    Purpose       = "Production - Stock Trading Algorithm"
    MigratedFrom  = "626216981288"
    CreatedBy     = "Terraform"
    CreatedDate   = timestamp()
  }

  depends_on = [
    data.aws_organizations_organization.root
  ]
}

data "aws_organizations_organization" "root" {
  provider = aws.root
}

output "new_account_id" {
  description = "New AWS account ID (edgebrookelabs)"
  value       = aws_organizations_account.edgebrookelabs.id
}

output "new_account_email" {
  description = "New AWS account email"
  value       = aws_organizations_account.edgebrookelabs.email
}

# ============================================================
# 2. CROSS-ACCOUNT DEPLOYMENT ROLE
# ============================================================
# Allows terraform to deploy infrastructure in the new account

resource "aws_iam_role" "cross_account_deployment" {
  provider = aws.root
  name     = "TerraformCrossAccountDeploymentRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::626216981288:root"  # Old account can assume this role
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "terraform-cross-account-role"
  }
}

# Grant admin access for deployment
resource "aws_iam_role_policy_attachment" "cross_account_admin" {
  provider       = aws.root
  role           = aws_iam_role.cross_account_deployment.name
  policy_arn     = "arn:aws:iam::aws:policy/AdministratorAccess"
}

output "cross_account_role_arn" {
  description = "Cross-account role ARN for new account"
  value       = aws_iam_role.cross_account_deployment.arn
}

# ============================================================
# 3. RDS SNAPSHOT SHARING
# ============================================================
# Share the current RDS snapshot with the new account

resource "aws_db_snapshot_attribute" "share_rds_snapshot" {
  provider               = aws.root
  db_snapshot_identifier = aws_db_snapshot.final_backup.id
  attribute_name         = "restore"
  values                 = [aws_organizations_account.edgebrookelabs.id]
}

resource "aws_db_snapshot" "final_backup" {
  provider               = aws.root
  db_instance_identifier = var.old_rds_instance_id
  db_snapshot_identifier = "algo-db-migration-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  tags = {
    Purpose = "Migration to new account"
  }

  skip_final_snapshot = false

  depends_on = [
    aws_organizations_account.edgebrookelabs
  ]
}

output "rds_snapshot_id" {
  description = "RDS snapshot ID for migration"
  value       = aws_db_snapshot.final_backup.id
}

# ============================================================
# 4. TERRAFORM STATE FOR NEW ACCOUNT
# ============================================================
# Create S3 bucket + DynamoDB table for new account's terraform state

resource "aws_s3_bucket" "new_account_terraform_state" {
  provider = aws.new_account
  bucket   = "algo-terraform-state-${aws_organizations_account.edgebrookelabs.id}"

  tags = {
    Name = "Terraform State - New Account"
  }

  depends_on = [
    aws_iam_role.cross_account_deployment
  ]
}

resource "aws_s3_bucket_versioning" "new_account_state_versioning" {
  provider = aws.new_account
  bucket   = aws_s3_bucket.new_account_terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "new_account_state_encryption" {
  provider = aws.new_account
  bucket   = aws_s3_bucket.new_account_terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "new_account_lock_table" {
  provider       = aws.new_account
  name           = "algo-terraform-locks"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name = "Terraform Locks - New Account"
  }

  depends_on = [
    aws_iam_role.cross_account_deployment
  ]
}

output "new_account_terraform_state_bucket" {
  description = "S3 bucket for new account terraform state"
  value       = aws_s3_bucket.new_account_terraform_state.id
}

output "new_account_lock_table" {
  description = "DynamoDB table for terraform locks"
  value       = aws_dynamodb_table.new_account_lock_table.name
}
