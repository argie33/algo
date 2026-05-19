# AWS Phase 1 Implementation: Critical Security Fixes
**Estimated Time:** 4-6 hours  
**Target Date:** Today (May 19, 2026)  
**Outcome:** Production-ready security posture

---

## Overview

This guide provides step-by-step Terraform code to deploy 4 critical security enhancements:
1. CloudTrail (audit trail for all API calls)
2. GuardDuty (threat detection)
3. AWS Config (compliance monitoring)
4. VPC Flow Logs (network monitoring)

---

## Step 1: Create Security Module

Create a new module to house security services:

```bash
mkdir -p terraform/modules/security
```

### File: `terraform/modules/security/main.tf`

```hcl
# ============================================================
# Security Module - CloudTrail, GuardDuty, Config, VPC Flow Logs
# ============================================================

# ============================================================
# 1. S3 Bucket for CloudTrail Logs
# ============================================================

resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket = "${var.project_name}-cloudtrail-logs-${var.environment}"
  
  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cloudtrail-logs"
  })
}

resource "aws_s3_bucket_versioning" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    id     = "archive-old-logs"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365  # Delete after 1 year
    }
  }
}

# ============================================================
# 2. CloudTrail Configuration
# ============================================================

resource "aws_cloudtrail" "main" {
  name                          = "${var.project_name}-trail-${var.environment}"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_cloudwatch.arn

  depends_on = [aws_s3_bucket_policy.cloudtrail_logs]

  tags = var.common_tags
}

# CloudTrail S3 bucket policy
resource "aws_s3_bucket_policy" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

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
        Resource = aws_s3_bucket.cloudtrail_logs.arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_logs.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# CloudWatch Log Group for CloudTrail
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/${var.project_name}-${var.environment}"
  retention_in_days = 30
  kms_key_id        = var.enable_kms_encryption ? aws_kms_key.cloudtrail[0].arn : null

  tags = var.common_tags
}

# KMS Key for CloudTrail logs (optional)
resource "aws_kms_key" "cloudtrail" {
  count                   = var.enable_kms_encryption ? 1 : 0
  description             = "KMS key for CloudTrail logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = var.common_tags
}

# IAM role for CloudTrail to write to CloudWatch Logs
resource "aws_iam_role" "cloudtrail_cloudwatch" {
  name = "${var.project_name}-cloudtrail-cloudwatch-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "cloudtrail_cloudwatch" {
  name = "${var.project_name}-cloudtrail-cloudwatch-policy"
  role = aws_iam_role.cloudtrail_cloudwatch.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
      }
    ]
  })
}

# ============================================================
# 3. GuardDuty Configuration
# ============================================================

resource "aws_guardduty_detector" "main" {
  enable = true

  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs {
        enable = true
      }
    }
  }

  tags = var.common_tags
}

# CloudWatch Event Rule for GuardDuty Findings
resource "aws_cloudwatch_event_rule" "guardduty_high_findings" {
  name        = "${var.project_name}-guardduty-high-findings"
  description = "Alert on high-severity GuardDuty findings"

  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      severity = [7, 7.0, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 8, 8.0, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9]
    }
  })

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "guardduty_sns" {
  rule      = aws_cloudwatch_event_rule.guardduty_high_findings.name
  target_id = "GuardDutySNS"
  arn       = var.sns_alerts_topic_arn

  input_transformer {
    input_paths = {
      finding   = "$.detail.finding"
      severity  = "$.detail.severity"
      accountId = "$.detail.accountId"
      region    = "$.detail.region"
    }
    input_template = jsonencode({
      default = "GuardDuty Finding in ${accountId} (${region}): ${finding} [Severity: ${severity}]"
    })
  }
}

# ============================================================
# 4. AWS Config Configuration
# ============================================================

# Config S3 bucket for storing snapshots
resource "aws_s3_bucket" "aws_config" {
  bucket = "${var.project_name}-aws-config-${var.environment}"

  tags = var.common_tags
}

resource "aws_s3_bucket_public_access_block" "aws_config" {
  bucket = aws_s3_bucket.aws_config.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "aws_config" {
  bucket = aws_s3_bucket.aws_config.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Config Recorder
resource "aws_config_configuration_recorder" "main" {
  name       = "${var.project_name}-recorder-${var.environment}"
  role_arn   = aws_iam_role.config_recorder.arn
  depends_on = [aws_iam_role_policy.config_recorder]

  recording_group {
    all_supported = true
    include_global_resources = true
  }

  depends_on = [aws_s3_bucket.aws_config]
}

resource "aws_config_configuration_recorder_status" "main" {
  name       = aws_config_configuration_recorder.main.name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.main]

  depends_on = [aws_s3_bucket_policy.aws_config]
}

# Config Delivery Channel
resource "aws_config_delivery_channel" "main" {
  name           = "${var.project_name}-channel-${var.environment}"
  s3_bucket_name = aws_s3_bucket.aws_config.id
  depends_on     = [aws_config_configuration_recorder.main]

  sns_topic_arn = var.sns_alerts_topic_arn

  depends_on = [aws_config_configuration_recorder.main]
}

# IAM role for Config
resource "aws_iam_role" "config_recorder" {
  name = "${var.project_name}-config-recorder-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "config_recorder" {
  role       = aws_iam_role.config_recorder.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/ConfigRole"
}

resource "aws_iam_role_policy" "config_recorder" {
  name = "${var.project_name}-config-recorder-policy"
  role = aws_iam_role.config_recorder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetBucketVersioning",
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = [
          aws_s3_bucket.aws_config.arn,
          "${aws_s3_bucket.aws_config.arn}/*"
        ]
      }
    ]
  })
}

# Config Rules - Essential Compliance Checks
resource "aws_config_config_rule" "rds_encryption" {
  name = "${var.project_name}-rds-encryption-enabled"

  source {
    owner             = "AWS"
    source_identifier = "RDS_STORAGE_ENCRYPTED"
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}

resource "aws_config_config_rule" "s3_public_access_block" {
  name = "${var.project_name}-s3-public-access-block-enabled"

  source {
    owner             = "AWS"
    source_identifier = "S3_ACCOUNT_LEVEL_PUBLIC_ACCESS_BLOCKS"
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}

resource "aws_config_config_rule" "lambda_in_vpc" {
  name = "${var.project_name}-lambda-in-vpc"

  source {
    owner             = "AWS"
    source_identifier = "LAMBDA_INSIDE_VPC"
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}

resource "aws_config_config_rule" "cloudtrail_enabled" {
  name = "${var.project_name}-cloudtrail-enabled"

  source {
    owner             = "AWS"
    source_identifier = "CLOUD_TRAIL_ENABLED"
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}

resource "aws_config_config_rule" "ec2_encrypted_volumes" {
  name = "${var.project_name}-ec2-encrypted-volumes"

  source {
    owner             = "AWS"
    source_identifier = "ENCRYPTED_VOLUMES"
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}

# S3 bucket policy for Config
resource "aws_s3_bucket_policy" "aws_config" {
  bucket = aws_s3_bucket.aws_config.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSConfigBucketPermissionsCheck"
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action   = "s3:GetBucketVersioning"
        Resource = aws_s3_bucket.aws_config.arn
      },
      {
        Sid    = "AWSConfigBucketDelivery"
        Effect = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.aws_config.arn}/*"
      }
    ]
  })
}

# ============================================================
# 5. VPC Flow Logs
# ============================================================

resource "aws_flow_log" "vpc" {
  iam_role_arn    = aws_iam_role.vpc_flow_logs.arn
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = var.vpc_id

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-vpc-flow-logs"
  })
}

resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = "/aws/vpc/flowlogs/${var.project_name}-${var.environment}"
  retention_in_days = 7

  tags = var.common_tags
}

resource "aws_iam_role" "vpc_flow_logs" {
  name = "${var.project_name}-vpc-flow-logs-${var.environment}"

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
  name = "${var.project_name}-vpc-flow-logs-policy"
  role = aws_iam_role.vpc_flow_logs.id

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
        Resource = "${aws_cloudwatch_log_group.vpc_flow_logs.arn}:*"
      }
    ]
  })
}

# CloudWatch Metric Filter for detecting rejected connections
resource "aws_cloudwatch_log_metric_filter" "rejected_connections" {
  name           = "${var.project_name}-rejected-connections"
  log_group_name = aws_cloudwatch_log_group.vpc_flow_logs.name
  filter_pattern = "[version, account, eni, source, destination, srcport, destport, protocol, packets, bytes, windowstart, windowend, action=\"REJECT\", flowlogstatus]"

  metric_transformation {
    name      = "RejectedConnections"
    namespace = "${var.project_name}/VPC"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "rejected_connections" {
  alarm_name          = "${var.project_name}-rejected-connections-alarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "RejectedConnections"
  namespace           = "${var.project_name}/VPC"
  period              = 300
  statistic           = "Sum"
  threshold           = 10

  alarm_actions = [var.sns_alerts_topic_arn]

  tags = var.common_tags
}
```

### File: `terraform/modules/security/variables.tf`

```hcl
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for VPC Flow Logs"
  type        = string
}

variable "sns_alerts_topic_arn" {
  description = "SNS topic ARN for alerts"
  type        = string
}

variable "enable_kms_encryption" {
  description = "Enable KMS encryption for logs"
  type        = bool
  default     = false
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
}
```

### File: `terraform/modules/security/outputs.tf`

```hcl
output "cloudtrail_bucket_name" {
  value = aws_s3_bucket.cloudtrail_logs.id
}

output "config_bucket_name" {
  value = aws_s3_bucket.aws_config.id
}

output "guardduty_detector_id" {
  value = aws_guardduty_detector.main.id
}

output "cloudtrail_arn" {
  value = aws_cloudtrail.main.arn
}

output "vpc_flow_logs_log_group" {
  value = aws_cloudwatch_log_group.vpc_flow_logs.name
}
```

---

## Step 2: Update Root Terraform to Include Security Module

### File: `terraform/main.tf` (add this module call)

```hcl
module "security" {
  source = "./modules/security"

  project_name          = var.project_name
  environment           = var.environment
  vpc_id                = module.vpc.vpc_id
  sns_alerts_topic_arn  = module.services.sns_alerts_topic_arn
  enable_kms_encryption = var.environment == "prod"
  common_tags           = local.common_tags
}
```

---

## Step 3: Deploy

```bash
cd terraform

# Initialize the new module
terraform init

# Plan changes
terraform plan -target=module.security

# Apply (if plan looks good)
terraform apply -target=module.security

# Verify all resources created
terraform show | grep -E "aws_cloudtrail|aws_guardduty|aws_config|aws_flow_log"
```

---

## Step 4: Verification Checklist

After deployment, verify each component:

### CloudTrail
```bash
# Check if trail is enabled
aws cloudtrail describe-trails \
  --region $(aws configure get region) \
  | jq '.trailList[] | {Name: .Name, IsMultiRegionTrail: .IsMultiRegionTrail, S3BucketName: .S3BucketName}'

# Verify logs are being delivered
aws s3 ls s3://your-cloudtrail-bucket/ --recursive
```

### GuardDuty
```bash
# Check detector status
aws guardduty list-detectors | jq '.DetectorIds'

# Get detector details
aws guardduty get-detector --detector-id <DETECTOR_ID>
```

### AWS Config
```bash
# Check recorder status
aws configservice describe-configuration-recorder-status

# List compliance rules
aws configservice describe-config-rules | jq '.ConfigRules[] | {ConfigRuleName: .ConfigRuleName, ConfigRuleState: .ConfigRuleState}'

# Check rule compliance
aws configservice describe-compliance-by-config-rule | jq '.ComplianceByConfigRules[] | {ConfigRuleName: .ConfigRuleName, Compliance: .Compliance.ComplianceType}'
```

### VPC Flow Logs
```bash
# Verify flow logs are active
aws ec2 describe-flow-logs | jq '.FlowLogs[] | {FlowLogId: .FlowLogId, ResourceId: .ResourceId, FlowLogStatus: .FlowLogStatus}'

# Check log group
aws logs describe-log-groups | grep vpc-flowlogs
```

---

## Step 5: Monitor & Alert

### Create dashboard for security metrics

```hcl
resource "aws_cloudwatch_dashboard" "security" {
  dashboard_name = "${var.project_name}-security-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/CloudTrail", "DataEvents", { stat = "Sum" }],
            [".", "APICallsOverTime", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "CloudTrail Events"
        }
      },
      {
        type = "log"
        properties = {
          query = "fields @timestamp, @message | stats count() as findings by @message"
          region = var.aws_region
          title  = "GuardDuty Findings"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Config", "ComplianceScore", { stat = "Average" }]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "AWS Config Compliance Score"
        }
      }
    ]
  })
}
```

---

## Expected Outcomes After Phase 1

✅ **CloudTrail:**
- All API calls logged to S3 with integrity validation
- Query logs searchable in CloudWatch
- 1-year retention in S3 (90 days hot, 270 days cold storage)

✅ **GuardDuty:**
- Threat detection enabled (malware, unauthorized access, etc.)
- High-severity findings alert to SNS (your email/Slack)
- S3 data source monitoring enabled

✅ **AWS Config:**
- Continuous configuration monitoring
- 5 compliance rules deployed (RDS encryption, S3 public access, Lambda VPC, CloudTrail, EC2 encryption)
- Remediation ready for drift detection

✅ **VPC Flow Logs:**
- Network traffic monitoring
- Alert on rejected connections (suspicious activity detection)
- 7-day retention for forensics

---

## Total Cost After Phase 1

- **CloudTrail:** ~$2/month
- **GuardDuty:** ~$3/month
- **AWS Config:** ~$2/month  
- **VPC Flow Logs:** ~$1/month
- **Additional S3/Logs storage:** ~$5-10/month

**Total: +$13-18/month**

---

## Troubleshooting

### CloudTrail not delivering logs
```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket <bucket-name>

# Check trail status
aws cloudtrail get-trail-status --name <trail-name>
```

### GuardDuty findings not arriving
```bash
# Check SNS subscription
aws sns list-subscriptions-by-topic --topic-arn <topic-arn>

# Check CloudWatch Event Rule
aws events describe-rule --name <rule-name>
```

### Config rules showing "Not applicable"
```bash
# Ensure recorder is running
aws configservice start-configuration-recorder --configuration-recorder-names <recorder-name>

# Check recorder status
aws configservice describe-configuration-recorder-status
```

---

## Next Steps

Once Phase 1 is complete:
1. ✅ Verify all 4 services are operational
2. ✅ Test alert channels (email, Slack if configured)
3. ✅ Document runbooks for common alerts
4. 📋 Plan Phase 2: X-Ray, RDS Proxy, Lambda Reserved Concurrency, AWS Backup
