# ============================================================
# State Backend Module - Terraform State S3 + DynamoDB
# Manages tfstate bucket with full protection
# ============================================================

terraform {
  # State for the state backend itself is stored locally
  backend "local" {
    path = ".terraform/local-state/backend.tfstate"
  }
}

# ============================================================
# S3 Bucket for Terraform State
# ============================================================

resource "aws_s3_bucket" "terraform_state" {
  bucket              = var.state_bucket_name
  force_destroy       = false # CRITICAL: Never auto-destroy state bucket
  object_lock_enabled = false # Can enable if you want immutability

  tags = merge(var.common_tags, {
    Name          = "terraform-state"
    CriticalAsset = "true"
  })
}

# ============================================================
# Enable Versioning (Required for state protection)
# ============================================================

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status     = "Enabled"
    mfa_delete = "Disabled" # Set to Enabled if MFA protection desired
  }
}

# ============================================================
# Block All Public Access
# ============================================================

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Server-Side Encryption (AES-256)
# ============================================================

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ============================================================
# Bucket Policy - Least Privilege
# ============================================================

resource "aws_s3_bucket_policy" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.terraform_state.json
}

data "aws_iam_policy_document" "terraform_state" {
  # Deny deletion of bucket
  statement {
    sid    = "DenyDeleteBucket"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    actions = [
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutLifecycleConfiguration"
    ]
    resources = [aws_s3_bucket.terraform_state.arn]
  }

  # Deny unencrypted uploads
  statement {
    sid    = "DenyUnencryptedObjectUploads"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.terraform_state.arn}/*"]
    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["AES256"]
    }
  }

  # Deny deletion of state files (but allow overwrite/update)
  statement {
    sid    = "DenyDeleteStateFile"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    actions   = ["s3:DeleteObject"]
    resources = ["${aws_s3_bucket.terraform_state.arn}/*"]
    condition {
      string_like = {
        "s3:key" = "*/terraform.tfstate"
      }
    }
  }

  # Allow read/write for authorized accounts
  statement {
    sid    = "AllowTerraformStateAccess"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${var.aws_account_id}:root"]
    }
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketVersioning"
    ]
    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*"
    ]
  }
}

# ============================================================
# Lifecycle Policy - Prevent accidental deletion
# ============================================================

resource "aws_s3_bucket_lifecycle_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    id     = "RetainAllVersions"
    status = "Enabled"
    filter {}

    # Keep all current versions
    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_transition {
      noncurrent_days = 90
      storage_class   = "GLACIER_IR"
    }

    # Never delete, even old versions (manual cleanup only)
  }
}

# ============================================================
# CloudWatch Alarms for State Bucket
# ============================================================

resource "aws_cloudwatch_log_group" "s3_access" {
  name              = "/aws/s3/terraform-state-access"
  retention_in_days = 90

  tags = merge(var.common_tags, {
    Name = "terraform-state-access-logs"
  })
}

resource "aws_s3_bucket_logging" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  target_bucket = aws_s3_bucket.terraform_state.id
  target_prefix = "access-logs/"
}

# ============================================================
# DynamoDB Table for State Locking
# ============================================================

resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${var.state_bucket_name}-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  stream_specification {
    stream_view_type = "NEW_AND_OLD_IMAGES"
  }

  attribute {
    name = "LockID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(var.common_tags, {
    Name = "terraform-state-locks"
  })
}

# ============================================================
# CloudWatch Alarm for State Modifications
# ============================================================

resource "aws_cloudwatch_metric_alarm" "state_bucket_puts" {
  alarm_name          = "terraform-state-put-object-count"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "NumberOfObjects"
  namespace           = "AWS/S3"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alert on state file modifications"
  treat_missing_data  = "notBreaching"

  dimensions = {
    BucketName  = aws_s3_bucket.terraform_state.id
    StorageType = "AllStorageTypes"
  }

  tags = merge(var.common_tags, {
    Name = "terraform-state-modifications"
  })
}
