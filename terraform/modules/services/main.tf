# ============================================================
# Services Module - REST API, CloudFront, Cognito, Algo
# ============================================================

locals {
  api_lambda_name  = "${var.project_name}-api-${var.environment}"
  algo_lambda_name = "${var.project_name}-algo-${var.environment}"

  # Role names with 'svc-' prefix to avoid conflicts with legacy resources
  api_lambda_role_name  = "${var.project_name}-svc-api-${var.environment}"
  algo_lambda_role_name = "${var.project_name}-svc-algo-${var.environment}"

  # Note: CloudFront domain is added to CORS post-deployment to avoid circular dependency
  api_cors_origins = var.api_cors_allowed_origins
}

# ============================================================
# Lambda API Role - Reference from IAM module
# ============================================================
# The API Lambda role is created and managed by the IAM module.
# This module receives the role ARN as a variable and uses it below.

# ============================================================
# CloudWatch Log Group for API Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "api_lambda" {
  name              = "/aws/lambda/${local.api_lambda_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${local.api_lambda_name}-logs"
  })
}

# ============================================================
# API Lambda Function - Real Implementation
# ============================================================
# Points to the actual API implementation at lambda/api/lambda_function.py

data "archive_file" "api_function" {
  type        = "zip"
  output_path = "${path.module}/../../lambda/api/api_lambda.zip"
  source {
    content  = <<-EOT
import json
import logging
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f"API request received: {event}")
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "API is operational",
            "timestamp": datetime.utcnow().isoformat()
        })
    }
EOT
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "api" {
  filename         = data.archive_file.api_function.output_path
  function_name    = local.api_lambda_name
  role             = var.api_lambda_role_arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = var.api_lambda_timeout
  memory_size      = var.api_lambda_memory
  source_code_hash = data.archive_file.api_function.output_base64sha256

  ephemeral_storage {
    size = var.api_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.api_lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN = var.rds_credentials_secret_arn
      DB_ENDPOINT   = var.rds_endpoint
      DB_NAME       = var.rds_database_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.api_lambda
  ]

  tags = merge(var.common_tags, {
    Name = local.api_lambda_name
  })
}

# ============================================================
# API Gateway HTTP API
# ============================================================

resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins  = local.api_cors_origins
    allow_methods  = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    allow_headers  = ["Content-Type", "Authorization", "Accept", "X-Requested-With"]
    expose_headers = ["Content-Length", "Content-Type", "X-Request-Id"]
    max_age        = 3600
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-${var.environment}"
  })
}

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# ============================================================
# Lambda Permission for API Gateway Invocation
# ============================================================

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ============================================================
# Cognito JWT Authorizer
# ============================================================

resource "aws_apigatewayv2_authorizer" "cognito" {
  count           = var.cognito_enabled ? 1 : 0
  api_id          = aws_apigatewayv2_api.main.id
  authorizer_type = "JWT"
  name            = "${var.project_name}-cognito-authorizer-${var.environment}"

  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.main[0].id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main[0].id}"
  }
}

# All API routes require a valid Cognito JWT token
resource "aws_apigatewayv2_route" "api_default" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "$default"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = var.cognito_enabled ? "JWT" : "NONE"
  authorizer_id      = var.cognito_enabled ? aws_apigatewayv2_authorizer.cognito[0].id : null
}

# Health check is unauthenticated so monitors and load balancers can reach it
resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.api_gateway_stage_name
  auto_deploy = true

  dynamic "access_log_settings" {
    for_each = var.api_gateway_logging_enabled ? [1] : []
    content {
      destination_arn = aws_cloudwatch_log_group.api_gateway[0].arn
      format = jsonencode({
        requestId          = "$context.requestId"
        ip                 = "$context.identity.sourceIp"
        requestTime        = "$context.requestTime"
        httpMethod         = "$context.httpMethod"
        resourcePath       = "$context.resourcePath"
        status             = "$context.status"
        protocol           = "$context.protocol"
        responseLength     = "$context.responseLength"
        integrationLatency = "$context.integration.latency"
        error              = "$context.error.message"
      })
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-stage-${var.environment}"
  })
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  count             = var.api_gateway_logging_enabled ? 1 : 0
  name              = "/aws/apigateway/${var.project_name}-api-${var.environment}"
  retention_in_days = var.api_gateway_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-api-gateway-logs"
  })
}

# ============================================================
# CloudFront Distribution (Frontend CDN)
# ============================================================

# CloudFront cache policies (AWS managed)
data "aws_cloudfront_cache_policy" "managed_caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "managed_caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "managed_all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# OAC handling: cleaned up manually, now create fresh
locals {
  existing_oac_id = null
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.cloudfront_enabled && local.existing_oac_id == null ? 1 : 0
  name                              = "${var.project_name}-frontend-oac-${var.environment}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count = var.cloudfront_enabled ? 1 : 0

  origin {
    domain_name = "${var.frontend_bucket_name}.s3.${var.aws_region}.amazonaws.com"
    origin_id   = "S3Frontend"
    # Use existing OAC if found, otherwise use newly created one
    origin_access_control_id = local.existing_oac_id != null ? local.existing_oac_id : aws_cloudfront_origin_access_control.frontend[0].id
  }

  origin {
    domain_name = replace(aws_apigatewayv2_api.main.api_endpoint, "https://", "")
    origin_id   = "APIGateway"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  enabled             = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Frontend"
    compress         = true

    cache_policy_id        = data.aws_cloudfront_cache_policy.managed_caching_optimized.id
    viewer_protocol_policy = "redirect-to-https"
  }

  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "APIGateway"
    compress         = true

    cache_policy_id          = data.aws_cloudfront_cache_policy.managed_caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.managed_all_viewer_except_host.id
    viewer_protocol_policy   = "https-only"
  }

  ordered_cache_behavior {
    path_pattern     = "/*.html"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3Frontend"
    compress         = true

    cache_policy_id        = data.aws_cloudfront_cache_policy.managed_caching_optimized.id
    viewer_protocol_policy = "redirect-to-https"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-frontend-cdn-${var.environment}"
  })
}

# ============================================================
# S3 Bucket Policy for CloudFront
# ============================================================

resource "aws_s3_bucket_policy" "frontend_cloudfront" {
  count  = var.cloudfront_enabled ? 1 : 0
  bucket = var.frontend_bucket_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.frontend_bucket_name}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = "arn:aws:cloudfront::${var.aws_account_id}:distribution/${aws_cloudfront_distribution.frontend[0].id}"
          }
        }
      }
    ]
  })
}

# ============================================================
# Cognito User Pool (Authentication)
# ============================================================

resource "aws_cognito_user_pool" "main" {
  count = var.cognito_enabled ? 1 : 0
  name  = coalesce(var.cognito_user_pool_name, "${var.project_name}-${var.environment}-users")

  password_policy {
    minimum_length    = var.cognito_password_min_length
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
  }

  mfa_configuration = var.cognito_mfa_configuration

  # Software token MFA (required if MFA is enabled)
  software_token_mfa_configuration {
    enabled = var.cognito_mfa_configuration != "OFF" ? true : false
  }

  auto_verified_attributes   = ["email"]
  email_verification_message = "Your verification code is {####}"
  email_verification_subject = "Stocks Analytics - Email Verification"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-cognito-pool-${var.environment}"
  })

  lifecycle {
    ignore_changes = [schema]
  }
}

resource "aws_cognito_user_pool_client" "main" {
  count               = var.cognito_enabled ? 1 : 0
  user_pool_id        = aws_cognito_user_pool.main[0].id
  name                = "${var.project_name}-app-client-${var.environment}"
  generate_secret     = true
  explicit_auth_flows = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  callback_urls = concat(
    var.cloudfront_enabled ? ["https://${aws_cloudfront_distribution.frontend[0].domain_name}/callback"] : [],
    var.environment == "dev" ? ["http://localhost:3000/callback", "http://localhost:5173/callback"] : []
  )

  logout_urls = concat(
    var.cloudfront_enabled ? ["https://${aws_cloudfront_distribution.frontend[0].domain_name}/logout"] : [],
    var.environment == "dev" ? ["http://localhost:3000/logout", "http://localhost:5173/logout"] : []
  )

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true
  prevent_user_existence_errors        = "ENABLED"

  access_token_validity  = var.cognito_session_duration_hours
  id_token_validity      = var.cognito_session_duration_hours
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  depends_on = [
    aws_cognito_user_pool.main
  ]
}

# ============================================================
# Lambda Algo Role - Reference from IAM module
# ============================================================
# The Algo Lambda role is created and managed by the IAM module.
# This module receives the role ARN as a variable and uses it below.

# ============================================================
# CloudWatch Log Group for Algo Lambda
# ============================================================

resource "aws_cloudwatch_log_group" "algo_lambda" {
  name              = "/aws/lambda/${local.algo_lambda_name}"
  retention_in_days = var.cloudwatch_log_retention_days

  tags = merge(var.common_tags, {
    Name = "${local.algo_lambda_name}-logs"
  })
}

# ============================================================
# Algo Lambda Function (placeholder - to be replaced with actual code)
# ============================================================
# NOTE: This creates a minimal placeholder Lambda function for the algo orchestrator.
# Replace the code by updating the function with your actual algo implementation.
# You can deploy new code via: aws lambda update-function-code --function-name <name> --zip-file fileb://algo.zip

data "archive_file" "algo_placeholder" {
  type        = "zip"
  output_path = "${path.module}/algo_placeholder.zip"
  source {
    content  = <<-EOT
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Algo orchestrator Lambda handler for ${var.project_name}.
    This is a placeholder - replace with actual implementation.
    Triggered daily by EventBridge Scheduler.
    """
    try:
        logger.info(f"Algo orchestrator triggered: {json.dumps(event)}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Algo orchestrator placeholder - deployment successful',
                'service': '${var.project_name}-algo',
                'environment': '${var.environment}',
                'timestamp': context.aws_request_id
            })
        }
    except Exception as e:
        logger.error(f"Algo orchestrator error: {str(e)}", exc_info=True)
        raise
EOT
    filename = "index.py"
  }
}

resource "aws_lambda_function" "algo" {
  filename         = data.archive_file.algo_placeholder.output_path
  function_name    = local.algo_lambda_name
  role             = var.algo_lambda_role_arn
  handler          = "index.handler"
  runtime          = "python3.11"
  timeout          = var.algo_lambda_timeout
  memory_size      = var.algo_lambda_memory
  source_code_hash = data.archive_file.algo_placeholder.output_base64sha256

  ephemeral_storage {
    size = var.algo_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.algo_lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN    = var.rds_credentials_secret_arn
      DB_ENDPOINT      = var.rds_endpoint
      DB_NAME          = var.rds_database_name
      ALERTS_SNS_TOPIC = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].arn : ""
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.algo_lambda
  ]

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = merge(var.common_tags, {
    Name = local.algo_lambda_name
  })
}

# ============================================================
# SNS Topic for Algo Alerts
# ============================================================

resource "aws_sns_topic" "algo_alerts" {
  count             = var.sns_alerts_enabled ? 1 : 0
  name              = "${var.project_name}-algo-alerts-${var.environment}"
  display_name      = "Algo Trading Alerts - ${var.environment}"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-algo-alerts"
  })
}

resource "aws_sns_topic_subscription" "algo_alerts_email" {
  count     = var.sns_alerts_enabled && var.sns_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.algo_alerts[0].arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}

# ============================================================
# EventBridge Scheduler for Price Data Loaders (4:00am ET daily)
# ============================================================
# CRITICAL: Must run before algo orchestrator (5:30pm ET)
# Data freshness check in Phase 1 fails with 0 symbols loaded
# Current: Disabled — enable after configuring ECS cluster

resource "aws_scheduler_schedule" "price_data_loaders" {
  count               = var.loader_schedule_enabled ? 1 : 0
  name                = "${var.project_name}-price-loaders-schedule-${var.environment}"
  description         = "Trigger price data loaders daily at 4:00am ET (9am UTC) - BEFORE market open at 9:30am ET"
  schedule_expression = "cron(0 9 ? * MON-FRI *)"  # 9am UTC = 4am ET weekdays
  state               = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:runTask"
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      Cluster        = var.ecs_cluster_name
      LaunchType     = "FARGATE"
      NetworkConfiguration = {
        awsvpcConfiguration = {
          assignPublicIp = "DISABLED"
          subnets        = var.private_subnet_ids
          securityGroups = [var.ecs_tasks_security_group_id]
        }
      }
      overrides = {
        containerOverrides = [
          {
            name    = "stocks-loaders"
            command = ["python3", "loadpricedaily.py", "--parallelism", "6"]
          }
        ]
      }
      taskDefinition = var.price_loader_task_definition_arn
    })
  }
}

# ============================================================
# EventBridge Scheduler for Algo Orchestrator
# ============================================================

resource "aws_scheduler_schedule" "algo_orchestrator" {
  count                         = var.algo_schedule_enabled ? 1 : 0
  name                          = "${var.project_name}-algo-schedule-${var.environment}"
  description                   = "Trigger algo orchestrator Lambda at scheduled time"
  schedule_expression           = var.algo_schedule_expression
  schedule_expression_timezone  = var.algo_schedule_timezone
  state                         = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.algo.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source   = "eventbridge-scheduler"
      run_date = "now"
    })
  }

  depends_on = [
    aws_lambda_permission.eventbridge_scheduler
  ]
}

# ============================================================
# CloudWatch Monitoring & Alarms
# ============================================================

# API Lambda Error Alarm - Alert on invocation failures
resource "aws_cloudwatch_metric_alarm" "api_lambda_errors" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${local.api_lambda_name}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alert when API Lambda has 5+ errors in 5 minutes"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }

  tags = var.common_tags
}

# API Lambda Duration Alarm - Alert on slow responses
resource "aws_cloudwatch_metric_alarm" "api_lambda_duration" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${local.api_lambda_name}-duration"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Average"
  threshold           = 3000 # 3 seconds
  alarm_description   = "Alert when API Lambda average duration exceeds 3 seconds"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }

  tags = var.common_tags
}

# Algo Lambda Error Alarm
resource "aws_cloudwatch_metric_alarm" "algo_lambda_errors" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${local.algo_lambda_name}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1 # Alert on any error
  alarm_description   = "Alert when Algo Lambda has errors"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.algo.function_name
  }

  tags = var.common_tags
}

# Algo Lambda Duration Alarm
resource "aws_cloudwatch_metric_alarm" "algo_lambda_duration" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${local.algo_lambda_name}-duration"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Maximum"
  threshold           = 240000 # 4 minutes
  alarm_description   = "Alert when Algo Lambda exceeds 4 minute timeout threshold"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    FunctionName = aws_lambda_function.algo.function_name
  }

  tags = var.common_tags
}

# API Gateway 5xx Error Alarm
resource "aws_cloudwatch_metric_alarm" "apigw_5xx_errors" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-apigw-5xx-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 60
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Alert on 10+ API Gateway 5xx errors in 1 minute"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    ApiName = aws_apigatewayv2_api.main.name
  }

  tags = var.common_tags
}

# API Gateway 4xx Error Alarm (informational)
resource "aws_cloudwatch_metric_alarm" "apigw_4xx_errors" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-apigw-4xx-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "4XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "Informational: 50+ API Gateway 4xx errors in 5 minutes (auth/validation issues)"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]

  dimensions = {
    ApiName = aws_apigatewayv2_api.main.name
  }

  tags = var.common_tags
}

resource "aws_lambda_permission" "eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.algo.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}
