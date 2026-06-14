# ============================================================
# Security Monitoring Module - Phase 1: AWS Infrastructure
# ============================================================
# CloudTrail + GuardDuty + AWS Config + VPC Flow Logs

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

# ============================================================
# Data Sources
# ============================================================

data "aws_caller_identity" "current" {}

# ============================================================
# S3 Bucket for CloudTrail Logs
# ============================================================

resource "aws_s3_bucket" "cloudtrail_logs" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = "${var.project_name}-cloudtrail-logs-${var.aws_region}-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cloudtrail-logs"
  })
}

resource "aws_s3_bucket_versioning" "cloudtrail_logs" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail_logs" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "cloudtrail_logs" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudTrail S3 Bucket Policy
resource "aws_s3_bucket_policy" "cloudtrail_logs" {
  count  = var.cloudtrail_enabled ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail_logs[0].arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_logs[0].arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# ============================================================
# CloudTrail - Audit Logging
# ============================================================

resource "aws_cloudtrail" "main" {
  count                      = var.cloudtrail_enabled ? 1 : 0
  name                       = "${var.project_name}-trail-${var.environment}"
  s3_bucket_name             = aws_s3_bucket.cloudtrail_logs[0].id
  depends_on                 = [aws_s3_bucket_policy.cloudtrail_logs]
  is_multi_region_trail      = true
  enable_log_file_validation = true
  event_selector {
    read_write_type           = "All"
    include_management_events = true
    data_resource {
      type   = "AWS::S3::Object"
      values = ["arn:aws:s3:::${var.project_name}-*/*"]
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cloudtrail"
  })
}

# ============================================================
# GuardDuty - Threat Detection
# ============================================================

resource "aws_guardduty_detector" "main" {
  count                        = var.guardduty_enabled ? 1 : 0
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-guardduty"
  })
}

resource "aws_guardduty_detector_feature" "s3_logs" {
  count       = var.guardduty_enabled ? 1 : 0
  detector_id = aws_guardduty_detector.main[0].id
  name        = "S3_DATA_EVENTS"
  status      = "ENABLED"
}

resource "aws_guardduty_detector_feature" "k8s_logs" {
  count       = var.guardduty_enabled ? 1 : 0
  detector_id = aws_guardduty_detector.main[0].id
  name        = "EKS_AUDIT_LOGS"
  status      = "ENABLED"
}

# ============================================================
# AWS Config - Compliance Monitoring
# ============================================================

resource "aws_config_configuration_recorder" "main" {
  count      = var.aws_config_enabled ? 1 : 0
  name       = "${var.project_name}-config-recorder"
  role_arn   = aws_iam_role.config_role[0].arn
  depends_on = [aws_iam_role_policy.config_policy]

  recording_group {
    all_supported = true
  }
}

resource "aws_config_configuration_recorder_status" "main" {
  count      = var.aws_config_enabled ? 1 : 0
  name       = aws_config_configuration_recorder.main[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.main, aws_config_configuration_recorder.main]
}

resource "aws_config_delivery_channel" "main" {
  count          = var.aws_config_enabled ? 1 : 0
  name           = "${var.project_name}-config-channel"
  s3_bucket_name = aws_s3_bucket.config_bucket[0].id
  depends_on     = [aws_config_configuration_recorder.main, aws_iam_role_policy.config_policy]
}

# Config S3 Bucket
resource "aws_s3_bucket" "config_bucket" {
  count          = var.aws_config_enabled ? 1 : 0
  bucket         = "${var.project_name}-config-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy  = true

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-config-bucket"
  })
}

resource "aws_s3_bucket_versioning" "config_bucket" {
  count  = var.aws_config_enabled ? 1 : 0
  bucket = aws_s3_bucket.config_bucket[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "config_bucket" {
  count  = var.aws_config_enabled ? 1 : 0
  bucket = aws_s3_bucket.config_bucket[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Config Rules
resource "aws_config_config_rule" "rds_encryption" {
  count       = var.aws_config_enabled ? 1 : 0
  name        = "${var.project_name}-rds-encryption-enabled"
  description = "Checks that RDS instances have encryption enabled"
  depends_on  = [aws_config_configuration_recorder_status.main]

  source {
    owner             = "AWS"
    source_identifier = "RDS_STORAGE_ENCRYPTED"
  }
}

resource "aws_config_config_rule" "s3_public_access" {
  count       = var.aws_config_enabled ? 1 : 0
  name        = "${var.project_name}-s3-public-access-blocked"
  description = "Checks that S3 buckets block public access"
  depends_on  = [aws_config_configuration_recorder_status.main]

  source {
    owner             = "AWS"
    source_identifier = "S3_BUCKET_PUBLIC_READ_PROHIBITED"
  }
}

resource "aws_config_config_rule" "lambda_vpc" {
  count       = var.aws_config_enabled ? 1 : 0
  name        = "${var.project_name}-lambda-in-vpc"
  description = "Checks that Lambda functions are in a VPC"
  depends_on  = [aws_config_configuration_recorder_status.main]

  source {
    owner             = "AWS"
    source_identifier = "LAMBDA_FUNCTION_PUBLIC_ACCESS_PROHIBITED"
  }
}

# ============================================================
# VPC Flow Logs
# ============================================================

resource "aws_flow_log" "main" {
  count           = var.vpc_flow_logs_enabled ? 1 : 0
  iam_role_arn    = aws_iam_role.vpc_flow_logs[0].arn
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs[0].arn
  traffic_type    = "ALL"
  vpc_id          = var.vpc_id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc-flow-logs"
  })
}

resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  count             = var.vpc_flow_logs_enabled ? 1 : 0
  name              = "/aws/vpc/flowlogs/${var.project_name}-${var.environment}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc-flow-logs"
  })
}

# ============================================================
# IAM Roles for Security Services
# ============================================================

resource "aws_iam_role" "config_role" {
  count = var.aws_config_enabled ? 1 : 0
  name  = "${var.project_name}-config-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "config_policy" {
  count = var.aws_config_enabled ? 1 : 0
  name  = "${var.project_name}-config-policy"
  role  = aws_iam_role.config_role[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketVersioning",
          "s3:PutObject",
          "s3:GetObject",
          "s3:GetBucketAcl"
        ]
        Resource = [
          aws_s3_bucket.config_bucket[0].arn,
          "${aws_s3_bucket.config_bucket[0].arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "config:PutConfigurationRecorder",
          "config:DescribeConfigurationRecorders",
          "config:StartConfigurationRecorder",
          "config:StopConfigurationRecorder",
          "config:GetComplianceDetailsByConfigRule",
          "config:DescribeComplianceByConfigRule"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "vpc_flow_logs" {
  count = var.vpc_flow_logs_enabled ? 1 : 0
  name  = "${var.project_name}-vpc-flow-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "vpc_flow_logs" {
  count = var.vpc_flow_logs_enabled ? 1 : 0
  name  = "${var.project_name}-vpc-flow-logs-policy"
  role  = aws_iam_role.vpc_flow_logs[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.vpc_flow_logs[0].arn}:*"
      }
    ]
  })
}
