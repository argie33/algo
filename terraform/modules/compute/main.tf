# ============================================================
# Compute Module - ECS Cluster, Bastion, ECR
# ============================================================

# ============================================================
# 1. ECS Cluster (Fargate + Spot)
# ============================================================

resource "aws_ecs_cluster" "main" {
  name = coalesce(var.ecs_cluster_name, "${var.project_name}-cluster")

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecs-cluster"
  })
}

# ECS Cluster Capacity Providers (FARGATE + FARGATE_SPOT)
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = var.ecs_capacity_providers

  default_capacity_provider_strategy {
    capacity_provider = var.ecs_default_capacity_provider_strategy[0].capacity_provider
    weight            = var.ecs_default_capacity_provider_strategy[0].weight
    base              = 0
  }

  dynamic "default_capacity_provider_strategy" {
    for_each = slice(var.ecs_default_capacity_provider_strategy, 1, length(var.ecs_default_capacity_provider_strategy))
    content {
      capacity_provider = default_capacity_provider_strategy.value.capacity_provider
      weight            = default_capacity_provider_strategy.value.weight
    }
  }
}

# ============================================================
# 2. ECR Repository (Docker images)
# ============================================================

resource "aws_ecr_repository" "main" {
  name                 = coalesce(var.ecr_repository_name, "${var.project_name}-registry")
  image_tag_mutability = var.ecr_image_tag_mutability

  image_scanning_configuration {
    scan_on_push = var.ecr_image_scan_enabled
  }

  encryption_configuration {
    encryption_type = "AES256" # Use default encryption
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecr"
  })

  lifecycle {
    prevent_destroy = true
  }
}

# ECR repository policy: Allow pull from ECS & Lambda
resource "aws_ecr_repository_policy" "main" {
  repository = aws_ecr_repository.main.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECRPullFromECSAndLambda"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.aws_account_id}:root"
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:DescribeImages"
        ]
      }
    ]
  })
}

# ECR Lifecycle Policy: Keep last 10 images, delete old ones
resource "aws_ecr_lifecycle_policy" "main" {
  repository = aws_ecr_repository.main.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images, delete older ones"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================
# 3. CloudWatch Log Groups for ECS
# ============================================================

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}-cluster"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-ecs-logs"
  })
}

# ============================================================
# 4. Bastion Host (Spot ASG)
# ============================================================

resource "aws_launch_template" "bastion" {
  count                = var.bastion_enabled ? 1 : 0
  name                 = "${var.project_name}-bastion-lt"
  image_id            = data.aws_ami.amazon_linux_2[0].id
  instance_type       = var.bastion_instance_type
  iam_instance_profile {
    name = var.bastion_instance_profile_name
  }

  vpc_security_group_ids = [var.bastion_security_group_id]

  # Spot instance configuration
  instance_market_options {
    market_type = "spot"
    spot_options {
      spot_instance_type = "one-time"
    }
  }

  # No SSH key pair (use SSM Session Manager instead)
  user_data = base64encode(<<-EOF
              #!/bin/bash
              set -e
              # Enable CloudWatch agent and SSM agent
              yum update -y
              yum install -y amazon-cloudwatch-agent amazon-ssm-agent
              systemctl enable amazon-ssm-agent
              systemctl start amazon-ssm-agent
              # Configure CloudWatch Logs for SSM sessions
              cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWCONFIG'
              {
                "logs": {
                  "logs_collected": {
                    "files": {
                      "collect_list": [
                        {
                          "file_path": "/var/log/secure",
                          "log_group_name": "/aws/ssm/sessions",
                          "log_stream_name": "{instance_id}"
                        }
                      ]
                    }
                  }
                }
              }
              CWCONFIG
              /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
                -a fetch-config \
                -m ec2 \
                -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
                -s
              EOF
  )

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(var.common_tags, {
      Name = "${var.project_name}-bastion"
    })
  }
}

# AMI data source
data "aws_ami" "amazon_linux_2" {
  count       = var.bastion_enabled ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Bastion Auto Scaling Group
resource "aws_autoscaling_group" "bastion" {
  count                = var.bastion_enabled ? 1 : 0
  name                 = "${var.project_name}-bastion-asg"
  vpc_zone_identifier  = var.public_subnet_ids
  min_size             = 1
  max_size             = 1
  desired_capacity     = 1
  launch_template {
    id      = aws_launch_template.bastion[0].id
    version = "$Latest"
  }

  instance_refresh {
    strategy = "Rolling"
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-bastion"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes = [
      launch_template  # Ignore launch template version changes that don't require replacement
    ]
  }

  depends_on = [aws_launch_template.bastion]
}

# ============================================================
# 5. Lambda for Bastion Auto-Shutdown (Cost Optimization)
# ============================================================

resource "aws_iam_role" "bastion_stop" {
  count              = var.bastion_enabled ? 1 : 0
  name               = "${var.project_name}-bastion-stop-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume[0].json

  tags = var.common_tags
}

data "aws_iam_policy_document" "lambda_assume" {
  count = var.bastion_enabled ? 1 : 0

  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role_policy" "bastion_stop" {
  count  = var.bastion_enabled ? 1 : 0
  name   = "${var.project_name}-bastion-stop-policy"
  role   = aws_iam_role.bastion_stop[0].id
  policy = data.aws_iam_policy_document.bastion_stop[0].json
}

data "aws_iam_policy_document" "bastion_stop" {
  count = var.bastion_enabled ? 1 : 0

  statement {
    sid    = "TerminateASGInstances"
    effect = "Allow"

    actions = [
      "autoscaling:TerminateInstanceInAutoScalingGroup",
      "ec2:TerminateInstances"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.aws_account_id]
    }
  }

  statement {
    sid    = "DescribeASG"
    effect = "Allow"

    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "ec2:DescribeInstances"
    ]

    resources = ["*"]
  }
}

# Lambda function code (inline)
resource "aws_lambda_function" "bastion_stop" {
  count            = var.bastion_enabled ? 1 : 0
  filename         = data.archive_file.bastion_stop_zip[0].output_path
  function_name    = "${var.project_name}-bastion-stop"
  role             = aws_iam_role.bastion_stop[0].arn
  handler          = "index.handler"
  source_code_hash = data.archive_file.bastion_stop_zip[0].output_base64sha256
  runtime          = "python3.11"
  timeout          = 60

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-bastion-stop"
  })
}

# Lambda function source code
data "archive_file" "bastion_stop_zip" {
  count       = var.bastion_enabled ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/bastion_stop.zip"

  source {
    content  = "import boto3\nimport os\n\nasg_client = boto3.client('autoscaling')\nec2_client = boto3.client('ec2')\n\ndef handler(event, context):\n    asg_name = '${aws_autoscaling_group.bastion[0].name}'\n    response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])\n    \n    if response['AutoScalingGroups']:\n        instances = response['AutoScalingGroups'][0]['Instances']\n        instance_ids = [i['InstanceId'] for i in instances]\n        \n        if instance_ids:\n            asg_client.terminate_instance_in_auto_scaling_group(\n                InstanceId=instance_ids[0],\n                ShouldDecrementDesiredCapacity=False\n            )\n            return {'statusCode': 200, 'body': f'Terminated {instance_ids[0]}'}\n    \n    return {'statusCode': 200, 'body': 'No instances to terminate'}\n"
    filename = "index.py"
  }
}

# EventBridge rule: Stop Bastion at scheduled time
resource "aws_cloudwatch_event_rule" "bastion_shutdown" {
  count               = var.bastion_enabled ? 1 : 0
  name                = "${var.project_name}-bastion-shutdown"
  description         = "Stop Bastion at ${var.bastion_shutdown_hour_utc}:${format("%02d", var.bastion_shutdown_minute_utc)} UTC for cost savings"
  schedule_expression = "cron(${var.bastion_shutdown_minute_utc} ${var.bastion_shutdown_hour_utc} * * ? *)"

  tags = var.common_tags
}

resource "aws_cloudwatch_event_target" "bastion_shutdown" {
  count     = var.bastion_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.bastion_shutdown[0].name
  target_id = "BastonStopLambda"
  arn       = aws_lambda_function.bastion_stop[0].arn
}

resource "aws_lambda_permission" "bastion_shutdown" {
  count         = var.bastion_enabled ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bastion_stop[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.bastion_shutdown[0].arn
}

# ============================================================
# 6. CloudWatch Log Group for Bastion SSM Sessions
# ============================================================

resource "aws_cloudwatch_log_group" "bastion_ssm" {
  count             = var.enable_bastion_cloudwatch_logs && var.bastion_enabled ? 1 : 0
  name              = "/aws/ssm/${var.project_name}-bastion"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-bastion-ssm-logs"
  })
}
