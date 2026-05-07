# ============================================================
# Storage Module - S3 Buckets with Lifecycle Management
# ============================================================

# ============================================================
# 1. Code Bucket (versioned, 90-day expiration)
# ============================================================

resource "aws_s3_bucket" "code" {
  bucket = "${var.project_name}-code-${var.aws_account_id}"

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
      sse_algorithm = var.encryption_kms_key_id != null ? "aws:kms" : "AES256"
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

    expiration {
      days = var.code_bucket_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.code_bucket_expiration_days
    }
  }
}

# ============================================================
# 2. CloudFormation Templates Bucket (versioned)
# ============================================================

resource "aws_s3_bucket" "cf_templates" {
  bucket = "${var.project_name}-cf-templates-${var.aws_account_id}"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cf-templates-bucket"
  })
}

resource "aws_s3_bucket_versioning" "cf_templates" {
  bucket = aws_s3_bucket.cf_templates.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cf_templates" {
  bucket = aws_s3_bucket.cf_templates.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "cf_templates" {
  bucket                  = aws_s3_bucket.cf_templates.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# 3. Lambda Artifacts Bucket (versioned, 90-day expiration)
# ============================================================

resource "aws_s3_bucket" "lambda_artifacts" {
  bucket = "${var.project_name}-lambda-artifacts-${var.aws_account_id}"

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

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# ============================================================
# 4. Data Loading Bucket (30-day expiration)
# ============================================================

resource "aws_s3_bucket" "data_loading" {
  bucket = "${var.project_name}-data-loading-${var.aws_account_id}"

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

resource "aws_s3_bucket_lifecycle_configuration" "data_loading" {
  bucket = aws_s3_bucket.data_loading.id

  rule {
    id     = "DeleteOldData"
    status = "Enabled"

    expiration {
      days = var.data_bucket_expiration_days
    }
  }
}

# ============================================================
# 5. Log Archive Bucket (Intelligent-Tiering lifecycle)
# ============================================================

resource "aws_s3_bucket" "log_archive" {
  bucket = "${var.project_name}-log-archive-${var.aws_account_id}"

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
  bucket = "${var.project_name}-frontend-${var.aws_account_id}"

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
        Action   = "s3:*"
        Resource = [
          aws_s3_bucket.code.arn,
          "${aws_s3_bucket.code.arn}/*"
        ]
        Condition = {
          StringEquals = {
            "aws:SourceVpce" = "*"
          }
        }
      }
    ]
  })
}
