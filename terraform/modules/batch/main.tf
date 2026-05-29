# ============================================================
# AWS Batch Module - Heavy Loader Processing (buyselldaily)
# ============================================================

# ============================================================
# 1. CloudWatch Log Group
# ============================================================

resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/batch/${var.project_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-logs"
  })

  lifecycle {
    ignore_changes = [retention_in_days]
  }
}

# ============================================================
# 2. IAM Role for Batch Service
# ============================================================

resource "aws_iam_role" "batch_service_role" {
  name = "${var.project_name}-batch-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "batch.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-service-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_service_policy" {
  role       = aws_iam_role.batch_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

# ============================================================
# 3. IAM Role for EC2 Instances (Compute Environment)
# ============================================================

resource "aws_iam_role" "batch_ecs_instance_role" {
  name = "${var.project_name}-batch-ecs-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-ecs-instance-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_ecs_instance_policy" {
  role       = aws_iam_role.batch_ecs_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "batch_ecs_instance_profile" {
  name = "${var.project_name}-batch-ecs-instance-profile"
  role = aws_iam_role.batch_ecs_instance_role.name
}

# Allow EC2 instances to access RDS and S3
resource "aws_iam_role_policy" "batch_ec2_access" {
  name = "${var.project_name}-batch-ec2-access"
  role = aws_iam_role.batch_ecs_instance_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRDSAccess"
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds:${var.aws_region}:${var.aws_account_id}:db/*"
      },
      {
        Sid    = "AllowS3DataBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.data_bucket_name}",
          "arn:aws:s3:::${var.data_bucket_name}/*"
        ]
      },
      {
        Sid    = "AllowSecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        # FIXED: Issue #9 - Scope to project secrets only (was Resource: "secret:*")
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
      },
      {
        Sid    = "AllowECRAuthToken"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        # GetAuthorizationToken requires wildcard (AWS API design)
        Resource = "*"
      },
      {
        Sid    = "AllowECRPull"
        Effect = "Allow"
        # FIXED: Issue #7 - Scope to project ECR repository
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer"
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/${var.project_name}*"
      }
    ]
  })
}

# ============================================================
# 4. IAM Role for Batch Job (Task Role)
# ============================================================

resource "aws_iam_role" "batch_job_role" {
  name = "${var.project_name}-batch-job-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-job-role"
  })
}

resource "aws_iam_role_policy" "batch_job_policy" {
  name = "${var.project_name}-batch-job-policy"
  role = aws_iam_role.batch_job_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3DataBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.data_bucket_name}",
          "arn:aws:s3:::${var.data_bucket_name}/*"
        ]
      },
      {
        Sid    = "AllowSecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}-*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.batch.arn}:*"
      }
    ]
  })
}

# ============================================================
# 5. Compute Environment (EC2 Spot Fleet)
# ============================================================

resource "aws_batch_compute_environment" "spot" {
  type         = "MANAGED"
  state        = "ENABLED"
  service_role = aws_iam_role.batch_service_role.arn

  compute_resources {
    type                = "SPOT"
    allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    min_vcpus           = 0
    max_vcpus           = var.batch_max_vcpus
    desired_vcpus       = 0
    instance_role       = aws_iam_instance_profile.batch_ecs_instance_profile.arn
    instance_type       = var.batch_instance_types
    subnets             = var.private_subnet_ids
    security_group_ids  = [var.ecs_tasks_security_group_id]
    bid_percentage      = var.batch_spot_bid_percentage # 70% = 60% cost savings vs on-demand
    spot_iam_fleet_role = aws_iam_role.batch_spot_fleet_role.arn
    tags = merge(var.common_tags, {
      Name = "${var.project_name}-batch-spot-fleet"
    })
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-compute-env"
  })

  depends_on = [aws_iam_role_policy_attachment.batch_service_policy]
}

# ============================================================
# 7. IAM Role for Spot Fleet
# ============================================================

resource "aws_iam_role" "batch_spot_fleet_role" {
  name = "${var.project_name}-batch-spot-fleet-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "spotfleet.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-spot-fleet-role"
  })
}

resource "aws_iam_role_policy_attachment" "batch_spot_fleet_policy" {
  role       = aws_iam_role.batch_spot_fleet_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2SpotFleetTaggingRole"
}

# ============================================================
# 8. Job Queue
# ============================================================

resource "aws_batch_job_queue" "spot" {
  name     = "${var.project_name}-batch-job-queue-spot"
  state    = "ENABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.spot.arn
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-batch-job-queue"
  })

  depends_on = [aws_batch_compute_environment.spot]
}

# ============================================================
# 9. Job Definition for buyselldaily
# ============================================================

resource "aws_batch_job_definition" "buyselldaily" {
  name = "${var.project_name}-buyselldaily"
  type = "container"
  container_properties = jsonencode({
    image      = "${var.ecr_repository_uri}:loadbuyselldaily-latest"
    vcpus      = 4
    memory     = 4096
    jobRoleArn = aws_iam_role.batch_job_role.arn

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "buyselldaily"
      }
    }

    environment = [
      {
        name  = "DB_HOST"
        value = var.db_host
      },
      {
        name  = "DB_PORT"
        value = tostring(var.db_port)
      },
      {
        name  = "DB_NAME"
        value = var.db_name
      },
      {
        name  = "DB_USER"
        value = var.db_user
      },
      {
        name  = "RDS_SECRET_ARN"
        value = var.rds_secret_arn
      },
      {
        name  = "AWS_DEFAULT_REGION"
        value = var.aws_region
      },
      {
        name  = "S3_DATA_BUCKET"
        value = var.data_bucket_name
      }
    ]

    # Retry configuration
    retryStrategy = {
      attempts = 2
    }

    # Timeout in seconds - 1 hour per attempt (buyselldaily heavy loader)
    timeout = {
      attemptDurationSeconds = 3600
    }
  })

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-buyselldaily-job-def"
  })
}

# Auto-scaling via Application Auto Scaling removed: AWS deprecated
# batch:computeEnvironment:desiredvCpus as a scalable dimension.
# Batch managed compute environments handle vCPU scaling automatically
# via min_vcpus/max_vcpus on the compute environment resource.

# ============================================================
# 11. Data sources for AMI
# ============================================================

data "aws_ami" "ecs_optimized" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-ecs-hvm-*-x86_64-ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}
