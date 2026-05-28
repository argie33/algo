# ============================================================
# Services Module - REST API, CloudFront, Cognito, Algo
# ============================================================

locals {
  api_lambda_name  = "${var.project_name}-api-${var.environment}"
  algo_lambda_name = "${var.project_name}-algo-${var.environment}"

  # Role names with 'svc-' prefix to avoid conflicts with legacy resources
  api_lambda_role_name  = "${var.project_name}-svc-api-${var.environment}"
  algo_lambda_role_name = "${var.project_name}-svc-algo-${var.environment}"
}

# ============================================================
# Lambda Layers for Dependencies
# ============================================================
# Separate layers for API and Orchestrator Lambda functions
# Published by GitHub Actions deploy workflow

# API Layer - published as per variable configuration
data "aws_lambda_layer_version" "api_deps" {
  layer_name = var.api_lambda_layer_name
}

# Orchestrator Layer - published as "algo-orchestrator-layer"
data "aws_lambda_layer_version" "shared_deps" {
  layer_name = var.lambda_layer_name
}

# For compatibility with existing code
locals {
  api_layer_arn         = data.aws_lambda_layer_version.api_deps.arn
  shared_deps_layer_arn = data.aws_lambda_layer_version.shared_deps.arn
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

# API Lambda code: pre-built ZIP by GitHub Actions workflow, or reference local file for Terraform-only runs
# GitHub Actions builds lambda-api.zip in terraform/ directory before terraform apply
# For local/manual Terraform runs, fallback to looking for pre-built ZIP at terraform root

resource "aws_lambda_function" "api" {
  function_name = local.api_lambda_name
  role          = var.api_lambda_role_arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.api_lambda_timeout
  memory_size   = var.api_lambda_memory

  # Keep Lambda warm to avoid cold start timeouts (15-40s cold start would exceed 29s API Gateway timeout)
  reserved_concurrent_executions = 2

  layers = [local.api_layer_arn, var.psycopg2_layer_arn]

  # Use S3 package if available, otherwise pre-built local ZIP from GitHub Actions workflow
  s3_bucket         = local.api_lambda_use_s3 ? var.api_lambda_s3_bucket : null
  s3_key            = local.api_lambda_use_s3 ? var.api_lambda_s3_key : null
  s3_object_version = local.api_lambda_use_s3 && var.api_lambda_s3_object_version != "" ? var.api_lambda_s3_object_version : null
  filename          = !local.api_lambda_use_s3 ? "${path.module}/../../${var.api_lambda_code_file}" : null
  source_code_hash  = !local.api_lambda_use_s3 ? filebase64sha256("${path.module}/../../${var.api_lambda_code_file}") : null

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
      DB_HOST       = var.rds_proxy_endpoint != null ? var.rds_proxy_endpoint : split(":", var.rds_endpoint)[0]
      DB_PORT       = "5432"
      DB_NAME       = var.rds_database_name
      DB_USER       = var.rds_username
      DB_SSL        = "require"
      # Alpaca keys are fetched at runtime from ALGO_SECRETS_ARN — not stored as plaintext env vars
      ALGO_SECRETS_ARN     = var.algo_secrets_arn
      APCA_API_BASE_URL    = var.alpaca_api_base_url
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      COGNITO_CLIENT_ID    = var.cognito_client_id
      NODE_ENV             = var.node_env
      CLOUDFRONT_DOMAIN    = try("https://${aws_cloudfront_distribution.frontend[0].domain_name}", "")
      FRONTEND_URL         = try("https://${aws_cloudfront_distribution.frontend[0].domain_name}", "")
      FRONTEND_ORIGIN      = try("https://${aws_cloudfront_distribution.frontend[0].domain_name}", "")
      ALLOWED_ORIGINS      = try("https://${aws_cloudfront_distribution.frontend[0].domain_name},http://localhost:5173,http://localhost:3000", "http://localhost:5173,http://localhost:3000")
      # Data patrol task configuration (for /api/algo/patrol endpoint)
      ECS_CLUSTER_ARN            = var.ecs_cluster_arn
      PATROL_TASK_DEFINITION_ARN = var.patrol_task_definition_arn
      PATROL_CONTAINER_NAME      = var.patrol_task_container_name
      PATROL_SUBNET_IDS          = join(",", var.private_subnet_ids_for_patrol)
      PATROL_SECURITY_GROUP_ID   = var.ecs_tasks_sg_id
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

  # CORS is handled at both API Gateway level (safety net) and Lambda (primary)
  cors_configuration {
    allow_origins = [
      "http://localhost:3000",
      "http://localhost:5173",
      "https://d2u93283nn45h2.cloudfront.net"  # Frontend CloudFront domain (exact match required)
    ]
    allow_methods     = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    allow_headers     = ["Content-Type", "Authorization", "X-Requested-With", "Accept"]
    expose_headers    = ["Content-Length", "Content-Type"]
    max_age          = 3600
    allow_credentials = true
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
# Cognito JWT Authorizer - Enforces Authentication at API Boundary
# ============================================================
# All routes require valid Cognito JWT token (except /health which is public)
# This ensures authentication is enforced at the API Gateway level, not in Lambda

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

# API route - $default (catch-all for all requests)
# AWS HTTP API automatically creates and manages the $default route.
# With auto_deploy enabled on the stage, the integration will be automatically
# routed to by the $default route, so we don't need to explicitly create it.

# Health check is unauthenticated so monitors and load balancers can reach it
resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

# Public data endpoints (no auth required) — trading data is public
resource "aws_apigatewayv2_route" "signals_public" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /api/signals"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "scores_public" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /api/scores"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "market_public" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /api/market"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "economic_public" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /api/economic"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

# Default route - all routes use NONE auth, Lambda enforces auth via require_auth()
# This gives Lambda full control over which endpoints are public vs protected
resource "aws_apigatewayv2_route" "api_default" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "$default"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.api_gateway_stage_name
  auto_deploy = true

  # Issue #39: Global rate limiting via API Gateway throttling
  throttle_settings {
    burst_limit = 5000
    rate_limit  = 2000
  }

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

# OAC for CloudFront S3 origin - securely signs requests to S3
resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.cloudfront_enabled ? 1 : 0
  name                              = "${var.project_name}-frontend-oac-${var.environment}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count = var.cloudfront_enabled ? 1 : 0

  origin {
    domain_name              = "${var.frontend_bucket_name}.s3.${var.aws_region}.amazonaws.com"
    origin_id                = "S3Frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  origin {
    domain_name = replace(try(aws_apigatewayv2_api.main.api_endpoint, ""), "https://", "")
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

  # SPA error responses — redirect 403/404 to index.html for client-side routing
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
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

  # Restrict S3 access to CloudFront OAC only — direct S3 URL access is blocked.
  # The OAC signing (sigv4) ensures only CloudFront can fetch objects.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOACOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.frontend_bucket_name}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend[0].arn
          }
        }
      }
    ]
  })

  depends_on = [var.frontend_bucket_public_access_block_id]
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

# For local fallback: use pre-built zip file
# The zip file is built by GitHub Actions deploy workflow before terraform apply
# It contains: lambda_function.py handler + algo/, config/, utils/ modules

resource "aws_lambda_function" "algo" {
  function_name = local.algo_lambda_name
  role          = var.algo_lambda_role_arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.algo_lambda_timeout
  memory_size   = var.algo_lambda_memory

  # Keep orchestrator Lambda warm to minimize cold starts during critical trading hours
  reserved_concurrent_executions = 1

  layers        = [local.shared_deps_layer_arn, var.psycopg2_layer_arn] # Orchestrator dependencies + psycopg2 for database access

  # Use S3 package if available, otherwise pre-built local zip file
  s3_bucket         = local.algo_lambda_use_s3 ? var.algo_lambda_s3_bucket : null
  s3_key            = local.algo_lambda_use_s3 ? var.algo_lambda_s3_key : null
  s3_object_version = local.algo_lambda_use_s3 && var.algo_lambda_s3_object_version != "" ? var.algo_lambda_s3_object_version : null
  filename          = !local.algo_lambda_use_s3 ? "${path.module}/../../${var.algo_lambda_code_file}" : null
  source_code_hash  = !local.algo_lambda_use_s3 ? filebase64sha256("${path.module}/../../${var.algo_lambda_code_file}") : null

  ephemeral_storage {
    size = var.algo_lambda_ephemeral_storage
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.algo_lambda_security_group_id]
  }

  environment {
    variables = {
      DB_SECRET_ARN = var.rds_credentials_secret_arn
      DB_ENDPOINT   = var.rds_endpoint
      DB_HOST       = var.rds_proxy_endpoint != null ? var.rds_proxy_endpoint : split(":", var.rds_endpoint)[0]
      DB_PORT       = "5432"
      DB_NAME       = var.rds_database_name
      DB_USER       = var.rds_username
      DB_SSL        = "require"
      # Alpaca keys are fetched at runtime from ALGO_SECRETS_ARN — not stored as plaintext env vars
      ALGO_SECRETS_ARN       = var.algo_secrets_arn
      ALERTS_SNS_TOPIC       = var.sns_alerts_enabled ? aws_sns_topic.algo_alerts[0].arn : ""
      EXECUTION_MODE         = var.execution_mode
      ORCHESTRATOR_DRY_RUN   = tostring(var.orchestrator_dry_run)
      ALGO_LIVE_TRADING      = var.alpaca_paper_trading ? "" : "I_UNDERSTAND_REAL_MONEY"
      APCA_API_BASE_URL      = var.alpaca_api_base_url
      ALPACA_PAPER_TRADING   = tostring(var.alpaca_paper_trading)
      LOG_LEVEL              = var.orchestrator_log_level
      DATA_PATROL_ENABLED    = tostring(var.data_patrol_enabled)
      DATA_PATROL_TIMEOUT_MS = tostring(var.data_patrol_timeout_ms)
      DEV_MODE               = var.dev_mode
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
# NOTE: Loader scheduling is now managed by the loaders module
# via EventBridge rules (see modules/loaders/main.tf)
# All 40 loaders including price loaders are scheduled there
# ============================================================

# ============================================================
# EventBridge Scheduler for Algo Orchestrator
# NOTE: 2x daily schedules (morning + evening) are defined in 2x-daily-orchestrator.tf
# ============================================================

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

# ============================================================
# Algo Trading Business Logic Alarms (AlgoTrading namespace)
# ============================================================

# Page immediately if the orchestrator run fails (fires at 5:30pm ET daily)
resource "aws_cloudwatch_metric_alarm" "orchestrator_failure" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-orchestrator-failure-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "OrchestratorSuccess"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Minimum"
  threshold           = 1
  alarm_description   = "CRITICAL: Algo orchestrator run failed. Check CloudWatch Logs for phase details."
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  ok_actions          = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# Alert if no signals are generated for 3 consecutive trading days
resource "aws_cloudwatch_metric_alarm" "zero_signals" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-zero-signals-${var.environment}"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 3
  metric_name         = "SignalsGenerated"
  namespace           = "AlgoTrading"
  period              = 86400
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "WARNING: Zero BUY signals generated for 3+ consecutive trading days. Check data pipeline."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# Alert if data is stale (a loader failed to run)
resource "aws_cloudwatch_metric_alarm" "data_freshness_stale" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-data-freshness-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DataFreshnessAgeDays"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 3
  alarm_description   = "WARNING: Critical data table is 3+ days stale. A loader may have failed."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# Alert if any single loader run has 50+ symbol failures (silent data loss)
resource "aws_cloudwatch_metric_alarm" "loader_symbol_failures" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-loader-symbol-failures-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "LoaderSymbolsFailed"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 50
  alarm_description   = "WARNING: A loader run had 50+ symbol failures. Data may be incomplete."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# CRITICAL: Alert if price_daily is stale (no trading data for 3+ days)
resource "aws_cloudwatch_metric_alarm" "price_data_stale" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-price-data-stale-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "PriceDataAgeDays"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 3
  alarm_description   = "CRITICAL: price_daily table is 3+ days stale. No trading data available."
  treat_missing_data  = "breaching" # If no data, treat as breaching (fail-closed)
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# CRITICAL: Alert if stock_scores is stale (outdated scoring)
resource "aws_cloudwatch_metric_alarm" "scores_data_stale" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-scores-stale-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StockScoresAgeDays"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 3
  alarm_description   = "CRITICAL: stock_scores table is 3+ days stale. Signals may be invalid."
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# CRITICAL: Alert if buy_sell_daily is stale (no signal data)
resource "aws_cloudwatch_metric_alarm" "signals_data_stale" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-signals-stale-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "SignalsDataAgeDays"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Maximum"
  threshold           = 3
  alarm_description   = "CRITICAL: buy_sell_daily table is 3+ days stale. No trading signals available."
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# WARNING: Alert if any table has empty row count (loader failed completely)
resource "aws_cloudwatch_metric_alarm" "empty_critical_table" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-empty-table-warning-${var.environment}"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "CriticalTableRowCount"
  namespace           = "AlgoTrading"
  period              = 3600
  statistic           = "Minimum"
  threshold           = 100
  alarm_description   = "WARNING: A critical table has very few rows. Loader may have failed."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

# WARNING: Alert if multiple loaders failed in last 24 hours
resource "aws_cloudwatch_metric_alarm" "loader_failures_accumulating" {
  count               = var.sns_alerts_enabled ? 1 : 0
  alarm_name          = "${var.project_name}-loader-failures-24h-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "LoaderFailureCount24h"
  namespace           = "AlgoTrading"
  period              = 86400 # 24 hours
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "WARNING: 2+ loaders failed in the last 24 hours. Data pipeline degraded."
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.algo_alerts[0].arn]
  tags                = var.common_tags
}

resource "aws_lambda_permission" "eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.algo.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}
