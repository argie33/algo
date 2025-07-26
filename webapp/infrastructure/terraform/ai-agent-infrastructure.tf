# AI Agent Infrastructure - Terraform Implementation
# Integrated with existing Financial Dashboard infrastructure

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.2"
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
  description = "Private subnet IDs for Lambda functions"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "database_endpoint" {
  description = "Existing database endpoint"
  type        = string
}

variable "lambda_security_group_id" {
  description = "Existing Lambda security group ID (optional)"
  type        = string
  default     = ""
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for AI responses"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "conversation_retention_days" {
  description = "Number of days to retain conversation data"
  type        = number
  default     = 90
}

# Local values
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    Component   = "ai-agent"
  }
  
  create_lambda_sg = var.lambda_security_group_id == ""
  is_prod = var.environment == "prod"
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ==================== SECURITY GROUPS ====================

# Lambda Security Group (only if not provided)
resource "aws_security_group" "lambda" {
  count = local.create_lambda_sg ? 1 : 0
  
  name_prefix = "${local.name_prefix}-ai-lambda-"
  vpc_id      = var.vpc_id
  description = "Security group for AI agent Lambda functions"

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS outbound for Bedrock API"
  }

  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
    description = "PostgreSQL database access"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-lambda-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ==================== SECRETS MANAGEMENT ====================

# AI Configuration Secrets
resource "aws_secretsmanager_secret" "ai_configuration" {
  name        = "${local.name_prefix}-ai-configuration"
  description = "AI agent configuration including model parameters and API keys"

  tags = local.common_tags
}

resource "random_password" "api_encryption_key" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret_version" "ai_configuration" {
  secret_id = aws_secretsmanager_secret.ai_configuration.id
  secret_string = jsonencode({
    bedrock_model_id             = var.bedrock_model_id
    environment                  = var.environment
    project_name                 = var.project_name
    max_tokens                   = 2000
    temperature                  = 0.1
    streaming_enabled            = true
    conversation_retention_days  = var.conversation_retention_days
    api_encryption_key          = random_password.api_encryption_key.result
  })
}

# Conversation Encryption Secrets
resource "aws_secretsmanager_secret" "conversation_encryption" {
  name        = "${local.name_prefix}-conversation-encryption"
  description = "Encryption keys for conversation data"

  tags = local.common_tags
}

resource "random_password" "conversation_encryption_key" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret_version" "conversation_encryption" {
  secret_id = aws_secretsmanager_secret.conversation_encryption.id
  secret_string = jsonencode({
    algorithm                    = "AES-256-GCM"
    conversation_encryption_key  = random_password.conversation_encryption_key.result
  })
}

# ==================== IAM ROLES & POLICIES ====================

# AI Lambda Execution Role
resource "aws_iam_role" "ai_lambda" {
  name = "${local.name_prefix}-ai-lambda-role"

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

# AI Lambda Policy
resource "aws_iam_role_policy" "ai_lambda" {
  name = "${local.name_prefix}-ai-lambda-policy"
  role = aws_iam_role.ai_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Bedrock permissions
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.bedrock_model_id}",
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0"
        ]
      },
      # Secrets Manager
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.ai_configuration.arn,
          aws_secretsmanager_secret.conversation_encryption.arn
        ]
      },
      # Database access
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = "arn:aws:rds-db:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:dbuser:*/ai-agent-user"
      },
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      # WebSocket API Gateway
      {
        Effect = "Allow"
        Action = [
          "execute-api:ManageConnections"
        ]
        Resource = "${aws_apigatewayv2_api.ai_websocket.execution_arn}/*/*"
      },
      # CloudWatch metrics
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      # VPC access
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

# Attach VPC execution policy
resource "aws_iam_role_policy_attachment" "ai_lambda_vpc" {
  role       = aws_iam_role.ai_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ==================== WEBSOCKET API ====================

# WebSocket API
resource "aws_apigatewayv2_api" "ai_websocket" {
  name                       = "${local.name_prefix}-ai-websocket"
  protocol_type             = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
  description               = "WebSocket API for AI agent real-time streaming"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-websocket"
  })
}

# WebSocket Stage
resource "aws_apigatewayv2_stage" "ai_websocket" {
  api_id = aws_apigatewayv2_api.ai_websocket.id
  name   = var.environment

  default_route_settings {
    throttling_burst_limit = 500
    throttling_rate_limit  = 100
  }

  tags = local.common_tags
}

# ==================== LAMBDA FUNCTIONS ====================

# Connection Management Lambda
resource "aws_lambda_function" "ai_connection_manager" {
  filename         = data.archive_file.ai_connection_lambda.output_path
  function_name    = "${local.name_prefix}-ai-connection-manager"
  role            = aws_iam_role.ai_lambda.arn
  handler         = "index.handler"
  runtime         = "nodejs18.x"
  timeout         = 30
  memory_size     = 256

  source_code_hash = data.archive_file.ai_connection_lambda.output_base64sha256

  vpc_config {
    subnet_ids = var.private_subnet_ids
    security_group_ids = [
      local.create_lambda_sg ? aws_security_group.lambda[0].id : var.lambda_security_group_id
    ]
  }

  environment {
    variables = {
      WEBSOCKET_API_ENDPOINT = "https://${aws_apigatewayv2_api.ai_websocket.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${var.environment}"
      AI_CONFIG_SECRET_ARN   = aws_secretsmanager_secret.ai_configuration.arn
      DATABASE_ENDPOINT      = var.database_endpoint
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-connection-manager"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ai_lambda_vpc,
    aws_cloudwatch_log_group.ai_connection
  ]
}

# AI Processing Lambda
resource "aws_lambda_function" "ai_processing" {
  filename         = data.archive_file.ai_processing_lambda.output_path
  function_name    = "${local.name_prefix}-ai-processing"
  role            = aws_iam_role.ai_lambda.arn
  handler         = "index.handler"
  runtime         = "nodejs18.x"
  timeout         = 60
  memory_size     = 512

  source_code_hash = data.archive_file.ai_processing_lambda.output_base64sha256

  vpc_config {
    subnet_ids = var.private_subnet_ids
    security_group_ids = [
      local.create_lambda_sg ? aws_security_group.lambda[0].id : var.lambda_security_group_id
    ]
  }

  environment {
    variables = {
      AI_CONFIG_SECRET_ARN         = aws_secretsmanager_secret.ai_configuration.arn
      CONVERSATION_SECRET_ARN      = aws_secretsmanager_secret.conversation_encryption.arn
      DATABASE_ENDPOINT            = var.database_endpoint
      WEBSOCKET_API_ENDPOINT       = "https://${aws_apigatewayv2_api.ai_websocket.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${var.environment}"
      ENVIRONMENT                  = var.environment
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-processing"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ai_lambda_vpc,
    aws_cloudwatch_log_group.ai_processing
  ]
}

# Database Setup Lambda
resource "aws_lambda_function" "ai_database_setup" {
  filename         = data.archive_file.ai_database_lambda.output_path
  function_name    = "${local.name_prefix}-ai-db-setup"
  role            = aws_iam_role.ai_lambda.arn
  handler         = "index.handler"
  runtime         = "nodejs18.x"
  timeout         = 300
  memory_size     = 256

  source_code_hash = data.archive_file.ai_database_lambda.output_base64sha256

  vpc_config {
    subnet_ids = var.private_subnet_ids
    security_group_ids = [
      local.create_lambda_sg ? aws_security_group.lambda[0].id : var.lambda_security_group_id
    ]
  }

  environment {
    variables = {
      DATABASE_ENDPOINT = var.database_endpoint
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ai-db-setup"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ai_lambda_vpc,
    aws_cloudwatch_log_group.ai_database_setup
  ]
}

# ==================== LAMBDA PACKAGES ====================

# Connection Manager Lambda Package
data "archive_file" "ai_connection_lambda" {
  type        = "zip"
  output_path = "/tmp/ai-connection-lambda.zip"
  
  source {
    content = templatefile("${path.module}/lambda/ai-connection-manager.js", {
      websocket_endpoint = "https://${aws_apigatewayv2_api.ai_websocket.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${var.environment}"
    })
    filename = "index.js"
  }

  source {
    content = jsonencode({
      name = "ai-connection-manager"
      version = "1.0.0"
      main = "index.js"
      dependencies = {
        "aws-sdk" = "^2.1400.0"
        "pg" = "^8.8.0"
      }
    })
    filename = "package.json"
  }
}

# AI Processing Lambda Package
data "archive_file" "ai_processing_lambda" {
  type        = "zip"
  output_path = "/tmp/ai-processing-lambda.zip"
  
  source {
    content = file("${path.module}/lambda/ai-processing.js")
    filename = "index.js"
  }

  source {
    content = jsonencode({
      name = "ai-processing"
      version = "1.0.0"
      main = "index.js"
      dependencies = {
        "@aws-sdk/client-bedrock-runtime" = "^3.400.0"
        "aws-sdk" = "^2.1400.0"
        "pg" = "^8.8.0"
      }
    })
    filename = "package.json"
  }
}

# Database Setup Lambda Package
data "archive_file" "ai_database_lambda" {
  type        = "zip"
  output_path = "/tmp/ai-database-lambda.zip"
  
  source {
    content = file("${path.module}/lambda/ai-database-setup.js")
    filename = "index.js"
  }

  source {
    content = jsonencode({
      name = "ai-database-setup"
      version = "1.0.0"
      main = "index.js"
      dependencies = {
        "pg" = "^8.8.0"
      }
    })
    filename = "package.json"
  }
}

# ==================== WEBSOCKET ROUTES ====================

# WebSocket Routes
resource "aws_apigatewayv2_route" "connect" {
  api_id    = aws_apigatewayv2_api.ai_websocket.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.connect.id}"
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.ai_websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.disconnect.id}"
}

resource "aws_apigatewayv2_route" "ai_message" {
  api_id    = aws_apigatewayv2_api.ai_websocket.id
  route_key = "ai_message"
  target    = "integrations/${aws_apigatewayv2_integration.ai_message.id}"
}

# WebSocket Integrations
resource "aws_apigatewayv2_integration" "connect" {
  api_id           = aws_apigatewayv2_api.ai_websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.ai_connection_manager.invoke_arn
}

resource "aws_apigatewayv2_integration" "disconnect" {
  api_id           = aws_apigatewayv2_api.ai_websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.ai_connection_manager.invoke_arn
}

resource "aws_apigatewayv2_integration" "ai_message" {
  api_id           = aws_apigatewayv2_api.ai_websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.ai_connection_manager.invoke_arn
}

# Lambda Permissions
resource "aws_lambda_permission" "websocket" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ai_connection_manager.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.ai_websocket.execution_arn}/*/*"
}

# ==================== CLOUDWATCH MONITORING ====================

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "ai_processing" {
  name              = "/aws/lambda/${local.name_prefix}-ai-processing"
  retention_in_days = local.is_prod ? 30 : 14

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "ai_connection" {
  name              = "/aws/lambda/${local.name_prefix}-ai-connection-manager"
  retention_in_days = local.is_prod ? 30 : 14

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "ai_database_setup" {
  name              = "/aws/lambda/${local.name_prefix}-ai-db-setup"
  retention_in_days = local.is_prod ? 30 : 14

  tags = local.common_tags
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "ai_processing_errors" {
  alarm_name          = "${local.name_prefix}-ai-processing-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "This metric monitors AI processing Lambda errors"

  dimensions = {
    FunctionName = aws_lambda_function.ai_processing.function_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ai_processing_duration" {
  alarm_name          = "${local.name_prefix}-ai-processing-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "30000" # 30 seconds
  alarm_description   = "This metric monitors AI processing Lambda duration"

  dimensions = {
    FunctionName = aws_lambda_function.ai_processing.function_name
  }

  tags = local.common_tags
}

# Custom CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "ai_agent" {
  dashboard_name = "${local.name_prefix}-AI-Agent"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.ai_processing.function_name],
            [".", "Errors", ".", "."],
            [".", "Duration", ".", "."]
          ]
          period = 300
          stat   = "Sum"
          region = data.aws_region.current.name
          title  = "AI Processing Lambda Metrics"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/ApiGatewayV2", "Count", "ApiId", aws_apigatewayv2_api.ai_websocket.id],
            [".", "IntegrationLatency", ".", "."]
          ]
          period = 300
          stat   = "Sum"
          region = data.aws_region.current.name
          title  = "WebSocket API Metrics"
        }
      }
    ]
  })
}

# ==================== OUTPUTS ====================

output "ai_websocket_api_url" {
  description = "WebSocket API URL for real-time AI communication"
  value       = "wss://${aws_apigatewayv2_api.ai_websocket.id}.execute-api.${data.aws_region.current.name}.amazonaws.com/${var.environment}"
}

output "ai_processing_lambda_arn" {
  description = "ARN of AI processing Lambda function"
  value       = aws_lambda_function.ai_processing.arn
}

output "ai_configuration_secrets_arn" {
  description = "ARN of AI configuration secrets"
  value       = aws_secretsmanager_secret.ai_configuration.arn
}

output "conversation_encryption_secrets_arn" {
  description = "ARN of conversation encryption secrets"
  value       = aws_secretsmanager_secret.conversation_encryption.arn
}

output "ai_lambda_execution_role_arn" {
  description = "ARN of AI Lambda execution role"
  value       = aws_iam_role.ai_lambda.arn
}

output "ai_dashboard_url" {
  description = "CloudWatch Dashboard URL for AI Agent monitoring"
  value       = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${local.name_prefix}-AI-Agent"
}

output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  value       = local.create_lambda_sg ? aws_security_group.lambda[0].id : var.lambda_security_group_id
}