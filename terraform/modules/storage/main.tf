# ============================================================
# Storage Module - S3 Buckets with Lifecycle Management
# ============================================================

# ============================================================
# 1. Code Bucket (versioned, 90-day expiration)
# ============================================================

resource "aws_s3_bucket" "code" {
  bucket        = "${var.project_name}-code-${var.aws_account_id}"
  force_destroy = false # CRITICAL: Never auto-destroy buckets. Prevents accidental data loss.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-code-bucket"
  })
}

resource "aws_s3_bucket_versioning" "code" {
  bucket = aws_s3_bucket.code.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "code" {
  bucket = aws_s3_bucket.code.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.encryption_kms_key_id != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.encryption_kms_key_id != null ? "arn:aws:kms:${var.aws_region}:${var.aws_account_id}:key/${var.encryption_kms_key_id}" : null
    }
  }
}

resource "aws_s3_bucket_public_access_block" "code" {
  bucket                  = aws_s3_bucket.code.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "code" {
  bucket = aws_s3_bucket.code.id

  rule {
    id     = "DeleteOldArtifacts"
    status = "Enabled"
    filter {}

    expiration {
      days = var.code_bucket_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.code_bucket_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "DeleteExpiredMarkers"
    status = "Enabled"
    filter {}

    expiration {
      expired_object_delete_marker = true
    }
  }
}

# ============================================================
# 2. Lambda Artifacts Bucket (versioned, 90-day expiration)
# ============================================================

resource "aws_s3_bucket" "lambda_artifacts" {
  bucket        = "${var.project_name}-lambda-artifacts-${var.aws_account_id}"
  force_destroy = false # CRITICAL: Never auto-destroy buckets. Prevents accidental data loss.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-lambda-artifacts-bucket"
  })
}

resource "aws_s3_bucket_versioning" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lambda_artifacts" {
  bucket                  = aws_s3_bucket.lambda_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "lambda_artifacts" {
  bucket = aws_s3_bucket.lambda_artifacts.id

  rule {
    id     = "DeleteOldArtifacts"
    status = "Enabled"
    filter {}

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "DeleteExpiredMarkers"
    status = "Enabled"
    filter {}

    expiration {
      expired_object_delete_marker = true
    }
  }
}

# ============================================================
# 3. Data Loading Bucket (30-day expiration)
# ============================================================

resource "aws_s3_bucket" "data_loading" {
  bucket        = "${var.project_name}-data-loading-${var.aws_account_id}"
  force_destroy = false # CRITICAL: Never auto-destroy buckets. Prevents accidental data loss.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-data-loading-bucket"
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_loading" {
  bucket = aws_s3_bucket.data_loading.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_loading" {
  bucket                  = aws_s3_bucket.data_loading.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data_loading" {
  bucket = aws_s3_bucket.data_loading.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data_loading" {
  bucket = aws_s3_bucket.data_loading.id

  rule {
    id     = "DeleteOldData"
    status = "Enabled"
    filter {}

    expiration {
      days = var.data_bucket_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "DeleteExpiredMarkers"
    status = "Enabled"
    filter {}

    expiration {
      expired_object_delete_marker = true
    }
  }
}

# ============================================================
# 5. Log Archive Bucket (Intelligent-Tiering lifecycle)
# ============================================================

resource "aws_s3_bucket" "log_archive" {
  bucket        = "${var.project_name}-log-archive-${var.aws_account_id}"
  force_destroy = false # CRITICAL: Never auto-destroy buckets. Prevents accidental data loss.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-log-archive-bucket"
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "log_archive" {
  bucket                  = aws_s3_bucket.log_archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

# Intelligent-Tiering (auto cost optimization)
resource "aws_s3_bucket_intelligent_tiering_configuration" "log_archive" {
  count  = var.log_archive_intelligent_tiering_enabled ? 1 : 0
  bucket = aws_s3_bucket.log_archive.id
  name   = "LogArchiveAutoTier"
  status = "Enabled"

  tiering {
    access_tier = "ARCHIVE_ACCESS"
    days        = 90
  }

  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180
  }
}

# Lifecycle: transition to cheaper storage tiers
resource "aws_s3_bucket_lifecycle_configuration" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  rule {
    id     = "TransitionToGlacier"
    status = "Enabled"
    filter {}

    transition {
      days          = var.log_archive_transition_ia_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.log_archive_transition_glacier_days
      storage_class = "GLACIER_IR"
    }

    transition {
      days          = var.log_archive_transition_deep_archive_days
      storage_class = "DEEP_ARCHIVE"
    }

    expiration {
      days = var.log_archive_expiration_days
    }
  }
}

# ============================================================
# 6. Frontend Bucket (webapp static assets)
# ============================================================

resource "aws_s3_bucket" "frontend" {
  bucket        = "${var.project_name}-frontend-${var.aws_account_id}"
  force_destroy = false # CRITICAL: Never auto-destroy buckets. Prevents accidental data loss.

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-frontend-bucket"
  })
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Bucket Policies - Allow VPC Endpoints only (for code bucket)
# ============================================================

resource "aws_s3_bucket_policy" "code_vpc_endpoint_only" {
  bucket = aws_s3_bucket.code.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowVPCEndpointAccess"
        Effect = "Allow"
        Principal = {
          AWS = "*"
        }
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.code.arn,
          "${aws_s3_bucket.code.arn}/*"
        ]
        Condition = {
          StringEquals = {
            "aws:PrincipalAccount" = var.aws_account_id
          }
        }
      },
      {
        Sid       = "DenyUnencryptedObjectUploads"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.code.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = var.enforce_kms_encryption ? "aws:kms" : "AES256"
          }
        }
      }
    ]
  })
}
