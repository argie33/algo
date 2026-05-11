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
# API Lambda Function
# ============================================================
# Uses S3-based code packages built and uploaded by GitHub Actions.
# Fallback to local file if S3 not configured.

# Conditional: use S3 if bucket provided, else local file
locals {
  api_lambda_use_s3 = var.api_lambda_s3_bucket != ""
}

# For local fallback: archive local code (for dev/testing)
data "archive_file" "api_function_local" {
  count       = local.api_lambda_use_s3 ? 0 : 1
  type        = "zip"
  output_path = "${path.module}/../../${var.api_lambda_code_file}"
  source {
    content  = "module.exports.handler = async (event) => { return { statusCode: 503, body: 'API Lambda stub - use S3 for production' }; };"
    filename = "index.js"
  }
}

resource "aws_lambda_function" "api" {
  function_name    = local.api_lambda_name
  role             = var.api_lambda_role_arn
  handler          = "index.handler"
  runtime          = "nodejs20.x"
  timeout          = var.api_lambda_timeout
  memory_size      = var.api_lambda_memory

  # Use S3 package if available, otherwise local file
  s3_bucket         = local.api_lambda_use_s3 ? var.api_lambda_s3_bucket : null
  s3_key            = local.api_lambda_use_s3 ? var.api_lambda_s3_key : null
  s3_object_version = local.api_lambda_use_s3 && var.api_lambda_s3_object_version != "" ? var.api_lambda_s3_object_version : null
  filename          = !local.api_lambda_use_s3 ? data.archive_file.api_function_local[0].output_path : null
  source_code_hash  = !local.api_lambda_use_s3 ? data.archive_file.api_function_local[0].output_base64sha256 : null

  ephemeral_storage {
    size = var.api_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.api_lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN        = var.rds_credentials_secret_arn
      DB_ENDPOINT          = var.rds_endpoint
      DB_NAME              = var.rds_database_name
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      COGNITO_CLIENT_ID    = var.cognito_client_id
      NODE_ENV             = "production"
      CLOUDFRONT_DOMAIN    = try("https://${aws_cloudfront_distribution.frontend.domain_name}", "")
      FRONTEND_URL         = try("https://${aws_cloudfront_distribution.frontend.domain_name}", "")
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.api_lambda
  ]

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

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
    audience = [var.cognito_client_id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${var.cognito_user_pool_id}"
  }
}

# TODO: Wire cognito module outputs to authorizer after root module is applied

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
# NOTE: Cognito is now managed by root-level cognito module
# (see ../cognito.tf for details)
# ============================================================
# Removed duplicate resources to avoid conflict with root cognito module.
# All Cognito configuration is now in modules/cognito/

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
# ============================================================
# Algo Orchestrator Lambda Function
# ============================================================
# Uses S3-based code packages built and uploaded by GitHub Actions.
# Fallback to local file if S3 not configured.

# Conditional: use S3 if bucket provided, else local file
locals {
  algo_lambda_use_s3 = var.algo_lambda_s3_bucket != ""
}

# For local fallback: archive local code (for dev/testing)
data "archive_file" "algo_function_local" {
  count       = local.algo_lambda_use_s3 ? 0 : 1
  type        = "zip"
  output_path = "${path.module}/../../${var.algo_lambda_code_file}"
  source {
    content  = "# Algo Lambda stub - use S3 for production"
    filename = "lambda_function.py"
  }
}

resource "aws_lambda_function" "algo" {
  function_name    = local.algo_lambda_name
  role             = var.algo_lambda_role_arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = var.algo_lambda_timeout
  memory_size      = var.algo_lambda_memory

  # Use S3 package if available, otherwise local file
  s3_bucket         = local.algo_lambda_use_s3 ? var.algo_lambda_s3_bucket : null
  s3_key            = local.algo_lambda_use_s3 ? var.algo_lambda_s3_key : null
  s3_object_version = local.algo_lambda_use_s3 && var.algo_lambda_s3_object_version != "" ? var.algo_lambda_s3_object_version : null
  filename          = !local.algo_lambda_use_s3 ? data.archive_file.algo_function_local[0].output_path : null
  source_code_hash  = !local.algo_lambda_use_s3 ? data.archive_file.algo_function_local[0].output_base64sha256 : null

  ephemeral_storage {
    size = var.algo_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.algo_lambda_security_group_id]
  }

  environment {
    variables = {
      DATABASE_SECRET_ARN    = var.rds_credentials_secret_arn
      DB_ENDPOINT            = var.rds_endpoint
      DB_NAME                = var.rds_database_name
      ALERTS_SNS_TOPIC       = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].arn : ""
      EXECUTION_MODE         = var.execution_mode
      DRY_RUN_MODE           = tostring(var.orchestrator_dry_run)
      APCA_API_KEY_ID        = var.alpaca_api_key_id
      APCA_API_SECRET_KEY    = var.alpaca_api_secret_key
      APCA_API_BASE_URL      = var.alpaca_api_base_url
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
      cluster        = var.ecs_cluster_name
      launchType     = "FARGATE"
      networkConfiguration = {
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
