# Enhanced Session Management Infrastructure using Terraform
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Variables
variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
  validation {
    condition     = can(regex("^(dev|staging|prod)$", var.environment))
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "stocks-webapp"
}

variable "vpc_id" {
  description = "VPC ID for resources"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda and Redis"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

# Local values
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Component   = "session-management"
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ElastiCache subnet group
resource "aws_elasticache_subnet_group" "session_store" {
  name       = "${local.name_prefix}-session-store-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-session-store-subnet-group"
  })
}

# Security group for Redis
resource "aws_security_group" "session_store" {
  name_prefix = "${local.name_prefix}-session-store-"
  vpc_id      = var.vpc_id
  description = "Security group for session store Redis cluster"

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "Redis access from Lambda"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-session-store-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Security group for Lambda
resource "aws_security_group" "lambda" {
  name_prefix = "${local.name_prefix}-lambda-"
  vpc_id      = var.vpc_id
  description = "Security group for Lambda functions"

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS outbound"
  }

  egress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.session_store.id]
    description     = "Redis access"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lambda-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# CloudWatch log group for Redis
resource "aws_cloudwatch_log_group" "session_store" {
  name              = "/aws/elasticache/${local.name_prefix}-session-store"
  retention_in_days = 14

  tags = local.common_tags
}

# ElastiCache Redis cluster
resource "aws_elasticache_replication_group" "session_store" {
  replication_group_id       = "${local.name_prefix}-session-store"
  description                = "Redis cluster for enhanced session management"
  
  node_type                  = "cache.t3.micro"
  port                       = 6379
  parameter_group_name       = "default.redis7"
  
  num_cache_clusters         = 1
  
  subnet_group_name          = aws_elasticache_subnet_group.session_store.name
  security_group_ids         = [aws_security_group.session_store.id]
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  
  multi_az_enabled           = false
  automatic_failover_enabled = false
  
  engine_version             = "7.0"
  
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.session_store.name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-session-store"
  })

  lifecycle {
    ignore_changes = [num_cache_clusters]
  }
}

# Secrets Manager secret for session management
resource "aws_secretsmanager_secret" "session_management" {
  name        = "${local.name_prefix}-session-management"
  description = "Session management configuration and encryption keys"

  tags = local.common_tags
}

# Generate secret string
resource "aws_secretsmanager_secret_version" "session_management" {
  secret_id = aws_secretsmanager_secret.session_management.id
  secret_string = jsonencode({
    redis_endpoint  = aws_elasticache_replication_group.session_store.primary_endpoint_address
    encryption_key  = random_password.encryption_key.result
    environment     = var.environment
    project_name    = var.project_name
  })
}

# Random password for encryption
resource "random_password" "encryption_key" {
  length  = 64
  special = false
}

# IAM role for Lambda
resource "aws_iam_role" "session_lambda" {
  name = "${local.name_prefix}-session-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM policy for Lambda
resource "aws_iam_role_policy" "session_lambda" {
  name = "${local.name_prefix}-session-lambda-policy"
  role = aws_iam_role.session_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.session_management.arn
      },
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminListGroupsForUser",
          "cognito-idp:AdminUserGlobalSignOut"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "elasticache:DescribeReplicationGroups",
          "elasticache:DescribeCacheClusters"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach VPC execution role policy
resource "aws_iam_role_policy_attachment" "session_lambda_vpc" {
  role       = aws_iam_role.session_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Lambda function package
data "archive_file" "session_lambda" {
  type        = "zip"
  output_path = "/tmp/session-management-lambda.zip"
  
  source {
    content = templatefile("${path.module}/lambda/session-management.js", {
      redis_endpoint = aws_elasticache_replication_group.session_store.primary_endpoint_address
      secrets_arn    = aws_secretsmanager_secret.session_management.arn
    })
    filename = "index.js"
  }

  source {
    content = jsonencode({
      name = "session-management-lambda"
      version = "1.0.0"
      main = "index.js"
      dependencies = {
        "ioredis" = "^5.3.2"
        "aws-sdk" = "^2.1400.0"
      }
    })
    filename = "package.json"
  }
}

# Lambda function
resource "aws_lambda_function" "session_management" {
  filename         = data.archive_file.session_lambda.output_path
  function_name    = "${local.name_prefix}-session-management"
  role            = aws_iam_role.session_lambda.arn
  handler         = "index.handler"
  runtime         = "nodejs18.x"
  timeout         = 30
  memory_size     = 256

  source_code_hash = data.archive_file.session_lambda.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      REDIS_ENDPOINT      = aws_elasticache_replication_group.session_store.primary_endpoint_address
      SESSION_SECRETS_ARN = aws_secretsmanager_secret.session_management.arn
      ENVIRONMENT         = var.environment
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-session-management-lambda"
  })

  depends_on = [
    aws_iam_role_policy_attachment.session_lambda_vpc,
    aws_cloudwatch_log_group.session_lambda
  ]
}

# CloudWatch log group for Lambda
resource "aws_cloudwatch_log_group" "session_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-session-management"
  retention_in_days = 14

  tags = local.common_tags
}

# API Gateway
resource "aws_api_gateway_rest_api" "session_management" {
  name        = "${local.name_prefix}-session-management-api"
  description = "API for enhanced session management"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = local.common_tags
}

# API Gateway resource
resource "aws_api_gateway_resource" "session" {
  rest_api_id = aws_api_gateway_rest_api.session_management.id
  parent_id   = aws_api_gateway_rest_api.session_management.root_resource_id
  path_part   = "session"
}

# API Gateway method
resource "aws_api_gateway_method" "session_any" {
  rest_api_id   = aws_api_gateway_rest_api.session_management.id
  resource_id   = aws_api_gateway_resource.session.id
  http_method   = "ANY"
  authorization = "AWS_IAM"
}

# API Gateway integration
resource "aws_api_gateway_integration" "session_lambda" {
  rest_api_id = aws_api_gateway_rest_api.session_management.id
  resource_id = aws_api_gateway_resource.session.id
  http_method = aws_api_gateway_method.session_any.http_method

  integration_http_method = "POST"
  type                   = "AWS_PROXY"
  uri                    = aws_lambda_function.session_management.invoke_arn
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.session_management.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.session_management.execution_arn}/*/*"
}

# API Gateway deployment
resource "aws_api_gateway_deployment" "session_management" {
  depends_on = [
    aws_api_gateway_method.session_any,
    aws_api_gateway_integration.session_lambda
  ]

  rest_api_id = aws_api_gateway_rest_api.session_management.id
  stage_name  = var.environment

  lifecycle {
    create_before_destroy = true
  }
}

# CloudWatch alarms
resource "aws_cloudwatch_metric_alarm" "redis_connections" {
  alarm_name          = "${local.name_prefix}-session-store-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CurrConnections"
  namespace           = "AWS/ElastiCache"
  period              = "300"
  statistic           = "Average"
  threshold           = "50"
  alarm_description   = "This metric monitors Redis connection count"

  dimensions = {
    CacheClusterId = "${aws_elasticache_replication_group.session_store.replication_group_id}-001"
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name_prefix}-session-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "This metric monitors Lambda function errors"

  dimensions = {
    FunctionName = aws_lambda_function.session_management.function_name
  }

  tags = local.common_tags
}

# Outputs
output "session_store_endpoint" {
  description = "Redis endpoint for session storage"
  value       = aws_elasticache_replication_group.session_store.primary_endpoint_address
}

output "session_management_api_url" {
  description = "API Gateway URL for session management"
  value       = "https://${aws_api_gateway_rest_api.session_management.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${var.environment}"
}

output "session_secrets_arn" {
  description = "ARN of session management secrets"
  value       = aws_secretsmanager_secret.session_management.arn
}

output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  value       = aws_security_group.lambda.id
}